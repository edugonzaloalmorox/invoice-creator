import json
import unittest

from backend.app.config import CONFIG_TEMPLATE_ID, load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import call, configured_values


class DetectionTest(unittest.TestCase):
    def test_template_fields_returns_map_metadata_and_warnings(self):
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        provider = FixtureDocumentProvider(fields={"service_start_date": ("table:0", "table:1")})
        status, payload = call(create_app(load_config(values).config, provider), "/api/template/fields")
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload["template"]["version"], "2026-01")
        total = next(field for field in payload["fields"] if field["name"] == "total_amount")
        self.assertIn("missing_field", total["warnings"])
        start = next(field for field in payload["fields"] if field["name"] == "service_start_date")
        self.assertIn("ambiguous_field", start["warnings"])
        self.assertIn("table", start["source"]["section"])
        self.assertNotIn("body", json.dumps(payload["warnings"]))

    def test_provider_error_is_safe(self):
        values = configured_values()
        values[CONFIG_TEMPLATE_ID] = "fixture-template"
        provider = FixtureDocumentProvider(failures={"read_template": "permission_denied"})
        status, payload = call(create_app(load_config(values).config, provider), "/api/template/fields")
        self.assertEqual(status["status"], "502 Bad Gateway")
        self.assertEqual(payload["error"]["code"], "provider_error")
        self.assertNotIn("permission_denied", json.dumps(payload))

