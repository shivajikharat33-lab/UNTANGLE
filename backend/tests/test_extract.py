"""PDF extraction and the Read stage."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import pdf_extract
from app.services.pdf_extract import extract_pdf
from tests.test_jobs import post_pair, scanned_pdf_bytes, settings_for, workbook_bytes


def _known_vector_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=100)
    page.insert_text((10, 30), "PT-101", fontsize=12)
    page.draw_line((10, 40), (90, 40), width=1)
    page.draw_line((90, 40), (150, 40), width=1)
    page.draw_rect(fitz.Rect(20, 50, 40, 70), width=0.5)
    page.draw_circle(fitz.Point(100, 60), 8, width=0.6)
    page.draw_line((5, 5), (6, 5), width=0.4)
    payload = document.tobytes()
    document.close()
    return payload


def _rotated_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=100)
    page.draw_line((10, 40), (90, 40), width=1)
    page.set_rotation(90)
    payload = document.tobytes()
    document.close()
    return payload


def _ten_page_pdf() -> bytes:
    document = fitz.open()
    for index in range(10):
        page = document.new_page(width=120, height=80)
        page.draw_line((10, 10 + index), (50, 10 + index), width=1)
    payload = document.tobytes()
    document.close()
    return payload


def _write(tmp_path: Path, payload: bytes) -> Path:
    path = tmp_path / "drawing.pdf"
    path.write_bytes(payload)
    return path


def test_vector_pdf_counts_and_keeps_short_lines(tmp_path: Path) -> None:
    result = extract_pdf(_write(tmp_path, _known_vector_pdf()))
    page = result.pages[0]
    assert result.status == "ok"
    assert result.summary.words == 1
    assert page.words[0].text == "PT-101"
    assert result.summary.lines == 3
    assert result.summary.polylines == 2
    assert result.summary.shapes == 1
    assert result.summary.circles == 1
    assert result.summary.unused_primitives == 0
    assert result.summary.primitives_read == result.summary.primitives_used
    merged = next(item for item in page.polylines if item.segment_count == 2)
    flat = [round(value, 3) for point in merged.points for value in point]
    assert flat[0:2] == [10.0, 40.0] or flat[-2:] == [10.0, 40.0]
    assert [150.0, 40.0] in [[round(point[0], 3), round(point[1], 3)] for point in merged.points]
    short = next(item for item in page.polylines if item.segment_count == 1)
    assert short.points[0] != short.points[1]


def test_rotated_page_uses_displayed_coordinates(tmp_path: Path) -> None:
    path = _write(tmp_path, _rotated_pdf())
    document = fitz.open(path)
    page = document[0]
    expected_start = fitz.Point(10, 40) * page.rotation_matrix
    expected_end = fitz.Point(90, 40) * page.rotation_matrix
    width = float(page.rect.width)
    height = float(page.rect.height)
    document.close()

    result = extract_pdf(path)
    extracted = result.pages[0]
    assert extracted.rotation == 90
    assert extracted.width == width
    assert extracted.height == height
    assert extracted.width == 100
    assert extracted.height == 200
    points = extracted.polylines[0].points
    assert points[0] == [expected_start.x, expected_start.y]
    assert points[1] == [expected_end.x, expected_end.y]
    assert points[0][0] == points[1][0]
    assert abs(points[0][1] - points[1][1]) == 80


def test_image_only_pdf_is_not_a_fake_extraction(tmp_path: Path) -> None:
    result = extract_pdf(_write(tmp_path, scanned_pdf_bytes()))
    assert result.pages[0].reader == "raster"
    assert result.status in {"ocr_unavailable", "ok"}
    assert all(word.source == "raster" for page in result.pages for word in page.words)
    if result.status == "ocr_unavailable":
        assert result.summary.words == 0
        assert "Tesseract" in result.message


def test_ten_pages_are_read(tmp_path: Path) -> None:
    result = extract_pdf(_write(tmp_path, _ten_page_pdf()))
    assert result.meta.page_count == 10
    assert len(result.pages) == 10
    assert result.summary.lines == 10
    assert result.meta.duration_ms >= 0
    assert result.meta.coordinate_system


def _client(tmp_path: Path, pdf: bytes) -> tuple[TestClient, str, Path]:
    application = create_app(settings_for(tmp_path))
    client = TestClient(application)
    client.__enter__()
    created = post_pair(client, pdf=pdf, workbook=workbook_bytes())
    assert created.status_code == 201
    job_id = created.json()["id"]
    return client, job_id, tmp_path / "uploads" / job_id


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_process_persists_read_and_keeps_originals(tmp_path: Path) -> None:
    client, job_id, folder = _client(tmp_path, _known_vector_pdf())
    try:
        before = (_sha(folder / "original.pdf"), _sha(folder / "io_list.xlsx"))
        missing = client.get(f"/api/jobs/{job_id}/extraction")
        assert missing.status_code == 404
        started = client.post(f"/api/jobs/{job_id}/process")
        assert started.status_code == 202
        assert started.json()["stages"][1]["name"] == "Read"
        assert started.json()["stages"][1]["status"] == "running"
        finished = client.get(f"/api/jobs/{job_id}")
        read = finished.json()["stages"][1]
        assert read["status"] == "done"
        assert read["duration_ms"] is not None
        assert finished.json()["stages"][2]["name"] == "Detect"
        assert finished.json()["stages"][2]["status"] == "failed"
        assert "Prerequisite missing" in finished.json()["stages"][2]["error"]
        assert finished.json()["stages"][0]["status"] == "done"
        extracted = client.get(f"/api/jobs/{job_id}/extraction")
        assert extracted.status_code == 200
        assert extracted.json()["summary"]["words"] == 1
        assert extracted.json()["summary"]["circles"] == 1
        assert _sha(folder / "original.pdf") == before[0]
        assert _sha(folder / "io_list.xlsx") == before[1]
    finally:
        client.__exit__(None, None, None)


def test_concurrent_process_is_rejected(tmp_path: Path) -> None:
    client, job_id, _folder = _client(tmp_path, _known_vector_pdf())
    entered = threading.Event()
    release = threading.Event()
    real = pdf_extract.extract_pdf

    def blocked(path: Path):
        entered.set()
        assert release.wait(timeout=5)
        return real(path)

    pdf_extract.extract_pdf = blocked
    other = TestClient(client.app)
    try:
        other.__enter__()
        box: list[object] = []

        def run() -> None:
            box.append(client.post(f"/api/jobs/{job_id}/process"))

        worker = threading.Thread(target=run)
        worker.start()
        assert entered.wait(timeout=5)
        rejected = other.post(f"/api/jobs/{job_id}/process")
        assert rejected.status_code == 409
        assert rejected.json()["error_code"] == "JOB_ALREADY_RUNNING"
        release.set()
        worker.join(timeout=5)
        assert box and box[0].status_code == 202  # type: ignore[attr-defined]
    finally:
        pdf_extract.extract_pdf = real
        release.set()
        other.__exit__(None, None, None)
        client.__exit__(None, None, None)


def test_read_failure_sets_failed_and_keeps_intake(tmp_path: Path) -> None:
    client, job_id, folder = _client(tmp_path, _known_vector_pdf())
    before = (_sha(folder / "original.pdf"), _sha(folder / "io_list.xlsx"))
    real = pdf_extract.extract_pdf

    def broken(path: Path):
        raise RuntimeError("synthetic failure")

    pdf_extract.extract_pdf = broken
    try:
        response = client.post(f"/api/jobs/{job_id}/process")
        assert response.status_code == 202
        finished = client.get(f"/api/jobs/{job_id}")
        assert finished.json()["stages"][0]["status"] == "done"
        assert finished.json()["stages"][1]["status"] == "failed"
        assert "original files were not changed" in finished.json()["stages"][1]["error"]
        assert client.get(f"/api/jobs/{job_id}/extraction").status_code == 404
        assert _sha(folder / "original.pdf") == before[0]
        assert _sha(folder / "io_list.xlsx") == before[1]
    finally:
        pdf_extract.extract_pdf = real
        client.__exit__(None, None, None)
