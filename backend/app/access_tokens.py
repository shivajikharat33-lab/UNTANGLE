"""In-memory demo gate. This is a shared passcode, not a user account."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time


def codes_match(provided: str, expected: str) -> bool:
    """Compare two codes without leaking which one is longer."""
    left = hashlib.sha256(provided.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


class AccessRegistry:
    """Session tokens kept in this process. They disappear when the process stops."""

    def __init__(self) -> None:
        self._expiry: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._expiry[token] = time.time() + ttl_seconds
        return token

    def valid(self, token: str) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            expiry = self._expiry.get(token)
            if expiry is None:
                return False
            if expiry < now:
                self._expiry.pop(token, None)
                return False
            return True
