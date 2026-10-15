"""Flow stops when direction is unknown. Connectivity is a separate walk."""

import pytest

from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import DiagramGraph, Edge, Node
from app.services.trace import item_detail, trace_item


def _confidence(score: float = 0.8) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, tag: str = "") -> Node:
    return Node(id=node_id, type="equipment", tag=tag, confidence=_confidence(0.9), certainty="confirmed")


def _edge(edge_id: str, from_id: str, to_id: str, direction: str) -> Edge:
    return Edge(id=edge_id, from_id=from_id, to_id=to_id, direction=direction, line_type="process", confidence=_confidence())  # type: ignore[arg-type]


def _graph() -> DiagramGraph:
    return DiagramGraph(
        nodes=[_node("a", "T-1"), _node("b", "P-1"), _node("c", "E-1")],
        edges=[_edge("ab", "a", "b", "forward"), _edge("bc", "b", "c", "unknown")],
    )


def test_downstream_stops_at_unknown_and_connected_continues() -> None:
    graph = _graph()
    flow = trace_item(graph, "a", "downstream")
    assert flow.traced_ids == ["a", "b"]
    assert any("direction unknown, trace stopped here" in note for note in flow.stopped)
    assert "c" not in flow.traced_ids
    connected = trace_item(graph, "a", "connected")
    assert connected.traced_ids == ["a", "b", "c"]
    assert connected.note == "Connectivity, not flow."
    detail = item_detail(graph, None, None, "a")
    assert detail.tag == "T-1"
    assert detail.original_ids == ["a"]
    with pytest.raises(AppError) as caught:
        trace_item(graph, "missing", "downstream")
    assert caught.value.status_code == 404
