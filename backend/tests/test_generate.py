import json
import unittest
from io import BytesIO

from backend.app.config import CONFIG_TEMPLATE_ID, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_preview import invoice_body


def configured_app(provider):
    values = {
        "INVOICE_ENVIRONMENT": "test",
        "INVOICE_FRONTEND_ORIGIN": "http://localhost:3000",
        "GOOGLE_CREDENTIALS_REFERENCE": "secret-manager://invoice/google",
        CONFIG_TEMPLATE_ID: "fixture-template",
        "INVOICE_MAX_REQUEST_BYTES": "1048576",
        "INVOICE_MAX_RESPONSE_BYTES": "5242880",
        "GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS": "3",
        "GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS": "10",
    }
    return create_app(load_config(values).config, provider)


def call_raw(app, body: bytes, headers: dict[str, str] | None = None, remote_addr: str | None = None):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    response = b"".join(app({
        "REQUEST_METHOD": "POST", "PATH_INFO": "/api/invoices/generate",
        "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
        "REMOTE_ADDR": remote_addr or "",
        **{f"HTTP_{name.upper().replace('-', '_')}": value for name, value in (headers or {}).items()},
    }, start_response))
    return captured, response


class GenerateEndpointTest(unittest.TestCase):
    def test_success_returns_pdf_and_cleans_up_copy(self):
        provider = FixtureDocumentProvider()
        status, body = call_raw(configured_app(provider), invoice_body())
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(status["headers"]["Content-Type"], "application/pdf")
        self.assertEqual(status["headers"]["Cache-Control"], "no-store")
        self.assertEqual(status["headers"]["Content-Disposition"], 'attachment; filename="invoice-2026-09-01.pdf"')
        self.assertTrue(body.startswith(b"%PDF"))
        self.assertEqual([operation for operation, _ in provider.calls], ["copy_document", "replace_values", "export_pdf", "delete_document"])

    def test_validation_failure_does_not_call_provider(self):
        provider = FixtureDocumentProvider()
        values = json.loads(invoice_body())
        values["pay_per_day"] = "-1"
        status, body = call_raw(configured_app(provider), json.dumps(values).encode())
        self.assertEqual(status["status"], "400 Bad Request")
        self.assertEqual(json.loads(body)["error"]["code"], "validation_error")
        self.assertEqual(provider.calls, [])

    def test_export_failure_and_empty_pdf_still_clean_up(self):
        for provider in (
            FixtureDocumentProvider(failures={"export_pdf": "timeout"}),
            FixtureDocumentProvider(empty_pdf=True),
        ):
            with self.subTest(provider=provider):
                status, body = call_raw(configured_app(provider), invoice_body())
                self.assertIn(status["status"], {"502 Bad Gateway", "504 Gateway Timeout"})
                self.assertNotIn(b"%PDF", body)
                self.assertEqual(provider.calls[-1][0], "delete_document")

    def test_cleanup_failure_is_not_a_successful_pdf(self):
        provider = FixtureDocumentProvider(failures={"delete_document": "cleanup_failed"})
        status, body = call_raw(configured_app(provider), invoice_body())
        self.assertEqual(status["status"], "502 Bad Gateway")
        self.assertEqual(json.loads(body)["error"]["code"], "provider_error")

    def test_response_limit_rejects_large_pdf_before_return_and_cleans_up(self):
        provider = FixtureDocumentProvider()
        values = {
            "INVOICE_ENVIRONMENT": "test",
            "INVOICE_FRONTEND_ORIGIN": "http://localhost:3000",
            "GOOGLE_CREDENTIALS_REFERENCE": "secret-manager://invoice/google",
            CONFIG_TEMPLATE_ID: "fixture-template",
            "INVOICE_MAX_REQUEST_BYTES": "1048576",
            "INVOICE_MAX_RESPONSE_BYTES": "10",
            "GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS": "3",
            "GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS": "10",
        }
        status, body = call_raw(create_app(load_config(values).config, provider), invoice_body())
        self.assertEqual(status["status"], "502 Bad Gateway")
        self.assertEqual(json.loads(body)["error"]["code"], "provider_error")
        self.assertEqual(provider.calls[-1][0], "delete_document")
