"""Document-provider contract and deterministic credential-free fixture.

The real Google provider will implement ``DocumentProvider`` in a later task.
Provider methods return sanitized domain values and raise ``ProviderError``;
provider payloads and document identifiers are intentionally not exposed by the
exception's public message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """Sanitized document structure returned by a provider read."""

    document_id: str
    title: str
    fields: Mapping[str, tuple[str, ...]]
    values: Mapping[str, str]
    version: str = "2026-01"


class ProviderError(RuntimeError):
    """Safe provider failure classified by operation and stable error code."""

    def __init__(self, operation: str, code: str, *, retryable: bool = False):
        self.operation = operation
        self.code = code
        self.retryable = retryable
        super().__init__(f"Document provider {operation} failed: {code}")


class DocumentProvider(Protocol):
    """Provider operations required by document generation.

    ``read_template`` returns normalized structure, ``copy_document`` creates
    an isolated temporary copy, ``replace_values`` mutates only that copy,
    ``export_pdf`` returns non-empty PDF bytes, and ``delete_document`` cleans
    up the temporary copy. Implementations must bound external calls according
    to application configuration and classify provider failures as
    ``ProviderError``.
    """

    def read_template(self, template_id: str) -> DocumentSnapshot: ...

    def copy_document(self, template_id: str, title: str) -> str: ...

    def replace_values(self, document_id: str, replacements: Mapping[str, str]) -> None: ...

    def export_pdf(self, document_id: str) -> bytes: ...

    def delete_document(self, document_id: str) -> None: ...


class FixtureDocumentProvider:
    """Deterministic in-memory provider for unit and integration tests."""

    def __init__(
        self,
        *,
        fields: Mapping[str, tuple[str, ...]] | None = None,
        failures: Mapping[str, str] | None = None,
        empty_pdf: bool = False,
    ):
        self._template_id = "fixture-template"
        self._template = DocumentSnapshot(
            self._template_id,
            "fixture-invoice-template",
            dict(fields or {"service_start_date": ("body:0",), "total_amount": ("table:0",)}),
            {"service_start_date": "", "total_amount": ""},
        )
        self._copies: dict[str, DocumentSnapshot] = {}
        self._failures = dict(failures or {})
        self._empty_pdf = empty_pdf
        self._copy_number = 0
        self.calls: list[tuple[str, str]] = []

    def _check_failure(self, operation: str) -> None:
        if operation in self._failures:
            code = self._failures[operation]
            raise ProviderError(operation, code, retryable=code in {"timeout", "unavailable"})

    def read_template(self, template_id: str) -> DocumentSnapshot:
        self.calls.append(("read_template", template_id))
        self._check_failure("read_template")
        if template_id != self._template_id:
            raise ProviderError("read_template", "template_not_found")
        return self._template

    def copy_document(self, template_id: str, title: str) -> str:
        self.calls.append(("copy_document", template_id))
        self._check_failure("copy_document")
        if template_id != self._template_id:
            raise ProviderError("copy_document", "template_not_found")
        self._copy_number += 1
        document_id = f"fixture-copy-{self._copy_number}"
        self._copies[document_id] = DocumentSnapshot(
            document_id, title, dict(self._template.fields), dict(self._template.values), self._template.version
        )
        return document_id

    def replace_values(self, document_id: str, replacements: Mapping[str, str]) -> None:
        self.calls.append(("replace_values", document_id))
        self._check_failure("replace_values")
        document = self._copies.get(document_id)
        if document is None:
            raise ProviderError("replace_values", "document_not_found")
        values = dict(document.values)
        for field, value in replacements.items():
            locations = document.fields.get(field, ())
            if not locations:
                raise ProviderError("replace_values", "field_missing")
            if len(locations) > 1:
                raise ProviderError("replace_values", "field_ambiguous")
            values[field] = value
        self._copies[document_id] = DocumentSnapshot(document.document_id, document.title, document.fields, values)

    def export_pdf(self, document_id: str) -> bytes:
        self.calls.append(("export_pdf", document_id))
        self._check_failure("export_pdf")
        if document_id not in self._copies:
            raise ProviderError("export_pdf", "document_not_found")
        if self._empty_pdf:
            return b""
        return b"%PDF-1.4\n% fixture invoice\n%%EOF\n"

    def delete_document(self, document_id: str) -> None:
        self.calls.append(("delete_document", document_id))
        self._check_failure("delete_document")
        if document_id not in self._copies:
            raise ProviderError("delete_document", "document_not_found")
        del self._copies[document_id]

    def copy_snapshot(self, document_id: str) -> DocumentSnapshot:
        """Expose fixture state for tests without exposing this as provider API."""

        return self._copies[document_id]
