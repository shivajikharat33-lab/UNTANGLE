"""Edit and history routes. Version 0 content is never replaced here."""

from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.errors import AppError
from app.schemas.job import Version
from app.services import edits

router = APIRouter()


def _engine(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "The database is not available.")
    return engine


@router.get("/api/jobs/{job_id}/versions")
def get_versions(job_id: str, request: Request) -> list[Version]:
    """List saved versions, creating version 0 from the sketch on the first call."""
    settings = request.app.state.settings
    return edits.list_versions(_engine(request), settings.upload_dir, job_id)


@router.post("/api/jobs/{job_id}/versions/accept")
def accept_original(job_id: str, request: Request) -> Version:
    """Mark version 0 accepted without changing its drawing."""
    settings = request.app.state.settings
    return edits.accept_original(_engine(request), settings.upload_dir, job_id)


@router.post("/api/jobs/{job_id}/draft")
def open_draft(job_id: str, request: Request) -> dict:
    """Start a working copy from version 0."""
    settings = request.app.state.settings
    return edits.start_modify(_engine(request), settings.upload_dir, job_id, settings.modify_enabled)


@router.get("/api/jobs/{job_id}/draft")
def read_draft(job_id: str, request: Request) -> dict:
    """Return the working copy."""
    settings = request.app.state.settings
    return edits.load_draft(settings.upload_dir, job_id)


@router.post("/api/jobs/{job_id}/draft/operations")
def post_operation(job_id: str, request: Request, body: dict = Body()) -> dict:
    """Apply one connection-list operation and redraw."""
    settings = request.app.state.settings
    return edits.apply_operation(_engine(request), settings.upload_dir, job_id, body, settings.modify_enabled)


@router.post("/api/jobs/{job_id}/draft/undo")
def post_undo(job_id: str, request: Request) -> dict:
    """Undo the last edit on the working copy."""
    settings = request.app.state.settings
    return edits.undo_draft(_engine(request), settings.upload_dir, job_id, settings.modify_enabled)


@router.post("/api/jobs/{job_id}/draft/redo")
def post_redo(job_id: str, request: Request) -> dict:
    """Redo an undone edit on the working copy."""
    settings = request.app.state.settings
    return edits.redo_draft(_engine(request), settings.upload_dir, job_id, settings.modify_enabled)


@router.post("/api/jobs/{job_id}/draft/save")
def post_save(job_id: str, request: Request, body: dict = Body(default={})) -> Version:
    """Save the working copy as the next version."""
    settings = request.app.state.settings
    return edits.save_draft(_engine(request), settings.upload_dir, job_id, str(body.get("note", "")), settings.modify_enabled)


@router.post("/api/jobs/{job_id}/versions/{number}/restore")
def post_restore(job_id: str, number: int, request: Request) -> Version:
    """Copy a saved version into a new version."""
    settings = request.app.state.settings
    return edits.restore_version(_engine(request), settings.upload_dir, job_id, number, settings.modify_enabled)


@router.get("/api/jobs/{job_id}/versions/compare")
def get_compare(job_id: str, request: Request, left: int = 0, right: int = 1) -> dict:
    """Diff two saved versions."""
    return edits.compare_versions(_engine(request), job_id, left, right)


@router.get("/api/jobs/{job_id}/connections.xlsx")
def download_connections(job_id: str, request: Request) -> Response:
    """Download the connection workbook."""
    settings = request.app.state.settings
    payload = edits.export_workbook(_engine(request), settings.upload_dir, job_id)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{job_id}-connections.xlsx"'},
    )


@router.post("/api/jobs/{job_id}/connections/validate")
async def validate_connections(job_id: str, request: Request, workbook: UploadFile = File(...)) -> dict:
    """Validate an edited workbook and return the diff. Nothing is saved."""
    settings = request.app.state.settings
    payload = await workbook.read()
    return edits.validate_workbook(settings.upload_dir, job_id, workbook.filename or "", payload, settings.max_upload_mb * 1024 * 1024)


@router.post("/api/jobs/{job_id}/connections/apply")
async def apply_connections(job_id: str, request: Request, workbook: UploadFile = File(...)) -> dict:
    """Apply a workbook that has no blocking errors."""
    settings = request.app.state.settings
    payload = await workbook.read()
    return edits.apply_workbook(
        _engine(request),
        settings.upload_dir,
        job_id,
        workbook.filename or "",
        payload,
        settings.max_upload_mb * 1024 * 1024,
        settings.modify_enabled,
    )


@router.get("/api/jobs/{job_id}/print.pdf")
def download_print(job_id: str, request: Request, page_size: str = "A4", orientation: str = "landscape") -> Response:
    """Download a vector print PDF with a title block and legend."""
    settings = request.app.state.settings
    payload = edits.print_pdf(settings.upload_dir, job_id, page_size=page_size, orientation=orientation)
    return Response(content=payload, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{job_id}-print.pdf"'})
