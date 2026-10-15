"""Compare a graph with a hand-built answer key.

The result is a list of matches and misses for that one drawing.
It is not a general accuracy percentage.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.answer_key import AnswerKey
from app.schemas.graph import DiagramGraph


class ScoreReport(BaseModel):
    """Counts for one drawing. Missing ids are listed. No overall percentage is stored."""

    drawing_id: str
    tags_expected: int = 0
    tags_matched: int = 0
    tags_missing: list[str] = Field(default_factory=list)
    equipment_expected: int = 0
    equipment_matched: int = 0
    equipment_missing: list[str] = Field(default_factory=list)
    connections_expected: int = 0
    connections_matched: int = 0
    connections_missing: list[str] = Field(default_factory=list)
    direction_matched: int = 0
    direction_unknown: list[str] = Field(default_factory=list)
    groups_expected: int = 0
    groups_matched: int = 0
    groups_missing: list[str] = Field(default_factory=list)
    note: str = "These counts are for this drawing only. They are not a general accuracy percentage."


def score_graph(graph: DiagramGraph, key: AnswerKey) -> ScoreReport:
    """Score tags, equipment, connections, and duty/standby groups against one key."""
    tags = {node.tag.upper() for node in graph.nodes if node.tag}
    equipment = {node.tag.upper() for node in graph.nodes if node.type == "equipment" and node.tag}
    missing_tags = [item.tag for item in key.expected_tags if item.tag.upper() not in tags]
    missing_equipment = [item.tag for item in key.expected_equipment if item.tag.upper() not in equipment]
    missing_connections: list[str] = []
    unknown_direction: list[str] = []
    matched_connections = 0
    matched_direction = 0
    for item in key.expected_connections:
        label = f"{item.from_} -> {item.to}"
        path = _path(graph, item.from_, item.to)
        if path is None:
            missing_connections.append(label)
            continue
        matched_connections += 1
        if _direction_matches(graph, path, item.direction):
            matched_direction += 1
        else:
            unknown_direction.append(label)
    missing_groups = []
    matched_groups = 0
    for group in key.expected_duty_standby_groups:
        wanted = {tag.upper() for tag in group.member_tags}
        found = False
        for pattern in graph.patterns:
            if pattern.type != "pump_group":
                continue
            members = {node.tag.upper() for node in graph.nodes if node.id in pattern.member_node_ids and node.tag}
            if wanted <= members:
                found = True
                break
        if found:
            matched_groups += 1
        else:
            missing_groups.append(group.id)
    return ScoreReport(
        drawing_id=key.drawing_id,
        tags_expected=len(key.expected_tags),
        tags_matched=len(key.expected_tags) - len(missing_tags),
        tags_missing=missing_tags,
        equipment_expected=len(key.expected_equipment),
        equipment_matched=len(key.expected_equipment) - len(missing_equipment),
        equipment_missing=missing_equipment,
        connections_expected=len(key.expected_connections),
        connections_matched=matched_connections,
        connections_missing=missing_connections,
        direction_matched=matched_direction,
        direction_unknown=unknown_direction,
        groups_expected=len(key.expected_duty_standby_groups),
        groups_matched=matched_groups,
        groups_missing=missing_groups,
    )


def _path(graph: DiagramGraph, start_tag: str, end_tag: str) -> list[tuple[str, bool]] | None:
    """Return edges walked from the start tag to the end tag.

    The boolean is true when the walk follows the edge from_id to to_id.
    """
    starts = [node.id for node in graph.nodes if node.tag.upper() == start_tag.upper()]
    ends = {node.id for node in graph.nodes if node.tag.upper() == end_tag.upper()}
    if not starts or not ends:
        return None
    neighbors: dict[str, list[tuple[str, str, bool]]] = {}
    for edge in graph.edges:
        neighbors.setdefault(edge.from_id, []).append((edge.to_id, edge.id, True))
        neighbors.setdefault(edge.to_id, []).append((edge.from_id, edge.id, False))
    for start in starts:
        seen = {start}
        queue: list[tuple[str, list[tuple[str, bool]]]] = [(start, [])]
        while queue:
            current, trail = queue.pop(0)
            if current in ends and trail:
                return trail
            for nxt, edge_id, along in neighbors.get(current, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append((nxt, [*trail, (edge_id, along)]))
    return None


def _direction_matches(graph: DiagramGraph, steps: list[tuple[str, bool]], direction: str) -> bool:
    """True when every edge on the path agrees with the key direction."""
    if direction in {"unknown", "bidirectional"}:
        return True
    by_id = {edge.id: edge for edge in graph.edges}
    for edge_id, along_from_to in steps:
        edge = by_id[edge_id]
        if edge.direction not in {"forward", "reverse"}:
            return False
        agrees = edge.direction == "forward" if along_from_to else edge.direction == "reverse"
        if direction == "reverse":
            agrees = not agrees
        if not agrees:
            return False
    return True
