"""Create a project from two files, and read it back."""

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import JobRow
from app.schemas.intake import JobListItem, PublicConfig
from app.schemas.job import Job
from app.services.uploads import create_uploaded_job, job_from_row

router = APIRouter()


def _engine_or_error(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "The database is not available.")
    return engine


@router.get("/api/config")
def public_config(request: Request) -> PublicConfig:
    """The upload size limit. Health stays a separate check."""
    settings = request.app.state.settings
    return PublicConfig(max_upload_mb=settings.max_upload_mb)


@router.post("/api/jobs")
async def create_job(
    request: Request,
    pid_pdf: UploadFile | None = File(default=None),
    io_list: UploadFile | None = File(default=None),
    name: str = Form(default=""),
) -> JSONResponse:
    """Store one PDF and one xlsx workbook and record Intake."""
    settings = request.app.state.settings
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        job = await create_uploaded_job(
            settings=settings,
            session=session,
            pid_pdf=pid_pdf,
            io_list=io_list,
            name=name,
        )
    finally:
        session.close()
    return JSONResponse(status_code=201, content=job.model_dump(mode="json"))


@router.get("/api/jobs")
def list_jobs(request: Request) -> list[JobListItem]:
    """Newest project first. The list does not include file contents."""
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        rows = session.scalars(select(JobRow).order_by(JobRow.created_at.desc(), JobRow.id.desc())).all()
        items: list[JobListItem] = []
        for row in rows:
            job = job_from_row(row)
            if job.intake is None or job.created_at is None:
                continue
            items.append(
                JobListItem(
                    id=job.id,
                    name=job.name,
                    created_at=job.created_at.isoformat(),
                    status="uploaded",
                    pdf_verdict=job.intake.verdict,
                    page_count=job.intake.page_count,
                )
            )
        return items
    finally:
        session.close()


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> Job:
    """Full project, including Intake and the stage list."""
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
    finally:
        session.close()
    if row is None:
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    return job_from_row(row)
