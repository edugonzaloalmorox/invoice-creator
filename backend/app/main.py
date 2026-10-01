"""Dependency-free liveness and readiness HTTP application."""

from __future__ import annotations

import json
from io import BytesIO
import secrets
from typing import Callable

from .config import AppConfig, ConfigLoad, load_config
from .detection import detect_fields
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


class Application:
    """Small WSGI application with configuration captured at startup."""

    def __init__(self, config_result: ConfigLoad, provider=None):
        self.config_result = config_result
        self.provider = provider or FixtureDocumentProvider()

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        request_id = _request_id()
        path = environ.get("PATH_INFO", "")
        if path == "/api/invoices/preview":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            return self._preview(environ, start_response, request_id)

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

    def _preview(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(
                start_response,
                "503 Service Unavailable",
                "service_not_ready",
                "Service configuration is unavailable.",
                request_id,
            )

        content_type = environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _error_response(
                start_response,
                "400 Bad Request",
                "invalid_json",
                "Request body must be JSON.",
                request_id,
            )

        raw_length = environ.get("CONTENT_LENGTH", "")
        try:
            content_length = int(raw_length)
        except (TypeError, ValueError):
            content_length = None
        if content_length is None or content_length <= 0:
            return _error_response(
                start_response,
                "400 Bad Request",
                "invalid_json",
                "Request body must contain a JSON object.",
                request_id,
            )
        if content_length > self.config_result.config.max_request_bytes:
            return _error_response(
                start_response,
                "413 Request Entity Too Large",
                "request_too_large",
                "Request body is too large.",
                request_id,
            )

        body = environ.get("wsgi.input", BytesIO()).read(content_length)
        if len(body) != content_length:
            return _error_response(
                start_response,
                "400 Bad Request",
                "invalid_json",
                "Request body must contain valid JSON.",
                request_id,
            )
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error_response(
                start_response,
                "400 Bad Request",
                "invalid_json",
                "Request body must contain valid JSON.",
                request_id,
            )
        if not isinstance(payload, dict):
            return _error_response(
                start_response,
                "400 Bad Request",
                "invalid_json",
                "Request body must contain a JSON object.",
                request_id,
            )

        result = validate_invoice(payload)
        if not result.valid:
            fields = [
                {"name": error.name, "code": error.code, "message": error.message}
                for error in result.errors
            ]
            return _error_response(
                start_response,
                "400 Bad Request",
                "validation_error",
                "One or more fields are invalid.",
                request_id,
                fields=fields,
            )

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

    def _template_fields(self, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        try:
            payload = detect_fields(self.provider, self.config_result.config.template_id)
        except ProviderError:
            return _error_response(start_response, "502 Bad Gateway", "provider_error", "The document provider returned an unusable response.", request_id)
        return _json_response(start_response, "200 OK", payload, request_id)


def create_app(config: AppConfig | None = None, provider=None) -> Application:
    """Create the app; invalid config is retained for the readiness endpoint."""

    if config is not None:
        result = ConfigLoad(config, ())
    else:
        result = load_config()
    return Application(result, provider)


app = create_app()
