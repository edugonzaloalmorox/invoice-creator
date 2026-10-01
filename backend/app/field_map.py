"""Versioned field map for the sanitized invoice template fixture."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


TEMPLATE_ID = "fixture-template"
TEMPLATE_VERSION = "2026-01"


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    name: str
    label: str
    location: str
    format: str
    type: str
    required: bool
    calculated: bool = False


FIELD_MAP = MappingProxyType({
    "service_start_date": FieldDefinition("service_start_date", "Service start date", "table:0/row:1/cell:1", "YYYY-MM-DD", "date", True),
    "service_end_date": FieldDefinition("service_end_date", "Service end date", "table:0/row:2/cell:1", "YYYY-MM-DD", "date", False),
    "days_worked": FieldDefinition("days_worked", "Days worked", "body:paragraph:4", "decimal(2)", "number", True),
    "pay_per_day": FieldDefinition("pay_per_day", "Pay per day", "body:paragraph:5", "decimal(2)", "money", True),
    "currency": FieldDefinition("currency", "Currency", "header:paragraph:1", "ISO-4217", "currency", True),
    "bank_name": FieldDefinition("bank_name", "Bank name", "footer:paragraph:1", "text", "text", False),
    "account_holder": FieldDefinition("account_holder", "Account holder", "body:paragraph:6", "text", "text", False),
    "iban_or_account_number": FieldDefinition("iban_or_account_number", "IBAN or account number", "body:paragraph:7", "uppercase-text", "text", False),
    "swift_or_bic": FieldDefinition("swift_or_bic", "SWIFT/BIC", "body:paragraph:8/split-run:1", "BIC", "text", False),
    "total_amount": FieldDefinition("total_amount", "Total", "table:1/row:3/cell:1", "decimal(2)", "money", True, True),
})


def field_definition(name: str) -> FieldDefinition | None:
    return FIELD_MAP.get(name)
