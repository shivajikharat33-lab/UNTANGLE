"""Compare two jobs. This does not merge them and does not write either graph."""

from __future__ import annotations

from app.schemas.graph import DiagramGraph, Node
from app.services.edits import _diff


def compare_jobs(left: DiagramGraph, right: DiagramGraph) -> dict:
    """Match tags first. Untagged equipment matches on label and rounded position."""
    left_tags = {node.tag.upper(): node for node in left.nodes if node.tag}
    right_tags = {node.tag.upper(): node for node in right.nodes if node.tag}
    added_instruments = [node.tag for node in right.nodes if node.type == "instrument" and node.tag and node.tag.upper() not in left_tags]
    removed_instruments = [node.tag for node in left.nodes if node.type == "instrument" and node.tag and node.tag.upper() not in right_tags]
    added_equipment = [node.tag or node.label for node in right.nodes if node.type == "equipment" and (node.tag.upper() if node.tag else "") not in left_tags and not _position_match(node, left)]
    removed_equipment = [node.tag or node.label for node in left.nodes if node.type == "equipment" and (node.tag.upper() if node.tag else "") not in right_tags and not _position_match(node, right)]
    links = _diff(_snapshot(left), _snapshot(right))
    return {
        "added_instruments": added_instruments,
        "removed_instruments": removed_instruments,
        "added_equipment": added_equipment,
        "removed_equipment": removed_equipment,
        "connections": links,
        "note": "Jobs were compared and not merged.",
    }


def _snapshot(graph: DiagramGraph) -> list[dict]:
    labels = {node.id: node.tag or node.id for node in graph.nodes}
    return [
        {"from": labels.get(edge.from_id, edge.from_id), "to": labels.get(edge.to_id, edge.to_id), "direction": edge.direction, "crossing_mode": edge.crossing_mode, "status": edge.status, "color": edge.color, "style": edge.style}
        for edge in graph.edges
    ]


def _position_match(node: Node, other: DiagramGraph) -> bool:
    if node.tag or node.bbox is None:
        return False
    for candidate in other.nodes:
        if candidate.type != "equipment" or candidate.tag or candidate.bbox is None:
            continue
        if candidate.label == node.label and round(candidate.bbox.x) == round(node.bbox.x) and round(candidate.bbox.y) == round(node.bbox.y):
            return True
    return False
