"""Invoice input validation and authoritative money calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Mapping


SUPPORTED_CURRENCIES = ("EUR", "GBP")
CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£"}
MAX_DAYS_WORKED = Decimal("366")
MAX_PAY_PER_DAY = Decimal("1000000.00")
MAX_TEXT_LENGTH = 200
MAX_INVOICE_NUMBER_LENGTH = 50
MAX_ACCOUNT_LENGTH = 34
MAX_BIC_LENGTH = 11
MONEY_PLACES = Decimal("0.01")

_DECIMAL_RE = re.compile(r"^(?:0|[0-9]+)(?:\.[0-9]+)?$")
_BIC_RE = re.compile(r"^[A-Z0-9]{8}(?:[A-Z0-9]{3})?$")


@dataclass(frozen=True, slots=True)
class InvoiceInput:
    invoice_number: str
    service_start_date: str
    service_end_date: str | None
    days_worked: Decimal
    pay_per_day: Decimal
    currency: str
    bank_name: str | None
    account_holder: str | None
    iban_or_account_number: str | None
    swift_or_bic: str | None
    week_ending: str | None = None
    start_date_service: str | None = None
    finish_date_service: str | None = None
    payment_reference: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    name: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class InvoiceValidation:
    value: InvoiceInput | None
    errors: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return self.value is not None and not self.errors


def _issue(name: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(name, code, message)


def _text(
    data: Mapping[str, object],
    name: str,
    errors: list[ValidationIssue],
    *,
    required: bool = False,
    maximum: int = MAX_TEXT_LENGTH,
) -> str | None:
    raw = data.get(name)
    if raw is None:
        if required:
            errors.append(_issue(name, "required", "This field is required."))
        return None
    if not isinstance(raw, str):
        errors.append(_issue(name, "invalid_text", "Enter text for this field."))
        return None
    value = " ".join(raw.split())
    if not value and required:
        errors.append(_issue(name, "required", "This field is required."))
    elif len(value) > maximum:
        errors.append(_issue(name, "too_long", f"Use at most {maximum} characters."))
    return value or None


def _date_value(
    data: Mapping[str, object],
    name: str,
    errors: list[ValidationIssue],
    *,
    required: bool,
) -> date | None:
    raw = data.get(name)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            errors.append(_issue(name, "required", "This field is required."))
        return None
    if not isinstance(raw, str):
        errors.append(_issue(name, "invalid_date", "Enter a date as YYYY-MM-DD."))
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        errors.append(_issue(name, "invalid_date", "Enter a date as YYYY-MM-DD."))
        return None
    return parsed


def _decimal_value(
    data: Mapping[str, object],
    name: str,
    errors: list[ValidationIssue],
    *,
    maximum: Decimal,
) -> Decimal | None:
    raw = data.get(name)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        errors.append(_issue(name, "required", "This field is required."))
        return None
    if not isinstance(raw, str):
        errors.append(_issue(name, "invalid_decimal", "Enter a valid non-negative amount."))
        return None
    normalized = raw.strip()
    if not _DECIMAL_RE.fullmatch(normalized):
        errors.append(_issue(name, "invalid_decimal", "Enter a valid non-negative amount."))
        return None
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        errors.append(_issue(name, "invalid_decimal", "Enter a valid non-negative amount."))
        return None
    if value.as_tuple().exponent < -2:
        errors.append(_issue(name, "too_precise", "Use at most 2 decimal places."))
    elif value > maximum:
        errors.append(_issue(name, "out_of_range", f"Use a value no greater than {maximum}."))
    return value


def validate_invoice(data: Mapping[str, object]) -> InvoiceValidation:
    """Validate and normalize an invoice payload without persisting it."""

    errors: list[ValidationIssue] = []
    invoice_number = _text(data, "invoice_number", errors, required=True, maximum=MAX_INVOICE_NUMBER_LENGTH)
    invoice_date = _date_value(data, "service_start_date", errors, required=True)
    week_ending = _date_value(data, "week_ending", errors, required=False)
    start = _date_value(data, "start_date_service", errors, required=False)
    end = _date_value(data, "finish_date_service", errors, required=False)
    # Accept the original API names while clients migrate to the template names.
    if start is None and "start_date_service" not in data:
        start = invoice_date
    if end is None and "finish_date_service" not in data:
        end = _date_value(data, "service_end_date", errors, required=False)
    days = _decimal_value(data, "days_worked", errors, maximum=MAX_DAYS_WORKED)
    pay_name = "pay_per_day" if "pay_per_day" in data else "rate"
    pay = _decimal_value(data, pay_name, errors, maximum=MAX_PAY_PER_DAY)

    currency_raw = data.get("currency")
    currency = currency_raw.strip().upper() if isinstance(currency_raw, str) else ""
    if not currency:
        errors.append(_issue("currency", "required", "This field is required."))
    elif currency not in SUPPORTED_CURRENCIES:
        errors.append(_issue("currency", "unsupported_currency", "Use EUR or GBP."))

    bank_name = _text(data, "bank_name", errors)
    account_holder = _text(data, "account_holder", errors)
    account_name = "iban" if "iban" in data else "iban_or_account_number"
    bic_name = "swift" if "swift" in data else "swift_or_bic"
    account = _text(data, account_name, errors, maximum=MAX_ACCOUNT_LENGTH)
    bic = _text(data, bic_name, errors, maximum=MAX_BIC_LENGTH)
    if bic is not None:
        bic = bic.replace(" ", "").upper()
        if not _BIC_RE.fullmatch(bic):
            errors.append(_issue(bic_name, "invalid_bic", "Enter an 8 or 11 character BIC."))
    if account is not None:
        account = account.replace(" ", "").upper()

    if start is not None and end is not None and end < start:
        end_name = "finish_date_service" if "finish_date_service" in data else "service_end_date"
        errors.append(_issue(end_name, "before_start_date", "End date cannot precede start date."))

    payment_reference = _text(data, "payment_reference", errors)

    if errors or invoice_number is None or invoice_date is None or start is None or days is None or pay is None:
        return InvoiceValidation(None, tuple(errors))
    return InvoiceValidation(
        InvoiceInput(
            invoice_number,
            invoice_date.isoformat(),
            end.isoformat() if end is not None else None,
            days,
            pay,
            currency,
            bank_name,
            account_holder,
            account,
            bic,
            week_ending.isoformat() if week_ending is not None else None,
            start.isoformat(),
            end.isoformat() if end is not None else None,
            payment_reference,
        ),
        (),
    )


def calculate_total(invoice: InvoiceInput) -> Decimal:
    """Return the server-authoritative total rounded to cents, half-up."""

    return (invoice.days_worked * invoice.pay_per_day).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def format_total(invoice: InvoiceInput) -> str:
    """Serialize the authoritative total as the API's decimal string."""

    return f"{calculate_total(invoice):.2f}"


def currency_symbol(currency: str) -> str:
    """Return the display symbol for a validated ISO currency code."""

    return CURRENCY_SYMBOLS[currency]
