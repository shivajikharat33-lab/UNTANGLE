"""Download header values. User-supplied names are reduced to a safe display name."""

from __future__ import annotations

import re
from pathlib import Path


def attachment_disposition(filename: str) -> str:
    """Content-Disposition for a download. The name cannot be a path."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    if not cleaned:
        cleaned = "download"
    return f'attachment; filename="{cleaned[:180]}"'
