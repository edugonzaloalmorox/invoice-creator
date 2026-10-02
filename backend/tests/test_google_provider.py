import copy
import tempfile
import unittest
from types import SimpleNamespace

from googleapiclient.errors import HttpError

from backend.app.google_provider import (
    GOOGLE_DOC_MIME_TYPE,
    GoogleDocumentProvider,
    google_document_id,
    load_service_account_credentials,
    normalize_google_document,
)
from backend.app.provider import ProviderError


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self, **kwargs):
        return copy.deepcopy(self.payload)


class FakeFiles:
    def __init__(self, metadata):
        self.metadata = metadata
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self.metadata)

    def copy(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest({"id": "temporary-copy-id"})

    def export(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(b"%PDF-1.4\n%%EOF\n")

    def delete(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest({})


class FakeDrive:
    def __init__(self, metadata):
        self.files_api = FakeFiles(metadata)
        self.writes = []

    def files(self):
        return self.files_api


class FakeDocuments:
    def __init__(self, document):
        self.document = document
        self.calls = []
        self.writes = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self.document)

    def batchUpdate(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest({})


class FakeDocs:
    def __init__(self, document):
        self.documents_api = FakeDocuments(document)

    def documents(self):
        return self.documents_api


def google_document():
    return {
        "title": "Sanitized Google invoice",
        "body": {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": "Days: {{days_worked}}\n"}}]}},
                {"paragraph": {"elements": [{"textRun": {"content": "Swift: {{swift_"}}, {"textRun": {"content": "or_bic}}\n"}}]}},
                {
                    "table": {
                        "tableRows": [
                            {"tableCells": [{"content": [{"paragraph": {"elements": [{"textRun": {"content": "Start {{service_start_date}}"}}]}}]}]},
                        ]
                    }
                },
            ]
        },
        "headers": {
            "h1": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "{{currency}}"}}]}}]}
        },
        "footers": {
            "f1": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "{{bank_name}}"}}]}}]}
        },
    }


class GoogleProviderTest(unittest.TestCase):
    def test_google_document_id_accepts_only_google_docs_links(self):
        self.assertEqual(google_document_id("https://docs.google.com/document/d/abc_123/edit"), "abc_123")
        self.assertIsNone(google_document_id("http://docs.google.com/document/d/abc/edit"))
        self.assertIsNone(google_document_id("https://example.test/document/d/abc/edit"))

    def test_normalizes_body_table_header_footer_and_split_runs(self):
        snapshot = normalize_google_document(google_document(), document_id="real-template-id")

        self.assertEqual(snapshot.document_id, "real-template-id")
        self.assertEqual(snapshot.title, "Sanitized Google invoice")
        self.assertTrue(snapshot.fields["days_worked"])
        self.assertTrue(snapshot.fields["service_start_date"])
        self.assertTrue(snapshot.fields["currency"])
        self.assertTrue(snapshot.fields["bank_name"])
        self.assertTrue(snapshot.fields["swift_or_bic"])
        self.assertEqual(snapshot.values, {})

    def test_read_only_provider_reads_metadata_and_document_without_writes(self):
        drive = FakeDrive({"id": "real-template-id", "name": "Invoice", "mimeType": GOOGLE_DOC_MIME_TYPE, "version": "7"})
        docs = FakeDocs(google_document())
        provider = GoogleDocumentProvider("/run/secrets/google.json", drive_service=drive, docs_service=docs)

        first = provider.read_template("real-template-id")
        second = provider.read_template("real-template-id")

        self.assertEqual(first, second)
        self.assertEqual(len(drive.files_api.calls), 2)
        self.assertEqual(len(docs.documents_api.calls), 2)
        self.assertEqual(drive.writes, [])
        self.assertEqual(docs.documents_api.writes, [])

    def test_missing_template_and_permission_errors_are_safe(self):
        for status, code in ((404, "template_not_found"), (403, "permission_denied")):
            with self.subTest(status=status):
                response = SimpleNamespace(status=status, reason="provider error")
                error = HttpError(response, b"sensitive provider document payload")
                drive = FakeDrive({"id": "real-template-id", "name": "Invoice", "mimeType": GOOGLE_DOC_MIME_TYPE})
                drive.files_api.get = lambda **kwargs: (_ for _ in ()).throw(error)
                provider = GoogleDocumentProvider("/run/secrets/google.json", drive_service=drive, docs_service=FakeDocs({}))

                with self.assertRaises(ProviderError) as context:
                    provider.read_template("real-template-id")
                self.assertEqual(context.exception.code, code)
                self.assertNotIn("sensitive", str(context.exception))

    def test_credential_reference_never_treats_secret_manager_uri_as_file(self):
        with self.assertRaises(ProviderError) as context:
            load_service_account_credentials("secret-manager://invoice/google")
        self.assertEqual(context.exception.code, "credentials_unavailable")
        self.assertNotIn("invoice/google", str(context.exception))

    def test_missing_and_malformed_credential_files_are_safe(self):
        with self.assertRaisesRegex(ProviderError, "credentials_unavailable"):
            load_service_account_credentials("/run/secrets/missing-google.json")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as credential_file:
            credential_file.write("not-json")
            credential_file.flush()
            with self.assertRaisesRegex(ProviderError, "credentials_invalid"):
                load_service_account_credentials(credential_file.name)

    def test_copy_replace_export_and_delete_use_isolated_google_operations(self):
        drive = FakeDrive({})
        docs = FakeDocs({})
        provider = GoogleDocumentProvider("/run/secrets/google.json", drive_service=drive, docs_service=docs)

        copy_id = provider.copy_document("template", "invoice-2026-09-01")
        provider.replace_values(copy_id, {"bank_name": "TEST-BANK"})
        pdf = provider.export_pdf(copy_id)
        provider.delete_document(copy_id)

        self.assertEqual(copy_id, "temporary-copy-id")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(drive.files_api.calls[0]["fileId"], "template")
        self.assertEqual(drive.files_api.calls[-1]["fileId"], copy_id)
        self.assertEqual(docs.documents_api.calls[0]["documentId"], copy_id)
        self.assertEqual(docs.documents_api.calls[0]["body"]["requests"][0]["replaceAllText"]["replaceText"], "TEST-BANK")
