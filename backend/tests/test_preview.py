import json
import unittest

from backend.app.main import create_app
from backend.tests.test_configuration import configured_values, call
from backend.app.config import load_config


def invoice_body() -> bytes:
    return json.dumps(
        {
            "service_start_date": "2026-09-01",
            "service_end_date": "2026-09-05",
            "days_worked": "5",
            "pay_per_day": "240.00",
            "currency": "eur",
            "bank_name": "Example Bank",
            "account_holder": "Test Account Holder",
            "iban_or_account_number": "TEST-IBAN-0001",
            "swift_or_bic": "TESTBIC1",
        }
    ).encode()


def configured_app():
    return create_app(load_config(configured_values()).config)


class PreviewEndpointTest(unittest.TestCase):
    def test_valid_invoice_returns_normalized_input_and_authoritative_total(self):
        status, payload = call(
            configured_app(),
            "/api/invoices/preview",
            method="POST",
            body=invoice_body(),
            content_type="application/json; charset=utf-8",
        )
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload["input"]["currency"], "EUR")
        self.assertEqual(payload["calculation"]["total_amount"], "1200.00")
        self.assertTrue(payload["ready_for_generation"])

    def test_invalid_json_missing_body_and_wrong_content_type_use_safe_errors(self):
        app = configured_app()
        cases = (
            (b"not-json", "application/json", "invalid_json"),
            (b"", "application/json", "invalid_json"),
            (invoice_body(), "text/plain", "invalid_json"),
        )
        for body, content_type, code in cases:
            with self.subTest(code=code, content_type=content_type):
                status, payload = call(
                    app,
                    "/api/invoices/preview",
                    method="POST",
                    body=body,
                    content_type=content_type,
                )
                self.assertEqual(status["status"], "400 Bad Request")
                self.assertEqual(payload["error"]["code"], code)
                self.assertNotIn("TEST-IBAN-0001", json.dumps(payload))

    def test_invalid_fields_return_field_errors_without_a_total(self):
        values = json.loads(invoice_body())
        values["days_worked"] = "-1"
        values["bank_name"] = "TEST-SENSITIVE-BANK"
        status, payload = call(
            configured_app(),
            "/api/invoices/preview",
            method="POST",
            body=json.dumps(values).encode(),
            content_type="application/json",
        )
        self.assertEqual(status["status"], "400 Bad Request")
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("days_worked", {field["name"] for field in payload["error"]["fields"]})
        self.assertNotIn("calculation", payload)
        self.assertNotIn("TEST-SENSITIVE-BANK", json.dumps(payload))

    def test_preview_rejects_when_service_is_not_ready(self):
        status, payload = call(
            create_app(load_config({}).config),
            "/api/invoices/preview",
            method="POST",
            body=invoice_body(),
            content_type="application/json",
        )
        self.assertEqual(status["status"], "503 Service Unavailable")
        self.assertEqual(payload["error"]["code"], "service_not_ready")

