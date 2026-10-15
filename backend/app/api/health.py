"""GET /api/health. This is the only product route in this step."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import APP_VERSION
from app.database import check_database
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report that the process is up and whether SQLite accepted a query."""
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        database=check_database(request.app.state.engine),
        time=datetime.now(timezone.utc),
    )
