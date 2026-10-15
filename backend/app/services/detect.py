"""Rule-based symbol candidates. A shape without a label is kept and not promoted."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import Evidence
from app.schemas.reports import TagReport
from app.services.io_list import decode_prefix, normalize_tag
from app.services.pdf_extract import CircleItem, ExtractionResult, ShapeItem, WordItem
from app.services.storage import DETECTIONS_NAME, job_folder, read_json, write_json


class DetectionItem(BaseModel):
    id: str
    kind: str
    subtype: str
    page: int = Field(ge=1)
    bbox: list[float]
    label: str = ""
    tag: str = ""
    confidence: Confidence
    evidence: list[Evidence]
    source: str
    direction: str | None = None


class DetectionCensus(BaseModel):
    instrument: int = Field(ge=0, default=0)
    equipment: int = Field(ge=0, default=0)
    valve: int = Field(ge=0, default=0)
    arrow: int = Field(ge=0, default=0)
    unclassified: int = Field(ge=0, default=0)
    linked_to_io: int = Field(ge=0, default=0)


class DetectionPage(BaseModel):
    page: int = Field(ge=1)
    width: float
    height: float


class DetectionResult(BaseModel):
    items: list[DetectionItem]
    pages: list[DetectionPage] = Field(default_factory=list)
    census: DetectionCensus


_EQUIPMENT = {"T": "tank", "V": "vessel", "E": "exchanger", "P": "pump"}
_INSTRUMENT = {"PT", "FT", "LT", "TT"}
_CONTROL = {"FV", "LV"}


def _confidence(score: float, reason: str) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason=reason)  # type: ignore[arg-type]


def _xywh(bbox: list[float]) -> list[float]:
    return [bbox[0], bbox[1], max(0.0, bbox[2] - bbox[0]), max(0.0, bbox[3] - bbox[1])]


def _center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _contains(outer: list[float], point: tuple[float, float], pad: float = 6) -> bool:
    return outer[0] - pad <= point[0] <= outer[2] + pad and outer[1] - pad <= point[1] <= outer[3] + pad


def _overlaps(left: list[float], right: list[float], pad: float = 4) -> bool:
    return not (left[2] + pad < right[0] or right[2] + pad < left[0] or left[3] + pad < right[1] or right[3] + pad < left[1])


def _unique_points(points: list[list[float]]) -> list[list[float]]:
    unique: list[list[float]] = []
    for point in points:
        if any(abs(point[0] - kept[0]) < 1 and abs(point[1] - kept[1]) < 1 for kept in unique):
            continue
        unique.append(point)
    return unique


def _is_triangle(shape: ShapeItem) -> bool:
    return len(_unique_points(shape.points)) == 3


def _triangle_apex(shape: ShapeItem) -> tuple[list[float], str]:
    points = _unique_points(shape.points)
    centroid = (sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points))
    apex = max(points, key=lambda point: (point[0] - centroid[0]) ** 2 + (point[1] - centroid[1]) ** 2)
    angle = math.degrees(math.atan2(apex[1] - centroid[1], apex[0] - centroid[0]))
    if abs(angle) <= 45:
        direction = "right"
    elif abs(angle) >= 135:
        direction = "left"
    elif angle > 0:
        direction = "down"
    else:
        direction = "up"
    return apex, direction


def _nearby_word(words: list[WordItem], bbox: list[float], used: set[int], pad: float = 14) -> WordItem | None:
    found: list[WordItem] = []
    for index, word in enumerate(words):
        if index in used:
            continue
        if _contains(bbox, _center(word.bbox), pad):
            found.append(word)
    tagged = [word for word in found if normalize_tag(word.text)]
    if tagged:
        return tagged[0]
    return found[0] if found else None


def _tag_of(word: WordItem | None) -> str:
    if word is None:
        return ""
    return normalize_tag(word.text) or ""


def _io_hit(report: TagReport | None, tag: str) -> bool:
    if report is None or not tag:
        return False
    return any(row.tag == tag and row.status in {"found", "fuzzy"} for row in report.rows)


def _evidence(kind: str, description: str, page: int) -> Evidence:
    return Evidence(source=kind, description=description, page=page)


def build_detections(extraction: ExtractionResult, report: TagReport | None) -> DetectionResult:
    """Apply shape-plus-label rules. Unmatched shapes stay in the list."""
    items: list[DetectionItem] = []
    counter = 0

    def add(**kwargs: object) -> None:
        nonlocal counter
        counter += 1
        items.append(DetectionItem.model_validate({"id": f"d{counter}", **kwargs}))

    for page in extraction.pages:
        used_shapes: set[int] = set()
        used_circles: set[int] = set()
        used_words: set[int] = set()
        words = list(page.words)
        shapes = list(page.shapes)
        circles = list(page.circles)

        for circle_index, circle in enumerate(circles):
            circle_box = [circle.center[0] - circle.radius, circle.center[1] - circle.radius, circle.center[0] + circle.radius, circle.center[1] + circle.radius]
            triangles = [index for index, shape in enumerate(shapes) if index not in used_shapes and _is_triangle(shape) and _overlaps(circle_box, shape.bbox, 8)]
            word = _nearby_word(words, circle_box, used_words)
            tag = _tag_of(word)
            prefix = tag.split("-", 1)[0] if tag else ""
            if triangles and prefix == "P":
                used_circles.add(circle_index)
                used_shapes.update(triangles)
                if word is not None:
                    used_words.add(words.index(word))
                linked = _io_hit(report, tag)
                add(
                    kind="equipment",
                    subtype="pump",
                    page=page.page,
                    bbox=_xywh(circle_box),
                    label=word.text if word else "",
                    tag=tag,
                    confidence=_confidence(0.90 if linked else 0.86, "Circle, triangle, and a P- label were all present, so this is a pump candidate."),
                    evidence=[
                        _evidence("shape", "A circle and a triangle sit together.", page.page),
                        _evidence("label", f"The label normalizes to {tag}.", page.page),
                    ],
                    source=circle.source,
                )

        for shape_index, shape in enumerate(shapes):
            if shape_index in used_shapes or _is_triangle(shape):
                continue
            width, height = shape.bbox[2] - shape.bbox[0], shape.bbox[3] - shape.bbox[1]
            if min(width, height) < 28:
                continue
            word = _nearby_word(words, shape.bbox, used_words)
            tag = _tag_of(word)
            prefix = tag.split("-", 1)[0] if tag else ""
            if prefix not in _EQUIPMENT or prefix == "P":
                continue
            used_shapes.add(shape_index)
            if word is not None:
                used_words.add(words.index(word))
            subtype = _EQUIPMENT[prefix]
            linked = _io_hit(report, tag)
            add(
                kind="equipment",
                subtype=subtype,
                page=page.page,
                bbox=_xywh(shape.bbox),
                label=word.text if word else "",
                tag=tag,
                confidence=_confidence(0.92 if linked else 0.88, f"A closed shape and a {prefix}- label were both present, so this is a {subtype} candidate."),
                evidence=[
                    _evidence("shape", "The closed shape is large enough to be equipment.", page.page),
                    _evidence("label", f"The label normalizes to {tag}.", page.page),
                ],
                source=shape.source,
            )

        for circle_index, circle in enumerate(circles):
            if circle_index in used_circles:
                continue
            circle_box = [circle.center[0] - circle.radius, circle.center[1] - circle.radius, circle.center[0] + circle.radius, circle.center[1] + circle.radius]
            inside = [word for index, word in enumerate(words) if index not in used_words and _contains(circle_box, _center(word.bbox), circle.radius * 0.35)]
            raw = "".join(word.text for word in sorted(inside, key=lambda word: (word.bbox[1], word.bbox[0])))
            tag = normalize_tag(raw) or ""
            prefix = tag.split("-", 1)[0] if tag else ""
            if prefix not in _INSTRUMENT and prefix not in _CONTROL:
                continue
            if prefix in _CONTROL and any(
                _is_triangle(shape) and _overlaps(circle_box, shape.bbox, 12) for shape in shapes
            ):
                continue
            for word in inside:
                used_words.add(words.index(word))
            used_circles.add(circle_index)
            divider = False
            for line in page.polylines:
                if len(line.points) < 2:
                    continue
                y_values = [point[1] for point in line.points]
                x_values = [point[0] for point in line.points]
                if max(y_values) - min(y_values) > 3:
                    continue
                mid_y = sum(y_values) / len(y_values)
                if abs(mid_y - circle.center[1]) > circle.radius * 0.45:
                    continue
                if min(x_values) <= circle.center[0] <= max(x_values):
                    divider = True
            linked = _io_hit(report, tag)
            _code, instrument_type = decode_prefix(tag)
            evidence = [
                _evidence("shape", "A circle contains the tag text.", page.page),
                _evidence("label", f"The text inside the circle normalizes to {tag}, a {instrument_type}.", page.page),
            ]
            if divider:
                evidence.append(_evidence("shape", "A horizontal line crosses the circle.", page.page))
            if linked:
                evidence.append(_evidence("io-list", "The tag is in the checked IO list.", page.page))
            add(
                kind="instrument",
                subtype="bubble",
                page=page.page,
                bbox=_xywh(circle_box),
                label=raw,
                tag=tag,
                confidence=_confidence(0.93 if linked else 0.74, "The circle and the tag text agree. Shape alone was not enough."),
                evidence=evidence,
                source=circle.source,
            )

        triangle_indexes = [index for index, shape in enumerate(shapes) if index not in used_shapes and _is_triangle(shape)]
        paired: set[int] = set()
        for left_pos, left_index in enumerate(triangle_indexes):
            if left_index in paired:
                continue
            left = shapes[left_index]
            for right_index in triangle_indexes[left_pos + 1 :]:
                if right_index in paired:
                    continue
                right = shapes[right_index]
                if not _overlaps(left.bbox, right.bbox, 8):
                    continue
                pair_box = [
                    min(left.bbox[0], right.bbox[0]),
                    min(left.bbox[1], right.bbox[1]),
                    max(left.bbox[2], right.bbox[2]),
                    max(left.bbox[3], right.bbox[3]),
                ]
                word = _nearby_word(words, pair_box, used_words, pad=32)
                tag = _tag_of(word)
                prefix = tag.split("-", 1)[0] if tag else ""
                actuator = False
                for index, circle in enumerate(circles):
                    circle_box = [
                        circle.center[0] - circle.radius,
                        circle.center[1] - circle.radius,
                        circle.center[0] + circle.radius,
                        circle.center[1] + circle.radius,
                    ]
                    if index not in used_circles and _overlaps(pair_box, circle_box, 8):
                        actuator = True
                        used_circles.add(index)
                control = prefix in _CONTROL or actuator
                if word is not None:
                    used_words.add(words.index(word))
                paired.add(left_index)
                paired.add(right_index)
                used_shapes.add(left_index)
                used_shapes.add(right_index)
                reason = (
                    "Two touching triangles plus an FV/LV label or an actuator circle make this a control-valve candidate."
                    if control
                    else "Two touching triangles without an actuator or an FV/LV label make this a manual-valve candidate."
                )
                add(
                    kind="valve",
                    subtype="control" if control else "manual",
                    page=page.page,
                    bbox=_xywh(pair_box),
                    label=word.text if word else "",
                    tag=tag,
                    confidence=_confidence(0.90 if control else 0.78, reason),
                    evidence=[
                        _evidence("shape", "The bow-tie is two triangles.", page.page),
                        _evidence("label", reason, page.page),
                    ],
                    source=left.source,
                )
                break

        for shape_index, shape in enumerate(shapes):
            if shape_index in used_shapes or not _is_triangle(shape):
                continue
            width = shape.bbox[2] - shape.bbox[0]
            height = shape.bbox[3] - shape.bbox[1]
            if max(width, height) > 28 or shape.fill is None:
                continue
            _apex, direction = _triangle_apex(shape)
            near_line = False
            for line in page.polylines:
                for point in (line.points[0], line.points[-1]):
                    if abs(point[0] - _center(shape.bbox)[0]) < 18 and abs(point[1] - _center(shape.bbox)[1]) < 18:
                        near_line = True
            if not near_line:
                continue
            used_shapes.add(shape_index)
            add(
                kind="arrow",
                subtype="flow-candidate",
                page=page.page,
                bbox=_xywh(shape.bbox),
                label="",
                tag="",
                confidence=_confidence(0.70, "A small filled triangle sits at a line end. Flow direction is not decided here."),
                evidence=[_evidence("shape", f"The triangle points {direction}.", page.page)],
                source=shape.source,
                direction=direction,
            )

        for shape_index, shape in enumerate(shapes):
            if shape_index in used_shapes:
                continue
            add(
                kind="unclassified",
                subtype="shape",
                page=page.page,
                bbox=_xywh(shape.bbox),
                label="",
                tag="",
                confidence=_confidence(0.40, "No symbol rule matched this shape, so it was kept."),
                evidence=[_evidence("shape", "The shape did not match an instrument, equipment, valve, or arrow rule.", page.page)],
                source=shape.source,
            )
        for circle_index, circle in enumerate(circles):
            if circle_index in used_circles:
                continue
            circle_box = [circle.center[0] - circle.radius, circle.center[1] - circle.radius, circle.center[0] + circle.radius, circle.center[1] + circle.radius]
            add(
                kind="unclassified",
                subtype="circle",
                page=page.page,
                bbox=_xywh(circle_box),
                label="",
                tag="",
                confidence=_confidence(0.40, "This circle had no tag label, so it was not called an instrument."),
                evidence=[_evidence("shape", "A circle without a tag label stays unclassified.", page.page)],
                source=circle.source,
            )

    census = DetectionCensus(
        instrument=sum(1 for item in items if item.kind == "instrument"),
        equipment=sum(1 for item in items if item.kind == "equipment"),
        valve=sum(1 for item in items if item.kind == "valve"),
        arrow=sum(1 for item in items if item.kind == "arrow"),
        unclassified=sum(1 for item in items if item.kind == "unclassified"),
        linked_to_io=sum(1 for item in items if item.tag and _io_hit(report, item.tag)),
    )
    return DetectionResult(
        items=items,
        pages=[DetectionPage(page=page.page, width=page.width, height=page.height) for page in extraction.pages],
        census=census,
    )


def load_detections(upload_dir: str, job_id: str) -> DetectionResult:
    folder = job_folder(upload_dir, job_id)
    path = folder / DETECTIONS_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "Symbol detection has not been run for this project.", {"job_id": job_id})
    return DetectionResult.model_validate(read_json(path))


def write_detections(upload_dir: str, job_id: str, result: DetectionResult) -> None:
    folder = job_folder(upload_dir, job_id)
    write_json(folder / DETECTIONS_NAME, result.model_dump(mode="json"))
