"""Build a simplified copy of the graph. The original graph is not changed.

Pass-through junctions collapse only when no tagged symbol, review flag, or
known flow is lost. Parallel edges merge only when they say the same thing.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from app import graph_config as cfg
from app.errors import AppError
from app.schemas.graph import DiagramGraph, Edge, LedgerEntry, Node, SimplifiedEdge, SimplifiedGraph, SimplifiedNode
from app.services.storage import SIMPLIFIED_NAME, job_folder, read_json, write_json

_KEPT_TYPES = {"equipment", "valve", "instrument", "terminal"}


def simplify_graph(graph: DiagramGraph) -> SimplifiedGraph:
    """Return a new simplified graph. `graph` is left unchanged."""
    before = graph.model_dump()
    sources: dict[str, list[str]] = {}
    kinds: dict[str, str] = {}
    nodes = {node.id: node.model_copy(deep=True) for node in graph.nodes}
    edges = {edge.id: edge.model_copy(deep=True) for edge in graph.edges}
    _collapse(nodes, edges, _protected_ids(graph), sources, kinds)
    _merge_parallel(edges, sources, kinds)
    result = _assemble(graph, nodes, edges, sources, kinds)
    if graph.model_dump() != before:
        raise RuntimeError("simplify_graph changed the original graph")
    return result


def load_simplified(upload_dir: str, job_id: str) -> SimplifiedGraph:
    """Read simplified.json. A missing file is a 404."""
    path = job_folder(upload_dir, job_id) / SIMPLIFIED_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The simplified graph has not been built for this project.", {"job_id": job_id})
    return SimplifiedGraph.model_validate(read_json(path))


def write_simplified(upload_dir: str, job_id: str, graph: SimplifiedGraph) -> None:
    """Write simplified.json. graph.json and the original files are not touched."""
    write_json(job_folder(upload_dir, job_id) / SIMPLIFIED_NAME, graph.model_dump(mode="json"))


def _protected_ids(graph: DiagramGraph) -> set[str]:
    protected = {node.id for node in graph.nodes if node.type in _KEPT_TYPES or node.tag or node.needs_review or node.type == "endpoint"}
    for pattern in graph.patterns:
        protected.update(pattern.member_node_ids)
    return protected


def _collapse(nodes: dict[str, Node], edges: dict[str, Edge], protected: set[str], sources: dict[str, list[str]], kinds: dict[str, str]) -> None:
    changed = True
    while changed:
        changed = False
        for node_id in sorted(list(nodes)):
            node = nodes.get(node_id)
            if node is None or node_id in protected or node.type != "junction":
                continue
            incident = [edge for edge in edges.values() if node_id in {edge.from_id, edge.to_id}]
            if len(incident) != cfg.PASS_THROUGH_DEGREE or any(edge.needs_review or edge.candidate_ids for edge in incident):
                continue
            merged = _merge_pair(incident[0], incident[1], node_id, sources)
            if merged is None:
                continue
            del edges[incident[0].id]
            del edges[incident[1].id]
            edges[merged.id] = merged
            kinds[merged.id] = "collapse"
            del nodes[node_id]
            changed = True
            break


def _merge_pair(left: Edge, right: Edge, junction_id: str, sources: dict[str, list[str]]) -> Edge | None:
    left_end = left.to_id if left.from_id == junction_id else left.from_id
    right_end = right.to_id if right.from_id == junction_id else right.from_id
    if left_end == junction_id or right_end == junction_id or left_end == right_end:
        return None
    direction = _combined_direction(left, right, junction_id)
    if direction is None:
        return None
    original = sorted(set(sources.get(left.id, [left.id]) + sources.get(right.id, [right.id])))
    merged = left.model_copy(
        update={
            "id": _stable("edge", original),
            "from_id": left_end,
            "to_id": right_end,
            "direction": direction,
            "segment_ids": sorted(set(left.segment_ids + right.segment_ids)),
            "evidence": left.evidence + right.evidence,
            "direction_evidence": left.direction_evidence + right.direction_evidence,
            "needs_review": False,
            "review_reasons": [],
            "candidate_ids": [],
        }
    )
    sources[merged.id] = original
    return merged


def _combined_direction(left: Edge, right: Edge, junction_id: str) -> str | None:
    """Direction from the left outer end toward the right outer end. None means flow would be lost."""
    left_side = _toward_junction(left, junction_id)
    right_side = _toward_junction(right, junction_id)
    if left_side == "in" and right_side == "in":
        return None
    if left_side == "out" and right_side == "out":
        return None
    if left_side == "in" and right_side in {"out", "either"}:
        return "forward"
    if left_side == "out" and right_side in {"in", "either"}:
        return "reverse"
    if left_side == "either" and right_side == "out":
        return "forward"
    if left_side == "either" and right_side == "in":
        return "reverse"
    return "unknown"


def _toward_junction(edge: Edge, junction_id: str) -> str:
    if edge.direction in {"unknown", "bidirectional"}:
        return "either"
    arrives = (edge.direction == "forward" and edge.to_id == junction_id) or (edge.direction == "reverse" and edge.from_id == junction_id)
    return "in" if arrives else "out"


def _merge_parallel(edges: dict[str, Edge], sources: dict[str, list[str]], kinds: dict[str, str]) -> None:
    groups: dict[tuple[str, str, str, str], list[Edge]] = defaultdict(list)
    for edge in edges.values():
        if edge.needs_review or edge.candidate_ids:
            continue
        groups[(edge.from_id, edge.to_id, edge.line_type, edge.direction)].append(edge)
    for group in groups.values():
        if len(group) < 2:
            continue
        signature = [tuple(item.description for item in edge.evidence) for edge in group]
        if len(set(signature)) != 1:
            continue
        original = sorted({item for edge in group for item in sources.get(edge.id, [edge.id])})
        merged = group[0].model_copy(update={"id": _stable("parallel", original), "segment_ids": sorted({segment for edge in group for segment in edge.segment_ids})})
        for edge in group:
            del edges[edge.id]
        sources[merged.id] = original
        kinds[merged.id] = "parallel"
        edges[merged.id] = merged


def _assemble(graph: DiagramGraph, nodes: dict[str, Node], edges: dict[str, Edge], sources: dict[str, list[str]], kinds: dict[str, str]) -> SimplifiedGraph:
    simple_nodes = [SimplifiedNode(**node.model_dump(), original_ids=[node.id]) for node in sorted(nodes.values(), key=lambda item: item.id)]
    simple_edges: list[SimplifiedEdge] = []
    for edge in sorted(edges.values(), key=lambda item: item.id):
        simple_edges.append(SimplifiedEdge(**edge.model_dump(), original_ids=sources.get(edge.id, [edge.id])))
    kept_nodes = {node_id for node in simple_nodes for node_id in node.original_ids}
    ledger: list[LedgerEntry] = []
    id_map: dict[str, str] = {}
    for node in graph.nodes:
        if node.id in kept_nodes:
            id_map[node.id] = node.id
        else:
            id_map[node.id] = ""
            ledger.append(_entry(node.id, node.type, node, "collapsed_passthrough", "This pass-through junction was collapsed. No tag, valve, instrument, or conflicting flow was on it."))
    for edge in graph.edges:
        owner = next((item for item in simple_edges if edge.id in item.original_ids), None)
        if owner is None:
            id_map[edge.id] = ""
            ledger.append(_entry(edge.id, "edge", None, "collapsed_passthrough", "This edge was removed and has no simplified edge. The connectivity check will fail."))
            continue
        id_map[edge.id] = owner.id
        if owner.id == edge.id:
            continue
        code = "merged_parallel_edge" if kinds.get(owner.id) == "parallel" else "collapsed_passthrough"
        text = "This duplicate edge was merged." if code == "merged_parallel_edge" else "This edge was merged through a pass-through junction."
        ledger.append(_entry(edge.id, "edge", None, code, text))
    accounted = kept_nodes | {edge.id for edge in graph.edges if id_map.get(edge.id, None) is not None}
    # id_map has every original edge. Accounted nodes are kept or ledgered.
    original_ids = {node.id for node in graph.nodes} | {edge.id for edge in graph.edges}
    missing = [item_id for item_id in original_ids if item_id not in id_map]
    connectivity_ok = not missing and _connectivity_matches(graph, simple_nodes, simple_edges)
    _ = accounted
    return SimplifiedGraph(
        nodes=simple_nodes,
        edges=simple_edges,
        ledger=sorted(ledger, key=lambda entry: (entry.reason_code, entry.item_id)),
        id_map=id_map,
        connectivity_ok=connectivity_ok,
        failed_check=not connectivity_ok,
        processing_version=cfg.SIMPLIFY_VERSION,
    )


def _stable(kind: str, parts: list[str]) -> str:
    raw = kind + "|" + "|".join(parts)
    return f"{kind}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _entry(item_id: str, item_type: str, node: Node | None, code: str, text: str) -> LedgerEntry:
    return LedgerEntry(
        item_id=item_id,
        item_type=item_type,
        page=node.bbox.page if node and node.bbox else None,
        position=[node.bbox.x, node.bbox.y] if node and node.bbox else [],
        reason_code=code,
        reason_text=text,
        stage="simplify",
    )


def _connectivity_matches(graph: DiagramGraph, nodes: list[SimplifiedNode], edges: list[SimplifiedEdge]) -> bool:
    kept = [node.original_ids[0] for node in nodes if node.original_ids]
    original_reach = _reach({node.id for node in graph.nodes}, list(graph.edges))
    simple_reach = _reach(set(kept), list(edges))
    for start in kept:
        for end in kept:
            if start == end:
                continue
            if (end in original_reach[start]) != (end in simple_reach[start]):
                return False
    return True


def _reach(node_ids: set[str], edges: list[Edge]) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        if edge.from_id not in neighbors or edge.to_id not in neighbors:
            continue
        if edge.direction in {"unknown", "bidirectional", "forward"}:
            neighbors[edge.from_id].add(edge.to_id)
        if edge.direction in {"unknown", "bidirectional", "reverse"}:
            neighbors[edge.to_id].add(edge.from_id)
    reach = {}
    for start in node_ids:
        stack = [start]
        seen = {start}
        while stack:
            current = stack.pop()
            for nxt in neighbors.get(current, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        seen.discard(start)
        reach[start] = seen
    return reach
