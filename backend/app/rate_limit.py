"""Per-process request counter.

Each API process has its own counters. A second process, or a restart, starts
again at zero. This is not a shared firewall.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Sliding window keyed by client address and bucket name."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._hits.get(key, []) if now - stamp < window_seconds]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


def bucket_for(method: str, path: str) -> str | None:
    """Return the limit bucket for a heavy or upload route."""
    if method == "POST" and path == "/api/access":
        return "access"
    if method == "POST" and (path == "/api/jobs" or path.endswith("/connections/validate") or path.endswith("/connections/apply")):
        return "upload"
    if method == "POST" and path.endswith("/process"):
        return "heavy"
    if method == "GET" and ("/exports/" in path or path.endswith("/print.pdf") or "/pages/" in path or path.endswith("/connections.xlsx")):
        return "heavy"
    return None
