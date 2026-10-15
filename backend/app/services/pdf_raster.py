"""Raster reading for scanned pages. Vector pages never come through here."""

from __future__ import annotations

import logging

import fitz
import numpy as np

from app.services.pdf_extract import (
    CircleItem,
    PageCounts,
    PageExtraction,
    PolylineItem,
    ShapeItem,
    UnusedPrimitive,
    WordItem,
    _Segment,
    merge_segments,
)

logger = logging.getLogger("untangle.pdf_raster")

RASTER_DPI = 300
RASTER_CONFIDENCE = 0.70
OCR_INSTALL = (
    "OCR is not installed. PaddleOCR and EasyOCR are not required. "
    "Install the Tesseract program and keep pytesseract available, then run extraction again. "
    "Vector pages are unaffected."
)
OCR_NOT_IN_BUILD = (
    "OCR is not available in this build. Text was not invented. Vector pages are unaffected."
)

_OCR_IN_BUILD: bool | None = None


def set_ocr_in_build(enabled: bool) -> None:
    """Remember whether this process was started with OCR included."""
    global _OCR_IN_BUILD
    _OCR_IN_BUILD = enabled


def ocr_in_this_build() -> bool:
    """False only for an image built without the OCR program."""
    if _OCR_IN_BUILD is not None:
        return _OCR_IN_BUILD
    return True


def ocr_message() -> str:
    """The sentence stored when a scanned page cannot be read as text."""
    if ocr_in_this_build():
        return OCR_INSTALL
    return OCR_NOT_IN_BUILD


def pixel_to_pdf(px: float, py: float, zoom: float) -> tuple[float, float]:
    """Map a rendered pixel back to displayed PDF points. Y stays downward."""
    return px / zoom, py / zoom


def ocr_available() -> bool:
    """True only when this build includes OCR and the Tesseract program can be started."""
    if not ocr_in_this_build():
        return False
    try:
        import pytesseract
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def recognize_words(gray: np.ndarray) -> list[dict[str, object]]:
    """Return OCR words in pixel boxes. Confidence is 0 to 1 and is never treated as exact."""
    import pytesseract

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    words: list[dict[str, object]] = []
    for index, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        try:
            score = float(data["conf"][index])
        except (TypeError, ValueError):
            continue
        if score < 0:
            continue
        left = float(data["left"][index])
        top = float(data["top"][index])
        width = float(data["width"][index])
        height = float(data["height"][index])
        words.append(
            {
                "text": text,
                "bbox": [left, top, left + width, top + height],
                "confidence": max(0.0, min(1.0, score / 100)),
            }
        )
    return words


def _zoom() -> float:
    return RASTER_DPI / 72


def _render(page: fitz.Page) -> tuple[np.ndarray, float]:
    zoom = _zoom()
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    channels = pixmap.n
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, channels)
    if channels == 4:
        image = image[:, :, :3]
    return image.copy(), zoom


def _binarize(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _threshold, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return gray, binary


def _skeleton(binary: np.ndarray) -> np.ndarray:
    import cv2

    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    image = binary.copy()
    skel = np.zeros(binary.shape, np.uint8)
    guard = 0
    while guard < max(binary.shape):
        guard += 1
        opened = cv2.morphologyEx(image, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(image, opened)
        eroded = cv2.erode(image, element)
        skel = cv2.bitwise_or(skel, temp)
        image = eroded.copy()
        if cv2.countNonZero(image) == 0:
            break
    return skel


def _lines(binary: np.ndarray, zoom: float) -> tuple[list[_Segment], int]:
    import cv2

    foreground = cv2.countNonZero(binary)
    if foreground and foreground < binary.size * 0.2:
        edges = _skeleton(binary)
    else:
        edges = cv2.Canny(binary, 50, 150)
    min_length = max(8, int(12 * zoom))
    found = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=min_length, maxLineGap=max(2, int(3 * zoom)))
    segments: list[_Segment] = []
    if found is None:
        return segments, 0
    for row in found:
        x0, y0, x1, y1 = [float(value) for value in row[0]]
        start = pixel_to_pdf(x0, y0, zoom)
        end = pixel_to_pdf(x1, y1, zoom)
        segment = _Segment(start, end, RASTER_CONFIDENCE, [0.0, 0.0, 0.0], "")
        segment.source = "raster"
        segment.confidence = RASTER_CONFIDENCE
        segment.stroke_width = 1.0
        segments.append(segment)
    return segments, len(segments)


def _circles(gray: np.ndarray, zoom: float) -> list[CircleItem]:
    import cv2

    blur = cv2.medianBlur(gray, 5)
    found = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(10, int(16 * zoom)),
        param1=120,
        param2=30,
        minRadius=max(4, int(8 * zoom)),
        maxRadius=max(12, int(60 * zoom)),
    )
    circles: list[CircleItem] = []
    if found is None:
        return circles
    for px, py, radius in found[0]:
        cx, cy = pixel_to_pdf(float(px), float(py), zoom)
        pdf_radius = float(radius) / zoom
        circles.append(
            CircleItem(
                center=[cx, cy],
                radius=pdf_radius,
                bbox=[cx - pdf_radius, cy - pdf_radius, cx + pdf_radius, cy + pdf_radius],
                stroke_width=1.0,
                color=[0.0, 0.0, 0.0],
                source="raster",
                confidence=RASTER_CONFIDENCE,
            )
        )
    kept: list[CircleItem] = []
    for circle in circles:
        if any(
            abs(circle.center[0] - other.center[0]) < other.radius and abs(circle.center[1] - other.center[1]) < other.radius
            for other in kept
        ):
            continue
        kept.append(circle)
    return kept


