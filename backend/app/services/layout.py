"""Left-to-right orthogonal layout using elkjs. Coordinates come from ELK.

Unknown direction is not turned into a direction, and those edges get no arrowhead.
A graph over the size limit returns a structured error and no coordinates.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from app import graph_config as cfg
from app.errors import AppError
from app.schemas.graph import SimplifiedGraph
from app.services.storage import LAYOUT_NAME, job_folder, read_json, write_json

logger = logging.getLogger("untangle.layout")

class LayoutNode(BaseModel):
    id: str
    x: float
    y: float
    width: float
    height: float
    arrowhead: bool = False
    direction: str = "unknown"
    group_id: str = ""


class LayoutEdge(BaseModel):
    id: str
    points: list[list[float]]
    bends: int = 0
    direction: str = "unknown"
    arrowhead: bool = False
    line_type: str = "process"


class LayoutCrossing(BaseModel):
    x: float
    y: float
    edge_ids: list[str]
    kind: Literal["jump"] = "jump"


class LayoutGroup(BaseModel):
    id: str
    x: float
    y: float
    width: float
    height: float
    member_ids: list[str] = Field(default_factory=list)


class LayoutResult(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    message: str = ""
    nodes: list[LayoutNode] = Field(default_factory=list)
    edges: list[LayoutEdge] = Field(default_factory=list)
    crossings: list[LayoutCrossing] = Field(default_factory=list)
    groups: list[LayoutGroup] = Field(default_factory=list)
    route_clear: bool = True
    processing_version: str = ""


def layout_graph(graph: SimplifiedGraph) -> LayoutResult:
    """Lay out a simplified graph. An oversized graph raises AppError and invents nothing."""
    if len(graph.nodes) > cfg.MAX_LAYOUT_NODES:
        raise AppError(
            422,
            "LAYOUT_TOO_LARGE",
            f"This graph has {len(graph.nodes)} nodes. The layout limit is {cfg.MAX_LAYOUT_NODES}. No coordinates were invented.",
            {"nodes": len(graph.nodes), "limit": cfg.MAX_LAYOUT_NODES},
        )
    if not graph.nodes:
        return LayoutResult(status="ok", message="The simplified graph has no nodes.", processing_version=cfg.LAYOUT_VERSION)
    payload = _elk_graph(graph)
    laid = _run_elk(payload)
    return _read_layout(graph, laid)


def load_layout(upload_dir: str, job_id: str) -> LayoutResult:
    """Read layout.json. A missing file is a 404."""
    path = job_folder(upload_dir, job_id) / LAYOUT_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The layout has not been built for this project.", {"job_id": job_id})
    return LayoutResult.model_validate(read_json(path))


def write_layout(upload_dir: str, job_id: str, result: LayoutResult) -> None:
    """Write layout.json. The original upload is not touched."""
    write_json(job_folder(upload_dir, job_id) / LAYOUT_NAME, result.model_dump(mode="json"))


def _script_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[3] / "tools" / "layout" / "elk_layout.mjs"


def _elk_graph(graph: SimplifiedGraph) -> dict:
    children = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        width = max(cfg.DEFAULT_NODE_WIDTH, node.bbox.w if node.bbox else cfg.DEFAULT_NODE_WIDTH)
        height = max(cfg.DEFAULT_NODE_HEIGHT, node.bbox.h if node.bbox else cfg.DEFAULT_NODE_HEIGHT)
        child: dict = {"id": node.id, "width": width, "height": height}
        constraint = _terminal_constraint(node, graph)
        if constraint:
            child["layoutOptions"] = {"elk.layered.layering.layerConstraint": constraint}
        children.append(child)
    return {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.spacing.nodeNode": str(cfg.LAYOUT_NODE_GAP),
            "elk.layered.spacing.nodeNodeBetweenLayers": str(cfg.LAYOUT_LAYER_GAP),
            "elk.spacing.edgeNode": str(cfg.LAYOUT_ROUTE_MARGIN),
            "elk.layered.spacing.edgeNodeBetweenLayers": str(cfg.LAYOUT_ROUTE_MARGIN),
            "elk.separateConnectedComponents": "true",
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
        },
        "children": children,
        "edges": [
            {"id": edge.id, "sources": [edge.from_id], "targets": [edge.to_id]}
            for edge in sorted(graph.edges, key=lambda item: item.id)
        ],
    }


def layout_with_groups(graph: SimplifiedGraph, groups: dict[str, list[str]] | None = None) -> LayoutResult:
    """Lay out, wrapping named groups so their members stay together."""
    if len(graph.nodes) > cfg.MAX_LAYOUT_NODES:
        return layout_graph(graph)
    if not graph.nodes:
        return layout_graph(graph)
    payload = _elk_graph(graph)
    if groups:
        by_id = {child["id"]: child for child in payload["children"]}
        payload["children"] = [child for child in payload["children"] if child["id"] not in {member for members in groups.values() for member in members}]
        for group_id, members in sorted(groups.items()):
            kids = [by_id[member] for member in sorted(members) if member in by_id]
            if len(kids) < 2:
                payload["children"].extend(kids)
                continue
            payload["children"].append({
                "id": group_id,
                "layoutOptions": {"elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.padding": "[top=16,left=16,bottom=16,right=16]"},
                "children": kids,
            })
    laid = _run_elk(payload)
    result = _read_layout(graph, laid)
    result.groups = _groups_from_elk(laid, groups or {})
    return result


def _terminal_constraint(node, graph: SimplifiedGraph) -> str:
    if node.type != "terminal":
        return ""
    if node.subtype == "in":
        return "FIRST"
    if node.subtype == "out":
        return "LAST"
    # No invented side when the terminal does not state a direction.
    return ""


def _run_elk(payload: dict) -> dict:
    script = _script_path()
    if not script.is_file():
        logger.info("layout script missing")
        raise AppError(500, "LAYOUT_ENGINE_MISSING", "The elkjs layout script is not available.")
    completed = subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        logger.info("layout engine failed")
        raise AppError(500, "LAYOUT_ENGINE_FAILED", "ELK did not return a layout. No coordinates were invented.")
    return json.loads(completed.stdout)


def _read_layout(graph: SimplifiedGraph, laid: dict) -> LayoutResult:
    directions = {edge.id: edge.direction for edge in graph.edges}
    line_types = {edge.id: edge.line_type for edge in graph.edges}
    nodes: list[LayoutNode] = []
    _collect_nodes(laid, 0.0, 0.0, "", nodes)
    edges = [_edge_from_elk(edge, directions.get(edge["id"], "unknown"), line_types.get(edge["id"], "process")) for edge in _collect_edges(laid)]
    nodes.sort(key=lambda item: item.id)
    edges = [_clear_route(edge, graph, nodes) for edge in edges]
    edges.sort(key=lambda item: item.id)
    crossings = _crossings(edges)
    route_clear = _routes_clear(graph, nodes, edges)
    status = "ok" if route_clear else "degraded"
    message = "" if route_clear else "A route still meets a node box after it was moved outside that box."
    return LayoutResult(
        status=status,
        message=message,
        nodes=nodes,
        edges=edges,
        crossings=crossings,
        route_clear=route_clear,
        processing_version=cfg.LAYOUT_VERSION,
    )


def _collect_nodes(container: dict, origin_x: float, origin_y: float, group_id: str, found: list[LayoutNode]) -> None:
    for child in container.get("children", []):
        absolute_x = origin_x + float(child.get("x", 0))
        absolute_y = origin_y + float(child.get("y", 0))
        if child.get("children"):
            _collect_nodes(child, absolute_x, absolute_y, child["id"], found)
            continue
        found.append(LayoutNode(id=child["id"], x=absolute_x, y=absolute_y, width=float(child["width"]), height=float(child["height"]), group_id=group_id))


def _collect_edges(container: dict) -> list[dict]:
    found = list(container.get("edges", []))
    for child in container.get("children", []):
        found.extend(_collect_edges(child))
    return found


def _edge_from_elk(edge: dict, direction: str, line_type: str) -> LayoutEdge:
    points: list[list[float]] = []
    bends = 0
    for section in edge.get("sections", []):
        start = section.get("startPoint")
        if start:
            points.append([float(start["x"]), float(start["y"])])
        for bend in section.get("bendPoints", []):
            points.append([float(bend["x"]), float(bend["y"])])
            bends += 1
        end = section.get("endPoint")
        if end:
            points.append([float(end["x"]), float(end["y"])])
    known = direction in {"forward", "reverse"}
    return LayoutEdge(id=edge["id"], points=points, bends=bends, direction=direction, arrowhead=known, line_type=line_type)


def _groups_from_elk(laid: dict, groups: dict[str, list[str]]) -> list[LayoutGroup]:
    found: list[LayoutGroup] = []
    def walk(container: dict, origin_x: float, origin_y: float) -> None:
        for child in container.get("children", []):
            if child["id"] not in groups:
                continue
            found.append(LayoutGroup(
                id=child["id"],
                x=origin_x + float(child.get("x", 0)),
                y=origin_y + float(child.get("y", 0)),
                width=float(child.get("width", 0)),
                height=float(child.get("height", 0)),
                member_ids=sorted(groups[child["id"]]),
            ))
    walk(laid, 0.0, 0.0)
    return found


def _crossings(edges: list[LayoutEdge]) -> list[LayoutCrossing]:
    found: list[LayoutCrossing] = []
    for index, left in enumerate(edges):
        for right in edges[index + 1 :]:
            for start, end in zip(left.points, left.points[1:]):
                for other_start, other_end in zip(right.points, right.points[1:]):
                    point = _proper_cross(start, end, other_start, other_end)
                    if point is None:
                        continue
                    found.append(LayoutCrossing(x=point[0], y=point[1], edge_ids=sorted([left.id, right.id])))
    return found


def _proper_cross(a0: list[float], a1: list[float], b0: list[float], b1: list[float]) -> tuple[float, float] | None:
    horizontal = abs(a0[1] - a1[1]) < 0.1 and abs(b0[0] - b1[0]) < 0.1
    vertical = abs(a0[0] - a1[0]) < 0.1 and abs(b0[1] - b1[1]) < 0.1
    if horizontal:
        x, y = b0[0], a0[1]
        if min(a0[0], a1[0]) < x < max(a0[0], a1[0]) and min(b0[1], b1[1]) < y < max(b0[1], b1[1]):
            return (x, y)
    if vertical:
        x, y = a0[0], b0[1]
        if min(b0[0], b1[0]) < x < max(b0[0], b1[0]) and min(a0[1], a1[1]) < y < max(a0[1], a1[1]):
            return (x, y)
    return None


def _clear_route(edge: LayoutEdge, graph: SimplifiedGraph, nodes: list[LayoutNode]) -> LayoutEdge:
    """Pull a route out of node boxes. The direction is not changed."""
    source = next((item for item in graph.edges if item.id == edge.id), None)
    owned = {source.from_id, source.to_id} if source else set()
    points = list(edge.points)
    by_id = {node.id: node for node in nodes}
    if source and points:
        points = _clip_end(points, by_id.get(source.from_id), at_start=True)
        points = _clip_end(points, by_id.get(source.to_id), at_start=False)
    for _ in range(4):
        nxt: list[list[float]] = []
        changed = False
        for start, end in zip(points, points[1:]):
            if not nxt:
                nxt.append(start)
            blocker = next((node for node in nodes if node.id not in owned and _segment_hits_box(start, end, node)), None)
            if blocker is None:
                nxt.append(end)
                continue
            detour = _detour(start, end, blocker)
            nxt.extend(detour[1:])
            changed = True
        points = nxt or points
        if not changed:
            break
    bends = sum(1 for index in range(1, len(points) - 1) if _turns(points[index - 1], points[index], points[index + 1]))
    return edge.model_copy(update={"points": points, "bends": bends})


def _clip_end(points: list[list[float]], node: LayoutNode | None, *, at_start: bool) -> list[list[float]]:
    if node is None or len(points) < 2:
        return points
    if at_start and _inside(points[0], node):
        points = [_border(points[0], points[1], node), *points[1:]]
    if not at_start and _inside(points[-1], node):
        points = [*points[:-1], _border(points[-1], points[-2], node)]
    return points


def _border(inside: list[float], outside: list[float], node: LayoutNode) -> list[float]:
    """Move a point that sits inside a box to the box edge, toward the other point."""
    low, high = 0.0, 1.0
    for _ in range(12):
        mid = (low + high) / 2
        x = inside[0] + (outside[0] - inside[0]) * mid
        y = inside[1] + (outside[1] - inside[1]) * mid
        if _inside([x, y], node):
            low = mid
        else:
            high = mid
    return [inside[0] + (outside[0] - inside[0]) * high, inside[1] + (outside[1] - inside[1]) * high]


def _detour(start: list[float], end: list[float], node: LayoutNode) -> list[list[float]]:
    margin = cfg.LAYOUT_ROUTE_MARGIN
    if abs(start[1] - end[1]) <= 0.2:
        above = node.y - margin
        below = node.y + node.height + margin
        y = above if abs(start[1] - above) <= abs(start[1] - below) else below
        return [start, [start[0], y], [end[0], y], end]
    if abs(start[0] - end[0]) <= 0.2:
        left = node.x - margin
        right = node.x + node.width + margin
        x = left if abs(start[0] - left) <= abs(start[0] - right) else right
        return [start, [x, start[1]], [x, end[1]], end]
    return [start, end]


def _turns(before: list[float], corner: list[float], after: list[float]) -> bool:
    first = (corner[0] - before[0], corner[1] - before[1])
    second = (after[0] - corner[0], after[1] - corner[1])
    return abs(first[0] * second[1] - first[1] * second[0]) > 0.1


def _inside(point: list[float], node: LayoutNode) -> bool:
    return node.x < point[0] < node.x + node.width and node.y < point[1] < node.y + node.height


def _routes_clear(graph: SimplifiedGraph, nodes: list[LayoutNode], edges: list[LayoutEdge]) -> bool:
    owned = {edge.id: {edge.from_id, edge.to_id} for edge in graph.edges}
    for edge in edges:
        skip = owned.get(edge.id, set())
        for start, end in zip(edge.points, edge.points[1:]):
            for node in nodes:
                if node.id in skip:
                    continue
                if _segment_hits_box(start, end, node):
                    return False
    return True


def _segment_hits_box(start: list[float], end: list[float], node: LayoutNode) -> bool:
    # Endpoints may touch the border of the nodes they connect. An interior hit is not allowed.
    padding = 0.5
    left, right = node.x + padding, node.x + node.width - padding
    top, bottom = node.y + padding, node.y + node.height - padding
    samples = 5
    for step in range(1, samples):
        ratio = step / samples
        x = start[0] + (end[0] - start[0]) * ratio
        y = start[1] + (end[1] - start[1]) * ratio
        if left < x < right and top < y < bottom:
            return True
    return False
