"""Run PDF and workbook inspection in a child process.

A timeout kills that child. The API process keeps running. The child is not
used for the later drawing stages; those still run in this process and stop
at the next stage boundary when the job clock runs out.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.errors import AppError
from app.services.excel_intake import SheetFacts

logger = logging.getLogger("untangle.inspect")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PdfFacts:
    """The intake fields the upload route stores."""

    page_count: int
    verdict: str
    reason: str


def _unlink(path: Path) -> None:
    for _ in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.05)


def _run(kind: str, data: bytes, settings: Settings) -> dict[str, object]:
    scratch = Path(settings.upload_dir) / "_inspect"
    scratch.mkdir(parents=True, exist_ok=True)
    suffix = ".pdf" if kind == "pdf" else ".xlsx"
    handle = tempfile.NamedTemporaryFile(dir=scratch, suffix=suffix, delete=False)
    path = Path(handle.name)
    try:
        handle.write(data)
        handle.close()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONWARNINGS"] = "ignore"
        command = [
            sys.executable,
            "-m",
            "app.services.inspect_worker",
            kind,
            str(path),
            str(settings.max_pdf_pages),
            str(settings.zip_max_uncompressed_bytes),
            str(settings.zip_max_entries),
        ]
        kwargs: dict[str, object] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.inspect_timeout_seconds,
                cwd=str(_BACKEND_ROOT),
                env=env,
                check=False,
                **kwargs,
            )
        except subprocess.TimeoutExpired:
            logger.info("inspect child timed out for %s", kind)
            raise AppError(
                400,
                "FILE_TIMEOUT",
                "That file took too long to inspect. Nothing was stored.",
            ) from None
    finally:
        _unlink(path)
    if completed.returncode != 0 or not completed.stdout.strip():
        logger.info("inspect child failed for %s exit=%s", kind, completed.returncode)
        raise AppError(400, "FILE_UNREADABLE", "The file could not be opened. It may be damaged.")
    text = completed.stdout.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.info("inspect child returned unreadable output for %s", kind)
        raise AppError(400, "FILE_UNREADABLE", "The file could not be opened. It may be damaged.") from None
    if not isinstance(payload, dict):
        raise AppError(400, "FILE_UNREADABLE", "The file could not be opened. It may be damaged.")
    if not payload.get("ok"):
        code = str(payload.get("error_code") or "FILE_UNREADABLE")
        message = str(payload.get("message") or "The file could not be opened. It may be damaged.")
        status = 400
        raise AppError(status, code, message)
    return payload


def inspect_pdf(data: bytes, settings: Settings) -> PdfFacts:
    """Classify PDF bytes without doing that work inside the API process."""
    payload = _run("pdf", data, settings)
    facts = payload.get("pdf")
    if not isinstance(facts, dict):
        raise AppError(400, "FILE_UNREADABLE", "The PDF could not be opened. It may be damaged.")
    return PdfFacts(
        page_count=int(facts["page_count"]),
        verdict=str(facts["verdict"]),
        reason=str(facts["reason"]),
    )


def inspect_xlsx(data: bytes, settings: Settings) -> list[SheetFacts]:
    """Read workbook sheet names after the archive limits pass."""
    payload = _run("xlsx", data, settings)
    sheets = payload.get("sheets")
    if not isinstance(sheets, list):
        raise AppError(400, "FILE_UNREADABLE", "The Excel file could not be opened. It may be damaged.")
    found: list[SheetFacts] = []
    for item in sheets:
        if not isinstance(item, dict):
            continue
        columns = item.get("columns")
        found.append(
            SheetFacts(
                name=str(item.get("name") or ""),
                columns=[str(column) for column in columns] if isinstance(columns, list) else [],
                row_count=int(item.get("row_count") or 0),
            )
        )
    return found