def _shapes(binary: np.ndarray, zoom: float, circle_count: int) -> tuple[list[ShapeItem], list[UnusedPrimitive], int, int, int]:
    import cv2

    contours, _hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shapes: list[ShapeItem] = []
    unused: list[UnusedPrimitive] = []
    read_count = 0
    used_count = 0
    speck_count = 0
    min_area = (8 * zoom) ** 2
    for contour in contours:
        read_count += 1
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        if area < min_area or width < 4 or height < 4:
            speck_count += 1
            continue
        ratio = width / height if height else 0
        if circle_count and 0.85 <= ratio <= 1.18:
            used_count += 1
            continue
        x0, y0 = pixel_to_pdf(float(x), float(y), zoom)
        x1, y1 = pixel_to_pdf(float(x + width), float(y + height), zoom)
        shapes.append(
            ShapeItem(
                kind="closed",
                bbox=[x0, y0, x1, y1],
                stroke_width=1.0,
                color=[0.0, 0.0, 0.0],
                source="raster",
                confidence=RASTER_CONFIDENCE,
            )
        )
        used_count += 1
    if speck_count:
        unused.append(
            UnusedPrimitive(
                kind="speck",
                reason=f"{speck_count} raster specks were below the size cutoff and were counted, not promoted to shapes.",
            )
        )
    return shapes, unused, read_count, used_count, speck_count


def _words(gray: np.ndarray, zoom: float) -> list[WordItem]:
    words: list[WordItem] = []
    for index, raw in enumerate(recognize_words(gray)):
        bbox = raw["bbox"]
        assert isinstance(bbox, list)
        x0, y0 = pixel_to_pdf(float(bbox[0]), float(bbox[1]), zoom)
        x1, y1 = pixel_to_pdf(float(bbox[2]), float(bbox[3]), zoom)
        score = float(raw["confidence"])
        words.append(
            WordItem(
                text=str(raw["text"]),
                bbox=[x0, y0, x1, y1],
                block=0,
                line=0,
                word=index,
                font_size=max(0.0, y1 - y0),
                source="raster",
                confidence=score,
                ocr_confidence=score,
            )
        )
    return words


def read_raster_page(page: fitz.Page, number: int) -> PageExtraction:
    """Read one scanned page into the vector extraction shape, flagged as raster."""
    image, zoom = _render(page)
    gray, binary = _binarize(image)
    segments, line_count = _lines(binary, zoom)
    polylines: list[PolylineItem] = merge_segments(segments)
    circles = _circles(gray, zoom)
    shapes, unused, contour_count, contour_used, speck_count = _shapes(binary, zoom, len(circles))
    text_available = ocr_available()
    words = _words(gray, zoom) if text_available else []
    if not text_available:
        unused.append(UnusedPrimitive(kind="ocr", reason=ocr_message()))
    read_count = line_count + len(circles) + contour_count + (0 if text_available else 1)
    used_count = line_count + len(circles) + contour_used
    counts = PageCounts(
        words=len(words),
        lines=line_count,
        polylines=len(polylines),
        shapes=len(shapes),
        circles=len(circles),
        primitives_read=read_count,
        primitives_used=used_count,
        unused_primitives=speck_count + (0 if text_available else 1),
    )
    if text_available:
        status = "ok"
        message = "This page was read from a raster image at 300 DPI. OCR text is not an exact read."
    else:
        status = "ocr_unavailable"
        message = ocr_message()
    logger.info("raster page %s status=%s words=%s lines=%s", number, status, len(words), line_count)
    return PageExtraction(
        page=number,
        width=float(page.rect.width),
        height=float(page.rect.height),
        rotation=int(page.rotation),
        status=status,
        reader="raster",
        message=message,
        words=words,
        polylines=polylines,
        shapes=shapes,
        circles=circles,
        unused=unused,
        counts=counts,
    )
