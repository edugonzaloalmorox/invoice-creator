import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from backend.app.config import CONFIG_TEMPLATE_ID, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import configured_values, call
from backend.tests.test_generate import call_raw
from backend.tests.test_preview import invoice_body


class BoundedSecurityRegressionTest(unittest.TestCase):
    def test_repeated_preview_requests_remain_bounded_and_safe(self):
        app = create_app(load_config(configured_values()).config, FixtureDocumentProvider())
        for _ in range(20):
            status, payload = call(app, "/api/invoices/preview", method="POST", body=invoice_body(), content_type="application/json")
            self.assertEqual(status["status"], "200 OK")
            self.assertEqual(payload["calculation"]["total_amount"], "1200.00")

    def test_concurrent_preview_requests_are_safe_and_isolated(self):
        app = create_app(load_config(configured_values()).config, FixtureDocumentProvider())

        def request(_index):
            return call(app, "/api/invoices/preview", method="POST", body=invoice_body(), content_type="application/json")

        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(request, range(20)))

        self.assertEqual([status["status"] for status, _ in results], ["200 OK"] * 20)
        self.assertEqual({payload["calculation"]["total_amount"] for _, payload in results}, {"1200.00"})

    def test_generation_rate_limit_bounds_repeated_work(self):
        provider = FixtureDocumentProvider()
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        app = create_app(load_config(values).config, provider)
        statuses = [call_raw(app, invoice_body())[0]["status"] for _ in range(11)]
        self.assertEqual(statuses[-1], "429 Too Many Requests")
        self.assertEqual(statuses.count("200 OK"), 10)
        self.assertEqual(len([call for call in provider.calls if call[0] == "copy_document"]), 10)
        metrics_status, metrics = call(app, "/api/metrics")
        self.assertEqual(metrics_status["status"], "200 OK")
        self.assertEqual(metrics["operational_events"]["rate_limited"], 1)

    def test_repeated_malformed_requests_never_echo_sensitive_values(self):
        app = create_app(load_config(configured_values()).config, FixtureDocumentProvider())
        for index in range(20):
            secret = f'{{"bank_name":"TEST-SENSITIVE-{index}","bad":}}'.encode()
            status, payload = call(app, "/api/invoices/preview", method="POST", body=secret, content_type="application/json")
            self.assertEqual(status["status"], "400 Bad Request")
            self.assertEqual(payload["error"]["code"], "invalid_json")
            self.assertNotIn(f"TEST-SENSITIVE-{index}", json.dumps(payload))

    def test_repeated_provider_timeouts_cleanup_every_created_copy(self):
        provider = FixtureDocumentProvider(failures={"export_pdf": "timeout"})
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        app = create_app(load_config(values).config, provider)

        statuses = [call_raw(app, invoice_body())[0]["status"] for _ in range(10)]

        self.assertEqual(statuses, ["504 Gateway Timeout"] * 10)
        self.assertEqual(len([entry for entry in provider.calls if entry[0] == "copy_document"]), 10)
        self.assertEqual(len([entry for entry in provider.calls if entry[0] == "delete_document"]), 10)
        metrics_status, metrics = call(app, "/api/metrics")
        self.assertEqual(metrics_status["status"], "200 OK")
        self.assertEqual(metrics["operational_events"]["provider_failure"], 10)

    def test_cleanup_failures_are_visible_without_document_identifiers(self):
        provider = FixtureDocumentProvider(failures={"delete_document": "cleanup_failed"})
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        app = create_app(load_config(values).config, provider)

        status, _ = call_raw(app, invoice_body())
        self.assertEqual(status["status"], "502 Bad Gateway")
        metrics_status, metrics = call(app, "/api/metrics")
        self.assertEqual(metrics_status["status"], "200 OK")
        self.assertEqual(metrics["operational_events"]["cleanup_failure"], 1)
        self.assertNotIn("fixture", json.dumps(metrics).lower())

    def test_malformed_payload_does_not_echo_sensitive_data(self):
        app = create_app(load_config(configured_values()).config)
        secret = b'{"bank_name":"TEST-SENSITIVE-BANK","bad":}'
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/api/invoices/preview", "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(secret)), "wsgi.input": BytesIO(secret)}, start_response))
        self.assertEqual(captured["status"], "400 Bad Request")
        self.assertNotIn("TEST-SENSITIVE-BANK", json.dumps(json.loads(body)))
