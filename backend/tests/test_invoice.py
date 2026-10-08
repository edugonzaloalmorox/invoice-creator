import unittest
from decimal import Decimal

from backend.app.invoice import (
    MAX_DAYS_WORKED,
    MAX_PAY_PER_DAY,
    calculate_total,
    format_total,
    validate_invoice,
)


def valid_invoice() -> dict[str, str]:
    return {
        "service_start_date": "2026-09-01",
        "invoice_number": "INV-2026-0001",
        "service_end_date": "2026-09-05",
        "days_worked": "5",
        "pay_per_day": "240.00",
        "currency": "eur",
        "bank_name": "  Example   Bank ",
        "account_holder": " Test Account Holder ",
        "iban_or_account_number": "test-iban-0001",
        "swift_or_bic": "testbic1",
    }


class InvoiceValidationTest(unittest.TestCase):
    def test_valid_invoice_is_normalized(self):
        result = validate_invoice(valid_invoice())
        self.assertTrue(result.valid)
        self.assertEqual(result.value.service_start_date, "2026-09-01")
        self.assertEqual(result.value.invoice_number, "INV-2026-0001")
        self.assertEqual(result.value.service_end_date, "2026-09-05")
        self.assertEqual(result.value.currency, "EUR")
        self.assertEqual(result.value.bank_name, "Example Bank")
        self.assertEqual(result.value.iban_or_account_number, "TEST-IBAN-0001")
        self.assertEqual(result.value.swift_or_bic, "TESTBIC1")

    def test_invalid_dates_and_reversed_range_are_rejected(self):
        values = valid_invoice()
        values["service_start_date"] = "2026-02-30"
        result = validate_invoice(values)
        self.assertFalse(result.valid)
        self.assertEqual({error.name for error in result.errors}, {"service_start_date"})

        values = valid_invoice()
        values["service_end_date"] = "2026-08-31"
        result = validate_invoice(values)
        self.assertFalse(result.valid)
        self.assertEqual({error.name for error in result.errors}, {"service_end_date"})

    def test_days_and_pay_require_nonnegative_two_decimal_values_within_limits(self):
        cases = (
            ("days_worked", "-1", "invalid_decimal"),
            ("days_worked", "1.001", "too_precise"),
            ("days_worked", str(MAX_DAYS_WORKED + 1), "out_of_range"),
            ("pay_per_day", "abc", "invalid_decimal"),
            ("pay_per_day", "1.001", "too_precise"),
            ("pay_per_day", str(MAX_PAY_PER_DAY + Decimal("0.01")), "out_of_range"),
        )
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                values = valid_invoice()
                values[field] = value
                result = validate_invoice(values)
                self.assertFalse(result.valid)
                self.assertIn(code, {error.code for error in result.errors if error.name == field})

    def test_currency_and_bank_boundaries(self):
        values = valid_invoice()
        values["currency"] = "USD"
        values["bank_name"] = "x" * 201
        values["swift_or_bic"] = "bad"
        result = validate_invoice(values)
        self.assertFalse(result.valid)
        self.assertEqual(
            {error.name for error in result.errors},
            {"currency", "bank_name", "swift_or_bic"},
        )

    def test_bank_fields_are_optional_individually(self):
        values = valid_invoice()
        values.pop("bank_name")
        values.pop("account_holder")
        values.pop("iban_or_account_number")
        values.pop("swift_or_bic")
        self.assertTrue(validate_invoice(values).valid)

    def test_invoice_number_is_required_and_normalized(self):
        values = valid_invoice()
        values["invoice_number"] = "  INV-2026-0002  "
        result = validate_invoice(values)
        self.assertTrue(result.valid)
        self.assertEqual(result.value.invoice_number, "INV-2026-0002")

        values.pop("invoice_number")
        result = validate_invoice(values)
        self.assertFalse(result.valid)
        self.assertIn("invoice_number", {error.name for error in result.errors})

    def test_missing_required_fields_do_not_echo_sensitive_values(self):
        result = validate_invoice({"bank_name": "TEST-SENSITIVE-BANK"})
        self.assertFalse(result.valid)
        self.assertNotIn("TEST-SENSITIVE-BANK", repr(result.errors))


class InvoiceCalculationTest(unittest.TestCase):
    def test_total_uses_decimal_arithmetic_and_half_up_rounding(self):
        values = valid_invoice()
        values["days_worked"] = "1.25"
        values["pay_per_day"] = "0.02"
        result = validate_invoice(values)
        self.assertTrue(result.valid)
        self.assertEqual(calculate_total(result.value), Decimal("0.03"))
        self.assertEqual(format_total(result.value), "0.03")
