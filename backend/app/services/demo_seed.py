"""Create one synthetic project when the public demo flag is on.

The files are drawn in memory. Customer drawings are not read.
"""

from __future__ import annotations

import logging
from io import BytesIO

import fitz
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import JobRow
from app.services.uploads import create_uploaded_job

logger = logging.getLogger("untangle.demo")


class BytesUpload:
    """The small file interface create_uploaded_job already reads."""

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def synthetic_pdf() -> bytes:
    """A one-page vector drawing with tags. It is not a customer P&ID."""
    document = fitz.open()
    page = document.new_page(width=420, height=240)
    page.draw_rect(fitz.Rect(20, 30, 120, 110), width=1.5)
    page.insert_text((36, 78), "T-101", fontsize=12)
    page.draw_circle(fitz.Point(280, 70), 18, width=1.2)
    page.insert_text((266, 74), "P-201", fontsize=10)
    page.draw_line((120, 70), (262, 70), width=1.5)
    payload = document.tobytes()
    document.close()
    return payload


def synthetic_workbook() -> bytes:
    """An IO list with the tag and description columns the checker recognizes."""
    book = Workbook()
    sheet = book.active
    sheet.title = "IO"
    sheet.append(["Tag", "Description"])
    sheet.append(["T-101", "Tank"])
    sheet.append(["P-201", "Pump"])
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


async def seed_demo(settings: Settings, engine: object) -> None:
    """Store the synthetic project once. An existing database is left alone."""
    with Session(engine) as session:
        existing = session.scalars(select(JobRow).limit(1)).first()
    if existing is not None:
        return
    session = Session(engine)
    try:
        job = await create_uploaded_job(
            settings=settings,
            session=session,
            pid_pdf=BytesUpload("synthetic-plant.pdf", synthetic_pdf()),
            io_list=BytesUpload("synthetic-io.xlsx", synthetic_workbook()),
            name="Synthetic demo plant",
        )
    finally:
        session.close()
    from app.services.io_list import validate_job

    validate_job(settings.upload_dir, job.id, None)
    if not settings.demo_seed_process:
        logger.info("seeded synthetic demo project %s without processing", job.id)
        return
    from app.services import pipeline as pipeline_service

    pipeline_service.begin_process(engine, settings.upload_dir, job.id, retry=False, force=False)
    pipeline_service.finish_process(
        engine,
        settings.upload_dir,
        job.id,
        settings.tag_fuzzy_threshold,
        settings.process_min_stroke,
        settings.signal_max_stroke,
        settings.snap_tolerance,
        settings.node_attach_tolerance,
        False,
        False,
        settings.cache_dir,
        "Read",
        settings.job_timeout_seconds,
    )
    logger.info("seeded synthetic demo project %s", job.id)
