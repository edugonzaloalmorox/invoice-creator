import json
from io import BytesIO
import os
import unittest
from unittest.mock import patch

from backend.app.config import (
    CONFIG_CONNECT_TIMEOUT,
    CONFIG_CREDENTIAL_REFERENCE,
    CONFIG_ENVIRONMENT,
    CONFIG_FRONTEND_ORIGIN,
    CONFIG_MAX_REQUEST_BYTES,
    CONFIG_MAX_RESPONSE_BYTES,
    CONFIG_READ_TIMEOUT,
    CONFIG_TEMPLATE_ID,
    load_config,
)
from backend.app.main import create_app


def configured_values() -> dict[str, str]:
    return {
        CONFIG_ENVIRONMENT: "test",
        CONFIG_FRONTEND_ORIGIN: "http://localhost:3000",
        CONFIG_CREDENTIAL_REFERENCE: "secret-manager://invoice/google",
        CONFIG_TEMPLATE_ID: "template-test-123",
        CONFIG_MAX_REQUEST_BYTES: "1048576",
        CONFIG_MAX_RESPONSE_BYTES: "5242880",
        CONFIG_CONNECT_TIMEOUT: "3",
        CONFIG_READ_TIMEOUT: "10",
    }


def call(app, path: str, *, method: str = "GET", body: bytes = b"", content_type: str = "", headers: dict[str, str] | None = None):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    response_body = b"".join(
        app(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": str(len(body)),
                "wsgi.input": BytesIO(body),
                **{f"HTTP_{name.upper().replace('-', '_')}": value for name, value in (headers or {}).items()},
            },
            start_response,
        )
    )
    return captured, json.loads(response_body)


class ConfigurationTest(unittest.TestCase):
    def test_valid_configuration_is_typed_and_ready(self):
        result = load_config(configured_values())
        self.assertTrue(result.ready)
        self.assertEqual(result.config.max_request_bytes, 1_048_576)
        self.assertEqual(result.config.provider_read_timeout_seconds, 10.0)

    def test_missing_and_invalid_configuration_has_safe_errors(self):
        result = load_config({CONFIG_TEMPLATE_ID: "real-secret-looking-id"})
        self.assertFalse(result.ready)
        joined = " ".join(result.errors)
        self.assertNotIn("real-secret-looking-id", joined)
        self.assertIn(CONFIG_ENVIRONMENT, joined)

    def test_health_does_not_require_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            status, payload = call(create_app(), "/api/health")
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload, {"status": "ok"})

    def test_readiness_reports_unconfigured_service_without_details(self):
        status, payload = call(create_app(load_config({}).config), "/api/ready")
        self.assertEqual(status["status"], "503 Service Unavailable")
        self.assertEqual(payload["error"]["code"], "service_not_ready")
        self.assertNotIn("GOOGLE", json.dumps(payload))

    def test_readiness_succeeds_after_validation(self):
        result = load_config(configured_values())
        status, payload = call(create_app(result.config), "/api/ready")
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload, {"status": "ready"})

    def test_invalid_frontend_origin_ports_are_not_ready(self):
        for origin in ("https://example.test:bad", "https://example.test:99999"):
            with self.subTest(origin=origin):
                values = configured_values()
                values[CONFIG_FRONTEND_ORIGIN] = origin
                result = load_config(values)

                self.assertFalse(result.ready)
                self.assertIn(CONFIG_FRONTEND_ORIGIN, " ".join(result.errors))
                status, payload = call(create_app(result.config), "/api/ready")
                self.assertEqual(status["status"], "503 Service Unavailable")
                self.assertEqual(payload["error"]["code"], "service_not_ready")

    def test_responses_include_request_id_and_no_store(self):
        status, payload = call(create_app(load_config(configured_values()).config), "/api/health")
        self.assertTrue(status["headers"]["X-Request-ID"].startswith("req_"))
        self.assertEqual(status["headers"]["Cache-Control"], "no-store")
        self.assertEqual(payload, {"status": "ok"})

    def test_metrics_expose_only_aggregate_request_data(self):
        app = create_app(load_config(configured_values()).config)
        call(app, "/api/health")
        call(app, "/api/unknown")
        status, payload = call(app, "/api/metrics")

        self.assertEqual(status["status"], "200 OK")
        self.assertGreaterEqual(payload["requests_by_path_and_status"]["/api/health"]["2"], 1)
        self.assertGreaterEqual(payload["requests_by_path_and_status"]["other"]["4"], 1)
        self.assertEqual(payload["operational_events"], {"cleanup_failure": 0, "provider_failure": 0, "rate_limited": 0})
        self.assertNotIn("request_body", json.dumps(payload))
        self.assertNotIn("credential", json.dumps(payload).lower())
