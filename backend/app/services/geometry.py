"""Line classification, snapping, and junction decisions. Flow is not chosen here."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.services.detect import DetectionResult
from app.services.pdf_extract import ExtractionResult
from app.services.storage import GEOMETRY_NAME, job_folder, read_json, write_json


class GeometryLine(BaseModel):
    id: str
    page: int
    points: list[list[float]]
    line_type: str
    reason: str
    source: str
    stroke_width: float | None = None
    dashes: str = ""
    length: float = 0


class SnapRecord(BaseModel):
    line_id: str
    endpoint: str
    original: list[float]
    snapped: list[float]


class Meeting(BaseModel):
    id: str
    page: int
    position: list[float]
    line_ids: list[str]
    decision: str
    reason: str
    confidence: Confidence


class FreeEndpoint(BaseModel):
    line_id: str
    page: int
    position: list[float]
    reason: str


class UnexplainedLine(BaseModel):
    line_id: str
    page: int
    position: list[float]
    length: float
    reason: str


class Coverage(BaseModel):
    total_length: float = 0
    explained_length: float = 0
    unexplained_length: float = 0
    free_endpoints: int = 0
    junctions: int = 0
    crossings: int = 0
    ambiguous: int = 0


class GeometryResult(BaseModel):
    lines: list[GeometryLine] = Field(default_factory=list)
    snaps: list[SnapRecord] = Field(default_factory=list)
    meetings: list[Meeting] = Field(default_factory=list)
    attachments: list[dict[str, str]] = Field(default_factory=list)
    free_endpoints: list[FreeEndpoint] = Field(default_factory=list)
    unexplained: list[UnexplainedLine] = Field(default_factory=list)
    coverage: Coverage


def _confidence(score: float, reason: str) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason=reason)  # type: ignore[arg-type]


def _length(points: list[list[float]]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:]):
        total += math.hypot(end[0] - start[0], end[1] - start[1])
    return total


def _dashed(dashes: str) -> bool:
    return any(float(number) > 0 for number in re.findall(r"\d+(?:\.\d+)?", dashes or ""))


def classify_line(width: float | None, dashes: str, process_min: float, signal_max: float = 0.75) -> tuple[str, str]:
    """Name a stroke. Dashed or thin lines are signal. Thick solid lines are process."""
    if _dashed(dashes):
        return "signal", "The stroke is dashed, so it is a signal or impulse line rather than a process line."
    if width is not None and width <= signal_max + 1e-6:
        return "signal", f"The solid stroke is {width:.2f} pt, at or below the {signal_max:.2f} pt thin-signal cutoff."
    if width is not None and width + 1e-6 < process_min:
        return "other", (
            f"The solid stroke is {width:.2f} pt. It is below the {process_min:.2f} pt process threshold "
            f"and above the {signal_max:.2f} pt thin-signal cutoff, and it is not dashed."
        )
    shown = "unknown" if width is None else f"{width:.2f} pt"
    return "process", f"The solid stroke is {shown}, which meets the process threshold of {process_min:.2f} pt."


def _dist(a: list[float] | tuple[float, float], b: list[float] | tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _near_point(point: tuple[float, float], ends: list[tuple[float, float]], tolerance: float) -> bool:
    return any(_dist(point, end) <= tolerance for end in ends)


def _projection_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> tuple[float, tuple[float, float]]:
    vx, vy = end[0] - start[0], end[1] - start[1]
    length_sq = vx * vx + vy * vy
    if length_sq == 0:
        return _dist(point, start), start
    t = ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length_sq
    t = max(0.0, min(1.0, t))
    projected = (start[0] + t * vx, start[1] + t * vy)
    return _dist(point, projected), projected


class _UnionFind:
    def __init__(self, count: int) -> None:
        self.parent = list(range(count))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        self.parent[self.find(left)] = self.find(right)


def _snap(lines: list[GeometryLine], tolerance: float) -> list[SnapRecord]:
    endpoints: list[tuple[int, int, float, float]] = []
    for index, line in enumerate(lines):
        if len(line.points) < 2:
            continue
        endpoints.append((index, 0, line.points[0][0], line.points[0][1]))
        endpoints.append((index, -1, line.points[-1][0], line.points[-1][1]))
    if not endpoints:
        return []
    points = [Point(item[2], item[3]) for item in endpoints]
    tree = STRtree(points)
    groups = _UnionFind(len(endpoints))
    for index, point in enumerate(points):
        for other in tree.query(point.buffer(tolerance)):
            other_index = int(other)
            if other_index <= index:
                continue
            if endpoints[index][0] == endpoints[other_index][0]:
                continue
            if points[index].distance(points[other_index]) <= tolerance:
                groups.union(index, other_index)
    clusters: dict[int, list[int]] = {}
    for index in range(len(endpoints)):
        clusters.setdefault(groups.find(index), []).append(index)
    snaps: list[SnapRecord] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        sx = sum(endpoints[index][2] for index in members) / len(members)
        sy = sum(endpoints[index][3] for index in members) / len(members)
        for index in members:
            line_index, which, ox, oy = endpoints[index]
            if abs(ox - sx) < 1e-6 and abs(oy - sy) < 1e-6:
                continue
            line = lines[line_index]
            line.points[which] = [sx, sy]
            snaps.append(
                SnapRecord(
                    line_id=line.id,
                    endpoint="start" if which == 0 else "end",
                    original=[ox, oy],
                    snapped=[sx, sy],
                )
            )
    for line in lines:
        line.length = _length(line.points)
    return snaps


def _has_dot(page_circles: list[tuple[float, float, float, bool]], position: tuple[float, float]) -> bool:
    for cx, cy, radius, filled in page_circles:
        if filled and radius <= 8 and _dist((cx, cy), position) <= radius + 2:
            return True
    return False


def _has_hop(lines: list[GeometryLine], position: tuple[float, float], used_ids: set[str]) -> bool:
    for line in lines:
        if line.id in used_ids:
            continue
        for point in line.points:
            distance = _dist(point, position)
            if 4 < distance <= 16:
                return True
    return False


def _meetings_for_page(lines: list[GeometryLine], circles: list[tuple[float, float, float]], tolerance: float) -> list[Meeting]:
    geoms = []
    usable = []
    for line in lines:
        if len(line.points) < 2 or line.length <= 0:
            continue
        geoms.append(LineString(line.points))
        usable.append(line)
    if not geoms:
        return []
    tree = STRtree(geoms)
    raw: list[tuple[tuple[float, float], str, str, str]] = []
    for index, geom in enumerate(geoms):
        for other in tree.query(geom):
            other_index = int(other)
            if other_index <= index:
                continue
            left = usable[index]
            right = usable[other_index]
            other_geom = geoms[other_index]
            if not geom.intersects(other_geom):
                continue
            intersection = geom.intersection(other_geom)
            if intersection.geom_type != "Point":
                continue
            position = (float(intersection.x), float(intersection.y))
            left_ends = [tuple(left.points[0]), tuple(left.points[-1])]
            right_ends = [tuple(right.points[0]), tuple(right.points[-1])]
            near_end = _near_point(position, [*left_ends, *right_ends], tolerance)
            if near_end:
                raw.append((position, left.id, right.id, "endpoint"))
            else:
                raw.append((position, left.id, right.id, "cross"))
        for end in (usable[index].points[0], usable[index].points[-1]):
            for other in tree.query(Point(end).buffer(tolerance)):
                other_index = int(other)
                if other_index == index:
                    continue
                distance, projected = _projection_on_segment(
                    (end[0], end[1]),
                    tuple(usable[other_index].points[0]),
                    tuple(usable[other_index].points[-1]),
                )
                if len(usable[other_index].points) != 2:
                    best = min(
                        (
                            _projection_on_segment((end[0], end[1]), tuple(start), tuple(stop))
                            for start, stop in zip(usable[other_index].points, usable[other_index].points[1:])
                        ),
                        key=lambda item: item[0],
                    )
                    distance, projected = best
                if distance > tolerance:
                    continue
                if _near_point(projected, [tuple(usable[other_index].points[0]), tuple(usable[other_index].points[-1])], tolerance):
                    continue
                raw.append(((end[0], end[1]), usable[index].id, usable[other_index].id, "tee"))

    groups: list[list[tuple[tuple[float, float], str, str, str]]] = []
    for event in raw:
        placed = False
        for group in groups:
            if _dist(event[0], group[0][0]) <= max(tolerance, 3):
                group.append(event)
                placed = True
                break
        if not placed:
            groups.append([event])

    meetings: list[Meeting] = []
    for index, group in enumerate(groups, start=1):
        position = group[0][0]
        line_ids = sorted({item[1] for item in group} | {item[2] for item in group})
        kinds = {item[3] for item in group}
        dot = _has_dot(circles, position)
        hop = _has_hop(lines, position, set(line_ids))
        if len(line_ids) > 2 and not dot:
            decision = "ambiguous"
            score = 0.45
            reason = "Needs Review. More than two lines meet here, and there is no junction dot, so the connection was not chosen."
        elif "cross" in kinds and dot:
            decision = "junction"
            score = 0.88
            reason = "The lines cross on a filled dot, so this is a junction."
        elif "cross" in kinds and hop:
            decision = "crossing"
            score = 0.84
            reason = "The lines cross under a hop, so they are not connected."
        elif "cross" in kinds and "tee" in kinds:
            decision = "ambiguous"
            score = 0.50
            reason = "Needs Review. The same place looks like both a crossing and a T-joint."
        elif kinds == {"cross"}:
            decision = "crossing"
            score = 0.90
            reason = "Two lines cross without a junction dot or a hop."
        elif "tee" in kinds or "endpoint" in kinds:
            decision = "junction"
            score = 0.90
            reason = "One line ends on another, or the lines meet at their ends, so this is a junction."
        else:
            decision = "ambiguous"
            score = 0.40
            reason = "Needs Review. The intersection does not match a T-joint, a plain crossing, a dot, or a hop."
        meetings.append(
            Meeting(
                id=f"m{index}",
                page=lines[0].page,
                position=[position[0], position[1]],
                line_ids=line_ids,
                decision=decision,
                reason=reason,
                confidence=_confidence(score, reason),
            )
        )
    return meetings


def _attached(point: list[float], detections: DetectionResult | None, page: int, tolerance: float) -> str | None:
    if detections is None:
        return None
    for item in detections.items:
        if item.page != page or item.kind == "arrow":
            continue
        x, y, width, height = item.bbox
        inside = x - tolerance <= point[0] <= x + width + tolerance and y - tolerance <= point[1] <= y + height + tolerance
        if inside:
            return item.id
    return None


def build_geometry(
    extraction: ExtractionResult,
    detections: DetectionResult | None = None,
    *,
    process_min_stroke: float = 1.0,
    signal_max_stroke: float = 0.75,
    snap_tolerance: float = 4.0,
) -> GeometryResult:
    """Classify and relate extracted polylines. Nothing undecidable is dropped."""
    lines: list[GeometryLine] = []
    unexplained: list[UnexplainedLine] = []
    counter = 0
    for page in extraction.pages:
        for polyline in page.polylines:
            counter += 1
            line_id = f"g{counter}"
            span = _length(polyline.points)
            if span <= 0 or len(polyline.points) < 2:
                unexplained.append(
                    UnexplainedLine(
                        line_id=line_id,
                        page=page.page,
                        position=polyline.points[0] if polyline.points else [0, 0],
                        length=span,
                        reason="The polyline has no length, so it was kept out of the spatial index.",
                    )
                )
                continue
            line_type, reason = classify_line(polyline.stroke_width, polyline.dashes, process_min_stroke, signal_max_stroke)
            lines.append(
                GeometryLine(
                    id=line_id,
                    page=page.page,
                    points=[list(point) for point in polyline.points],
                    line_type=line_type,
                    reason=reason,
                    source=polyline.source,
                    stroke_width=polyline.stroke_width,
                    dashes=polyline.dashes,
                    length=span,
                )
            )
    snaps = _snap(lines, snap_tolerance)
    meetings: list[Meeting] = []
    for page in extraction.pages:
        page_lines = [line for line in lines if line.page == page.page]
        circles = [
            (circle.center[0], circle.center[1], circle.radius, circle.fill is not None) for circle in page.circles
        ]
        page_meetings = _meetings_for_page(page_lines, circles, snap_tolerance)
        for meeting in page_meetings:
            meeting.id = f"m{len(meetings) + 1}"
            meetings.append(meeting)
    meeting_points = [(meeting.page, meeting.position) for meeting in meetings]
    free: list[FreeEndpoint] = []
    attachments: list[dict[str, str]] = []
    for line in lines:
        for endpoint, label in ((line.points[0], "start"), (line.points[-1], "end")):
            at_meeting = any(meeting_page == line.page and _dist(endpoint, position) <= snap_tolerance for meeting_page, position in meeting_points)
            symbol = _attached(endpoint, detections, line.page, snap_tolerance)
            if symbol and not at_meeting:
                attachments.append({"line_id": line.id, "symbol_id": symbol, "endpoint": label})
            if not at_meeting and symbol is None:
                free.append(
                    FreeEndpoint(
                        line_id=line.id,
                        page=line.page,
                        position=endpoint,
                        reason="This endpoint does not meet another line or a detected symbol.",
                    )
                )
    explained = sum(line.length for line in lines)
    unexplained_length = sum(item.length for item in unexplained)
    coverage = Coverage(
        total_length=explained + unexplained_length,
        explained_length=explained,
        unexplained_length=unexplained_length,
        free_endpoints=len(free),
        junctions=sum(1 for meeting in meetings if meeting.decision == "junction"),
        crossings=sum(1 for meeting in meetings if meeting.decision == "crossing"),
        ambiguous=sum(1 for meeting in meetings if meeting.decision == "ambiguous"),
    )
    return GeometryResult(
        lines=lines,
        snaps=snaps,
        meetings=meetings,
        attachments=attachments,
        free_endpoints=free,
        unexplained=unexplained,
        coverage=coverage,
    )


def load_geometry(upload_dir: str, job_id: str) -> GeometryResult:
    folder = job_folder(upload_dir, job_id)
    path = folder / GEOMETRY_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "Line geometry has not been run for this project.", {"job_id": job_id})
    return GeometryResult.model_validate(read_json(path))


def write_geometry(upload_dir: str, job_id: str, result: GeometryResult) -> None:
    folder = job_folder(upload_dir, job_id)
    write_json(folder / GEOMETRY_NAME, result.model_dump(mode="json"))
