"""Upload, list, and read projects."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, text

from app.config import Settings
from app.database import init_db, make_engine
from app.main import create_app
from app.models import JobRow, VersionRow
from app.schemas.errors import ErrorResponse
from app.schemas.stages import STAGE_ORDER
from sqlalchemy.orm import Session


def settings_for(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite:///" + (tmp_path / "untangle.db").as_posix(),
        "upload_dir": str(tmp_path / "uploads"),
        "max_upload_mb": 1,
        "frontend_origin": "http://127.0.0.1:5173",
    }
    values.update(overrides)
    return Settings(**values)


def pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.draw_line((10, 10), (80, 10))
    payload = document.tobytes()
    document.close()
    return payload


def workbook_bytes() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "IO"
    sheet.append(["Tag", "Description"])
    sheet.append(["FT-101", "Flow transmitter"])
    extra = book.create_sheet("Notes")
    extra.append(["Note"])
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def post_pair(
    client: TestClient,
    *,
    pdf: bytes | None = None,
    workbook: bytes | None = None,
    pdf_name: str = "drawing.pdf",
    workbook_name: str = "io.xlsx",
    name: str | None = "Feed water",
    include_pdf: bool = True,
    include_workbook: bool = True,
):
    files = {}
    if include_pdf:
        files["pid_pdf"] = (pdf_name, pdf if pdf is not None else pdf_bytes(), "application/pdf")
    if include_workbook:
        files["io_list"] = (
            workbook_name,
            workbook if workbook is not None else workbook_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    data = {} if name is None else {"name": name}
    return client.post("/api/jobs", files=files, data=data)


def assert_error(response, code: str) -> ErrorResponse:
    assert response.status_code >= 400
    body = response.json()
    parsed = ErrorResponse.model_validate(body)
    assert parsed.error_code == code
    assert parsed.message
    assert parsed.request_id == response.headers["X-Request-ID"]
    return parsed


def stored_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "uploads"
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def test_valid_upload_stores_safe_names_and_intake(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    drawing = pdf_bytes()
    workbook = workbook_bytes()
    with TestClient(application) as client:
        response = post_pair(
            client,
            pdf=drawing,
            workbook=workbook,
            pdf_name="../../x.pdf",
            workbook_name="..\\..\\io.xlsx",
            name="Feed water",
        )
        assert response.status_code == 201
        body = response.json()
        job_id = body["id"]
        listed = client.get("/api/jobs")
        detail = client.get(f"/api/jobs/{job_id}")

    assert body["status"] == "uploaded"
    assert body["name"] == "Feed water"
    assert body["versions"] == []
    assert body["intake"]["pdf"]["stored_name"] == "original.pdf"
    assert body["intake"]["pdf"]["original_name"] == "x.pdf"
    assert body["intake"]["pdf"]["sha256"] == hashlib.sha256(drawing).hexdigest()
    assert body["intake"]["io_list"]["stored_name"] == "io_list.xlsx"
    assert body["intake"]["io_list"]["original_name"] == "io.xlsx"
    assert body["intake"]["io_list"]["sha256"] == hashlib.sha256(workbook).hexdigest()
    assert ".." not in body["intake"]["pdf"]["original_name"]
    assert body["intake"]["page_count"] == 1
    assert body["intake"]["verdict"] == "VECTOR"
    assert body["intake"]["verdict_reason"]
    assert body["intake"]["sheets"][0]["name"] == "IO"
    assert body["intake"]["sheets"][0]["columns"] == ["Tag", "Description"]
    assert body["intake"]["sheets"][0]["row_count"] == 2
    assert [stage["name"] for stage in body["stages"]] == list(STAGE_ORDER)
    assert body["stages"][0]["status"] == "done"
    assert body["stages"][0]["started_at"]
    assert body["stages"][0]["ended_at"]
    assert body["stages"][0]["duration_ms"] >= 0
    assert all(stage["status"] == "pending" for stage in body["stages"][1:])
    assert "sample_text" not in body["intake"]

    folder = tmp_path / "uploads" / job_id
    assert (folder / "original.pdf").read_bytes() == drawing
    assert (folder / "io_list.xlsx").read_bytes() == workbook
    assert all(path.parent == folder and path.name in {"original.pdf", "io_list.xlsx"} for path in stored_files(tmp_path))
    assert not (tmp_path / "x.pdf").exists()
    assert not (tmp_path / "uploads" / "x.pdf").exists()

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id
    assert listed.json()[0]["pdf_verdict"] == "VECTOR"
    assert listed.json()[0]["page_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["intake"]["page_count"] == 1

    engine = make_engine(settings_for(tmp_path).database_url)
    with Session(engine) as session:
        assert session.get(VersionRow, job_id) is None
        versions = session.query(VersionRow).count()
        job = session.get(JobRow, job_id)
    engine.dispose()
    assert versions == 0
    assert job is not None
    assert job.pdf_sha256 == hashlib.sha256(drawing).hexdigest()


def scanned_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 24, 16), 0)
    pixmap.clear_with(80)
    page.insert_image(page.rect, pixmap=pixmap)
    payload = document.tobytes()
    document.close()
    return payload


def test_scanned_pdf_records_a_warning(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, pdf=scanned_pdf_bytes())
    assert response.status_code == 201
    body = response.json()
    assert body["intake"]["verdict"] == "SCANNED"
    assert body["intake"]["warnings"]
    assert "vector extraction will not be possible" in body["intake"]["warnings"][0]
    assert body["stages"][0]["warnings"] == body["intake"]["warnings"]


def test_list_is_newest_first(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        first = post_pair(client, name="First")
        second = post_pair(client, name="Second")
        listed = client.get("/api/jobs")
    assert first.status_code == 201
    assert second.status_code == 201
    names = [item["name"] for item in listed.json()]
    assert names == ["Second", "First"]


def test_wrong_extension_is_rejected(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, pdf_name="drawing.txt")
    assert_error(response, "WRONG_FILE_TYPE")
    assert stored_files(tmp_path) == []


def test_wrong_magic_bytes_are_rejected(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        pdf_response = post_pair(client, pdf=b"this is not a pdf")
        workbook_response = post_pair(client, workbook=b"this is not a workbook")
    assert_error(pdf_response, "WRONG_FILE_TYPE")
    assert_error(workbook_response, "WRONG_FILE_TYPE")
    assert stored_files(tmp_path) == []


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, pdf=b"")
    assert_error(response, "FILE_EMPTY")
    assert stored_files(tmp_path) == []


def test_oversize_file_leaves_nothing_behind(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    too_big = b"%PDF-" + (b"0" * (1024 * 1024))
    with TestClient(application) as client:
        response = post_pair(client, pdf=too_big)
    assert_error(response, "FILE_TOO_LARGE")
    assert stored_files(tmp_path) == []
    engine = make_engine(settings_for(tmp_path).database_url)
    with Session(engine) as session:
        count = session.query(JobRow).count()
    engine.dispose()
    assert count == 0


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, include_pdf=False)
    parsed = assert_error(response, "MISSING_FILE")
    assert parsed.details is not None
    assert "pid_pdf" in parsed.details["fields"]
    assert stored_files(tmp_path) == []


def test_corrupt_pdf_leaves_no_job(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, pdf=b"%PDF-1.4\nnot a pdf")
    assert_error(response, "FILE_UNREADABLE")
    assert stored_files(tmp_path) == []
    engine = make_engine(settings_for(tmp_path).database_url)
    with Session(engine) as session:
        count = session.query(JobRow).count()
    engine.dispose()
    assert count == 0


def test_corrupt_workbook_leaves_no_job(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, workbook=b"PK\x03\x04this is not a workbook")
    assert_error(response, "FILE_UNREADABLE")
    assert stored_files(tmp_path) == []


def test_unknown_job_uses_the_standard_error(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = client.get("/api/jobs/missing-project")
    parsed = assert_error(response, "NOT_FOUND")
    assert response.status_code == 404
    assert "project" in parsed.message.lower()
    assert parsed.details is not None
    assert parsed.details["path"] == "/api/jobs/missing-project"


def test_upload_limit_is_separate_from_health(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path, max_upload_mb=2))
    with TestClient(application) as client:
        health = client.get("/api/health")
        config = client.get("/api/config")
    assert set(health.json()) == {"status", "version", "database", "time"}
    assert config.status_code == 200
    assert config.json() == {"max_upload_mb": 2}


def test_old_jobs_table_gains_upload_columns(tmp_path: Path) -> None:
    database = tmp_path / "untangle.db"
    engine = create_engine("sqlite:///" + database.as_posix())
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE jobs (id VARCHAR PRIMARY KEY)"))
    engine.dispose()

    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        response = post_pair(client, name="Migrated")
    assert response.status_code == 201

    check = make_engine("sqlite:///" + database.as_posix())
    init_db(check)
    with check.connect() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(jobs)")).fetchall()}
    check.dispose()
    assert {"name", "status", "created_at", "pdf_sha256", "intake_json", "stages_json"} <= columns
