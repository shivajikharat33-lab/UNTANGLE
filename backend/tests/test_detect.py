"""Symbol rules on synthetic drawings."""

from io import BytesIO
from pathlib import Path

import fitz
from openpyxl import Workbook

from app.config import level_for_score
from app.services.detect import build_detections
from app.services.io_list import validate_workbook
from app.services.pdf_extract import extract_pdf
from app.services.tag_match import build_report


def _drawing(tmp_path: Path) -> Path:
    document = fitz.open()
    page = document.new_page(width=360, height=280)
    page.draw_rect(fitz.Rect(20, 20, 140, 110), color=(0, 0, 0), width=1.2)
    page.insert_text((36, 50), "T-101", fontsize=12)
    page.draw_rect(fitz.Rect(180, 30, 230, 70), color=(0, 0, 0), width=1)
    page.draw_circle(fitz.Point(60, 180), 16, color=(0, 0, 0), width=1)
    page.insert_text((46, 184), "PT-101", fontsize=9)
    page.draw_line((44, 180), (76, 180), color=(0, 0, 0), width=0.6)
    page.draw_circle(fitz.Point(250, 180), 14, color=(0, 0, 0), width=1.2)
    page.draw_polyline([(250, 168), (264, 180), (250, 192)], color=(0, 0, 0), closePath=True)
    page.insert_text((236, 160), "P-201", fontsize=10)
    page.draw_polyline([(20, 220), (36, 236), (20, 252)], color=(0, 0, 0), closePath=True)
    page.draw_polyline([(52, 220), (36, 236), (52, 252)], color=(0, 0, 0), closePath=True)
    page.draw_polyline([(120, 220), (136, 236), (120, 252)], color=(0, 0, 0), closePath=True)
    page.draw_polyline([(152, 220), (136, 236), (152, 252)], color=(0, 0, 0), closePath=True)
    page.draw_circle(fitz.Point(136, 206), 8, color=(0, 0, 0), width=1)
    page.insert_text((118, 200), "FV-12", fontsize=9)
    page.draw_line((200, 240), (280, 240), color=(0, 0, 0), width=1.4)
    page.draw_polyline([(280, 234), (294, 240), (280, 246)], color=(0, 0, 0), fill=(0, 0, 0), closePath=True)
    path = tmp_path / "symbols.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    return path


def _report(tmp_path: Path, extraction):
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Tag", "Description"])
    sheet.append(["PT-101", "Pressure"])
    sheet.append(["T-101", "Tank"])
    sheet.append(["P-201", "Pump"])
    sheet.append(["FV-12", "Control valve"])
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    path = tmp_path / "io.xlsx"
    path.write_bytes(buffer.getvalue())
    io_list = validate_workbook(path)
    return build_report(extraction, io_list, 0.80)


def test_symbols_follow_shape_and_label_rules(tmp_path: Path) -> None:
    extraction = extract_pdf(_drawing(tmp_path))
    report = _report(tmp_path, extraction)
    result = build_detections(extraction, report)
    by_tag = {item.tag: item for item in result.items if item.tag}
    assert by_tag["T-101"].kind == "equipment"
    assert by_tag["T-101"].subtype == "tank"
    assert by_tag["PT-101"].kind == "instrument"
    assert any(evidence.description.startswith("The tag is in the checked IO list") for evidence in by_tag["PT-101"].evidence)
    assert by_tag["P-201"].kind == "equipment"
    assert by_tag["P-201"].subtype == "pump"
    assert by_tag["FV-12"].kind == "valve"
    assert by_tag["FV-12"].subtype == "control"
    manual = [item for item in result.items if item.kind == "valve" and item.subtype == "manual"]
    assert manual
    assert "manual" in manual[0].confidence.reason
    arrow = next(item for item in result.items if item.kind == "arrow")
    assert arrow.direction == "right"
    assert "not decided" in arrow.confidence.reason
    unlabeled = [item for item in result.items if item.kind == "unclassified" and item.subtype == "shape"]
    assert unlabeled
    counts = result.census
    assert counts.instrument + counts.equipment + counts.valve + counts.arrow + counts.unclassified == len(result.items)
    assert counts.linked_to_io >= 1
    for item in result.items:
        assert item.confidence.level == level_for_score(item.confidence.score)
        if item.confidence.score >= 0.85:
            assert item.confidence.level == "high"
        elif item.confidence.score >= 0.60:
            assert item.confidence.level == "medium"
        else:
            assert item.confidence.level == "low"
