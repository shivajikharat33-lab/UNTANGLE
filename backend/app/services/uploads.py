"""Store a P&ID PDF and an IO workbook, then record what Intake could read."""

from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.models import JobRow
from app.schemas.intake import IntakeSummary, SheetSummary, StoredFile
from app.schemas.job import Job
from app.schemas.stages import STAGE_ORDER, StageRecord
from app.services.bounded_parse import inspect_pdf, inspect_xlsx

logger = logging.getLogger("untangle.uploads")

CHUNK_BYTES = 64 * 1024
PDF_STORED_NAME = "original.pdf"
IO_STORED_NAME = "io_list.xlsx"

_SCANNED_WARNING = "This PDF looks scanned, so vector extraction will not be possible."
_MIXED_WARNING = (
    "This PDF mixes vector drawing commands and embedded images. "
    "Vector extraction may miss the pictured parts."
)


def _display_name(raw: str | None, fallback: str) -> str:
    """Keep a filename for display. Never use it as a path."""
    text = (raw or "").replace("\\", "/").replace("\x00", "")
    name = Path(text).name.strip()
    if name in {"", ".", ".."}:
        return fallback
    return name[:200]


def _suffix(raw: str | None) -> str:
    return Path(raw or "").suffix.lower()


async def _read_bounded(upload: UploadFile, max_bytes: int, field: str) -> bytes:
    """Read in chunks and stop once the file passes the size limit."""
    total = 0
    parts: list[bytes] = []
    while True:
        chunk = await upload.read(CHUNK_BYTES)
        if not chunk:
            break
        if total + len(chunk) > max_bytes:
            limit_mb = max(1, max_bytes // (1024 * 1024))
            raise AppError(
                413,
                "FILE_TOO_LARGE",
                f"That file is larger than the {limit_mb} MB limit. Nothing from it was stored.",
                {"field": field, "max_upload_mb": limit_mb},
            )
        total += len(chunk)
        parts.append(chunk)
    if total == 0:
        raise AppError(400, "FILE_EMPTY", "That file is empty.", {"field": field})
    return b"".join(parts)


def _require_type(filename: str | None, expected: str, field: str, label: str) -> None:
    if _suffix(filename) != expected:
        raise AppError(
            400,
            "WRONG_FILE_TYPE",
            f"The {label} must be a {expected} file.",
            {"field": field},
        )


def _require_magic(data: bytes, prefix: bytes, field: str, label: str) -> None:
    if not data.startswith(prefix):
        raise AppError(
            400,
            "WRONG_FILE_TYPE",
            f"That file is named like a {label}, but its contents are not one.",
            {"field": field},
        )


def _job_folder(upload_dir: str, job_id: str) -> Path:
    """A new folder named only with the generated id, inside the upload directory."""
    if not job_id.isalnum():
        raise AppError(500, "INTERNAL_ERROR", "The server could not create a project folder.")
    root = Path(upload_dir).resolve()
    folder = (root / job_id).resolve()
    if folder.parent != root:
        raise AppError(500, "INTERNAL_ERROR", "The server could not create a project folder.")
    return folder


def _discard(folder: Path) -> None:
    if folder.exists():
        shutil.rmtree(folder)


def _warnings_for(verdict: str) -> list[str]:
    if verdict == "SCANNED":
        return [_SCANNED_WARNING]
    if verdict == "MIXED":
        return [_MIXED_WARNING]
    return []


def _stored(name: str, original_name: str, data: bytes) -> StoredFile:
    if name not in {PDF_STORED_NAME, IO_STORED_NAME}:
        raise AppError(500, "INTERNAL_ERROR", "The server refused an unsafe file name.")
    return StoredFile(
        stored_name=name,  # type: ignore[arg-type]
        original_name=original_name,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
    )


async def create_uploaded_job(
    *,
    settings: Settings,
    session: Session,
    pid_pdf: UploadFile | None,
    io_list: UploadFile | None,
    name: str,
) -> Job:
    """Validate both files, store them under safe names, and record Intake."""
    if pid_pdf is None or io_list is None:
        missing = []
        if pid_pdf is None:
            missing.append("pid_pdf")
        if io_list is None:
            missing.append("io_list")
        raise AppError(
            400,
            "MISSING_FILE",
            "Choose both a P&ID PDF and an IO workbook (.xlsx).",
            {"fields": missing},
        )

    _require_type(pid_pdf.filename, ".pdf", "pid_pdf", "P&ID")
    _require_type(io_list.filename, ".xlsx", "io_list", "IO list")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    pdf_bytes = await _read_bounded(pid_pdf, max_bytes, "pid_pdf")
    io_bytes = await _read_bounded(io_list, max_bytes, "io_list")
    _require_magic(pdf_bytes, b"%PDF-", "pid_pdf", "PDF")
    _require_magic(io_bytes, b"PK", "io_list", "Excel workbook")

    started = datetime.now(timezone.utc)
    try:
        pdf_report = inspect_pdf(pdf_bytes, settings)
    except AppError as exc:
        details = dict(exc.details or {})
        details.setdefault("field", "pid_pdf")
        raise AppError(exc.status_code, exc.error_code, exc.message, details) from None
    except Exception as exc:
        logger.info("pdf intake failed (%s)", type(exc).__name__)
        raise AppError(
            400,
            "FILE_UNREADABLE",
            "The PDF could not be opened. It may be damaged.",
            {"field": "pid_pdf"},
        ) from None
    if pdf_report.page_count < 1 or pdf_report.verdict not in {"VECTOR", "SCANNED", "MIXED"}:
        raise AppError(
            400,
            "FILE_UNREADABLE",
            "The PDF opened, but it has no pages to read.",
            {"field": "pid_pdf"},
        )
    try:
        sheets = inspect_xlsx(io_bytes, settings)
    except AppError as exc:
        details = dict(exc.details or {})
        details.setdefault("field", "io_list")
        raise AppError(exc.status_code, exc.error_code, exc.message, details) from None
    except Exception as exc:
        logger.info("excel intake failed (%s)", type(exc).__name__)
        raise AppError(
            400,
            "FILE_UNREADABLE",
            "The Excel file could not be opened. It may be damaged.",
            {"field": "io_list"},
        ) from None

    job_id = uuid4().hex
    folder = _job_folder(settings.upload_dir, job_id)
    pdf_path = folder / PDF_STORED_NAME
    io_path = folder / IO_STORED_NAME
    try:
        folder.mkdir(parents=True, exist_ok=False)
        pdf_path.write_bytes(pdf_bytes)
        io_path.write_bytes(io_bytes)
    except OSError:
        _discard(folder)
        logger.info("files were not stored for job %s", job_id)
        raise AppError(500, "INTERNAL_ERROR", "The files could not be stored.") from None

    ended = datetime.now(timezone.utc)
    duration_ms = max(0, int((ended - started).total_seconds() * 1000))
    warnings = _warnings_for(pdf_report.verdict)
    pdf_meta = _stored(PDF_STORED_NAME, _display_name(pid_pdf.filename, "original.pdf"), pdf_bytes)
    io_meta = _stored(IO_STORED_NAME, _display_name(io_list.filename, "io_list.xlsx"), io_bytes)
    intake = IntakeSummary(
        pdf=pdf_meta,
        io_list=io_meta,
        page_count=pdf_report.page_count,
        verdict=pdf_report.verdict,  # type: ignore[arg-type]
        verdict_reason=pdf_report.reason,
        sheets=[
            SheetSummary(name=sheet.name, columns=sheet.columns, row_count=sheet.row_count)
            for sheet in sheets
        ],
        warnings=warnings,
    )
    stages = [
        StageRecord(
            name="Intake",
            status="done",
            started_at=started,
            ended_at=ended,
            duration_ms=duration_ms,
            warnings=warnings,
        )
    ]
    stages.extend(StageRecord(name=stage_name, status="pending") for stage_name in STAGE_ORDER[1:])

    row = JobRow(
        id=job_id,
        name=name.strip()[:200],
        status="uploaded",
        created_at=ended.isoformat(),
        pdf_sha256=pdf_meta.sha256,
        io_sha256=io_meta.sha256,
        pdf_original_name=pdf_meta.original_name,
        io_original_name=io_meta.original_name,
        intake_json=intake.model_dump(mode="json"),
        stages_json=[stage.model_dump(mode="json") for stage in stages],
    )
    try:
        session.add(row)
        session.commit()
    except Exception as exc:
        session.rollback()
        _discard(folder)
        logger.info("job row was not stored for %s (%s)", job_id, type(exc).__name__)
        raise AppError(500, "INTERNAL_ERROR", "The project could not be saved.") from None

    logger.info("created job %s", job_id)
    return job_from_row(row)


def job_from_row(row: JobRow) -> Job:
    """Build the API job. versions stays empty because there is no sketch yet."""
    return Job.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "created_at": row.created_at or None,
            "intake": row.intake_json,
            "stages": row.stages_json or [],
            "versions": [],
        }
    )
