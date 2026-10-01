import unittest

from backend.app.provider import FixtureDocumentProvider, ProviderError
from backend.app.field_map import FIELD_MAP


class FixtureProviderTest(unittest.TestCase):
    def test_success_records_order_and_does_not_mutate_master(self):
        provider = FixtureDocumentProvider()
        master_before = provider.read_template("fixture-template")
        copy_id = provider.copy_document("fixture-template", "safe-temporary-title")
        provider.replace_values(copy_id, {"service_start_date": "2026-09-01"})
        pdf = provider.export_pdf(copy_id)
        provider.delete_document(copy_id)

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(
            [operation for operation, _ in provider.calls],
            ["read_template", "copy_document", "replace_values", "export_pdf", "delete_document"],
        )
        self.assertEqual(provider.read_template("fixture-template"), master_before)

    def test_missing_and_duplicate_fields_are_classified(self):
        missing = FixtureDocumentProvider()
        copy_id = missing.copy_document("fixture-template", "safe-title")
        with self.assertRaisesRegex(ProviderError, "field_missing"):
            missing.replace_values(copy_id, {"unknown": "value"})

        duplicate = FixtureDocumentProvider(fields={"total_amount": ("table:0", "table:1")})
        copy_id = duplicate.copy_document("fixture-template", "safe-title")
        with self.assertRaisesRegex(ProviderError, "field_ambiguous"):
            duplicate.replace_values(copy_id, {"total_amount": "1.00"})

    def test_injected_provider_failures_are_safe_and_cleanup_is_attempted(self):
        provider = FixtureDocumentProvider(failures={"export_pdf": "timeout"})
        copy_id = provider.copy_document("fixture-template", "safe-title")
        provider.replace_values(copy_id, {"total_amount": "1.00"})
        with self.assertRaisesRegex(ProviderError, "export_pdf failed: timeout") as context:
            provider.export_pdf(copy_id)
        self.assertTrue(context.exception.retryable)
        provider.delete_document(copy_id)
        self.assertEqual(provider.calls[-1], ("delete_document", copy_id))

    def test_provider_error_does_not_expose_document_identifiers(self):
        provider = FixtureDocumentProvider()
        with self.assertRaises(ProviderError) as context:
            provider.read_template("secret-document-id")
        self.assertNotIn("secret-document-id", str(context.exception))

    def test_all_mapped_locations_replace_only_the_temporary_copy(self):
        fields = {name: (definition.location,) for name, definition in FIELD_MAP.items()}
        provider = FixtureDocumentProvider(fields=fields)
        master_before = provider.read_template("fixture-template")
        first = provider.copy_document("fixture-template", "temporary-a")
        second = provider.copy_document("fixture-template", "temporary-b")
        replacements = {name: f"TEST-{name}" for name in FIELD_MAP}
        provider.replace_values(first, replacements)

        self.assertNotEqual(first, second)
        self.assertEqual(provider.copy_snapshot(first).values, replacements)
        self.assertEqual(provider.copy_snapshot(second).values, master_before.values)
        self.assertEqual(provider.read_template("fixture-template"), master_before)

    def test_cleanup_failure_is_classified_for_orchestration(self):
        provider = FixtureDocumentProvider(failures={"delete_document": "cleanup_failed"})
        copy_id = provider.copy_document("fixture-template", "temporary")
        with self.assertRaisesRegex(ProviderError, "cleanup_failed"):
            provider.delete_document(copy_id)
