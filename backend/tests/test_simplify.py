"""Simplified graph rules. The original graph object is not edited."""

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Evidence, Node, Pattern
from app.services.simplify import simplify_graph


def _confidence(score: float = 0.9) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, node_type: str = "junction", tag: str = "", needs_review: bool = False) -> Node:
    return Node(
        id=node_id,
        type=node_type,  # type: ignore[arg-type]
        tag=tag,
        bbox=BBox(page=1, x=0, y=0, w=4, h=4),
        confidence=_confidence(),
        needs_review=needs_review,
        certainty="confirmed",
    )


def _edge(edge_id: str, from_id: str, to_id: str, direction: str = "unknown", line_type: str = "process", evidence: str = "") -> Edge:
    return Edge(
        id=edge_id,
        from_id=from_id,
        to_id=to_id,
        direction=direction,  # type: ignore[arg-type]
        line_type=line_type,  # type: ignore[arg-type]
        confidence=_confidence(0.8),
        evidence=[Evidence(source="fixture", description=evidence or edge_id, page=1)],
        certainty="likely",
    )


def test_passthrough_junction_collapses_and_protected_nodes_stay() -> None:
    graph = DiagramGraph(
        nodes=[_node("a", "equipment", "T-1"), _node("j"), _node("b", "equipment", "T-2")],
        edges=[_edge("e1", "a", "j", "forward"), _edge("e2", "j", "b", "forward")],
    )
    before = graph.model_dump()
    simplified = simplify_graph(graph)
    assert graph.model_dump() == before
    assert [node.id for node in simplified.nodes] == ["a", "b"]
    assert simplified.edges[0].direction == "forward"
    assert simplified.edges[0].original_ids == ["e1", "e2"]
    assert any(entry.item_id == "j" and entry.reason_code == "collapsed_passthrough" for entry in simplified.ledger)
    assert simplified.connectivity_ok is True
    assert simplified.failed_check is False
    again = simplify_graph(graph)
    assert simplified.model_dump() == again.model_dump()

    tagged = graph.model_copy(deep=True)
    tagged.nodes[1].tag = "J-1"
    assert any(node.id == "j" for node in simplify_graph(tagged).nodes)

    reviewed = graph.model_copy(deep=True)
    reviewed.nodes[1].needs_review = True
    assert any(node.id == "j" for node in simplify_graph(reviewed).nodes)

    valve = DiagramGraph(
        nodes=[_node("a", "equipment", "T-1"), _node("v", "valve", "FV-1"), _node("b", "equipment", "T-2")],
        edges=[_edge("e1", "a", "v"), _edge("e2", "v", "b")],
    )
    assert any(node.id == "v" for node in simplify_graph(valve).nodes)

    member = graph.model_copy(deep=True)
    member.patterns = [Pattern(id="p", type="pump_group", member_node_ids=["j"], confidence=_confidence())]
    assert any(node.id == "j" for node in simplify_graph(member).nodes)


def test_parallel_edges_merge_only_when_they_match() -> None:
    graph = DiagramGraph(
        nodes=[_node("a", "equipment", "P-1"), _node("b", "equipment", "T-1")],
        edges=[_edge("e1", "a", "b", "forward", evidence="same"), _edge("e2", "a", "b", "forward", evidence="same")],
    )
    simplified = simplify_graph(graph)
    assert len(simplified.edges) == 1
    assert set(simplified.edges[0].original_ids) == {"e1", "e2"}
    assert any(entry.reason_code == "merged_parallel_edge" for entry in simplified.ledger)

    distinct = graph.model_copy(deep=True)
    distinct.edges[1].evidence[0].description = "other"
    assert len(simplify_graph(distinct).edges) == 2

    opposite = graph.model_copy(deep=True)
    opposite.edges[1].direction = "reverse"
    assert len(simplify_graph(opposite).edges) == 2


def test_every_original_id_is_kept_or_ledgered() -> None:
    graph = DiagramGraph(
        nodes=[_node("a", "equipment", "T-1"), _node("j"), _node("b", "valve", "HV-1")],
        edges=[_edge("e1", "a", "j"), _edge("e2", "j", "b"), _edge("e3", "a", "b", evidence="same"), _edge("e4", "a", "b", evidence="same")],
    )
    simplified = simplify_graph(graph)
    original = {node.id for node in graph.nodes} | {edge.id for edge in graph.edges}
    kept = {item for node in simplified.nodes for item in node.original_ids}
    kept |= {item for edge in simplified.edges for item in edge.original_ids}
    ledger = {entry.item_id for entry in simplified.ledger}
    assert original == (kept | ledger) or original <= (set(simplified.id_map) | ledger)
    assert original <= set(simplified.id_map)
    assert all(item_id in kept or item_id in ledger for item_id in original)


def test_conflicting_flow_is_not_collapsed() -> None:
    graph = DiagramGraph(
        nodes=[_node("a", "equipment", "T-1"), _node("j"), _node("b", "equipment", "T-2")],
        edges=[_edge("e1", "a", "j", "forward"), _edge("e2", "b", "j", "forward")],
    )
    simplified = simplify_graph(graph)
    assert any(node.id == "j" for node in simplified.nodes)
    assert simplified.failed_check is False
