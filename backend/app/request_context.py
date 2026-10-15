"""Request id for logs. The HTTP middleware sets it."""

from __future__ import annotations

import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("untangle_request_id", default="")
