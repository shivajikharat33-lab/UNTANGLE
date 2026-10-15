"""Scanned pages use the same extraction shape as vector pages."""

from pathlib import Path

import fitz

from app.services.pdf_extract import extract_pdf
from app.services import pdf_raster
from app.services.pdf_raster import pixel_to_pdf


def _image_pdf(tmp_path: Path) -> tuple[Path, float]:
    source = fitz.open()
    page = source.new_page(width=220, height=180)
    page.draw_circle(fitz.Point(70, 70), 24, color=(0, 0, 0), width=3)
    page.draw_line((20, 140), (190, 140), color=(0, 0, 0), width=3)
    page.insert_text((24, 36), "PT-101", fontsize=16)
    zoom = 2
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    source.close()
    document = fitz.open()
    scanned = document.new_page(width=220, height=180)
    scanned.insert_image(scanned.rect, pixmap=pixmap)
    path = tmp_path / "scanned.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    return path, pdf_raster._zoom()


def test_pixel_mapping_uses_the_render_zoom() -> None:
    zoom = 300 / 72
    assert pixel_to_pdf(zoom * 40, zoom * 25, zoom) == (40, 25)


def test_missing_ocr_is_reported_and_vector_text_is_not_invented(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(pdf_raster, "ocr_available", lambda: False)
    path, _zoom = _image_pdf(tmp_path)
    result = extract_pdf(path)
    assert result.status == "ocr_unavailable"
    assert result.pages[0].reader == "raster"
    assert result.summary.words == 0
    assert "Tesseract" in result.message
    assert result.summary.raster_items >= 1 or result.summary.lines >= 0


def test_raster_words_map_back_and_keep_ocr_confidence(tmp_path: Path, monkeypatch) -> None:
    path, zoom = _image_pdf(tmp_path)

    def fake_words(_gray):
        return [{"text": "PT-101", "bbox": [40 * zoom, 18 * zoom, 100 * zoom, 36 * zoom], "confidence": 0.62}]

    monkeypatch.setattr(pdf_raster, "ocr_available", lambda: True)
    monkeypatch.setattr(pdf_raster, "recognize_words", fake_words)
    result = extract_pdf(path)
    page = result.pages[0]
    assert page.reader == "raster"
    assert page.words[0].text == "PT-101"
    assert page.words[0].source == "raster"
    assert page.words[0].ocr_confidence == 0.62
    assert page.words[0].ocr_confidence < 0.85
    x0, y0, x1, y1 = page.words[0].bbox
    assert abs(x0 - 40) < 0.2
    assert abs(y0 - 18) < 0.2
    assert page.circles
    center = page.circles[0].center
    assert abs(center[0] - 70) < 8
    assert abs(center[1] - 70) < 8
    assert page.polylines
    flat_y = [point[1] for item in page.polylines for point in item.points]
    assert any(abs(value - 140) < 8 for value in flat_y)


def test_mixed_pdf_keeps_vector_page_and_flags_scanned_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(pdf_raster, "ocr_available", lambda: False)
    document = fitz.open()
    vector = document.new_page(width=200, height=100)
    vector.insert_text((10, 30), "FT-101", fontsize=12)
    vector.draw_line((10, 60), (80, 60), width=1)
    scanned = document.new_page(width=200, height=100)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 30, 20), 0)
    pixmap.clear_with(40)
    scanned.insert_image(scanned.rect, pixmap=pixmap)
    path = tmp_path / "mixed.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    result = extract_pdf(path)
    assert result.pages[0].reader == "vector"
    assert result.pages[0].words[0].text == "FT-101"
    assert result.pages[0].words[0].source == "vector"
    assert result.pages[1].reader == "raster"
    assert result.pages[1].status == "ocr_unavailable"
    assert result.status == "partial"
    assert result.summary.vector_items >= 1
