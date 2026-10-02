"""WSGI application for the invoice workflow."""

from __future__ import annotations

import json
from io import BytesIO
import secrets
import time
from typing import Callable

from .config import AppConfig, ConfigLoad, load_config
from .detection import detect_fields
from .google_provider import GoogleDocumentProvider, google_document_id
from .invoice import InvoiceInput, format_total, validate_invoice
from .provider import FixtureDocumentProvider, ProviderError


def project_name() -> str:
    """Return the name of the application scaffold."""

    return "invoice-filler"


def _request_id() -> str:
    return f"req_{secrets.token_urlsafe(12)}"


def _json_response(start_response: Callable, status: str, payload: dict, request_id: str) -> list[bytes]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Request-ID", request_id),
        ],
    )
    return [body]


def _error_response(
    start_response: Callable,
    status: str,
    code: str,
    message: str,
    request_id: str,
    *,
    fields: list[dict] | None = None,
) -> list[bytes]:
    error = {"code": code, "message": message, "request_id": request_id}
    if fields is not None:
        error["fields"] = fields
    return _json_response(start_response, status, {"error": error}, request_id)


def _decimal_string(value) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _invoice_payload(invoice: InvoiceInput) -> dict:
    return {
        "service_start_date": invoice.service_start_date,
        "service_end_date": invoice.service_end_date,
        "days_worked": _decimal_string(invoice.days_worked),
        "pay_per_day": format(invoice.pay_per_day, "f"),
        "currency": invoice.currency,
        "bank_name": invoice.bank_name,
        "account_holder": invoice.account_holder,
        "iban_or_account_number": invoice.iban_or_account_number,
        "swift_or_bic": invoice.swift_or_bic,
    }


def _read_json_body(environ: dict, maximum: int) -> tuple[dict | None, tuple[str, str, str] | None]:
    content_type = environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return None, ("400 Bad Request", "invalid_json", "Request body must be JSON.")
    try:
        content_length = int(environ.get("CONTENT_LENGTH", ""))
    except (TypeError, ValueError):
        content_length = None
    if content_length is None or content_length <= 0:
        return None, ("400 Bad Request", "invalid_json", "Request body must contain a JSON object.")
    if content_length > maximum:
        return None, ("413 Request Entity Too Large", "request_too_large", "Request body is too large.")
    body = environ.get("wsgi.input", BytesIO()).read(content_length)
    if len(body) != content_length:
        return None, ("400 Bad Request", "invalid_json", "Request body must contain valid JSON.")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, ("400 Bad Request", "invalid_json", "Request body must contain valid JSON.")
    if not isinstance(payload, dict):
        return None, ("400 Bad Request", "invalid_json", "Request body must contain a JSON object.")
    return payload, None


def _validation_response(start_response: Callable, result, request_id: str) -> list[bytes] | None:
    if result.valid:
        return None
    fields = [{"name": error.name, "code": error.code, "message": error.message} for error in result.errors]
    return _error_response(start_response, "400 Bad Request", "validation_error", "One or more fields are invalid.", request_id, fields=fields)


