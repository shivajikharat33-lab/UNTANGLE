"""Build a connection graph from Phase C detections and line geometry.

Junctions connect lines. Crossings do not. Direction is set only from an
arrow, a check valve, a recorded nozzle, or a terminal phrase. Nothing
here uses an LLM.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from app import graph_config as cfg
from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import (
    BBox,
    DiagramGraph,
    Edge,
    Evidence,
    GraphSummary,
    Node,
    Point,
    PreservedMeeting,
    StructureNote,
)
from app.schemas.reports import TagReport
from app.services.detect import DetectionResult
from app.services.geometry import GeometryResult, Meeting
from app.services.storage import GRAPH_NAME, job_folder, read_json, write_json

_SYMBOL_KINDS = {"equipment", "instrument", "valve"}


@dataclass
class _Chain:
    ids: list[str]
    points: list[tuple[float, float]]
    line_type: str
    page: int
    source: str
    review: list[str] = field(default_factory=list)


def stable_id(kind: str, page: int, x: float, y: float, tag: str = "") -> str:
    """Hash kind, page, rounded position, and tag. The same inputs always match."""
    raw = f"{kind}|{page}|{round(x, cfg.ID_DECIMALS)}|{round(y, cfg.ID_DECIMALS)}|{tag.strip().upper()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{kind}-{digest}"


def build_graph(
    detections: DetectionResult,
    geometry: GeometryResult,
    report: TagReport,
    *,
    source_sha256: str = "",
    snap_tolerance: float = cfg.DEFAULT_SNAP_TOLERANCE,
    node_tolerance: float = cfg.DEFAULT_NODE_ATTACH_TOLERANCE,
) -> DiagramGraph:
    """Return a schema-valid graph. Ambiguous attachments are kept and flagged."""
    nodes = _symbol_nodes(detections, report)
    nodes.extend(_junction_nodes(geometry))
    nodes.extend(_terminal_nodes(detections, report))
    _flag_duplicates(nodes)
    chains = _merge_chains(_chains_from_lines(geometry), geometry.meetings, nodes, snap_tolerance)
    edges = _edges_from_chains(chains, nodes, node_tolerance)
    _apply_direction(edges, nodes, detections)
    _attach_instruments(nodes, edges, node_tolerance)
    structure = _structure(nodes, edges)
    return DiagramGraph(
        nodes=nodes,
        edges=edges,
        structure=structure,
        crossings=[_preserved(item) for item in geometry.meetings if item.decision == "crossing"],
        ambiguous_meetings=[_preserved(item) for item in geometry.meetings if item.decision == "ambiguous"],
        source_sha256=source_sha256,
        processing_version=cfg.PROCESSING_VERSION,
    )


def summarize_graph(graph: DiagramGraph) -> GraphSummary:
    """Counts for the graph summary card."""
    kinds = {item.kind: item.item_ids for item in graph.structure}
    return GraphSummary(
        nodes=len(graph.nodes),
        edges=len(graph.edges),
        junctions=sum(1 for node in graph.nodes if node.type == "junction"),
        terminals=sum(1 for node in graph.nodes if node.type == "terminal"),
        orphans=len(kinds.get("orphan", [])),
        dead_ends=len(kinds.get("dead_end", [])),
        unattached_instruments=len(kinds.get("unattached_instrument", [])),
        disconnected_components=len(kinds.get("disconnected", [])),
        duplicates=len(kinds.get("duplicate", [])),
        unknown_direction=sum(1 for edge in graph.edges if edge.direction == "unknown"),
        needs_review=sum(1 for node in graph.nodes if node.needs_review) + sum(1 for edge in graph.edges if edge.needs_review),
        crossings=len(graph.crossings),
    )


def load_graph(upload_dir: str, job_id: str) -> DiagramGraph:
    """Read graph.json. A missing file is a 404."""
    path = job_folder(upload_dir, job_id) / GRAPH_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The graph has not been built for this project.", {"job_id": job_id})
    return DiagramGraph.model_validate(read_json(path))


def write_graph(upload_dir: str, job_id: str, graph: DiagramGraph) -> None:
    """Replace graph.json. The original PDF and workbook are not touched."""
    write_json(job_folder(upload_dir, job_id) / GRAPH_NAME, graph.model_dump(mode="json"))


def _confidence(score: float, reason: str) -> Confidence:
    bounded = min(1.0, max(0.0, score))
    return Confidence(level=level_for_score(bounded), score=bounded, reason=reason)  # type: ignore[arg-type]


def _certainty(score: float) -> str:
    return cfg.certainty_for_score(score)


def _bbox_from_xywh(page: int, box: list[float]) -> BBox:
    """Detection boxes are x, y, width, height, matching the overlay and geometry."""
    return BBox(page=page, x=box[0], y=box[1], w=max(0.0, box[2]), h=max(0.0, box[3]))


def _center_of(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2] / 2, box[1] + box[3] / 2)


def _node_center(node: Node) -> tuple[float, float]:
    if node.bbox is None:
        return (0.0, 0.0)
    return (node.bbox.x + node.bbox.w / 2, node.bbox.y + node.bbox.h / 2)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist_bbox(point: tuple[float, float], node: Node) -> float:
    if node.bbox is None:
        return _dist(point, (0.0, 0.0))
    box = node.bbox
    dx = max(box.x - point[0], 0.0, point[0] - (box.x + box.w))
    dy = max(box.y - point[1], 0.0, point[1] - (box.y + box.h))
    return math.hypot(dx, dy)


def _evidence(source: str, description: str, page: int | None = None) -> Evidence:
    return Evidence(source=source, description=description, page=page)


def _tag_row(report: TagReport, tag: str):
    target = tag.strip().upper()
    for row in report.rows:
        if row.tag.strip().upper() == target:
            return row
    return None


def _symbol_nodes(detections: DetectionResult, report: TagReport) -> list[Node]:
    nodes: list[Node] = []
    for item in detections.items:
        if item.kind not in _SYMBOL_KINDS:
            continue
        if _is_terminal_label(item.label) or _is_terminal_label(item.tag):
            continue
        center = _center_of(item.bbox)
        node = Node(
            id=stable_id(item.kind, item.page, center[0], center[1], item.tag or item.label),
            type=item.kind,  # type: ignore[arg-type]
            tag=item.tag,
            label=item.label,
            signal=item.tag.split("-")[0] if "-" in item.tag else "",
            bbox=_bbox_from_xywh(item.page, item.bbox),
            confidence=item.confidence,
            certainty=_certainty(item.confidence.score),  # type: ignore[arg-type]
            reason=item.confidence.reason,
            evidence=list(item.evidence),
            subtype=item.subtype,
            source_id=item.id,
            pointing=item.direction or "",
        )
        _add_tag_evidence(node, report)
        nodes.append(node)
    return nodes


def _terminal_nodes(detections: DetectionResult, report: TagReport) -> list[Node]:
    nodes: list[Node] = []
    for item in detections.items:
        label = f"{item.label} {item.tag}".upper()
        if not _is_terminal_label(label):
            continue
        center = _center_of(item.bbox)
        score = item.confidence.score
        node = Node(
            id=stable_id("terminal", item.page, center[0], center[1], item.label or item.tag),
            type="terminal",
            tag=item.tag,
            label=item.label,
            bbox=_bbox_from_xywh(item.page, item.bbox),
            confidence=item.confidence,
            certainty=_certainty(score),  # type: ignore[arg-type]
            reason="The label names an off-page connector, inlet, or outlet. No direction was guessed from where it sits on the page.",
            evidence=list(item.evidence),
            subtype=_terminal_flow(label) or "",
            source_id=item.id,
        )
        _add_tag_evidence(node, report)
        nodes.append(node)
    return nodes


def _is_terminal_label(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in cfg.TERMINAL_MARKERS) or any(
        phrase in upper for phrase in cfg.FLOW_IN_PHRASES + cfg.FLOW_OUT_PHRASES
    )


def _terminal_flow(label: str) -> str:
    upper = label.upper()
    if any(phrase in upper for phrase in cfg.FLOW_OUT_PHRASES):
        return "out"
    if any(phrase in upper for phrase in cfg.FLOW_IN_PHRASES):
        return "in"
    return ""


def _add_tag_evidence(node: Node, report: TagReport) -> None:
    if not node.tag:
        return
    row = _tag_row(report, node.tag)
    if row is None:
        node.evidence.append(_evidence("tag_report", "The tag check has no IO-list row for this tag.", node.bbox.page if node.bbox else None))
        return
    node.evidence.append(
        _evidence(
            "tag_report",
            f"The existing tag check marked {node.tag} as {row.status}. Matching was not run again.",
            node.bbox.page if node.bbox else None,
        )
    )
    if row.signal and not node.signal:
        node.signal = row.signal


def _junction_nodes(geometry: GeometryResult) -> list[Node]:
    nodes: list[Node] = []
    for meeting in geometry.meetings:
        if meeting.decision != "junction":
            continue
        x, y = meeting.position[0], meeting.position[1]
        score = meeting.confidence.score
        nodes.append(
            Node(
                id=stable_id("junction", meeting.page, x, y, meeting.id),
                type="junction",
                bbox=BBox(page=meeting.page, x=x - 1, y=y - 1, w=2, h=2),
                confidence=meeting.confidence,
                certainty=_certainty(score),  # type: ignore[arg-type]
                reason=meeting.reason,
                evidence=[_evidence("geometry", meeting.reason, meeting.page)],
                source_id=meeting.id,
            )
        )
    return nodes


def _flag_duplicates(nodes: list[Node]) -> None:
    for index, left in enumerate(nodes):
        if left.bbox is None or left.type in {"junction", "endpoint"}:
            continue
        for right in nodes[index + 1 :]:
            if right.bbox is None or right.type != left.type or right.bbox.page != left.bbox.page:
                continue
            if _dist(_node_center(left), _node_center(right)) > cfg.DUPLICATE_DISTANCE:
                continue
            message = "Two nodes of the same type sit on the same spot. Neither one was deleted."
            for node in (left, right):
                node.needs_review = True
                if message not in node.review_reasons:
                    node.review_reasons.append(message)


def _chains_from_lines(geometry: GeometryResult) -> list[_Chain]:
    chains: list[_Chain] = []
    for line in geometry.lines:
        if len(line.points) < 2 or line.line_type not in {"process", "signal", "other"}:
            continue
        chains.append(
            _Chain(
                ids=[line.id],
                points=[(float(point[0]), float(point[1])) for point in line.points],
                line_type=line.line_type,
                page=line.page,
                source=line.source,
            )
        )
    return chains


def _merge_chains(chains: list[_Chain], meetings: list[Meeting], nodes: list[Node], tolerance: float) -> list[_Chain]:
    pending = list(chains)
    changed = True
    while changed:
        changed = False
        for cluster in _endpoint_clusters(pending, tolerance):
            if len(cluster) != 2:
                continue
            (left_index, left_end), (right_index, right_end) = cluster
            if left_index == right_index:
                continue
            left, right = pending[left_index], pending[right_index]
            if left.page != right.page or left.line_type != right.line_type:
                continue
            point = left.points[0 if left_end == 0 else -1]
            if _blocked_merge(point, meetings, nodes, tolerance):
                note = "These lines meet without a junction classification, so they were not connected."
                if not _meeting_near(point, meetings, tolerance, {"junction"}):
                    left.review.append(note)
                    right.review.append(note)
                continue
            if not _continues(left, left_end, right, right_end):
                note = "These lines meet at an angle and Phase C did not call the point a junction, so they were not connected."
                left.review.append(note)
                right.review.append(note)
                continue
            pending[left_index] = _join(left, left_end, right, right_end)
            del pending[right_index]
            changed = True
            break
    return pending


def _endpoint_clusters(chains: list[_Chain], tolerance: float) -> list[list[tuple[int, int]]]:
    ends: list[tuple[int, int, tuple[float, float]]] = []
    for index, chain in enumerate(chains):
        ends.append((index, 0, chain.points[0]))
        ends.append((index, -1, chain.points[-1]))
    parent = list(range(len(ends)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left in range(len(ends)):
        for right in range(left + 1, len(ends)):
            if ends[left][0] == ends[right][0] and ends[left][1] == ends[right][1]:
                continue
            if _dist(ends[left][2], ends[right][2]) <= tolerance:
                parent[find(left)] = find(right)
    groups: dict[int, list[tuple[int, int]]] = {}
    for index, end in enumerate(ends):
        groups.setdefault(find(index), []).append((end[0], end[1]))
    return list(groups.values())


def _blocked_merge(point: tuple[float, float], meetings: list[Meeting], nodes: list[Node], tolerance: float) -> bool:
    if _meeting_near(point, meetings, tolerance, {"junction", "crossing", "ambiguous"}):
        return True
    return any(_dist_bbox(point, node) <= tolerance for node in nodes if node.type in _SYMBOL_KINDS or node.type == "terminal")


def _meeting_near(point: tuple[float, float], meetings: list[Meeting], tolerance: float, decisions: set[str]) -> bool:
    return any(meeting.decision in decisions and _dist(point, (meeting.position[0], meeting.position[1])) <= tolerance for meeting in meetings)


def _continues(left: _Chain, left_end: int, right: _Chain, right_end: int) -> bool:
    first = _into_chain(left, left_end)
    second = _into_chain(right, right_end)
    mag = math.hypot(*first) * math.hypot(*second)
    if mag == 0:
        return False
    cosine = (first[0] * second[0] + first[1] * second[1]) / mag
    return cosine <= cfg.COLLINEAR_COS_LIMIT


def _into_chain(chain: _Chain, end: int) -> tuple[float, float]:
    if end == 0:
        start, nxt = chain.points[0], chain.points[1]
    else:
        start, nxt = chain.points[-1], chain.points[-2]
    return (nxt[0] - start[0], nxt[1] - start[1])


def _join(left: _Chain, left_end: int, right: _Chain, right_end: int) -> _Chain:
    left_points = list(left.points if left_end == -1 else reversed(left.points))
    right_points = list(right.points if right_end == 0 else reversed(right.points))
    source = left.source if left.source == right.source else "raster"
    return _Chain(
        ids=left.ids + right.ids,
        points=left_points + right_points[1:],
        line_type=left.line_type,
        page=left.page,
        source=source,
        review=left.review + right.review,
    )


def _edges_from_chains(chains: list[_Chain], nodes: list[Node], node_tolerance: float) -> list[Edge]:
    created: dict[str, Node] = {}
    edges: list[Edge] = []
    for chain in chains:
        length = _polyline_length(chain.points)
        splits: list[tuple[float, Node, list[str]]] = []
        splits.append(_attach_end(chain.points[0], 0.0, chain, nodes, node_tolerance, created))
        splits.append(_attach_end(chain.points[-1], length, chain, nodes, node_tolerance, created))
        for node in nodes:
            if node.bbox is None or node.bbox.page != chain.page or node.type == "endpoint":
                continue
            distance, arc = _project(chain.points, _node_center(node))
            if distance <= node_tolerance and 1.0 < arc < length - 1.0:
                splits.append((arc, node, []))
        splits.sort(key=lambda item: item[0])
        ordered: list[tuple[float, Node, list[str]]] = []
        for split in splits:
            if ordered and abs(split[0] - ordered[-1][0]) < 1.0 and split[1].id == ordered[-1][1].id:
                continue
            ordered.append(split)
        for start, end in zip(ordered, ordered[1:]):
            if abs(end[0] - start[0]) < 0.5:
                continue
            piece = _slice(chain.points, start[0], end[0])
            if len(piece) < 2:
                continue
            review = list(dict.fromkeys(chain.review + start[2] + end[2]))
            candidates = [item for item in start[2] + end[2] if item.startswith("candidate:")]
            candidate_ids = [item.split(":", 1)[1] for item in candidates]
            review = [item for item in review if not item.startswith("candidate:")]
            score = cfg.RASTER_EDGE_SCORE if chain.source == "raster" else cfg.VECTOR_EDGE_SCORE
            midpoint = piece[len(piece) // 2]
            edges.append(
                Edge(
                    id=stable_id("edge", chain.page, midpoint[0], midpoint[1], "|".join(sorted(chain.ids))),
                    from_id=start[1].id,
                    to_id=end[1].id,
                    direction="unknown",
                    line_type=chain.line_type,  # type: ignore[arg-type]
                    polyline=[Point(x=point[0], y=point[1]) for point in piece],
                    confidence=_confidence(score, "The stroke was read. This score is not a confirmed connection."),
                    certainty=_certainty(score),  # type: ignore[arg-type]
                    evidence=[_evidence("geometry", f"Built from line(s) {', '.join(chain.ids)}.", chain.page)],
                    segment_ids=list(chain.ids),
                    needs_review=bool(review),
                    review_reasons=review,
                    candidate_ids=candidate_ids,
                )
            )
    nodes.extend(created.values())
    return edges


def _attach_end(
    point: tuple[float, float],
    arc: float,
    chain: _Chain,
    nodes: list[Node],
    node_tolerance: float,
    created: dict[str, Node],
) -> tuple[float, Node, list[str]]:
    nearby = [( _dist_bbox(point, node), node) for node in nodes if node.bbox and node.bbox.page == chain.page and node.type != "endpoint"]
    nearby = [(distance, node) for distance, node in nearby if distance <= node_tolerance]
    junctions = [(distance, node) for distance, node in nearby if node.type == "junction"]
    pool = junctions or nearby
    if pool:
        pool.sort(key=lambda item: (item[0], item[1].id))
        best = pool[0][0]
        tied = [node for distance, node in pool if distance <= best + cfg.TIE_EPSILON]
        if len(tied) == 1:
            return arc, tied[0], []
        review = [
            "More than one node is within the attachment tolerance at the same distance. Neither node was chosen.",
            *[f"candidate:{node.id}" for node in tied],
        ]
        return arc, _endpoint_node(point, chain, "tie:" + "|".join(sorted(node.id for node in tied)), created), review
    separate = any("not connected" in note for note in chain.review)
    salt = "|".join(chain.ids) if separate else ""
    review = ["This end meets another line, but that point is not a junction, so the lines were not connected."] if separate else []
    return arc, _endpoint_node(point, chain, salt, created), review


def _endpoint_node(point: tuple[float, float], chain: _Chain, salt: str, created: dict[str, Node]) -> Node:
    score = cfg.RASTER_EDGE_SCORE if chain.source == "raster" else cfg.VECTOR_EDGE_SCORE
    node = Node(
        id=stable_id("endpoint", chain.page, point[0], point[1], salt),
        type="endpoint",
        bbox=BBox(page=chain.page, x=point[0], y=point[1], w=0, h=0),
        confidence=_confidence(score, "This is a pipe end with no symbol or junction. It is not an inlet or an outlet."),
        certainty=_certainty(score),  # type: ignore[arg-type]
        reason="Pipe end kept because it does not meet a symbol or a junction.",
        evidence=[_evidence("geometry", "Free pipe end.", chain.page)],
        needs_review=True,
        review_reasons=["This pipe end does not meet a symbol or a junction."],
    )
    existing = created.get(node.id)
    if existing is not None:
        return existing
    created[node.id] = node
    return node


def _polyline_length(points: list[tuple[float, float]]) -> float:
    return sum(_dist(start, end) for start, end in zip(points, points[1:]))


def _project(points: list[tuple[float, float]], point: tuple[float, float]) -> tuple[float, float]:
    best_distance = float("inf")
    best_arc = 0.0
    walked = 0.0
    for start, end in zip(points, points[1:]):
        vx, vy = end[0] - start[0], end[1] - start[1]
        length_sq = vx * vx + vy * vy
        if length_sq == 0:
            continue
        ratio = max(0.0, min(1.0, ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length_sq))
        landed = (start[0] + ratio * vx, start[1] + ratio * vy)
        distance = _dist(point, landed)
        if distance < best_distance:
            best_distance = distance
            best_arc = walked + math.sqrt(length_sq) * ratio
        walked += math.sqrt(length_sq)
    return best_distance, best_arc


def _slice(points: list[tuple[float, float]], start_arc: float, end_arc: float) -> list[tuple[float, float]]:
    if end_arc < start_arc:
        start_arc, end_arc = end_arc, start_arc
    result: list[tuple[float, float]] = []
    walked = 0.0
    for start, end in zip(points, points[1:]):
        step = _dist(start, end)
        next_walk = walked + step
        if next_walk < start_arc:
            walked = next_walk
            continue
        if not result:
            result.append(_interpolate(start, end, start_arc - walked, step))
        if next_walk >= end_arc:
            result.append(_interpolate(start, end, end_arc - walked, step))
            break
        result.append(end)
        walked = next_walk
    return result


def _interpolate(start: tuple[float, float], end: tuple[float, float], along: float, step: float) -> tuple[float, float]:
    if step <= 0:
        return start
    ratio = max(0.0, min(1.0, along / step))
    return (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)


def _apply_direction(edges: list[Edge], nodes: list[Node], detections: DetectionResult) -> None:
    by_id = {node.id: node for node in nodes}
    arrows = [item for item in detections.items if item.kind == "arrow" and item.direction in cfg.DIRECTION_VECTORS]
    for edge in edges:
        votes: list[tuple[str, Evidence]] = []
        for arrow in arrows:
            anchor = by_id.get(edge.from_id)
            if anchor is None or anchor.bbox is None or arrow.page != anchor.bbox.page:
                continue
            center = _center_of(arrow.bbox)
            distance, _arc = _project([(point.x, point.y) for point in edge.polyline], center)
            if distance > cfg.ARROW_ON_PIPE_TOLERANCE:
                continue
            choice = _align(edge, cfg.DIRECTION_VECTORS[arrow.direction])
            if choice is None:
                continue
            votes.append((choice, _evidence("arrow", f"An arrow on the line points {arrow.direction}.", arrow.page)))
        votes.extend(_symbol_direction_votes(edge, by_id))
        chosen = {vote[0] for vote in votes}
        edge.direction_evidence = [vote[1] for vote in votes]
        if len(chosen) == 1:
            edge.direction = next(iter(chosen))  # type: ignore[assignment]
            edge.evidence.append(votes[0][1])
        elif len(chosen) > 1:
            edge.direction = "unknown"
            edge.needs_review = True
            edge.review_reasons.append("Direction evidence disagrees, so the direction was left unknown.")
        else:
            edge.direction = "unknown"


def _symbol_direction_votes(edge: Edge, by_id: dict[str, Node]) -> list[tuple[str, Evidence]]:
    votes: list[tuple[str, Evidence]] = []
    for node_id in (edge.from_id, edge.to_id):
        node = by_id.get(node_id)
        if node is None:
            continue
        if node.type == "valve" and node.subtype == "check":
            vector = _vector_from_reason(node)
            choice = _align(edge, vector) if vector else None
            if choice:
                votes.append((choice, _evidence("check_valve", "The check-valve direction recorded on the symbol was used.", node.bbox.page if node.bbox else None)))
        if node.type == "equipment" and cfg.NOZZLE_MARKER in " ".join(item.description.lower() for item in node.evidence):
            vector = _vector_from_reason(node)
            choice = _align(edge, vector) if vector else None
            if choice:
                votes.append((choice, _evidence("nozzle", "A recorded nozzle direction was used. Page position was not used.", node.bbox.page if node.bbox else None)))
        if node.type == "terminal" and node.subtype in {"in", "out"}:
            choice = _terminal_choice(edge, node)
            if choice:
                text = "The terminal label says flow leaves the drawing." if node.subtype == "out" else "The terminal label says flow enters the drawing."
                votes.append((choice, _evidence("terminal", text, node.bbox.page if node.bbox else None)))
    return votes


def _vector_from_reason(node: Node) -> tuple[float, float] | None:
    if node.pointing in cfg.DIRECTION_VECTORS:
        return cfg.DIRECTION_VECTORS[node.pointing]
    text = " ".join([node.reason, node.subtype, *[item.description for item in node.evidence]]).lower()
    for name, vector in cfg.DIRECTION_VECTORS.items():
        if name in text:
            return vector
    return None


def _align(edge: Edge, vector: tuple[float, float]) -> str | None:
    if len(edge.polyline) < 2:
        return None
    start, end = edge.polyline[0], edge.polyline[-1]
    tangent = (end.x - start.x, end.y - start.y)
    mag = math.hypot(*tangent) * math.hypot(*vector)
    if mag == 0:
        return None
    cosine = (tangent[0] * vector[0] + tangent[1] * vector[1]) / mag
    if cosine >= cfg.DIRECTION_COS_MIN:
        return "forward"
    if cosine <= -cfg.DIRECTION_COS_MIN:
        return "reverse"
    return None


def _terminal_choice(edge: Edge, node: Node) -> str | None:
    """Flow out means the edge runs toward the terminal. Flow in means the opposite."""
    toward = "forward" if edge.to_id == node.id else "reverse"
    if node.subtype == "out":
        return toward
    if node.subtype == "in":
        return "reverse" if toward == "forward" else "forward"
    return None


def _attach_instruments(nodes: list[Node], edges: list[Edge], node_tolerance: float) -> None:
    by_id = {node.id: node for node in nodes}
    for node in nodes:
        if node.type != "instrument" or node.bbox is None:
            continue
        signal = [
            edge
            for edge in edges
            if edge.line_type == "signal" and node.id in {edge.from_id, edge.to_id}
        ]
        if signal:
            other_id = signal[0].to_id if signal[0].from_id == node.id else signal[0].from_id
            node.attachment = "via_signal_line"
            node.attachment_target = other_id
            node.evidence.append(_evidence("signal_line", "A signal line ends on this instrument.", node.bbox.page))
            continue
        center = _node_center(node)
        process = [edge for edge in edges if edge.line_type == "process" and edge.polyline]
        nearest_edge = None
        nearest_distance = float("inf")
        for edge in process:
            distance, _arc = _project([(point.x, point.y) for point in edge.polyline], center)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_edge = edge
        if nearest_edge is not None and nearest_distance <= cfg.INSTRUMENT_PIPE_TOLERANCE:
            node.attachment = "on_pipe"
            node.attachment_target = nearest_edge.id
            node.evidence.append(_evidence("proximity", f"The bubble is {nearest_distance:.1f} pt from a process line.", node.bbox.page))
            continue
        equipment = [item for item in nodes if item.type == "equipment" and item.bbox and item.bbox.page == node.bbox.page]
        nearest_equipment = None
        equipment_distance = float("inf")
        for item in equipment:
            distance = _dist_bbox(center, item)
            if distance < equipment_distance:
                equipment_distance = distance
                nearest_equipment = item
        if nearest_equipment is not None and equipment_distance <= cfg.INSTRUMENT_EQUIPMENT_TOLERANCE:
            node.attachment = "on_equipment"
            node.attachment_target = nearest_equipment.id
            node.evidence.append(_evidence("proximity", f"The bubble is {equipment_distance:.1f} pt from equipment.", node.bbox.page))
            continue
        node.attachment = "unattached"
        node.needs_review = True
        node.review_reasons.append("No pipe, equipment, or signal line is close enough to attach this instrument.")
    _ = by_id
    _ = node_tolerance


def _structure(nodes: list[Node], edges: list[Edge]) -> list[StructureNote]:
    degree = {node.id: 0 for node in nodes}
    for edge in edges:
        degree[edge.from_id] = degree.get(edge.from_id, 0) + 1
        degree[edge.to_id] = degree.get(edge.to_id, 0) + 1
    notes: list[StructureNote] = []
    orphans = [node.id for node in nodes if degree.get(node.id, 0) == 0 and node.type != "endpoint"]
    if orphans:
        notes.append(StructureNote(kind="orphan", item_ids=orphans, message="These nodes have no pipe or signal edge."))
    dead = [node.id for node in nodes if node.type == "endpoint"]
    if dead:
        notes.append(StructureNote(kind="dead_end", item_ids=dead, message="These pipe ends do not meet a symbol or a junction."))
    loose = [node.id for node in nodes if node.type == "instrument" and node.attachment == "unattached"]
    if loose:
        notes.append(StructureNote(kind="unattached_instrument", item_ids=loose, message="These instruments were kept and were not attached."))
    duplicates = [node.id for node in nodes if any("same spot" in reason for reason in node.review_reasons)]
    if duplicates:
        notes.append(StructureNote(kind="duplicate", item_ids=duplicates, message="These nodes occupy the same location and were both kept."))
    components = _components(nodes, edges)
    if len(components) > 1:
        notes.append(
            StructureNote(
                kind="disconnected",
                item_ids=[item for group in components for item in group],
                message=f"The graph has {len(components)} separate components. They were not joined.",
            )
        )
    return notes


def _components(nodes: list[Node], edges: list[Edge]) -> list[list[str]]:
    parent = {node.id: node.id for node in nodes}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for edge in edges:
        if edge.from_id in parent and edge.to_id in parent:
            parent[find(edge.from_id)] = find(edge.to_id)
    groups: dict[str, list[str]] = {}
    for node in nodes:
        groups.setdefault(find(node.id), []).append(node.id)
    return list(groups.values())


def _preserved(meeting: Meeting) -> PreservedMeeting:
    return PreservedMeeting(
        id=meeting.id,
        page=meeting.page,
        position=list(meeting.position),
        line_ids=list(meeting.line_ids),
        decision=meeting.decision,
        reason=meeting.reason,
    )
