"""Tag matching against a checked IO list."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import level_for_score
from app.main import create_app
from app.schemas.io_list import IoListResult
from app.services.io_list import normalize_tag_confusion
from app.services.pdf_extract import extract_pdf
from app.services.tag_match import build_report
from tests.test_jobs import pdf_bytes, post_pair, settings_for


def _book(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "IO"
    sheet.append(["Tag", "Description"])
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def _io(tmp_path: Path, rows: list[tuple[str, str]]) -> IoListResult:
    from app.services.io_list import validate_workbook

    path = tmp_path / "io.xlsx"
    path.write_bytes(_book([[tag, signal] for tag, signal in rows]))
    return validate_workbook(path)


def test_confusion_normalizer_keeps_suffix() -> None:
    assert normalize_tag_confusion("FT-1O1B") == "FT-101B"
    assert normalize_tag_confusion("FT-101B") == "FT-101B"


def test_matches_exact_confusion_missing_and_extra(tmp_path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=240, height=240)
    page.insert_text((20, 40), "PT-101", fontsize=12)
    page.insert_text((20, 80), "FT-1O1B", fontsize=12)
    page.insert_text((20, 120), "XV-9", fontsize=12)
    path = tmp_path / "drawing.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    extraction = extract_pdf(path)
    report = build_report(
        extraction,
        _io(tmp_path, [("PT-101", "Pressure"), ("FT-101B", "Flow"), ("LT-50", "Level")]),
        0.80,
    )
    by_tag = {row.tag: row for row in report.rows if row.status != "extra"}
    assert set(by_tag) == {"PT-101", "FT-101B", "LT-50"}
    assert by_tag["PT-101"].status == "found"
    assert by_tag["PT-101"].confidence.score == 1
    assert by_tag["PT-101"].confidence.level == "high"
    assert by_tag["FT-101B"].status == "fuzzy"
    assert by_tag["FT-101B"].confidence.score == 0.75
    assert by_tag["FT-101B"].confidence.level == "medium"
    assert "Needs Review" in by_tag["FT-101B"].confidence.reason
    assert "FT-1O1B" in by_tag["FT-101B"].confidence.reason
    assert by_tag["FT-101B"].suffix_hint == "B"
    assert by_tag["LT-50"].status == "not_found"
    assert by_tag["LT-50"].suggestion
    extras = [row for row in report.rows if row.status == "extra"]
    assert [row.tag for row in extras] == ["XV-9"]
    assert report.summary.total == 3
    assert report.summary.found + report.summary.fuzzy + report.summary.not_found == report.summary.total
    assert report.summary.extra == 1
    for row in report.rows:
        assert row.confidence.level == level_for_score(row.confidence.score)


def test_rapidfuzz_near_match_is_fuzzy_needs_review(tmp_path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=200, height=80)
    page.insert_text((20, 40), "FT-102", fontsize=12)
    path = tmp_path / "near.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    report = build_report(extract_pdf(path), _io(tmp_path, [("FT-101", "Flow")]), 0.80)
    row = report.rows[0]
    assert row.status == "fuzzy"
    assert row.confidence.score >= 0.80
    assert row.confidence.level == level_for_score(row.confidence.score)
    assert "Needs Review" in row.confidence.reason
    assert "FT-102" in row.confidence.reason


def test_confidence_cutoffs_match_the_contract() -> None:
    assert level_for_score(0.85) == "high"
    assert level_for_score(0.60) == "medium"
    assert level_for_score(0.59) == "low"


def test_ambiguous_double_match_is_not_chosen(tmp_path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=240, height=160)
    page.insert_text((20, 40), "PT-101", fontsize=12)
    page.insert_text((20, 90), "PT-101", fontsize=12)
    path = tmp_path / "drawing.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    report = build_report(extract_pdf(path), _io(tmp_path, [("PT-101", "Pressure")]), 0.80)
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.status == "fuzzy"
    assert row.location is None
    assert row.suggestion is not None and "Candidates" in row.suggestion
    assert "Needs Review" in row.confidence.reason
    assert report.summary.extra == 0


def test_split_bubble_text_is_joined(tmp_path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.draw_circle(fitz.Point(100, 100), 36, width=0.8)
    page.insert_text((90, 96), "FT", fontsize=11)
    page.insert_text((84, 112), "101B", fontsize=11)
    path = tmp_path / "bubble.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    extraction = extract_pdf(path)
    assert extraction.summary.circles == 1
    assert extraction.summary.words == 2
    report = build_report(extraction, _io(tmp_path, [("FT-101B", "Flow")]), 0.80)
    assert report.rows[0].status == "found"
    assert report.rows[0].tag == "FT-101B"
    assert report.summary.extra == 0
    assert report.summary.found == 1


def test_tag_report_endpoint_and_missing_io_list(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    with TestClient(application) as client:
        created = post_pair(client, pdf=pdf_bytes(), workbook=_book([["PT-101", "Pressure"]]))
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert client.get(f"/api/jobs/{job_id}/tag-report").status_code == 404
        started = client.post(f"/api/jobs/{job_id}/process")
        assert started.status_code == 202
        finished = client.get(f"/api/jobs/{job_id}")
        stages = {stage["name"]: stage for stage in finished.json()["stages"]}
        assert stages["Read"]["status"] == "done"
        assert stages["MatchTags"]["status"] == "failed"
        assert "Prerequisite missing" in stages["MatchTags"]["error"]
        checked = client.post(f"/api/jobs/{job_id}/io-list/validate", json={})
        assert checked.status_code == 200
        again = client.post(f"/api/jobs/{job_id}/process")
        assert again.status_code == 202
        done = client.get(f"/api/jobs/{job_id}")
        assert {stage["name"]: stage["status"] for stage in done.json()["stages"]}["MatchTags"] == "done"
        report = client.get(f"/api/jobs/{job_id}/tag-report")
        assert report.status_code == 200
        body = report.json()
        assert body["summary"]["total"] == body["summary"]["found"] + body["summary"]["fuzzy"] + body["summary"]["not_found"]
        assert body["summary"]["not_found"] == 1
