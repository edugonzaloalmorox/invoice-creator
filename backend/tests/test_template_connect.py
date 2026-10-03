import json
import unittest

from backend.app.config import CONFIG_TEMPLATE_ID, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import call, configured_values
from backend.tests.test_generate import call_raw
from backend.tests.test_preview import invoice_body


class TemplateConnectTest(unittest.TestCase):
    def configured_app(self, provider=None):
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        return create_app(load_config(values).config, provider or FixtureDocumentProvider())

    def connect(self, app, url):
        return call(
            app,
            "/api/template/connect",
            method="POST",
            body=json.dumps({"url": url}).encode(),
            content_type="application/json",
        )

    def test_connect_reads_valid_google_docs_link_and_returns_opaque_selection(self):
        provider = FixtureDocumentProvider()
        status, payload = self.connect(self.configured_app(provider), "https://docs.google.com/document/d/fixture-template/edit?usp=sharing")

        self.assertEqual(status["status"], "200 OK")
        self.assertTrue(payload["selection_token"].startswith("tpl_"))
        self.assertNotIn("fixture-template", payload["selection_token"])
        self.assertIn("fields", payload)
        self.assertEqual(provider.calls, [("read_template", "fixture-template")])

    def test_selected_template_is_required_for_and_forwarded_to_preview(self):
        provider = FixtureDocumentProvider()
        app = self.configured_app(provider)
        _, connected = self.connect(app, "https://docs.google.com/document/d/fixture-template/edit")
        token = connected["selection_token"]

        status, payload = call(
            app,
            "/api/invoices/preview",
            method="POST",
            body=invoice_body(),
            content_type="application/json",
            headers={"X-Template-Selection": token},
        )
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload["calculation"]["total_amount"], "1200.00")

        status, payload = call(app, "/api/invoices/preview", method="POST", body=invoice_body(), content_type="application/json", headers={"X-Template-Selection": "tpl_invalid"})
        self.assertEqual(status["status"], "400 Bad Request")
        self.assertEqual(payload["error"]["code"], "template_not_selected")

        status, body = call_raw(app, invoice_body(), headers={"X-Template-Selection": token})
        self.assertEqual(status["status"], "200 OK")
        self.assertTrue(body.startswith(b"%PDF"))
        self.assertEqual(provider.calls[0], ("read_template", "fixture-template"))
        self.assertEqual(provider.calls[-4][0], "copy_document")
        self.assertEqual(provider.calls[-4][1], "fixture-template")

    def test_invalid_url_and_provider_errors_are_safe(self):
        app = self.configured_app()
        for url in ("https://example.test/document/d/fixture-template", "not a url", "http://docs.google.com/document/d/fixture-template/edit"):
            with self.subTest(url=url):
                status, payload = self.connect(app, url)
                self.assertEqual(status["status"], "400 Bad Request")
                self.assertEqual(payload["error"]["code"], "invalid_template_url")
                self.assertNotIn(url, json.dumps(payload))

        cases = {
            "permission_denied": ("403 Forbidden", "template_access_denied"),
            "template_not_found": ("404 Not Found", "template_not_found"),
            "credentials_invalid": ("401 Unauthorized", "reauthorization_required"),
            "unavailable": ("503 Service Unavailable", "provider_unavailable"),
            "timeout": ("504 Gateway Timeout", "provider_timeout"),
        }
        for failure, expected in cases.items():
            with self.subTest(failure=failure):
                denied = self.configured_app(FixtureDocumentProvider(failures={"read_template": failure}))
                status, payload = self.connect(denied, "https://docs.google.com/document/d/fixture-template/edit")
                self.assertEqual((status["status"], payload["error"]["code"]), expected)
                self.assertNotIn("sensitive provider payload", json.dumps(payload))
