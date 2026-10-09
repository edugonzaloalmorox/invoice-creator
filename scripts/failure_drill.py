#!/usr/bin/env python3
"""Run a sanitized local failure drill against the fixture provider."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import load_config
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider


CONFIG = {
    "INVOICE_ENVIRONMENT": "test",
    "INVOICE_FRONTEND_ORIGIN": "http://localhost:3000",
    "GOOGLE_CREDENTIALS_REFERENCE": "fixture://failure-drill",
    "GOOGLE_TEMPLATE_ID": "fixture-template",
    "INVOICE_MAX_REQUEST_BYTES": "1048576",
    "INVOICE_MAX_RESPONSE_BYTES": "5242880",
    "GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS": "3",
    "GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS": "10",
}

INVOICE = {
    "service_start_date": "2026-09-01",
    "service_end_date": "2026-09-05",
    "days_worked": "5",
    "pay_per_day": "240.00",
    "currency": "EUR",
    "bank_name": "TEST-BANK",
    "account_holder": "TEST-ACCOUNT-HOLDER",
    "iban_or_account_number": "TEST-IBAN-0001",
    "swift_or_bic": "TESTBIC1",
}


def call(app, path: str, body: bytes = b"") -> str:
    """Call one local WSGI endpoint and return only its HTTP status."""

    captured: dict[str, str] = {}

    def start_response(status, _headers):
        """Capture the WSGI status for the drill assertion."""

        captured["status"] = status

    app(
        {
            "REQUEST_METHOD": "POST" if body else "GET",
            "PATH_INFO": path,
            "CONTENT_TYPE": "application/json" if body else "",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": BytesIO(body),
        },
        start_response,
    )
    return captured["status"]


def main() -> int:
    """Run the failure, cleanup, metrics, and recovery checks."""

    config = load_config(CONFIG).config
    failing_provider = FixtureDocumentProvider(failures={"export_pdf": "timeout"})
    failing_app = create_app(config, failing_provider)

    detected_status = call(failing_app, "/api/invoices/generate", json.dumps(INVOICE).encode())
    metrics_status = call(failing_app, "/api/metrics")
    drill_metrics = failing_app.metrics.snapshot()
    operations = [operation for operation, _ in failing_provider.calls]
    if detected_status != "504 Gateway Timeout" or metrics_status != "200 OK":
        raise RuntimeError("failure drill did not detect the expected provider timeout")
    if operations[-1] != "delete_document" or drill_metrics["operational_events"]["provider_failure"] != 1:
        raise RuntimeError("failure drill did not verify temporary-copy cleanup")

    recovery_app = create_app(config, FixtureDocumentProvider())
    recovery_status = call(recovery_app, "/api/ready")
    if recovery_status != "200 OK":
        raise RuntimeError("failure drill recovery readiness check failed")

    print(
        json.dumps(
            {
                "scenario": "fixture_provider_export_timeout",
                "detection": {"status": detected_status, "metrics_status": metrics_status},
                "escalation": {"owner": "ROLE_SERVICE_OWNER", "status": "recorded"},
                "mitigation": {"temporary_copy_cleanup": "verified", "provider_failure_events": 1},
                "recovery": {"readiness_status": recovery_status},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
