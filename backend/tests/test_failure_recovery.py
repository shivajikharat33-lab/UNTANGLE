"""Bad files and a stopped pipeline end in a clear failed state."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import create_app
from app.services import detect, pdf_extract
from tests.test_jobs import pdf_bytes, post_pair, settings_for, workbook_bytes


def _io(rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "IO"
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def test_missing_columns_and_duplicate_tags_do_not_hang(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        created = post_pair(client, workbook=_io([["Foo", "Bar"], ["x", "y"]]))
        job_id = created.json()["id"]
        started = client.post(f"/api/jobs/{job_id}/process")
        finished = client.get(f"/api/jobs/{job_id}")
        missing = client.post(f"/api/jobs/{job_id}/io-list/validate", json={})
        duplicate_job = post_pair(
            client,
            workbook=_io([["Tag", "Description"], ["FT-101", "Flow"], ["FT-101", "Flow again"]]),
        )
        duplicate_id = duplicate_job.json()["id"]
        duplicate = client.post(f"/api/jobs/{duplicate_id}/io-list/validate", json={})
    assert created.status_code == 201
    assert missing.status_code == 200
    assert missing.json()["status"] == "needs_columns"
    assert started.status_code == 202
    stages = {stage["name"]: stage["status"] for stage in finished.json()["stages"]}
    assert "running" not in stages.values()
    assert stages["MatchTags"] == "failed"
    assert "Traceback" not in finished.text
    assert duplicate.status_code == 200
    assert "duplicated" in duplicate.text.lower()


def test_mid_pipeline_exception_marks_failed(tmp_path: Path, monkeypatch) -> None:
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret-boom")

    monkeypatch.setattr(detect, "build_detections", explode)
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        created = post_pair(client, pdf=pdf_bytes(), workbook=_io([["Tag", "Description"], ["FT-101", "Flow"]]))
        job_id = created.json()["id"]
        checked = client.post(f"/api/jobs/{job_id}/io-list/validate", json={})
        started = client.post(f"/api/jobs/{job_id}/process")
        finished = client.get(f"/api/jobs/{job_id}")
    assert checked.status_code == 200
    assert started.status_code == 202
    detect_stage = next(stage for stage in finished.json()["stages"] if stage["name"] == "Detect")
    assert detect_stage["status"] == "failed"
    assert "secret-boom" not in finished.text
    assert "Traceback" not in finished.text
    assert "kept" in (detect_stage["error"] or "").lower() or "could not" in (detect_stage["error"] or "").lower()


def test_timeout_ends_the_job(tmp_path: Path, monkeypatch) -> None:
    real = pdf_extract.extract_pdf

    def slow(path: Path):
        time.sleep(1.4)
        return real(path)

    monkeypatch.setattr(pdf_extract, "extract_pdf", slow)
    application = create_app(settings_for(tmp_path, job_timeout_seconds=1))
    with TestClient(application) as client:
        created = post_pair(client)
        job_id = created.json()["id"]
        started = client.post(f"/api/jobs/{job_id}/process")
        finished = client.get(f"/api/jobs/{job_id}")
    assert started.status_code == 202
    read = next(stage for stage in finished.json()["stages"] if stage["name"] == "Read")
    assert read["status"] == "failed"
    assert "timed out" in (read["error"] or "").lower()
    assert all(stage["status"] != "running" for stage in finished.json()["stages"])


def test_retry_after_a_failed_read(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}
    real = pdf_extract.extract_pdf

    def flaky(path: Path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("once")
        return real(path)

    monkeypatch.setattr(pdf_extract, "extract_pdf", flaky)
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        created = post_pair(client, workbook=workbook_bytes())
        job_id = created.json()["id"]
        client.post(f"/api/jobs/{job_id}/process")
        failed = client.get(f"/api/jobs/{job_id}")
        missing = client.post(f"/api/jobs/{job_id}/cancel")
        retried = client.post(f"/api/jobs/{job_id}/process?retry=true")
        done = client.get(f"/api/jobs/{job_id}")
    assert next(stage["status"] for stage in failed.json()["stages"] if stage["name"] == "Read") == "failed"
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "NOT_FOUND"
    assert retried.status_code == 202
    assert next(stage["status"] for stage in done.json()["stages"] if stage["name"] == "Read") == "done"


def test_scanned_page_without_ocr_build_does_not_invent_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.pdf_raster.ocr_in_this_build", lambda: False)
    document = fitz.open()
    page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 24, 16), 0)
    pixmap.clear_with(80)
    page.insert_image(page.rect, pixmap=pixmap)
    path = tmp_path / "scan.pdf"
    document.save(path)
    document.close()
    result = pdf_extract.extract_pdf(path)
    assert result.status == "ocr_unavailable"
    assert result.summary.words == 0
    assert "not available in this build" in result.message
    assert "Tesseract" not in result.message
