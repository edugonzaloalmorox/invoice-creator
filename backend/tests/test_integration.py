import json
import unittest

from backend.app.config import CONFIG_TEMPLATE_ID, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import call, configured_values
from backend.tests.test_generate import call_raw
from backend.tests.test_preview import invoice_body


class CredentialFreeWorkflowTest(unittest.TestCase):
    def test_detection_review_calculation_generation_and_cleanup_are_one_workflow(self):
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        provider = FixtureDocumentProvider()
        app = create_app(load_config(values).config, provider)
        master_before = provider.read_template("fixture-template")

        detection_status, detection = call(app, "/api/template/fields")
        self.assertEqual(detection_status["status"], "200 OK")
        review_payload = json.loads(invoice_body())
        self.assertEqual(
            {field["name"] for field in detection["fields"]},
            {"service_start_date", "service_end_date", "days_worked", "pay_per_day", "currency", "bank_name", "account_holder", "iban_or_account_number", "swift_or_bic", "total_amount"},
        )

        preview_status, preview = call(app, "/api/invoices/preview", method="POST", body=invoice_body(), content_type="application/json")
        self.assertEqual(preview_status["status"], "200 OK")
        self.assertEqual(preview["calculation"]["total_amount"], "1200.00")

        generate_status, pdf = call_raw(app, invoice_body())
        self.assertEqual(generate_status["status"], "200 OK")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual([operation for operation, _ in provider.calls[-4:]], ["copy_document", "replace_values", "export_pdf", "delete_document"])
        self.assertEqual(provider.read_template("fixture-template"), master_before)
        self.assertNotIn("TEST-IBAN-0001", generate_status["headers"])
        self.assertNotIn("TEST-IBAN-0001", generate_status["headers"].get("X-Request-ID", ""))

