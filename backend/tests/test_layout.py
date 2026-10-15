"""ELK layout. Coordinates come from elkjs. Oversized graphs invent none."""

from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, Edge, SimplifiedEdge, SimplifiedGraph, SimplifiedNode
from app.services.layout import LayoutEdge, _crossings, layout_graph, layout_with_groups
from app import graph_config as cfg


def _confidence(score: float = 0.8) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, node_type: str = "equipment", tag: str = "", subtype: str = "") -> SimplifiedNode:
    return SimplifiedNode(
        id=node_id,
        type=node_type,  # type: ignore[arg-type]
        tag=tag,
        subtype=subtype,
        bbox=BBox(page=1, x=0, y=0, w=40, h=20),
        confidence=_confidence(0.9),
        original_ids=[node_id],
        certainty="confirmed",
    )


def _edge(edge_id: str, from_id: str, to_id: str, direction: str = "unknown") -> SimplifiedEdge:
    return SimplifiedEdge(
        id=edge_id,
        from_id=from_id,
        to_id=to_id,
        direction=direction,  # type: ignore[arg-type]
        line_type="process",
        confidence=_confidence(),
        original_ids=[edge_id],
        certainty="likely",
    )


def test_empty_single_disconnected_cycle_and_direction() -> None:
    empty = layout_graph(SimplifiedGraph())
    assert empty.nodes == []
    assert empty.status == "ok"

    single = layout_graph(SimplifiedGraph(nodes=[_node("only")]))
    assert len(single.nodes) == 1
    assert single.nodes[0].id == "only"

    apart = layout_graph(SimplifiedGraph(nodes=[_node("a"), _node("b")]))
    assert {node.id for node in apart.nodes} == {"a", "b"}

    cycle = layout_graph(SimplifiedGraph(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[_edge("e1", "a", "b"), _edge("e2", "b", "c"), _edge("e3", "c", "a")],
    ))
    assert len(cycle.nodes) == 3
    assert cycle.processing_version == "E2"

    unknown = layout_graph(SimplifiedGraph(nodes=[_node("a"), _node("b")], edges=[_edge("e", "a", "b", "unknown")]))
    assert unknown.edges[0].direction == "unknown"
    assert unknown.edges[0].arrowhead is False

    forward = layout_graph(SimplifiedGraph(nodes=[_node("a"), _node("b")], edges=[_edge("e", "a", "b", "forward")]))
    placed = {node.id: node for node in forward.nodes}
    assert placed["a"].x <= placed["b"].x
    assert forward.edges[0].arrowhead is True
    assert layout_graph(SimplifiedGraph(nodes=[_node("a"), _node("b")], edges=[_edge("e", "a", "b", "forward")])).model_dump() == forward.model_dump()


def test_crossing_is_a_jump_and_not_a_node() -> None:
    from app.services.layout import LayoutEdge, _crossings

    edges = [
        LayoutEdge(id="h", points=[[0, 10], [20, 10]], direction="unknown"),
        LayoutEdge(id="v", points=[[10, 0], [10, 20]], direction="unknown"),
    ]
    crossings = _crossings(edges)
    assert len(crossings) == 1
    assert crossings[0].kind == "jump"
    assert crossings[0].edge_ids == ["h", "v"]


def test_a_route_cross_is_a_jump_and_not_a_node() -> None:
    crossings = _crossings([
        LayoutEdge(id="h", points=[[0, 10], [20, 10]], direction="unknown"),
        LayoutEdge(id="v", points=[[10, 0], [10, 20]], direction="unknown"),
    ])
    assert len(crossings) == 1
    assert crossings[0].kind == "jump"
    assert crossings[0].edge_ids == ["h", "v"]


def test_terminal_side_group_and_size_limit(monkeypatch) -> None:
    terminal = layout_graph(SimplifiedGraph(
        nodes=[_node("src", "equipment", "T-1"), _node("out", "terminal", subtype="out")],
        edges=[_edge("e", "src", "out", "forward")],
    ))
    placed = {node.id: node for node in terminal.nodes}
    assert placed["src"].x <= placed["out"].x

    grouped = layout_with_groups(
        SimplifiedGraph(nodes=[_node("p1", tag="P-1"), _node("p2", tag="P-2")], edges=[_edge("e", "p1", "p2")]),
        {"pumps": ["p1", "p2"]},
    )
    assert grouped.groups and grouped.groups[0].member_ids == ["p1", "p2"]
    assert {node.group_id for node in grouped.nodes} == {"pumps"}

    monkeypatch.setattr(cfg, "MAX_LAYOUT_NODES", 1)
    try:
        layout_graph(SimplifiedGraph(nodes=[_node("a"), _node("b")]))
        raise AssertionError("expected the size limit")
    except AppError as exc:
        assert exc.error_code == "LAYOUT_TOO_LARGE"
        assert "invented" in exc.message
