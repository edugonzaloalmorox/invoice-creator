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


class Metrics:
    """Thread-safe aggregate metrics with bounded endpoint cardinality."""

    def __init__(self):
        self._lock = Lock()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._duration_ms: Counter[str] = Counter()

    def record(self, path: str, status_code: str, duration_ms: float) -> None:
        safe_path = path if path in KNOWN_PATHS else "other"
        safe_status = status_code if status_code in {"2", "3", "4", "5"} else "other"
        with self._lock:
            self._requests[(safe_path, safe_status)] += 1
            self._duration_ms[safe_path] += round(duration_ms)

    def snapshot(self) -> dict:
        with self._lock:
            paths = sorted(KNOWN_PATHS | {"other"})
            requests = {
                path: {status: self._requests[(path, status)] for status in ("2", "3", "4", "5")}
                for path in paths
            }
            durations = dict(sorted(self._duration_ms.items()))
        return {"requests_by_path_and_status": requests, "duration_ms_total_by_path": durations}
