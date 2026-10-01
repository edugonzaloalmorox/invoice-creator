"""Sanitized structure fixture covering every supported document section."""

SANITIZED_TEMPLATE = {
    "template_id": "fixture-template",
    "version": "2026-01",
    "sections": {
        "body": [
            {"location": "body:paragraph:4", "text": "Days worked: {{days_worked}}"},
            {"location": "body:paragraph:5", "text": "Pay per day: {{pay_per_day}}"},
            {"location": "body:paragraph:6", "text": "Account holder: {{account_holder}}"},
            {"location": "body:paragraph:7", "text": "Account: {{iban_or_account_number}}"},
            {"location": "body:paragraph:8/split-run:1", "text": "SWIFT/BIC: {{swift_or_bic}}"},
        ],
        "table": [
            {"location": "table:0/row:1/cell:1", "text": "Start: {{service_start_date}}"},
            {"location": "table:0/row:2/cell:1", "text": "End: {{service_end_date}}"},
            {"location": "table:1/row:3/cell:1", "text": "Total: {{total_amount}}"},
        ],
        "header": [{"location": "header:paragraph:1", "text": "Currency: {{currency}}"}],
        "footer": [{"location": "footer:paragraph:1", "text": "Bank: {{bank_name}}"}],
    },
}
