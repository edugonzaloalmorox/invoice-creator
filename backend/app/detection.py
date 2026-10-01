"""Field-map-driven detection over normalized provider document snapshots."""

from __future__ import annotations

from .field_map import FIELD_MAP, TEMPLATE_ID, TEMPLATE_VERSION
from .provider import DocumentProvider, DocumentSnapshot, ProviderError


def detect_fields(provider: DocumentProvider, template_id: str) -> dict:
    """Return reviewable mapped fields without exposing unrelated document text."""

    snapshot = provider.read_template(template_id)
    if snapshot.document_id != TEMPLATE_ID or snapshot.version != TEMPLATE_VERSION:
        raise ProviderError("read_template", "unsupported_template")
    fields = []
    warnings = []
    for name, definition in FIELD_MAP.items():
        locations = snapshot.fields.get(name, ())
        value = snapshot.values.get(name) or None
        field_warnings: list[str] = []
        if not locations:
            field_warnings.append("missing_field")
        elif len(locations) > 1:
            field_warnings.append("ambiguous_field")
        if value is not None:
            field_warnings.append("already_filled")
        if field_warnings:
            warnings.extend({"field": name, "code": warning} for warning in field_warnings)
        fields.append({
            "name": definition.name,
            "label": definition.label,
            "type": definition.type,
            "value": value,
            "required": definition.required,
            "calculated": definition.calculated,
            "confidence": "high" if len(locations) == 1 else "low",
            "source": {"section": definition.location.split(":", 1)[0], "location": definition.location},
            "warnings": field_warnings,
        })
    return {"template": {"name": snapshot.title, "version": TEMPLATE_VERSION}, "fields": fields, "warnings": warnings}
