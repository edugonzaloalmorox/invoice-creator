"""Typed, non-secret application configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


CONFIG_ENVIRONMENT = "INVOICE_ENVIRONMENT"
CONFIG_FRONTEND_ORIGIN = "INVOICE_FRONTEND_ORIGIN"
CONFIG_CREDENTIAL_REFERENCE = "GOOGLE_CREDENTIALS_REFERENCE"
CONFIG_TEMPLATE_ID = "GOOGLE_TEMPLATE_ID"
CONFIG_MAX_REQUEST_BYTES = "INVOICE_MAX_REQUEST_BYTES"
CONFIG_MAX_RESPONSE_BYTES = "INVOICE_MAX_RESPONSE_BYTES"
CONFIG_CONNECT_TIMEOUT = "GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS"
CONFIG_READ_TIMEOUT = "GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS"
CONFIG_OAUTH_CLIENT_ID = "GOOGLE_OAUTH_CLIENT_ID"
CONFIG_OAUTH_CLIENT_SECRET = "GOOGLE_OAUTH_CLIENT_SECRET"
CONFIG_OAUTH_REDIRECT_URI = "GOOGLE_OAUTH_REDIRECT_URI"
CONFIG_OAUTH_SCOPES = "GOOGLE_OAUTH_SCOPES"
CONFIG_SESSION_SECRET = "SESSION_SECRET"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated settings used by the application.

    ``credential_reference`` identifies where credentials are managed; it is not
    the credential itself and is never included in public responses.
    """

    environment: str
    frontend_origin: str
    credential_reference: str
    template_id: str
    max_request_bytes: int
    max_response_bytes: int
    provider_connect_timeout_seconds: float
    provider_read_timeout_seconds: float
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_redirect_uri: str | None = None
    oauth_scopes: tuple[str, ...] = ()
    session_secret: str | None = None

    @property
    def oauth_configured(self) -> bool:
        return bool(self.oauth_client_id)


@dataclass(frozen=True, slots=True)
class ConfigLoad:
    config: AppConfig | None
    errors: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.config is not None and not self.errors


def _required(values: dict[str, str], name: str, errors: list[str]) -> str:
    value = values.get(name, "").strip()
    if not value:
        errors.append(f"{name} is required")
    return value


def _positive_number(
    values: dict[str, str], name: str, errors: list[str], *, maximum: float
) -> float:
    raw = _required(values, name, errors)
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{name} must be a number")
        return 0.0
    if not 0 < value <= maximum:
        errors.append(f"{name} must be greater than zero and at most {maximum:g}")
    return value


def _positive_integer(
    values: dict[str, str], name: str, errors: list[str], *, maximum: int
) -> int:
    raw = _required(values, name, errors)
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{name} must be an integer")
        return 0
    if not 0 < value <= maximum:
        errors.append(f"{name} must be greater than zero and at most {maximum}")
    return value


def load_config(values: dict[str, str] | None = None) -> ConfigLoad:
    """Read and validate configuration without exposing any values.

    A mapping can be supplied by tests or an embedding server; production code
    defaults to the process environment.
    """

    source = dict(os.environ if values is None else values)
    errors: list[str] = []
    environment = _required(source, CONFIG_ENVIRONMENT, errors)
    frontend_origin = _required(source, CONFIG_FRONTEND_ORIGIN, errors)
    credential_reference = _required(source, CONFIG_CREDENTIAL_REFERENCE, errors)
    template_id = _required(source, CONFIG_TEMPLATE_ID, errors)

    if frontend_origin:
        try:
            parsed = urlparse(frontend_origin)
            # Accessing ``port`` performs urllib's validation for non-numeric
            # and out-of-range ports. An explicit empty port is invalid too.
            port = parsed.port
            has_empty_port = parsed.netloc.endswith(":")
        except ValueError:
            parsed = None
            port = None
            has_empty_port = False

        if (
            parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or has_empty_port
            or port == 0
        ):
            errors.append(f"{CONFIG_FRONTEND_ORIGIN} must be an HTTP(S) origin")
        elif environment.lower() == "production" and parsed.scheme != "https":
            errors.append(f"{CONFIG_FRONTEND_ORIGIN} must use HTTPS in production")

    max_request = _positive_integer(source, CONFIG_MAX_REQUEST_BYTES, errors, maximum=10_485_760)
    max_response = _positive_integer(source, CONFIG_MAX_RESPONSE_BYTES, errors, maximum=52_428_800)
    connect_timeout = _positive_number(source, CONFIG_CONNECT_TIMEOUT, errors, maximum=300)
    read_timeout = _positive_number(source, CONFIG_READ_TIMEOUT, errors, maximum=300)

    oauth_values = {name: source.get(name, "").strip() for name in (
        CONFIG_OAUTH_CLIENT_ID,
        CONFIG_OAUTH_CLIENT_SECRET,
        CONFIG_OAUTH_REDIRECT_URI,
        CONFIG_OAUTH_SCOPES,
        CONFIG_SESSION_SECRET,
    )}
    if any(oauth_values.values()) and not all(oauth_values.values()):
        errors.append("Google OAuth configuration must be complete")
    oauth_redirect = oauth_values[CONFIG_OAUTH_REDIRECT_URI]
    if oauth_redirect:
        parsed_redirect = urlparse(oauth_redirect)
        if parsed_redirect.scheme not in {"http", "https"} or not parsed_redirect.netloc or parsed_redirect.query or parsed_redirect.fragment:
            errors.append(f"{CONFIG_OAUTH_REDIRECT_URI} must be an HTTP(S) callback URL")
    oauth_scopes = tuple(scope for scope in oauth_values[CONFIG_OAUTH_SCOPES].replace(",", " ").split() if scope)
    if oauth_values[CONFIG_OAUTH_CLIENT_ID] and "openid" not in oauth_scopes:
        errors.append(f"{CONFIG_OAUTH_SCOPES} must include openid for user identity")

    if errors:
        return ConfigLoad(None, tuple(errors))
    return ConfigLoad(
        AppConfig(
            environment,
            frontend_origin.rstrip("/"),
            credential_reference,
            template_id,
            max_request,
            max_response,
            connect_timeout,
            read_timeout,
            oauth_values[CONFIG_OAUTH_CLIENT_ID] or None,
            oauth_values[CONFIG_OAUTH_CLIENT_SECRET] or None,
            oauth_redirect or None,
            oauth_scopes,
            oauth_values[CONFIG_SESSION_SECRET] or None,
        ),
        (),
    )