class Application:
    """Small WSGI application with configuration captured at startup."""

    def __init__(self, config_result: ConfigLoad, provider=None):
        self.config_result = config_result
        self.provider = provider or FixtureDocumentProvider()
        self._template_selections: dict[str, str] = {}
        self._generation_attempts: dict[str, list[float]] = {}
        self._generation_limit = 10
        self._generation_window_seconds = 60.0

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        request_id = _request_id()
        path = environ.get("PATH_INFO", "")
        request_origin = environ.get("HTTP_ORIGIN")
        configured_origin = self.config_result.config.frontend_origin if self.config_result.config else None
        if request_origin and configured_origin and request_origin != configured_origin:
            return _error_response(start_response, "403 Forbidden", "origin_forbidden", "Request origin is not allowed.", request_id)
        if request_origin and configured_origin == request_origin:
            original_start_response = start_response

            def cors_start_response(status, headers):
                headers = list(headers) + [("Access-Control-Allow-Origin", request_origin), ("Vary", "Origin")]
                original_start_response(status, headers)

            start_response = cors_start_response
        if environ.get("REQUEST_METHOD") == "OPTIONS" and request_origin:
            if configured_origin != request_origin:
                return _error_response(start_response, "403 Forbidden", "origin_forbidden", "Request origin is not allowed.", request_id)
            start_response("204 No Content", [("Content-Length", "0"), ("Access-Control-Allow-Origin", request_origin), ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, X-Template-Selection"), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
            return [b""]
        if path == "/api/template/connect":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            return self._connect_template(environ, start_response, request_id)
        if path == "/api/invoices/preview":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            return self._preview(environ, start_response, request_id)
        if path == "/api/invoices/generate":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            if not self._allow_generation(environ):
                return _error_response(start_response, "429 Too Many Requests", "rate_limited", "Generation limit exceeded. Try again later.", request_id)
            return self._generate(environ, start_response, request_id)

        if path == "/api/template/fields":
            if environ.get("REQUEST_METHOD") != "GET":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only GET is supported.", "request_id": request_id}}, request_id)
            return self._template_fields(start_response, request_id)

        if environ.get("REQUEST_METHOD") != "GET":
            return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only GET is supported.", "request_id": request_id}}, request_id)

        if path == "/api/health":
            return _json_response(start_response, "200 OK", {"status": "ok"}, request_id)
        if path == "/api/ready":
            if self.config_result.ready:
                return _json_response(start_response, "200 OK", {"status": "ready"}, request_id)
            return _json_response(
                start_response,
                "503 Service Unavailable",
                {"error": {"code": "service_not_ready", "message": "Service configuration is unavailable.", "request_id": request_id}},
                request_id,
            )
        return _json_response(start_response, "404 Not Found", {"error": {"code": "not_found", "message": "Resource not found.", "request_id": request_id}}, request_id)

    def _allow_generation(self, environ: dict) -> bool:
        now = time.monotonic()
        client = environ.get("REMOTE_ADDR", "unknown")
        attempts = [stamp for stamp in self._generation_attempts.get(client, []) if now - stamp < self._generation_window_seconds]
        if len(attempts) >= self._generation_limit:
            self._generation_attempts[client] = attempts
            return False
        attempts.append(now)
        self._generation_attempts[client] = attempts
        return True

    def _template_id(self, environ: dict) -> str | None:
        selection = environ.get("HTTP_X_TEMPLATE_SELECTION")
        if selection:
            return self._template_selections.get(selection)
        return self.config_result.config.template_id if self.config_result.config else None

    def _connect_template(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        payload, parse_error = _read_json_body(environ, self.config_result.config.max_request_bytes)
        if parse_error:
            return _error_response(start_response, *parse_error, request_id)
        template_id = google_document_id(payload.get("url"))
        if template_id is None:
            return _error_response(start_response, "400 Bad Request", "invalid_template_url", "Paste a valid Google Docs document link.", request_id)
        try:
            fields = detect_fields(self.provider, template_id)
        except ProviderError as error:
            status = "504 Gateway Timeout" if error.retryable else "502 Bad Gateway"
            code = "provider_timeout" if error.retryable else "template_unavailable"
            return _error_response(start_response, status, code, "The template could not be authenticated or read.", request_id)
        selection = f"tpl_{secrets.token_urlsafe(18)}"
        if len(self._template_selections) >= 100:
            self._template_selections.pop(next(iter(self._template_selections)))
        self._template_selections[selection] = template_id
        return _json_response(start_response, "200 OK", {"selection_token": selection, **fields}, request_id)

    def _preview(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(
                start_response,
                "503 Service Unavailable",
                "service_not_ready",
                "Service configuration is unavailable.",
                request_id,
            )

        if self._template_id(environ) is None:
            return _error_response(start_response, "400 Bad Request", "template_not_selected", "Select a readable Google Docs template first.", request_id)

        payload, parse_error = _read_json_body(environ, self.config_result.config.max_request_bytes)
        if parse_error:
            return _error_response(start_response, *parse_error, request_id)

        result = validate_invoice(payload)
        validation_error = _validation_response(start_response, result, request_id)
        if validation_error:
            return validation_error

        invoice = result.value
        return _json_response(
            start_response,
            "200 OK",
            {
                "input": _invoice_payload(invoice),
                "calculation": {
                    "total_amount": format_total(invoice),
                    "currency": invoice.currency,
                    "rounding": "2 decimal places, half-up",
                },
                "ready_for_generation": True,
            },
            request_id,
        )

    def _generate(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        if self._template_id(environ) is None:
            return _error_response(start_response, "400 Bad Request", "template_not_selected", "Select a readable Google Docs template first.", request_id)
        payload, parse_error = _read_json_body(environ, self.config_result.config.max_request_bytes)
        if parse_error:
            return _error_response(start_response, *parse_error, request_id)
        result = validate_invoice(payload)
        validation_error = _validation_response(start_response, result, request_id)
        if validation_error:
            return validation_error

        invoice = result.value
        document_id = None
        primary_error: ProviderError | None = None
        pdf: bytes | None = None
        try:
            document_id = self.provider.copy_document(self._template_id(environ), f"invoice-{invoice.service_start_date}")
            replacements = {name: value for name, value in _invoice_payload(invoice).items() if value is not None}
            replacements["total_amount"] = format_total(invoice)
            self.provider.replace_values(document_id, replacements)
            pdf = self.provider.export_pdf(document_id)
            if not pdf or not pdf.startswith(b"%PDF"):
                raise ProviderError("export_pdf", "invalid_pdf")
            if len(pdf) > self.config_result.config.max_response_bytes:
                raise ProviderError("export_pdf", "response_too_large")
        except ProviderError as error:
            primary_error = error
        finally:
            if document_id is not None:
                try:
                    self.provider.delete_document(document_id)
                except ProviderError as cleanup_error:
                    if primary_error is None:
                        primary_error = cleanup_error
        if primary_error is not None:
            status = "504 Gateway Timeout" if primary_error.retryable else "502 Bad Gateway"
            code = "provider_timeout" if primary_error.retryable else "provider_error"
            return _error_response(start_response, status, code, "The document provider could not complete the request.", request_id)
        filename = f"invoice-{invoice.service_start_date}.pdf"
        start_response("200 OK", [("Content-Type", "application/pdf"), ("Content-Length", str(len(pdf))), ("Content-Disposition", f'attachment; filename="{filename}"'), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
        return [pdf]

    def _template_fields(self, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        try:
            template_id = self.config_result.config.template_id
            payload = detect_fields(self.provider, template_id)
        except ProviderError:
            return _error_response(start_response, "502 Bad Gateway", "provider_error", "The document provider returned an unusable response.", request_id)
        return _json_response(start_response, "200 OK", payload, request_id)


def create_app(config: AppConfig | None = None, provider=None) -> Application:
    """Create the app; invalid config is retained for the readiness endpoint."""

    if config is not None:
        result = ConfigLoad(config, ())
    else:
        result = load_config()
    if provider is None:
        if result.ready and not result.config.credential_reference.startswith("fixture://"):
            provider = GoogleDocumentProvider(
                result.config.credential_reference,
                connect_timeout_seconds=result.config.provider_connect_timeout_seconds,
                read_timeout_seconds=result.config.provider_read_timeout_seconds,
            )
        else:
            provider = FixtureDocumentProvider()
    return Application(result, provider)


app = create_app()
