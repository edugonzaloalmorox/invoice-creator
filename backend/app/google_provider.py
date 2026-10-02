"""Read-only Google Docs provider for the configured invoice template."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import google.auth.exceptions
import httplib2
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .field_map import FIELD_MAP, TEMPLATE_VERSION
from .provider import DocumentSnapshot, ProviderError


GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
FIELD_MARKER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
GOOGLE_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def google_document_id(document_url: str) -> str | None:
    """Return a document ID only for a canonical Google Docs document URL."""

    if not isinstance(document_url, str) or len(document_url) > 2048:
        return None
    try:
        parsed = urlparse(document_url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[:2] != ["document", "d"]:
        return None
    document_id = parts[2]
    return document_id if GOOGLE_DOCUMENT_ID.fullmatch(document_id) else None


def _credential_path(reference: str) -> Path:
    """Resolve only a filesystem credential reference, never inline secrets."""

    if reference.startswith("file://"):
        path = Path(reference.removeprefix("file://"))
    elif reference.startswith("/"):
        path = Path(reference)
    else:
        raise ProviderError("authenticate", "credentials_unavailable")
    if not path.is_file():
        raise ProviderError("authenticate", "credentials_unavailable")
    return path


def load_service_account_credentials(reference: str):
    """Load a service account from a secret-mounted JSON file."""

    path = _credential_path(reference)
    try:
        return service_account.Credentials.from_service_account_file(str(path), scopes=GOOGLE_SCOPES)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ProviderError("authenticate", "credentials_invalid") from error


def _provider_error(operation: str, error: Exception) -> ProviderError:
    """Map Google/client failures to stable messages without provider payloads."""

    if isinstance(error, HttpError):
        status = getattr(error.resp, "status", None)
        if status == 401:
            return ProviderError(operation, "credentials_invalid")
        if status == 403:
            return ProviderError(operation, "permission_denied")
        if status == 404:
            return ProviderError(operation, "template_not_found")
        if status == 429 or status is not None and status >= 500:
            return ProviderError(operation, "provider_unavailable", retryable=True)
    if isinstance(error, (TimeoutError, google.auth.exceptions.TransportError)):
        return ProviderError(operation, "timeout", retryable=True)
    if isinstance(error, google.auth.exceptions.GoogleAuthError):
        return ProviderError(operation, "credentials_invalid")
    return ProviderError(operation, "provider_unavailable", retryable=True)


def _text_run_content(element: Mapping[str, Any]) -> str:
    text_run = element.get("textRun", {})
    return str(text_run.get("content", ""))


def _walk_content(content: list[Mapping[str, Any]], section: str, prefix: str):
    """Yield text and stable locations from body, table, header, or footer content."""

    for index, element in enumerate(content):
        location = f"{section}:{prefix}:{index}"
        if "paragraph" in element:
            paragraph = element["paragraph"]
            text = "".join(_text_run_content(item) for item in paragraph.get("elements", []))
            yield text, location
        elif "table" in element:
            for row_index, row in enumerate(element["table"].get("tableRows", [])):
                for cell_index, cell in enumerate(row.get("tableCells", [])):
                    cell_prefix = f"{prefix}:{index}/row:{row_index}/cell:{cell_index}"
                    yield from _walk_content(cell.get("content", []), section, cell_prefix)


def normalize_google_document(document: Mapping[str, Any], *, document_id: str) -> DocumentSnapshot:
    """Convert a Google Docs resource into the provider's sanitized snapshot."""

    locations: dict[str, list[str]] = {name: [] for name in FIELD_MAP}
    values: dict[str, str] = {}

    sections: list[tuple[str, list[Mapping[str, Any]], str]] = [
        ("body", document.get("body", {}).get("content", []), "content"),
    ]
    for header_id, header in sorted(document.get("headers", {}).items()):
        sections.append(("header", header.get("content", []), str(header_id)))
    for footer_id, footer in sorted(document.get("footers", {}).items()):
        sections.append(("footer", footer.get("content", []), str(footer_id)))

    title = str(document.get("title", "configured-invoice-template"))
    for section, content, prefix in sections:
        for text, location in _walk_content(content, section, prefix):
            for match in FIELD_MARKER.finditer(text):
                name = match.group(1)
                if name in locations:
                    locations[name].append(location)

    return DocumentSnapshot(
        document_id=document_id,
        title=title,
        fields={name: tuple(items) for name, items in locations.items()},
        values=values,
        version=TEMPLATE_VERSION,
    )


class GoogleDocumentProvider:
    """Google Drive/Docs provider using an isolated temporary copy for filling."""

    def __init__(
        self,
        credential_reference: str,
        *,
        connect_timeout_seconds: float = 3,
        read_timeout_seconds: float = 10,
        drive_service=None,
        docs_service=None,
        credentials_loader: Callable[[str], Any] = load_service_account_credentials,
    ):
        self.credential_reference = credential_reference
        self.timeout_seconds = max(connect_timeout_seconds, read_timeout_seconds)
        self._drive_service = drive_service
        self._docs_service = docs_service
        self._credentials_loader = credentials_loader

    def _services(self):
        if self._drive_service is not None and self._docs_service is not None:
            return self._drive_service, self._docs_service
        try:
            credentials = self._credentials_loader(self.credential_reference)
            http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=self.timeout_seconds))
            self._drive_service = build("drive", "v3", http=http, cache_discovery=False)
            self._docs_service = build("docs", "v1", http=http, cache_discovery=False)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("authenticate", error) from error
        return self._drive_service, self._docs_service

    def read_template(self, template_id: str) -> DocumentSnapshot:
        try:
            drive, docs = self._services()
            metadata = (
                drive.files()
                .get(fileId=template_id, fields="id,name,mimeType,trashed,version", supportsAllDrives=True)
                .execute(num_retries=0)
            )
            if metadata.get("trashed") or metadata.get("mimeType") != GOOGLE_DOC_MIME_TYPE:
                raise ProviderError("read_template", "template_not_found")
            document = docs.documents().get(documentId=template_id).execute(num_retries=0)
            return normalize_google_document(document, document_id=template_id)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("read_template", error) from error

    def copy_document(self, template_id: str, title: str) -> str:
        try:
            drive, _ = self._services()
            result = (
                drive.files()
                .copy(fileId=template_id, body={"name": title}, fields="id", supportsAllDrives=True)
                .execute(num_retries=0)
            )
            document_id = result.get("id")
            if not document_id:
                raise ProviderError("copy_document", "malformed_response")
            return document_id
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("copy_document", error) from error

    def replace_values(self, document_id: str, replacements: Mapping[str, str]) -> None:
        try:
            _, docs = self._services()
            requests = [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{" + field + "}}", "matchCase": True},
                        "replaceText": str(value),
                    }
                }
                for field, value in replacements.items()
            ]
            if requests:
                docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute(num_retries=0)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("replace_values", error) from error

    def export_pdf(self, document_id: str) -> bytes:
        try:
            drive, _ = self._services()
            pdf = drive.files().export(fileId=document_id, mimeType="application/pdf").execute(num_retries=0)
            if not isinstance(pdf, bytes) or not pdf:
                raise ProviderError("export_pdf", "empty_response")
            return pdf
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("export_pdf", error) from error

    def delete_document(self, document_id: str) -> None:
        try:
            drive, _ = self._services()
            drive.files().delete(fileId=document_id, supportsAllDrives=True).execute(num_retries=0)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("delete_document", error) from error
