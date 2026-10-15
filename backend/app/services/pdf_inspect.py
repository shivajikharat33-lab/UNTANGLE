"""Decide whether a PDF page set is vector, scanned, or mixed.

A vector page is built from drawing commands. A scanned page is a picture
placed on the page. A mixed page has both. The inspection script and the
upload API both call this module so the verdict stays one decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class PdfReport:
    """Facts printed by scripts/inspect_pdf.py. The API does not return sample_text."""

    page_count: int
    page_sizes: list[tuple[float, float]]
    vector_ops: int
    text_words: int
    image_count: int
    sample_text: list[str]
    verdict: str
    reason: str


def classify_counts(*, vector_ops: int, image_count: int) -> tuple[str, str]:
    """Return VECTOR, SCANNED, or MIXED, plus the reason for that call."""
    if vector_ops < 0 or image_count < 0:
        raise ValueError("counts cannot be negative")
    if vector_ops > 0 and image_count > 0:
        return (
            "MIXED",
            f"Found {vector_ops} vector drawing operation(s) and {image_count} embedded image(s). "
            "The file has both live drawing commands and a picture.",
        )
    if vector_ops > 0:
        return (
            "VECTOR",
            f"Found {vector_ops} vector drawing operation(s) and no embedded images. "
            "The drawing is made of vector commands.",
        )
    if image_count > 0:
        return (
            "SCANNED",
            f"Found {image_count} embedded image(s) and no vector drawing operations. "
            "The page content is a picture, which is what a scan looks like.",
        )
    return (
        "SCANNED",
        "Found no vector drawing operations and no embedded images. "
        "There is no vector drawing to trace, so this is not a VECTOR file.",
    )


def _vector_ops_on_page(page: fitz.Page) -> int:
    """Count drawing paths. A lone rectangle used to place an image is not a vector path."""
    count = 0
    images_present = len(page.get_images()) > 0
    for drawing in page.get_drawings():
        items = drawing.get("items") or []
        kinds = [item[0] for item in items if item]
        if images_present and kinds == ["re"]:
            continue
        count += 1
    return count


def _report(document: fitz.Document) -> PdfReport:
    """Classify an open document. The caller closes it."""
    page_sizes: list[tuple[float, float]] = []
    vector_ops = 0
    text_words = 0
    image_count = 0
    sample: list[str] = []
    for page in document:
        rectangle = page.rect
        page_sizes.append((round(rectangle.width, 2), round(rectangle.height, 2)))
        vector_ops += _vector_ops_on_page(page)
        words = page.get_text("words")
        text_words += len(words)
        image_count += len(page.get_images())
        for word in words:
            if len(sample) >= 12:
                break
            sample.append(str(word[4]))
    verdict, reason = classify_counts(vector_ops=vector_ops, image_count=image_count)
    return PdfReport(
        page_count=document.page_count,
        page_sizes=page_sizes,
        vector_ops=vector_ops,
        text_words=text_words,
        image_count=image_count,
        sample_text=sample,
        verdict=verdict,
        reason=reason,
    )


def inspect_pdf(path: Path) -> PdfReport:
    """Read one PDF and classify it. The caller checks that the file exists."""
    document = fitz.open(path)
    try:
        return _report(document)
    finally:
        document.close()


def inspect_pdf_bytes(data: bytes) -> PdfReport:
    """Classify PDF bytes without opening a file on disk."""
    document = fitz.open(stream=data, filetype="pdf")
    try:
        return _report(document)
    finally:
        document.close()
