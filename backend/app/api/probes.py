"""Liveness and readiness. These responses do not include paths or file names."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.database import check_database
from pathlib import Path

router = APIRouter()


def _writable(folder: str) -> bool:
    try:
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def readiness(request: Request) -> JSONResponse:
    """Ready only when SQLite answers and the storage folders can be written."""
    settings = request.app.state.settings
    database_ok = check_database(request.app.state.engine) == "ok"
    storage_ok = _writable(settings.upload_dir) and _writable(settings.cache_dir)
    if database_ok and storage_ok:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready"})


@router.get("/health")
def liveness() -> dict[str, str]:
    """The process is up. This does not check the database."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    return readiness(request)


@router.get("/api/ready")
def api_ready(request: Request) -> JSONResponse:
    """Same check as /ready, for callers that prefix every route with /api."""
    return readiness(request)
