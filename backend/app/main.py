"""WSGI application for the invoice workflow."""

from __future__ import annotations

import json
from io import BytesIO
import secrets
import time
from typing import Callable
from urllib.parse import parse_qs

from .auth import AuthError, OAuthClient, OAuthSettings, SessionStore
from .config import AppConfig, ConfigLoad, load_config
from .detection import detect_fields
from .google_provider import GoogleDocumentProvider, google_document_id
from .invoice import InvoiceInput, format_total, validate_invoice
from .metrics import Metrics
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

    def __init__(self, config_result: ConfigLoad, provider=None, metrics: Metrics | None = None):
        self.config_result = config_result
        self.provider = provider or FixtureDocumentProvider()
        self.metrics = metrics or Metrics()
        self._template_selections: dict[str, tuple[str | None, str]] = {}
        self._generation_attempts: dict[str, list[float]] = {}
        self._generation_limit = 10
        self._generation_window_seconds = 60.0
        self._max_generation_clients = 1000
        self._sessions = SessionStore(config_result.config.session_secret) if config_result.config and config_result.config.oauth_configured else None
        self._oauth = OAuthClient(OAuthSettings(
            config_result.config.oauth_client_id,
            config_result.config.oauth_client_secret,
            config_result.config.oauth_redirect_uri,
            config_result.config.oauth_scopes,
            config_result.config.session_secret,
        )) if config_result.config and config_result.config.oauth_configured else None
        self._use_user_google_provider = bool(
            config_result.config
            and config_result.config.oauth_configured
            and (
                config_result.config.credential_reference.startswith("fixture://")
                or isinstance(self.provider, GoogleDocumentProvider)
            )
        )

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        request_id = _request_id()
        path = environ.get("PATH_INFO", "")
        started_at = time.monotonic()
        original_start_response = start_response

        def recording_start_response(status, headers):
            self.metrics.record(path, status.split(" ", 1)[0][:1], (time.monotonic() - started_at) * 1000)
            return original_start_response(status, headers)

        start_response = recording_start_response
        request_origin = environ.get("HTTP_ORIGIN")
        configured_origin = self.config_result.config.frontend_origin if self.config_result.config else None
        if request_origin and configured_origin and request_origin != configured_origin:
            return _error_response(start_response, "403 Forbidden", "origin_forbidden", "Request origin is not allowed.", request_id)
        if request_origin and configured_origin == request_origin:
            cors_original_start_response = start_response

            def cors_start_response(status, headers):
                headers = list(headers) + [("Access-Control-Allow-Origin", request_origin), ("Access-Control-Allow-Credentials", "true"), ("Vary", "Origin")]
                cors_original_start_response(status, headers)

            start_response = cors_start_response
        if environ.get("REQUEST_METHOD") == "OPTIONS" and request_origin:
            if configured_origin != request_origin:
                return _error_response(start_response, "403 Forbidden", "origin_forbidden", "Request origin is not allowed.", request_id)
            start_response("204 No Content", [("Content-Length", "0"), ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, X-Template-Selection"), ("Access-Control-Allow-Credentials", "true"), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
            return [b""]
        if path == "/auth/google":
            return self._auth_start(environ, start_response, request_id)
        if path == "/auth/google/callback":
            return self._auth_callback(environ, start_response, request_id)
        if path == "/auth/logout":
            return self._auth_logout(environ, start_response, request_id)
        if path == "/api/session":
            return self._session_status(environ, start_response, request_id)
        if path == "/api/template/connect":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            return self._connect_template(environ, start_response, request_id)
        if path == "/api/metrics":
            if environ.get("REQUEST_METHOD") != "GET":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only GET is supported.", "request_id": request_id}}, request_id)
            return _json_response(start_response, "200 OK", self.metrics.snapshot(), request_id)
        if path == "/api/invoices/preview":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            return self._preview(environ, start_response, request_id)
        if path == "/api/invoices/generate":
            if environ.get("REQUEST_METHOD") != "POST":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only POST is supported.", "request_id": request_id}}, request_id)
            if not self._allow_generation(environ):
                self.metrics.record_event("rate_limited")
                return _error_response(start_response, "429 Too Many Requests", "rate_limited", "Generation limit exceeded. Try again later.", request_id)
            return self._generate(environ, start_response, request_id)

        if path == "/api/template/fields":
            if environ.get("REQUEST_METHOD") != "GET":
                return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only GET is supported.", "request_id": request_id}}, request_id)
            required = self._require_session(environ, start_response, request_id)
            if required:
                return required
            return self._template_fields(environ, start_response, request_id)

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
        if client not in self._generation_attempts and len(self._generation_attempts) >= self._max_generation_clients:
            self._generation_attempts.pop(next(iter(self._generation_attempts)))
            self.metrics.record_event("suspicious_volume")
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
            selected = self._template_selections.get(selection)
            if selected is None:
                return None
            owner, template_id = selected
            session = self._session(environ)
            if self._sessions is not None and (session is None or owner != session.user_id):
                return None
            return template_id
        return self.config_result.config.template_id if self.config_result.config else None

    def _session(self, environ: dict):
        if self._sessions is None:
            return None
        session_id = self._sessions.session_id_from_environ(environ)
        session = self._sessions.get(session_id)
        if session is None:
            return None
        access_expires_at = session.access_expires_at or session.expires_at
        if self._oauth is not None and access_expires_at <= time.time() + 60:
            try:
                self._sessions.replace(session_id, self._oauth.refresh(session))
                session = self._sessions.get(session_id)
            except AuthError as error:
                if error.code == "authorization_revoked":
                    self._sessions.delete(session_id)
                    return None
        return session

    def _provider_for(self, environ: dict):
        if not self._use_user_google_provider or self._oauth is None:
            return self.provider
        session = self._session(environ)
        if session is None:
            return self.provider
        config = self.config_result.config
        return GoogleDocumentProvider.for_user_session(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            client_id=self._oauth.settings.client_id,
            client_secret=self._oauth.settings.client_secret,
            scopes=self._oauth.settings.scopes,
            connect_timeout_seconds=config.provider_connect_timeout_seconds,
            read_timeout_seconds=config.provider_read_timeout_seconds,
        )

    def _require_session(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes] | None:
        if self._sessions is not None and self._session(environ) is None:
            return _error_response(start_response, "401 Unauthorized", "authentication_required", "Sign in to continue.", request_id)
        return None

    def _secure_cookie(self) -> bool:
        return bool(self.config_result.config and self.config_result.config.environment.lower() == "production")

    def _auth_start(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            return _error_response(start_response, "405 Method Not Allowed", "method_not_allowed", "Only GET is supported.", request_id)
        if self._oauth is None or self._sessions is None:
            return _error_response(start_response, "503 Service Unavailable", "authentication_unavailable", "Sign-in is not configured.", request_id)
        state = self._sessions.start()
        location = self._oauth.authorization_url(state)
        start_response("302 Found", [("Location", location), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
        return [b""]

    def _auth_callback(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            return _error_response(start_response, "405 Method Not Allowed", "method_not_allowed", "Only GET is supported.", request_id)
        if self._oauth is None or self._sessions is None:
            return _error_response(start_response, "503 Service Unavailable", "authentication_unavailable", "Sign-in is not configured.", request_id)
        params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        state = params.get("state", [""])[0]
        if not state or not self._sessions.consume_state(state):
            return _error_response(start_response, "400 Bad Request", "invalid_oauth_state", "The sign-in request expired or is invalid.", request_id)
        if params.get("error"):
            return _error_response(start_response, "400 Bad Request", "authorization_denied", "Google sign-in was not completed.", request_id)
        code = params.get("code", [""])[0]
        if not code:
            return _error_response(start_response, "400 Bad Request", "authorization_denied", "Google sign-in was not completed.", request_id)
        try:
            session_id = self._sessions.put(self._oauth.exchange_code(code))
        except AuthError as error:
            status = "503 Service Unavailable" if error.retryable else "400 Bad Request"
            return _error_response(start_response, status, error.code, "Google sign-in could not be completed.", request_id)
        start_response("302 Found", [("Location", self.config_result.config.frontend_origin), ("Set-Cookie", self._sessions.cookie_header(session_id, secure=self._secure_cookie())), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
        return [b""]

    def _auth_logout(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "POST":
            return _error_response(start_response, "405 Method Not Allowed", "method_not_allowed", "Only POST is supported.", request_id)
        if self._sessions is not None:
            self._sessions.delete(self._sessions.session_id_from_environ(environ))
            start_response("204 No Content", [("Set-Cookie", self._sessions.clear_cookie_header(secure=self._secure_cookie())), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
            return [b""]
        start_response("204 No Content", [("Content-Length", "0"), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
        return [b""]

    def _session_status(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            return _error_response(start_response, "405 Method Not Allowed", "method_not_allowed", "Only GET is supported.", request_id)
        if self._sessions is None:
            return _json_response(start_response, "200 OK", {"authenticated": bool(self.config_result.ready), "auth_required": False}, request_id)
        session = self._session(environ)
        if session is None:
            return _json_response(start_response, "200 OK", {"authenticated": False, "auth_required": True}, request_id)
        return _json_response(start_response, "200 OK", {"authenticated": True, "auth_required": True, "user": {"id": session.user_id, "email": session.email}}, request_id)

    def _connect_template(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        required = self._require_session(environ, start_response, request_id)
        if required:
            return required
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        payload, parse_error = _read_json_body(environ, self.config_result.config.max_request_bytes)
        if parse_error:
            return _error_response(start_response, *parse_error, request_id)
        template_id = google_document_id(payload.get("url"))
        if template_id is None:
            return _error_response(start_response, "400 Bad Request", "invalid_template_url", "Paste a valid Google Docs document link.", request_id)
        try:
            fields = detect_fields(self._provider_for(environ), template_id)
        except ProviderError as error:
            status = "504 Gateway Timeout" if error.retryable else "502 Bad Gateway"
            code = "provider_timeout" if error.retryable else "template_unavailable"
            return _error_response(start_response, status, code, "The template could not be authenticated or read.", request_id)
        selection = f"tpl_{secrets.token_urlsafe(18)}"
        if len(self._template_selections) >= 100:
            self._template_selections.pop(next(iter(self._template_selections)))
        session = self._session(environ)
        self._template_selections[selection] = (session.user_id if session else None, template_id)
        return _json_response(start_response, "200 OK", {"selection_token": selection, **fields}, request_id)

    def _preview(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        required = self._require_session(environ, start_response, request_id)
        if required:
            return required
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
        required = self._require_session(environ, start_response, request_id)
        if required:
            return required
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
            provider = self._provider_for(environ)
            document_id = provider.copy_document(self._template_id(environ), f"invoice-{invoice.service_start_date}")
            replacements = {name: value for name, value in _invoice_payload(invoice).items() if value is not None}
            replacements["total_amount"] = format_total(invoice)
            provider.replace_values(document_id, replacements)
            pdf = provider.export_pdf(document_id)
            if not pdf or not pdf.startswith(b"%PDF"):
                raise ProviderError("export_pdf", "invalid_pdf")
            if len(pdf) > self.config_result.config.max_response_bytes:
                raise ProviderError("export_pdf", "response_too_large")
        except ProviderError as error:
            primary_error = error
            self.metrics.record_event("provider_failure")
        finally:
            if document_id is not None:
                try:
                    provider.delete_document(document_id)
                except ProviderError as cleanup_error:
                    self.metrics.record_event("cleanup_failure")
                    if primary_error is None:
                        primary_error = cleanup_error
        if primary_error is not None:
            status = "504 Gateway Timeout" if primary_error.retryable else "502 Bad Gateway"
            code = "provider_timeout" if primary_error.retryable else "provider_error"
            return _error_response(start_response, status, code, "The document provider could not complete the request.", request_id)
        filename = f"invoice-{invoice.service_start_date}.pdf"
        start_response("200 OK", [("Content-Type", "application/pdf"), ("Content-Length", str(len(pdf))), ("Content-Disposition", f'attachment; filename="{filename}"'), ("Cache-Control", "no-store"), ("X-Request-ID", request_id)])
        return [pdf]

    def _template_fields(self, environ: dict, start_response: Callable, request_id: str) -> list[bytes]:
        if not self.config_result.ready:
            return _error_response(start_response, "503 Service Unavailable", "service_not_ready", "Service configuration is unavailable.", request_id)
        try:
            template_id = self.config_result.config.template_id
            payload = detect_fields(self._provider_for(environ), template_id)
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
