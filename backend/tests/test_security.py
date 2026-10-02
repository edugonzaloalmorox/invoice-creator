import json
import unittest
from io import BytesIO

from backend.app.config import CONFIG_ENVIRONMENT, CONFIG_FRONTEND_ORIGIN, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import configured_values
from backend.tests.test_generate import call_raw
from backend.tests.test_preview import invoice_body


def call_with_origin(app, path, origin, method="GET"):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(app({"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_ORIGIN": origin, "CONTENT_LENGTH": "0", "wsgi.input": BytesIO()}, start_response))
    return captured, json.loads(body) if body else None


class SecurityControlsTest(unittest.TestCase):
    def test_production_rejects_http_frontend_origin(self):
        values = configured_values()
        values[CONFIG_ENVIRONMENT] = "production"
        result = load_config(values)
        self.assertFalse(result.ready)
        self.assertTrue(any("HTTPS" in error for error in result.errors))

    def test_cors_allows_only_configured_origin(self):
        app = create_app(load_config(configured_values()).config)
        allowed, _ = call_with_origin(app, "/api/health", "http://localhost:3000")
        self.assertEqual(allowed["status"], "200 OK")
        self.assertEqual(allowed["headers"]["Access-Control-Allow-Origin"], "http://localhost:3000")
        denied, payload = call_with_origin(app, "/api/health", "https://attacker.test")
        self.assertEqual(denied["status"], "403 Forbidden")
        self.assertEqual(payload["error"]["code"], "origin_forbidden")

    def test_cors_allows_the_makefile_frontend_origin(self):
        values = configured_values()
        values[CONFIG_FRONTEND_ORIGIN] = "http://127.0.0.1:3000"
        app = create_app(load_config(values).config)
        allowed, _ = call_with_origin(app, "/api/health", "http://127.0.0.1:3000")
        self.assertEqual(allowed["status"], "200 OK")
        self.assertEqual(allowed["headers"]["Access-Control-Allow-Origin"], "http://127.0.0.1:3000")

    def test_template_preflight_has_one_origin_header(self):
        values = configured_values()
        values[CONFIG_FRONTEND_ORIGIN] = "http://127.0.0.1:3000"
        app = create_app(load_config(values).config)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        app(
            {
                "REQUEST_METHOD": "OPTIONS",
                "PATH_INFO": "/api/template/connect",
                "HTTP_ORIGIN": "http://127.0.0.1:3000",
                "HTTP_ACCESS_CONTROL_REQUEST_METHOD": "POST",
                "HTTP_ACCESS_CONTROL_REQUEST_HEADERS": "content-type",
                "CONTENT_LENGTH": "0",
                "wsgi.input": BytesIO(),
            },
            start_response,
        )
        origin_headers = [value for name, value in captured["headers"] if name == "Access-Control-Allow-Origin"]
        self.assertEqual(captured["status"], "204 No Content")
        self.assertEqual(origin_headers, ["http://127.0.0.1:3000"])

    def test_oversized_generation_is_rejected_before_provider_work(self):
        provider = FixtureDocumentProvider()
        values = configured_values()
        values["INVOICE_MAX_REQUEST_BYTES"] = "10"
        app = create_app(load_config(values).config, provider)
        status, body = call_raw(app, invoice_body())
        self.assertEqual(status["status"], "413 Request Entity Too Large")
        self.assertEqual(provider.calls, [])

    def test_generation_is_rate_limited_without_sensitive_keys(self):
        provider = FixtureDocumentProvider()
        app = create_app(load_config(configured_values()).config, provider)
        last_status = None
        for _ in range(11):
            status, _ = call_raw(app, invoice_body())
            last_status = status["status"]
        self.assertEqual(last_status, "429 Too Many Requests")
        self.assertTrue(all("TEST" not in key for key in app._generation_attempts))
