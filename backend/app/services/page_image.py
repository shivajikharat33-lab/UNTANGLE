"""Render one PDF page to PNG and cache it by file hash, page, and zoom.

The original PDF is only read. The cache file is a new PNG.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

from app.errors import AppError
from app.services.storage import PDF_NAME, job_folder


def page_png(upload_dir: str, cache_dir: str, job_id: str, page_number: int, zoom: float) -> tuple[bytes, float, float]:
    """Return PNG bytes and the displayed page size in PDF points."""
    if page_number < 1:
        raise AppError(404, "NOT_FOUND", "That page is not in the drawing.", {"page": page_number})
    if zoom < 0.5 or zoom > 4:
        raise AppError(422, "ZOOM_OUT_OF_RANGE", "Zoom must be between 0.5 and 4.", {"zoom": zoom})
    folder = job_folder(upload_dir, job_id)
    pdf_path = folder / PDF_NAME
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cache_path = Path(cache_dir) / "pages" / digest / f"p{page_number}-z{zoom:.2f}.png"
    document = fitz.open(pdf_path)
    try:
        if page_number > document.page_count:
            raise AppError(404, "NOT_FOUND", "That page is not in the drawing.", {"page": page_number})
        page = document[page_number - 1]
        width = float(page.rect.width)
        height = float(page.rect.height)
        if not cache_path.is_file():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            cache_path.write_bytes(pixmap.tobytes("png"))
    finally:
        document.close()
    return cache_path.read_bytes(), width, height
