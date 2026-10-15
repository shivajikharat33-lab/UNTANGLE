"""SVG sketch rules, including hostile text."""

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, LedgerEntry, SimplifiedEdge, SimplifiedGraph, SimplifiedNode, VerificationStatus
from app.services.layout import LayoutEdge, LayoutNode, LayoutResult
from app.services.render import _shape, render_sketch
from app import graph_config as cfg


def _confidence(score: float = 0.9) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, node_type: str, tag: str = "", signal: str = "", needs_review: bool = False, subtype: str = "") -> SimplifiedNode:
    return SimplifiedNode(
        id=node_id,
        type=node_type,  # type: ignore[arg-type]
        tag=tag,
        signal=signal,
        subtype=subtype,
        bbox=BBox(page=1, x=0, y=0, w=40, h=20),
        confidence=_confidence(0.4 if needs_review else 0.9),
        certainty="uncertain" if needs_review else "confirmed",
        needs_review=needs_review,
        review_reasons=["Needs a look"] if needs_review else [],
        original_ids=[node_id],
    )


def _layout(nodes: list[SimplifiedNode], edges: list[LayoutEdge] | None = None) -> LayoutResult:
    placed = [LayoutNode(id=node.id, x=20 + index * 80, y=40, width=40, height=24) for index, node in enumerate(nodes)]
    return LayoutResult(nodes=placed, edges=edges or [], processing_version="E2")


def test_symbols_direction_escape_and_verified_word() -> None:
    nodes = [
        _node("tank", "equipment", "T-101", subtype="tank"),
        _node("valve", "valve", "HV-1"),
        _node("pt", "instrument", "PT-101", signal="pressure"),
        _node("odd", "equipment", '<script>alert(1)</script> &'),
        _node("flag", "equipment", "E-1", needs_review=True),
    ]
    graph = SimplifiedGraph(nodes=nodes, edges=[
        SimplifiedEdge(id="u", from_id="tank", to_id="valve", direction="unknown", line_type="process", confidence=_confidence(0.8), original_ids=["u"], certainty="likely"),
        SimplifiedEdge(id="k", from_id="valve", to_id="pt", direction="forward", line_type="signal", confidence=_confidence(0.8), original_ids=["k"], certainty="likely"),
    ], connectivity_ok=True, failed_check=False, ledger=[
        LedgerEntry(item_id="hidden-1", item_type="text", reason_code="text_unassigned", reason_text="not drawn", stage="read")
    ])
    unknown_edge = LayoutEdge(id="u", points=[[0, 10], [30, 10]], direction="unknown", arrowhead=False, line_type="process")
    known_edge = LayoutEdge(id="k", points=[[40, 10], [70, 10]], direction="forward", arrowhead=True, line_type="signal")
    svg, meta = render_sketch(graph, _layout(nodes, [unknown_edge, known_edge]), VerificationStatus(state="not_verified", failing=["tag_recall"], disclaimer=cfg.DISCLAIMER))
    assert "<circle" in svg
    assert "unknown" in _shape(type("Box", (), {"type": "widget", "subtype": ""})(), 0, 0, 40, 20, "#111", "")
    assert "<script>" not in svg
    assert "&amp;" in svg
    assert "marker-end" in svg
    assert svg.count("marker-end") == 1
    assert "pressure" in svg
    assert "Hidden items: 1" in svg
    assert cfg.DISCLAIMER in svg
    assert ">Verified<" not in svg
    assert "hidden-1" not in svg
    assert 'id="node-tank"' in svg
    assert 'data-original-id="tank"' in svg
    assert "Needs a look" in svg
    assert meta.verified_label is False

    ok = SimplifiedGraph(nodes=[nodes[0]], connectivity_ok=True, failed_check=False)
    verified_svg, verified_meta = render_sketch(ok, _layout([nodes[0]]), VerificationStatus(state="verified", failing=[], disclaimer=cfg.DISCLAIMER))
    assert ">Verified<" in verified_svg
    assert verified_meta.verified_label is True

    blocked = SimplifiedGraph(nodes=[nodes[0]], connectivity_ok=False, failed_check=True)
    blocked_svg, blocked_meta = render_sketch(blocked, _layout([nodes[0]]), VerificationStatus(state="verified", failing=[], disclaimer=cfg.DISCLAIMER))
    assert ">Verified<" not in blocked_svg
    assert blocked_meta.verified_label is False
    assert "not verified" in blocked_svg
    draft_svg, draft_meta = render_sketch(
        ok,
        _layout([nodes[0]]),
        VerificationStatus(state="verified", failing=[], disclaimer=cfg.DISCLAIMER),
        draft=True,
        drafted_at="2026-10-15T12:00:00Z",
    )
    assert "DRAFT, not final, not verified" in draft_svg
    assert "2026-10-15T12:00:00Z" in draft_svg
    assert ">Verified<" not in draft_svg
    assert draft_meta.verified_label is False
