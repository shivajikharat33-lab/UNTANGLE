"""JSON logs for the untangle logger. File bytes and secrets are not written."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.request_context import request_id_var


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(""),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    """Attach one JSON handler. Repeat calls do not stack handlers."""
    log = logging.getLogger("untangle")
    log.setLevel(level.upper())
    if any(getattr(handler, "_untangle_json", False) for handler in log.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler._untangle_json = True  # type: ignore[attr-defined]
    log.addHandler(handler)
    log.propagate = False
