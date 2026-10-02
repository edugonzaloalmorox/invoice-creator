#!/usr/bin/env python3
"""Run bounded synthetic load checks against an approved disposable service."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SYNTHETIC_INVOICE = {
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


def request_once(base_url: str, endpoint: str, timeout: float) -> tuple[int, float]:
    body = json.dumps(SYNTHETIC_INVOICE).encode()
    request = Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, (monotonic() - started) * 1000
    except HTTPError as error:
        error.read()
        return error.code, (monotonic() - started) * 1000
    except URLError:
        return 0, (monotonic() - started) * 1000


def run(base_url: str, endpoint: str, requests: int, concurrency: int, timeout: float) -> dict:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda _: request_once(base_url, endpoint, timeout), range(requests)))
    statuses: dict[str, int] = {}
    durations = []
    for status, duration in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
        durations.append(duration)
    return {
        "requests": requests,
        "concurrency": concurrency,
        "endpoint": endpoint,
        "statuses": statuses,
        "duration_ms": {
            "min": round(min(durations), 2) if durations else 0,
            "max": round(max(durations), 2) if durations else 0,
            "average": round(sum(durations) / len(durations), 2) if durations else 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--endpoint", choices=("preview", "generate"), default="preview")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.requests <= 1000 or not 1 <= args.concurrency <= args.requests:
        parser.error("requests must be 1..1000 and concurrency must be between 1 and requests")
    print(json.dumps(run(args.base_url, f"/api/invoices/{args.endpoint}", args.requests, args.concurrency, args.timeout), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
