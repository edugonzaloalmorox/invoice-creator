import unittest

from backend.app.field_map import FIELD_MAP, TEMPLATE_ID, TEMPLATE_VERSION, field_definition
from backend.tests.fixtures.template_fixture import SANITIZED_TEMPLATE


class FieldMapTest(unittest.TestCase):
    def test_map_is_versioned_and_covers_sanitized_template_locations(self):
        self.assertEqual(SANITIZED_TEMPLATE["template_id"], TEMPLATE_ID)
        self.assertEqual(SANITIZED_TEMPLATE["version"], TEMPLATE_VERSION)
        locations = {
            item["location"]
            for section in SANITIZED_TEMPLATE["sections"].values()
            for item in section
        }
        self.assertTrue(locations)
        self.assertTrue(locations.issubset({definition.location for definition in FIELD_MAP.values()}))

    def test_every_definition_has_stable_metadata_and_total_is_calculated(self):
        self.assertEqual(len(FIELD_MAP), 22)
        for name, definition in FIELD_MAP.items():
            self.assertEqual(name, definition.name)
            self.assertTrue(definition.label)
            self.assertTrue(definition.location)
            self.assertTrue(definition.format)
            self.assertTrue(definition.type)
        self.assertTrue(field_definition("total_amount").calculated)
        self.assertIsNone(field_definition("unknown"))

    def test_invoice_fields_are_mapped_by_their_stable_names(self):
        expected = {
            "invoice_number", "invoice_date", "week_ending", "start_date_service",
            "finish_date_service", "rate", "amount", "subtotal", "total",
            "account_holder", "bank_name", "iban", "swift", "payment_reference",
        }
        self.assertTrue(expected.issubset(FIELD_MAP))
        self.assertTrue(field_definition("total").calculated)
