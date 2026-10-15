"""Text and vector geometry read from one PDF. No symbol classification."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from pathlib import Path

import fitz
from pydantic import BaseModel, Field

from app.errors import AppError

logger = logging.getLogger("untangle.pdf_extract")

COORDINATE_SYSTEM = (
    "Origin is the top-left of the displayed page after rotation. "
    "Units are PDF points (1/72 inch). Y increases downward. "
    "Word and drawing coordinates are mapped with the page rotation matrix "
    "so they match page.rect."
)

_ENDPOINT_TOLERANCE = 2.0
_ANGLE_TOLERANCE = math.radians(8)
_WIDTH_TOLERANCE = 0.2


class WordItem(BaseModel):
    text: str
    bbox: list[float]
    block: int
    line: int
    word: int
    font_size: float
    source: str = "vector"
    confidence: float | None = None
    ocr_confidence: float | None = None


class PolylineItem(BaseModel):
    points: list[list[float]]
    stroke_width: float | None = None
    color: list[float] | None = None
    dashes: str = ""
    segment_count: int = Field(ge=1)
    source: str = "vector"
    confidence: float | None = None


class ShapeItem(BaseModel):
    kind: str
    bbox: list[float]
    stroke_width: float | None = None
    color: list[float] | None = None
    fill: list[float] | None = None
    dashes: str = ""
    points: list[list[float]] = Field(default_factory=list)
    source: str = "vector"
    confidence: float | None = None


class CircleItem(BaseModel):
    center: list[float]
    radius: float = Field(ge=0)
    bbox: list[float]
    stroke_width: float | None = None
    color: list[float] | None = None
    fill: list[float] | None = None
    source: str = "vector"
    confidence: float | None = None


class UnusedPrimitive(BaseModel):
    kind: str
    reason: str


class PageCounts(BaseModel):
    words: int = Field(ge=0)
    lines: int = Field(ge=0)
    polylines: int = Field(ge=0)
    shapes: int = Field(ge=0)
    circles: int = Field(ge=0)
    primitives_read: int = Field(ge=0)
    primitives_used: int = Field(ge=0)
    unused_primitives: int = Field(ge=0)


class PageExtraction(BaseModel):
    page: int = Field(ge=1)
    width: float
    height: float
    rotation: int
    status: str
    reader: str = "vector"
    message: str
    words: list[WordItem]
    polylines: list[PolylineItem]
    shapes: list[ShapeItem]
    circles: list[CircleItem]
    unused: list[UnusedPrimitive]
    counts: PageCounts


class ExtractionSummary(PageCounts):
    """Totals across pages. unused_primitives is the count that was not classified."""

    vector_items: int = Field(default=0, ge=0)
    raster_items: int = Field(default=0, ge=0)


class ExtractionMeta(BaseModel):
    pdf_sha256: str
    page_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    pymupdf_version: str
    coordinate_system: str


class ExtractionResult(BaseModel):
    status: str
    message: str
    meta: ExtractionMeta
    pages: list[PageExtraction]
    summary: ExtractionSummary


class _Segment:
    def __init__(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        stroke_width: float | None,
        color: list[float] | None,
        dashes: str,
    ) -> None:
        self.start = start
        self.end = end
        self.stroke_width = stroke_width
        self.color = color
        self.dashes = dashes
        self.source = "vector"
        self.confidence: float | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _color(value: object) -> list[float] | None:
    if not isinstance(value, (tuple, list)):
        return None
    return [float(channel) for channel in value]


def _point(value: object, matrix: fitz.Matrix) -> tuple[float, float]:
    point = fitz.Point(value) * matrix
    return (float(point.x), float(point.y))


def _bbox_from_points(points: list[tuple[float, float]]) -> list[float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _transform_rect(rect: fitz.Rect, matrix: fitz.Matrix) -> list[float]:
    corners = [
        _point((rect.x0, rect.y0), matrix),
        _point((rect.x1, rect.y0), matrix),
        _point((rect.x0, rect.y1), matrix),
        _point((rect.x1, rect.y1), matrix),
    ]
    return _bbox_from_points(corners)


def _transform_word_bbox(bbox: tuple[float, float, float, float], matrix: fitz.Matrix) -> list[float]:
    x0, y0, x1, y1 = bbox
    return _transform_rect(fitz.Rect(x0, y0, x1, y1), matrix)


def _nearly(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _ENDPOINT_TOLERANCE and abs(a[1] - b[1]) <= _ENDPOINT_TOLERANCE


def _aligned(base: float, new: float) -> bool:
    delta = abs(base - new) % (2 * math.pi)
    smallest = min(delta, (2 * math.pi) - delta)
    return smallest <= _ANGLE_TOLERANCE or smallest >= (math.pi - _ANGLE_TOLERANCE)


def _direction(start: tuple[float, float], end: tuple[float, float]) -> float | None:
    if _nearly(start, end) and abs(start[0] - end[0]) < 1e-6 and abs(start[1] - end[1]) < 1e-6:
        return None
    return math.atan2(end[1] - start[1], end[0] - start[0])


def _same_style(left: _Segment, right: _Segment) -> bool:
    if left.dashes != right.dashes or left.color != right.color:
        return False
    if left.stroke_width is None or right.stroke_width is None:
        return left.stroke_width == right.stroke_width
    return abs(left.stroke_width - right.stroke_width) <= _WIDTH_TOLERANCE


def _is_circle(items: list[tuple], rect: fitz.Rect) -> bool:
    if not items or len(items) > 4 or any(item[0] != "c" for item in items):
        return False
    width = float(rect.width)
    height = float(rect.height)
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return 0.85 <= ratio <= 1.18


def merge_segments(segments: list[_Segment]) -> list[PolylineItem]:
    """Join collinear connected segments. Every input segment is kept in some polyline."""
    unused = [False] * len(segments)
    polylines: list[PolylineItem] = []
    for index, segment in enumerate(segments):
        if unused[index]:
            continue
        unused[index] = True
        points = [segment.start, segment.end]
        used_count = 1
        grew = True
        while grew:
            grew = False
            for other_index, other in enumerate(segments):
                if unused[other_index] or not _same_style(segment, other):
                    continue
                attached = _attach(points, other)
                if attached is None:
                    continue
                points = attached
                unused[other_index] = True
                used_count += 1
                grew = True
        polylines.append(
            PolylineItem(
                points=[[point[0], point[1]] for point in points],
                stroke_width=segment.stroke_width,
                color=segment.color,
                dashes=segment.dashes,
                segment_count=used_count,
                source=segment.source,
                confidence=segment.confidence,
            )
        )
    return polylines


def _attach(points: list[tuple[float, float]], other: _Segment) -> list[tuple[float, float]] | None:
    if len(points) < 2:
        return None
    end_direction = _direction(points[-2], points[-1])
    start_direction = _direction(points[0], points[1])
    candidates = (
        (points[-1], other.start, other.end, end_direction, True),
        (points[-1], other.end, other.start, end_direction, True),
        (points[0], other.end, other.start, start_direction, False),
        (points[0], other.start, other.end, start_direction, False),
    )
    for anchor, touch, extra, direction, at_end in candidates:
        if not _nearly(anchor, touch):
            continue
        new_direction = _direction(anchor, extra)
        if direction is not None and new_direction is not None and not _aligned(direction, new_direction):
            continue
        if at_end:
            return [*points, extra]
        return [extra, *points]
    return None


def _style(drawing: dict) -> tuple[float | None, list[float] | None, list[float] | None, str]:
    width = drawing.get("width")
    stroke = float(width) if isinstance(width, (int, float)) else None
    return stroke, _color(drawing.get("color")), _color(drawing.get("fill")), str(drawing.get("dashes") or "")


def _extract_page(page: fitz.Page, number: int) -> PageExtraction:
    matrix = page.rotation_matrix
    words: list[WordItem] = []
    for raw in page.get_text("words"):
        x0, y0, x1, y1, text, block, line, word = raw[:8]
        bbox = _transform_word_bbox((float(x0), float(y0), float(x1), float(y1)), matrix)
        words.append(
            WordItem(
                text=str(text),
                bbox=bbox,
                block=int(block),
                line=int(line),
                word=int(word),
                font_size=abs(bbox[3] - bbox[1]),
            )
        )

    segments: list[_Segment] = []
    shapes: list[ShapeItem] = []
    circles: list[CircleItem] = []
    unused: list[UnusedPrimitive] = []
    read_count = 0
    used_count = 0

    for drawing in page.get_drawings():
        items = list(drawing.get("items") or [])
        stroke, color, fill, dashes = _style(drawing)
        if not items:
            read_count += 1
            unused.append(UnusedPrimitive(kind="empty", reason="The drawing had no geometry items."))
            continue
        read_count += len(items)
        rect = drawing.get("rect")
        if isinstance(rect, fitz.Rect) and _is_circle(items, rect):
            bbox = _transform_rect(rect, matrix)
            radius = min(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 2
            circles.append(
                CircleItem(
                    center=[(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
                    radius=radius,
                    bbox=bbox,
                    stroke_width=stroke,
                    color=color,
                    fill=fill,
                )
            )
            used_count += len(items)
            continue
        if len(items) == 1 and items[0][0] == "re":
            bbox = _transform_rect(items[0][1], matrix)
            shapes.append(
                ShapeItem(
                    kind="rectangle",
                    bbox=bbox,
                    points=[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]],
                    stroke_width=stroke,
                    color=color,
                    fill=fill,
                    dashes=dashes,
                )
            )
            used_count += 1
            continue
        if items and all(item[0] == "l" for item in items) and len(items) >= 3:
            outline: list[list[float]] = []
            for item in items:
                start = list(_point(item[1], matrix))
                end = list(_point(item[2], matrix))
                if not outline:
                    outline.append(start)
                outline.append(end)
            closed_loop = abs(outline[0][0] - outline[-1][0]) < 1 and abs(outline[0][1] - outline[-1][1]) < 1
            if closed_loop:
                bbox = _bbox_from_points([(point[0], point[1]) for point in outline])
                shapes.append(
                    ShapeItem(
                        kind="closed",
                        bbox=bbox,
                        points=outline,
                        stroke_width=stroke,
                        color=color,
                        fill=fill,
                        dashes=dashes,
                    )
                )
                used_count += len(items)
                continue
        if drawing.get("closePath") and items and all(item[0] in {"l", "re"} for item in items):
            boxes = [_transform_rect(item[1], matrix) for item in items if item[0] == "re"]
            line_points = [
                point
                for item in items
                if item[0] == "l"
                for point in (_point(item[1], matrix), _point(item[2], matrix))
            ]
            bbox = boxes[0] if boxes else _bbox_from_points(line_points)
            outline: list[list[float]] = []
            for item in items:
                if item[0] != "l":
                    continue
                start = list(_point(item[1], matrix))
                if not outline or abs(outline[-1][0] - start[0]) > 0.1 or abs(outline[-1][1] - start[1]) > 0.1:
                    outline.append(start)
                outline.append(list(_point(item[2], matrix)))
            shapes.append(
                ShapeItem(
                    kind="closed",
                    bbox=bbox,
                    points=outline,
                    stroke_width=stroke,
                    color=color,
                    fill=fill,
                    dashes=dashes,
                )
            )
            used_count += len(items)
            continue
        for item in items:
            kind = item[0]
            if kind == "l":
                segments.append(_Segment(_point(item[1], matrix), _point(item[2], matrix), stroke, color, dashes))
                used_count += 1
            elif kind == "re":
                shapes.append(
                    ShapeItem(
                        kind="rectangle",
                        bbox=_transform_rect(item[1], matrix),
                        stroke_width=stroke,
                        color=color,
                        fill=fill,
                        dashes=dashes,
                    )
                )
                used_count += 1
            else:
                unused.append(
                    UnusedPrimitive(
                        kind=str(kind),
                        reason="This primitive is not a line, rectangle, closed shape, or circle.",
                    )
                )

    polylines = merge_segments(segments)
    if sum(item.segment_count for item in polylines) != len(segments):
        raise RuntimeError("line segments were dropped during merge")
    line_count = len(segments)
    counts = PageCounts(
        words=len(words),
        lines=line_count,
        polylines=len(polylines),
        shapes=len(shapes),
        circles=len(circles),
        primitives_read=read_count,
        primitives_used=used_count,
        unused_primitives=len(unused),
    )
    if counts.primitives_read != counts.primitives_used + counts.unused_primitives:
        raise RuntimeError("primitive accounting does not add up")
    has_vector = bool(words or polylines or shapes or circles or read_count)
    if has_vector:
        status = "ok"
        message = "Vector text and geometry were read from this page."
    else:
        image_count = len(page.get_images())
        if image_count:
            from app.services.pdf_raster import read_raster_page

            return read_raster_page(page, number)
        status = "no_vector_content"
        message = "This page has no vector text or drawings, and it has no raster image. Nothing was invented."
    return PageExtraction(
        page=number,
        width=float(page.rect.width),
        height=float(page.rect.height),
        rotation=int(page.rotation),
        status=status,
        message=message,
        words=words,
        polylines=polylines,
        shapes=shapes,
        circles=circles,
        unused=unused,
        counts=counts,
    )


def _source_counts(pages: list[PageExtraction]) -> tuple[int, int]:
    vector = 0
    raster = 0
    for page in pages:
        for item in [*page.words, *page.polylines, *page.shapes, *page.circles]:
            if item.source == "raster":
                raster += 1
            else:
                vector += 1
    return vector, raster


def _summary(pages: list[PageExtraction]) -> ExtractionSummary:
    vector_items, raster_items = _source_counts(pages)
    return ExtractionSummary(
        words=sum(page.counts.words for page in pages),
        lines=sum(page.counts.lines for page in pages),
        polylines=sum(page.counts.polylines for page in pages),
        shapes=sum(page.counts.shapes for page in pages),
        circles=sum(page.counts.circles for page in pages),
        primitives_read=sum(page.counts.primitives_read for page in pages),
        primitives_used=sum(page.counts.primitives_used for page in pages),
        unused_primitives=sum(page.counts.unused_primitives for page in pages),
        vector_items=vector_items,
        raster_items=raster_items,
    )


def _document_status(pages: list[PageExtraction]) -> tuple[str, str]:
    if not pages:
        return "no_vector_content", "The PDF has no pages."
    statuses = {page.status for page in pages}
    raster_pages = any(page.reader == "raster" for page in pages)
    if statuses == {"ok"} and raster_pages:
        return (
            "ok",
            "Raster pages were read into the same extraction shape. OCR text is not an exact read.",
        )
    if statuses == {"ok"}:
        return "ok", "Vector content was read."
    if statuses == {"no_vector_content"}:
        return "no_vector_content", "No vector content was found, and there was no page image to read. Nothing was invented."
    if statuses == {"ocr_unavailable"}:
        from app.services.pdf_raster import ocr_in_this_build

        if not ocr_in_this_build():
            return (
                "ocr_unavailable",
                "This PDF has no vector content. OCR is not available in this build, so text was not invented. "
                "Vector files are unaffected.",
            )
        return (
            "ocr_unavailable",
            "This PDF has no vector content. OCR is not installed, so text was not invented. "
            "Install the Tesseract program, then run extraction again. Vector files are unaffected.",
        )
    if "ocr_unavailable" in statuses:
        from app.services.pdf_raster import ocr_in_this_build

        if not ocr_in_this_build():
            return "partial", "Some pages need OCR, which is not available in this build. Pages with vector content were still read."
        return "partial", "Some pages need OCR, which is not installed. Pages with vector content were still read."
    return "partial", "Some pages have vector content and some do not. Empty pages were not filled in."


def extract_pdf(path: Path) -> ExtractionResult:
    """Read one PDF page by page. The file is opened once."""
    started = time.perf_counter()
    document = fitz.open(path)
    try:
        pages = [_extract_page(page, index + 1) for index, page in enumerate(document)]
        page_count = document.page_count
    finally:
        document.close()
    status, message = _document_status(pages)
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    version = fitz.version
    version_text = version[0] if isinstance(version, tuple) and version else str(version)
    result = ExtractionResult(
        status=status,
        message=message,
        meta=ExtractionMeta(
            pdf_sha256=_sha256(path),
            page_count=page_count,
            duration_ms=duration_ms,
            pymupdf_version=str(version_text),
            coordinate_system=COORDINATE_SYSTEM,
        ),
        pages=pages,
        summary=_summary(pages),
    )
    logger.info(
        "extracted pdf pages=%s status=%s duration_ms=%s",
        result.meta.page_count,
        result.status,
        result.meta.duration_ms,
    )
    return result


def load_extraction(upload_dir: str, job_id: str) -> ExtractionResult:
    """Return the saved read, or 404 when Read has not produced a file."""
    from app.services.storage import EXTRACTION_NAME, job_folder, read_json

    folder = job_folder(upload_dir, job_id)
    path = folder / EXTRACTION_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The drawing has not been read for this project.", {"job_id": job_id})
    return ExtractionResult.model_validate(read_json(path))
