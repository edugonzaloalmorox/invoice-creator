"""Field-map-driven detection over normalized provider document snapshots."""

from __future__ import annotations

from .field_map import FIELD_ALIASES, FIELD_MAP, REPEATABLE_FIELDS, TEMPLATE_VERSION
from .provider import DocumentProvider, DocumentSnapshot, ProviderError


def detect_fields(provider: DocumentProvider, template_id: str) -> dict:
    """Return reviewable mapped fields without exposing unrelated document text."""

    snapshot = provider.read_template(template_id)
    if snapshot.document_id != template_id or snapshot.version != TEMPLATE_VERSION:
        raise ProviderError("read_template", "unsupported_template")
    fields = []
    warnings = []
    for name, definition in FIELD_MAP.items():
        locations = snapshot.fields.get(name, ())
        if not locations:
            alias_locations = snapshot.fields.get(FIELD_ALIASES.get(name), ()) if name in FIELD_ALIASES else ()
            if alias_locations:
                locations = alias_locations
        value = snapshot.values.get(name) or None
        field_warnings: list[str] = []
        if not locations:
            field_warnings.append("missing_field")
        elif len(locations) > 1 and name not in REPEATABLE_FIELDS:
            field_warnings.append("ambiguous_field")
        if value is not None:
            field_warnings.append("already_filled")
        if field_warnings:
            warnings.extend({"field": name, "code": warning} for warning in field_warnings)
        source_location = locations[0] if locations else definition.location
        fields.append({
            "name": definition.name,
            "label": definition.label,
            "type": definition.type,
            "value": value,
            "required": definition.required,
            "calculated": definition.calculated,
            "confidence": "high" if len(locations) == 1 or name in REPEATABLE_FIELDS else "low",
            "source": {"section": source_location.split(":", 1)[0], "location": source_location},
            "warnings": field_warnings,
        })
    return {"template": {"name": snapshot.title, "version": TEMPLATE_VERSION}, "fields": fields, "warnings": warnings}
