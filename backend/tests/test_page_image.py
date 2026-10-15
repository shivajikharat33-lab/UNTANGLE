"""Page images are cached. The original PDF bytes stay the same."""

import hashlib
from pathlib import Path

import fitz

from app.services.page_image import page_png


def test_page_png_is_cached_by_hash_page_and_zoom(tmp_path: Path) -> None:
    upload = tmp_path / "uploads"
    job = upload / "job1"
    job.mkdir(parents=True)
    document = fitz.open()
    document.new_page(width=100, height=80)
    pdf = job / "original.pdf"
    document.save(pdf)
    document.close()
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()
    cache = tmp_path / "cache"
    first, width, height = page_png(str(upload), str(cache), "job1", 1, 1.5)
    second, _, _ = page_png(str(upload), str(cache), "job1", 1, 1.5)
    other, _, _ = page_png(str(upload), str(cache), "job1", 1, 2.0)
    assert first == second
    assert first != other
    assert width == 100
    assert height == 80
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before
    stored = list((cache / "pages").rglob("*.png"))
    assert len(stored) == 2
