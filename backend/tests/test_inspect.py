"""Verdict checks use tiny PDFs created in the test. No customer drawing is read."""

import json
from pathlib import Path

import fitz
import pytest
from openpyxl import Workbook

from app.schemas.answer_key import AnswerKey
from scripts.excel_checks import inspect_workbook
from scripts.inspect_excel import main as excel_main
from scripts.inspect_pdf import main as pdf_main
from scripts.pdf_verdict import inspect_pdf

ROOT = Path(__file__).resolve().parents[2]


def test_vector_pdf_is_vector(tmp_path: Path) -> None:
    path = tmp_path / "vector.pdf"
    document = fitz.open()
    page = document.new_page()
    page.draw_line(fitz.Point(72, 120), fitz.Point(240, 120))
    page.insert_text(fitz.Point(72, 100), "FT-101")
    document.save(path)
    document.close()

    report = inspect_pdf(path)
    assert report.page_count == 1
    assert report.page_sizes[0][0] > 0
    assert report.vector_ops > 0
    assert report.text_words >= 1
    assert report.image_count == 0
    assert "FT-101" in report.sample_text
    assert report.verdict == "VECTOR"


def test_embedded_image_pdf_is_scanned(tmp_path: Path) -> None:
    path = tmp_path / "scanned.pdf"
    document = fitz.open()
    page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 24, 16), 0)
    pixmap.clear_with(80)
    page.insert_image(page.rect, pixmap=pixmap)
    document.save(path)
    document.close()

    report = inspect_pdf(path)
    assert report.image_count >= 1
    assert report.vector_ops == 0
    assert report.verdict == "SCANNED"


def test_missing_pdf_does_not_invent_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.pdf"
    code = pdf_main([str(missing)])
    captured = capsys.readouterr()
    assert code == 1
    assert "data" in captured.out and "samples" in captured.out
    assert missing.exists() is False


def test_excel_reports_empty_and_duplicate_tags(tmp_path: Path) -> None:
    path = tmp_path / "io.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "IO"
    sheet.append(["Tag", "Signal"])
    sheet.append(["FT-101", "FT"])
    sheet.append(["", "FT"])
    sheet.append(["FT-101", "FT"])
    workbook.save(path)

    facts = inspect_workbook(path)
    assert facts[0].name == "IO"
    assert facts[0].columns == ["Tag", "Signal"]
    assert facts[0].tag_column == "Tag"
    assert facts[0].preview_rows[0]["Tag"] == "FT-101"
    assert facts[0].empty_tag_rows == [3]
    assert facts[0].duplicate_tags == ["FT-101"]


def test_missing_workbook_does_not_invent_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.xlsx"
    code = excel_main([str(missing)])
    captured = capsys.readouterr()
    assert code == 1
    assert "samples" in captured.out
    assert missing.exists() is False


def test_answer_key_template_matches_the_contract() -> None:
    payload = json.loads((ROOT / "data" / "answer_keys" / "TEMPLATE.json").read_text(encoding="utf-8"))
    key = AnswerKey.model_validate(payload)
    assert key.drawing_id == "replace-with-your-drawing-id"
    assert key.expected_connections[0].from_ == "P-101"
    assert key.expected_duty_standby_groups[0].member_tags == ["P-101", "P-102"]
