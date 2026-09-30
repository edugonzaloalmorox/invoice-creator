"""Dependency-free liveness and readiness HTTP application."""

from __future__ import annotations

import json
import secrets
from typing import Callable

from .config import AppConfig, ConfigLoad, load_config


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


class Application:
    """Small WSGI application with configuration captured at startup."""

    def __init__(self, config_result: ConfigLoad):
        self.config_result = config_result

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        request_id = _request_id()
        if environ.get("REQUEST_METHOD") != "GET":
            return _json_response(start_response, "405 Method Not Allowed", {"error": {"code": "method_not_allowed", "message": "Only GET is supported.", "request_id": request_id}}, request_id)

        path = environ.get("PATH_INFO", "")
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


def create_app(config: AppConfig | None = None) -> Application:
    """Create the app; invalid config is retained for the readiness endpoint."""

    if config is not None:
        result = ConfigLoad(config, ())
    else:
        result = load_config()
    return Application(result)


app = create_app()
