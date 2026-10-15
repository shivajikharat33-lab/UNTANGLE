"""Item details and traces. Unknown direction stops the flow trace.

A crossing is not a connection, so a trace only walks stored edges.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Evidence, SimplifiedGraph
from app.schemas.reports import TagReport
from app import graph_config as cfg


class ItemDetail(BaseModel):
    """Facts already stored for one node or edge."""

    id: str
    type: str
    tag: str = ""
    confidence: Confidence
    certainty: str = "uncertain"
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    needs_review: bool = False
    patterns: list[str] = Field(default_factory=list)
    io_status: str = ""
    original_ids: list[str] = Field(default_factory=list)
    bbox: BBox | None = None
    direction: str = ""
    line_type: str = ""


class TraceStep(BaseModel):
    id: str
    via_edge: str = ""
    note: str = ""


class TraceResult(BaseModel):
    start_id: str
    mode: str
    depth: int
    traced_ids: list[str] = Field(default_factory=list)
    stopped: list[str] = Field(default_factory=list)
    note: str = ""


def item_detail(graph: DiagramGraph, simplified: SimplifiedGraph | None, report: TagReport | None, item_id: str) -> ItemDetail:
    """Return one stored item. An unknown id is an error, not an empty success."""
    simplified_node = next((node for node in (simplified.nodes if simplified else []) if node.id == item_id or item_id in node.original_ids), None)
    simplified_edge = next((edge for edge in (simplified.edges if simplified else []) if edge.id == item_id or item_id in edge.original_ids), None)
    target = item_id
    original_ids = [item_id]
    if simplified_node is not None:
        original_ids = simplified_node.original_ids or [simplified_node.id]
        target = original_ids[0]
    elif simplified_edge is not None:
        original_ids = simplified_edge.original_ids or [simplified_edge.id]
        target = original_ids[0]
    node = next((item for item in graph.nodes if item.id == target or item.id == item_id), None)
    edge = next((item for item in graph.edges if item.id == target or item.id == item_id), None)
    if node is None and edge is None and simplified_node is None and simplified_edge is None:
        raise AppError(404, "NOT_FOUND", "That item is not in the graph.", {"item_id": item_id})
    source = node or edge or simplified_node or simplified_edge
    assert source is not None
    findings = [finding.message for finding in graph.findings if source.id in finding.affected_ids or item_id in finding.affected_ids]
    patterns = [pattern.id for pattern in graph.patterns if source.id in pattern.member_node_ids or source.id in pattern.member_edge_ids]
    io_status = ""
    tag = getattr(source, "tag", "")
    if report and tag:
        row = next((item for item in report.rows if item.tag.upper() == tag.upper()), None)
        io_status = row.status if row else "no row"
    return ItemDetail(
        id=item_id,
        type=getattr(source, "type", None) or getattr(source, "line_type", "edge"),
        tag=tag,
        confidence=source.confidence,
        certainty=source.certainty,
        evidence=list(source.evidence),
        findings=findings,
        review_reasons=list(source.review_reasons),
        needs_review=source.needs_review,
        patterns=patterns,
        io_status=io_status,
        original_ids=original_ids,
        bbox=getattr(source, "bbox", None),
        direction=getattr(source, "direction", ""),
        line_type=getattr(source, "line_type", ""),
    )


def trace_item(graph: DiagramGraph, item_id: str, mode: str, depth: int | None = None) -> TraceResult:
    """Walk edges. Flow stops where direction is unknown. Connectivity is separate."""
    if mode not in {"downstream", "upstream", "connected"}:
        raise AppError(422, "TRACE_MODE", "Trace mode must be downstream, upstream, or connected.", {"mode": mode})
    limit = depth if depth is not None else cfg.TRACE_MAX_DEPTH
    start_nodes = _start_nodes(graph, item_id)
    if not start_nodes:
        raise AppError(404, "NOT_FOUND", "That item is not in the graph.", {"item_id": item_id})
    seen = set(start_nodes)
    traced = list(start_nodes)
    stopped: list[str] = []
    frontier = list(start_nodes)
    for _step in range(limit):
        nxt: list[str] = []
        for node_id in frontier:
            for neighbor, edge, allowed, reason in _steps(graph, node_id, mode):
                if neighbor in seen:
                    continue
                if not allowed:
                    stopped.append(f"{edge.id}: {reason}")
                    continue
                seen.add(neighbor)
                traced.append(neighbor)
                nxt.append(neighbor)
        frontier = nxt
        if not frontier:
            break
    note = "Connectivity, not flow." if mode == "connected" else "Flow uses only forward and reverse edges."
    return TraceResult(start_id=item_id, mode=mode, depth=limit, traced_ids=traced, stopped=stopped, note=note)


def _start_nodes(graph: DiagramGraph, item_id: str) -> list[str]:
    if any(node.id == item_id for node in graph.nodes):
        return [item_id]
    edge = next((item for item in graph.edges if item.id == item_id), None)
    if edge is None:
        return []
    return [edge.from_id, edge.to_id]


def _steps(graph: DiagramGraph, node_id: str, mode: str) -> list[tuple[str, object, bool, str]]:
    steps: list[tuple[str, object, bool, str]] = []
    for edge in graph.edges:
        if node_id not in {edge.from_id, edge.to_id}:
            continue
        other = edge.to_id if edge.from_id == node_id else edge.from_id
        if mode == "connected":
            steps.append((other, edge, True, ""))
            continue
        if edge.direction not in {"forward", "reverse", "bidirectional"}:
            steps.append((other, edge, False, "direction unknown, trace stopped here"))
            continue
        leaving = edge.direction == "bidirectional" or (
            edge.direction == "forward" and edge.from_id == node_id
        ) or (edge.direction == "reverse" and edge.to_id == node_id)
        if mode == "downstream" and leaving:
            steps.append((other, edge, True, ""))
        elif mode == "upstream" and not leaving and edge.direction != "bidirectional":
            steps.append((other, edge, True, ""))
        elif mode == "upstream" and edge.direction == "bidirectional":
            steps.append((other, edge, True, ""))
        else:
            steps.append((other, edge, False, "this edge does not run that way"))
    return steps
