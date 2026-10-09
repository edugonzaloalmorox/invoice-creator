"""Read-only Google Docs provider for the configured invoice template."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import google.auth.exceptions
import httplib2
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2 import service_account
from google.oauth2 import credentials as user_credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .field_map import FIELD_ALIASES, FIELD_MAP, REPEATABLE_FIELDS, TEMPLATE_VERSION
from .provider import DocumentSnapshot, ProviderError


GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
FIELD_MARKER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
GOOGLE_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


logger = logging.getLogger(__name__)


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

    status = getattr(getattr(error, "resp", None), "status", None)
    logger.error(
        "google_provider_failure operation=%s exception_type=%s http_status=%s",
        operation,
        type(error).__name__,
        status if isinstance(status, int) else "none",
    )

    if isinstance(error, HttpError):
        status = getattr(error.resp, "status", None)
        if status == 401:
            return ProviderError(operation, "credentials_invalid")
        if status == 403:
            return ProviderError(operation, "permission_denied")
        if status == 404:
            code = "template_not_found" if operation in {"read_template", "copy_document"} else "document_not_found"
            return ProviderError(operation, code)
        if status == 429 or status is not None and status >= 500:
            return ProviderError(operation, "provider_unavailable", retryable=True)
    if isinstance(error, (TimeoutError, google.auth.exceptions.TransportError)):
        return ProviderError(operation, "timeout", retryable=True)
    if isinstance(error, google.auth.exceptions.GoogleAuthError):
        return ProviderError(operation, "credentials_invalid")
    return ProviderError(operation, "provider_unavailable", retryable=True)


def _text_run_content(element: Mapping[str, Any]) -> str:
    """Return the text content of a Google Docs text-run element."""

    text_run = element.get("textRun", {})
    return str(text_run.get("content", ""))


def _document_text(document: Mapping[str, Any]) -> str:
    """Collect editable text for verification without returning provider content."""

    sections = list(_tab_sections(document.get("tabs", [])))
    if not sections:
        sections = [("body", document.get("body", {}).get("content", []), "content")]
        sections.extend(("header", header.get("content", []), str(key)) for key, header in sorted(document.get("headers", {}).items()))
        sections.extend(("footer", footer.get("content", []), str(key)) for key, footer in sorted(document.get("footers", {}).items()))
    return "\n".join(text for _, content, prefix in sections for text, _ in _walk_content(content, "text", prefix))


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


def _tab_sections(tabs: list[Mapping[str, Any]], prefix: str = ""):
    """Yield body, header, and footer content from a tab tree."""

    for index, tab in enumerate(tabs):
        properties = tab.get("tabProperties", {})
        tab_id = str(properties.get("tabId", index))
        tab_prefix = f"{prefix}{tab_id}"
        document_tab = tab.get("documentTab", {})
        yield ("body", document_tab.get("body", {}).get("content", []), f"tab:{tab_prefix}:content")
        for header_id, header in sorted(document_tab.get("headers", {}).items()):
            yield ("header", header.get("content", []), f"tab:{tab_prefix}:{header_id}")
        for footer_id, footer in sorted(document_tab.get("footers", {}).items()):
            yield ("footer", footer.get("content", []), f"tab:{tab_prefix}:{footer_id}")
        yield from _tab_sections(tab.get("childTabs", []), f"{tab_prefix}/")


def normalize_google_document(document: Mapping[str, Any], *, document_id: str) -> DocumentSnapshot:
    """Convert a Google Docs resource into the provider's sanitized snapshot."""

    locations: dict[str, list[str]] = {name: [] for name in FIELD_MAP}
    values: dict[str, str] = {}

    sections = list(_tab_sections(document.get("tabs", [])))
    if not sections:
        sections = [
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
                    # A paragraph/cell is one replacement location even when
                    # the same placeholder occurs more than once inside it.
                    # replaceAllText replaces all occurrences in that
                    # location; only distinct document locations are
                    # ambiguous.
                    if location not in locations[name]:
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
        credentials=None,
    ):
        """Configure Google Docs and Drive clients with injectable dependencies."""

        self.credential_reference = credential_reference
        self.timeout_seconds = max(connect_timeout_seconds, read_timeout_seconds)
        self._drive_service = drive_service
        self._docs_service = docs_service
        self._credentials_loader = credentials_loader
        self._credentials = credentials

    @classmethod
    def for_user_session(
        cls,
        *,
        access_token: str,
        refresh_token: str | None,
        client_id: str,
        client_secret: str,
        scopes: tuple[str, ...],
        connect_timeout_seconds: float = 3,
        read_timeout_seconds: float = 10,
    ):
        """Create a provider authorized with the signed-in user's OAuth token."""

        credentials = user_credentials.Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=list(scopes),
        )
        return cls(
            "oauth://signed-in-user",
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
            credentials=credentials,
        )

    def _services(self):
        """Build or return cached Drive and Docs service clients."""

        if self._drive_service is not None and self._docs_service is not None:
            return self._drive_service, self._docs_service
        try:
            credentials = self._credentials or self._credentials_loader(self.credential_reference)
            http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=self.timeout_seconds))
            self._drive_service = build("drive", "v3", http=http, cache_discovery=False)
            self._docs_service = build("docs", "v1", http=http, cache_discovery=False)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("authenticate", error) from error
        return self._drive_service, self._docs_service

    def read_template(self, template_id: str) -> DocumentSnapshot:
        """Read and normalize a Google Docs template without modifying it."""

        try:
            drive, docs = self._services()
            # ``drive.file`` only exposes files explicitly opened or created by
            # the app. A pasted link can point at any Google Doc the signed-in
            # user can read, so OAuth reads must go through Docs API with the
            # documents scope. Keep the Drive metadata check for service
            # accounts, where it also verifies the configured template type.
            if self.credential_reference != "oauth://signed-in-user":
                metadata = (
                    drive.files()
                    .get(fileId=template_id, fields="id,name,mimeType,trashed,version", supportsAllDrives=True)
                    .execute(num_retries=0)
                )
                if metadata.get("trashed") or metadata.get("mimeType") != GOOGLE_DOC_MIME_TYPE:
                    raise ProviderError("read_template", "template_not_found")
            document = docs.documents().get(documentId=template_id, includeTabsContent=True).execute(num_retries=0)
            return normalize_google_document(document, document_id=template_id)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("read_template", error) from error

    def copy_document(self, template_id: str, title: str) -> str:
        """Create an isolated temporary copy and return its opaque document ID."""

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
        """Replace mapped placeholders in a temporary document copy."""

        try:
            _, docs = self._services()
            current = docs.documents().get(documentId=document_id, includeTabsContent=True).execute(num_retries=0)
            snapshot = normalize_google_document(current, document_id=document_id)
            current_text = _document_text(current)
            markers = {match.group(1): match.group(0) for match in FIELD_MARKER.finditer(current_text)}
            effective_replacements = {}
            for field, value in replacements.items():
                locations = snapshot.fields.get(field, ())
                if not locations:
                    canonical_name = FIELD_ALIASES.get(field)
                    canonical_locations = snapshot.fields.get(canonical_name, ()) if canonical_name else ()
                    if len(canonical_locations) == 1:
                        # The canonical placeholder is present; the legacy
                        # alias is intentionally absent from this template.
                        continue
                # A completely empty fake response is tolerated here so the
                # operation remains independently testable; verification will
                # still reject it before export in the generation workflow.
                if not locations and current_text:
                    raise ProviderError("replace_values", "field_missing", field=field)
                if not locations and not current_text:
                    effective_replacements[field] = value
                    continue
                if len(locations) != 1 and field not in REPEATABLE_FIELDS:
                    raise ProviderError("replace_values", "field_ambiguous", field=field)
                effective_replacements[field] = value
            requests = [
                {
                    "replaceAllText": {
                        "containsText": {"text": markers.get(field, "{{" + field + "}}"), "matchCase": True},
                        "replaceText": str(value),
                    }
                }
                for field, value in effective_replacements.items()
            ]
            if requests:
                docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute(num_retries=0)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("replace_values", error) from error

    def verify_replacements(self, document_id: str, replacements: Mapping[str, str]) -> None:
        """Re-read a temporary document and confirm every replacement applied."""

        try:
            _, docs = self._services()
            document = docs.documents().get(documentId=document_id, includeTabsContent=True).execute(num_retries=0)
            text = _document_text(document)
            for field, value in replacements.items():
                if "{{" + field + "}}" in text or str(value) not in text:
                    raise ProviderError("verify_replacements", "replacement_not_applied")
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("verify_replacements", error) from error

    def export_pdf(self, document_id: str) -> bytes:
        """Export a temporary Google document as PDF bytes."""

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
        """Delete a temporary Google document after generation completes."""

        try:
            drive, _ = self._services()
            drive.files().delete(fileId=document_id, supportsAllDrives=True).execute(num_retries=0)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_error("delete_document", error) from error
