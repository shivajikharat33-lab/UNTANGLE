"""API scaffold: health, errors, and the SQLite tables."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import APP_VERSION, Settings
from app.database import init_db, make_engine
from app.main import create_app
from app.models import JobRow, VersionRow
from app.schemas.errors import ErrorResponse


def settings_for(tmp_path: Path, database_url: str | None = None) -> Settings:
    url = database_url or ("sqlite:///" + (tmp_path / "untangle.db").as_posix())
    return Settings(
        database_url=url,
        upload_dir=str(tmp_path / "uploads"),
        max_upload_mb=50,
        frontend_origin="http://127.0.0.1:5173",
    )


def test_health_returns_ok_and_a_request_id(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        first = client.get("/api/health")
        second = client.get("/api/health")

    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"status", "version", "database", "time"}
    assert body["status"] == "ok"
    assert body["version"] == APP_VERSION
    assert body["database"] == "ok"
    parsed = datetime.fromisoformat(body["time"])
    assert parsed.tzinfo is not None

    header = first.headers["X-Request-ID"]
    UUID(header)
    assert second.headers["X-Request-ID"] != header


def test_database_tables_are_created_at_startup(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    application = create_app(settings)
    with TestClient(application) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"

    engine = make_engine(settings.database_url)
    with engine.connect() as connection:
        names = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')")
            ).scalars()
        )
    engine.dispose()
    assert {"jobs", "versions", "versions_reject_update_of_original"} <= names


def test_unknown_route_uses_the_error_schema(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error_code", "message", "details", "request_id"}
    parsed = ErrorResponse.model_validate(body)
    assert parsed.error_code == "NOT_FOUND"
    assert parsed.details is not None
    assert parsed.details["path"] == "/api/does-not-exist"
    assert parsed.request_id == response.headers["X-Request-ID"]


def test_validation_error_uses_the_error_schema(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))

    class Probe(BaseModel):
        name: str = Field(min_length=1)

    @application.post("/api/_probe")
    def probe(body: Probe) -> dict[str, str]:
        return {"name": body.name}

    with TestClient(application) as client:
        response = client.post("/api/_probe", json={})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error_code", "message", "details", "request_id"}
    parsed = ErrorResponse.model_validate(body)
    assert parsed.error_code == "VALIDATION_ERROR"
    assert parsed.details is not None
    assert parsed.details["errors"]
    assert parsed.request_id == response.headers["X-Request-ID"]


def test_unexpected_error_uses_the_error_schema(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))

    @application.get("/api/_boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("disk failed")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/_boom")

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error_code", "message", "details", "request_id"}
    parsed = ErrorResponse.model_validate(body)
    assert parsed.error_code == "INTERNAL_ERROR"
    assert parsed.details is None
    assert "disk failed" not in parsed.message
    assert parsed.request_id == response.headers["X-Request-ID"]


def test_broken_database_url_reports_failed_without_crashing(tmp_path: Path) -> None:
    missing = tmp_path / "missing-folder" / "untangle.db"
    application = create_app(
        settings_for(tmp_path, database_url="sqlite:///" + missing.as_posix())
    )
    with TestClient(application) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "failed"
    assert missing.exists() is False


def test_version_zero_is_never_overwritten(tmp_path: Path) -> None:
    engine = make_engine("sqlite:///" + (tmp_path / "guard.db").as_posix())
    init_db(engine)
    original_svg = "<svg id='original'/>"
    with Session(engine) as session:
        session.add(JobRow(id="job-1"))
        session.add(
            VersionRow(
                id="ver-0",
                job_id="job-1",
                number=0,
                parent=None,
                status="auto",
                connection_list_snapshot=[],
                svg=original_svg,
                verification=None,
                change_log=[],
            )
        )
        session.commit()

    with pytest.raises(SQLAlchemyError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE versions SET svg = :svg WHERE number = 0"),
                {"svg": "<svg id='changed'/>"},
            )

    with engine.connect() as connection:
        stored = connection.execute(text("SELECT svg FROM versions WHERE id = 'ver-0'")).scalar_one()
    assert stored == original_svg

    with pytest.raises(SQLAlchemyError):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM versions WHERE number = 0"))

    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM versions")).scalar_one()
    assert count == 1
    engine.dispose()
