"""Small in-process metrics collector containing only aggregate safe data."""

from __future__ import annotations

from collections import Counter
from threading import Lock


KNOWN_PATHS = {
    "/api/health",
    "/api/ready",
    "/api/metrics",
    "/api/template/connect",
    "/api/template/fields",
    "/api/invoices/preview",
    "/api/invoices/generate",
}

KNOWN_EVENTS = {
    "provider_failure",
    "cleanup_failure",
    "rate_limited",
    "suspicious_volume",
}


class Metrics:
    """Thread-safe aggregate metrics with bounded endpoint cardinality."""

    def __init__(self):
        """Initialize empty aggregate counters and their synchronization lock."""

        self._lock = Lock()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._duration_ms: Counter[str] = Counter()
        self._events: Counter[str] = Counter()

    def record(self, path: str, status_code: str, duration_ms: float) -> None:
        """Record bounded request status and duration aggregates."""

        safe_path = path if path in KNOWN_PATHS else "other"
        safe_status = status_code if status_code in {"2", "3", "4", "5"} else "other"
        with self._lock:
            self._requests[(safe_path, safe_status)] += 1
            self._duration_ms[safe_path] += round(duration_ms)

    def record_event(self, event: str) -> None:
        """Record a bounded operational event without request or client data."""

        if event not in KNOWN_EVENTS:
            return
        with self._lock:
            self._events[event] += 1

    def snapshot(self) -> dict:
        """Return a stable, sanitized snapshot of all aggregate counters."""

        with self._lock:
            paths = sorted(KNOWN_PATHS | {"other"})
            requests = {
                path: {status: self._requests[(path, status)] for status in ("2", "3", "4", "5")}
                for path in paths
            }
            durations = dict(sorted(self._duration_ms.items()))
            events = {event: self._events[event] for event in sorted(KNOWN_EVENTS)}
        return {
            "requests_by_path_and_status": requests,
            "duration_ms_total_by_path": durations,
            "operational_events": events,
        }
