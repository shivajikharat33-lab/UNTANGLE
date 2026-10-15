"""One passing and one failing fixture for each configured check."""

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Evidence, Finding, Node, Pattern, StructureNote
from app.schemas.reports import TagReport, TagReportRow, TagReportSummary
from app.services.checks import RULES, CheckContext, apply_checks, register
from app.services.pdf_extract import ExtractionMeta, ExtractionResult, ExtractionSummary, PageCounts, PageExtraction, WordItem


def _confidence(score: float) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, node_type: str = "equipment", tag: str = "", **kwargs: object) -> Node:
    data = dict(
        id=node_id,
        type=node_type,
        tag=tag,
        bbox=BBox(page=1, x=0, y=0, w=8, h=8),
        confidence=_confidence(0.9),
    )
    data.update(kwargs)
    return Node(**data)  # type: ignore[arg-type]


def _edge(edge_id: str, from_id: str, to_id: str, direction: str = "unknown") -> Edge:
    return Edge(id=edge_id, from_id=from_id, to_id=to_id, direction=direction, line_type="process", confidence=_confidence(0.8))  # type: ignore[arg-type]


def _report(rows: list[TagReportRow] | None = None) -> TagReport:
    items = rows or []
    return TagReport(
        rows=items,
        summary=TagReportSummary(total=len(items), found=sum(row.status == "found" for row in items), fuzzy=0, not_found=sum(row.status == "not_found" for row in items), extra=0),
    )


def _ids(rule_id: str, graph: DiagramGraph) -> list[str]:
    return [finding.rule_id for finding in apply_checks(graph, _report()).findings if finding.rule_id == rule_id]


def test_each_rule_has_a_pass_and_a_fail() -> None:
    connected = DiagramGraph(nodes=[_node("a", tag="T-1"), _node("b", tag="T-2")], edges=[_edge("e", "a", "b", "forward")])
    assert "R-GRAPH-001" not in _ids("R-GRAPH-001", connected)
    orphan = connected.model_copy(update={"structure": [StructureNote(kind="orphan", item_ids=["a"], message="orphan")]})
    assert "R-GRAPH-001" in _ids("R-GRAPH-001", orphan)

    assert "R-GRAPH-002" not in _ids("R-GRAPH-002", connected)
    dead = connected.model_copy(update={"structure": [StructureNote(kind="dead_end", item_ids=["z"], message="dead")]})
    assert "R-GRAPH-002" in _ids("R-GRAPH-002", dead)

    assert "R-GRAPH-003" not in _ids("R-GRAPH-003", connected)
    split = connected.model_copy(update={"structure": [StructureNote(kind="disconnected", item_ids=["a", "b"], message="two pieces")]})
    assert "R-GRAPH-003" in _ids("R-GRAPH-003", split)

    assert "R-GRAPH-004" not in _ids("R-GRAPH-004", connected)
    dup = connected.model_copy(update={"structure": [StructureNote(kind="duplicate", item_ids=["a", "b"], message="same spot")]})
    assert "R-GRAPH-004" in _ids("R-GRAPH-004", dup)

    assert "R-GRAPH-005" not in _ids("R-GRAPH-005", connected)
    tied = connected.model_copy(update={"edges": [_edge("e", "a", "b").model_copy(update={"candidate_ids": ["a", "b"]})]})
    assert "R-GRAPH-005" in _ids("R-GRAPH-005", tied)

    known = connected.model_copy(update={"edges": [_edge("e", "a", "b", "forward")]})
    assert "R-FLOW-001" not in _ids("R-FLOW-001", known)
    assert "R-FLOW-001" in _ids("R-FLOW-001", connected.model_copy(update={"edges": [_edge("e", "a", "b", "unknown")]}))

    assert "R-FLOW-002" not in _ids("R-FLOW-002", known)
    conflict = known.model_copy(update={"edges": [known.edges[0].model_copy(update={"review_reasons": ["Direction evidence disagrees."], "direction": "unknown"})]})
    assert "R-FLOW-002" in _ids("R-FLOW-002", conflict)

    pump_ok = DiagramGraph(
        nodes=[_node("p", tag="P-101", subtype="pump"), _node("j", "junction")],
        edges=[_edge("e", "p", "j", "forward")],
    )
    assert "R-FLOW-003" not in _ids("R-FLOW-003", pump_ok)
    pump_bad = pump_ok.model_copy(update={"edges": [_edge("e", "p", "j", "unknown")]})
    assert "R-FLOW-003" in _ids("R-FLOW-003", pump_bad)

    assert "R-FLOW-004" not in _ids("R-FLOW-004", pump_ok)
    stopped = DiagramGraph(nodes=[_node("s", tag="T-1"), _node("t", tag="T-2")], edges=[_edge("e", "s", "t", "forward")])
    assert "R-FLOW-004" in _ids("R-FLOW-004", stopped)

    attached = DiagramGraph(nodes=[_node("i", "instrument", "PT-101", attachment="on_pipe", certainty="likely")], edges=[])
    assert "R-INST-001" not in _ids("R-INST-001", attached)
    loose = attached.model_copy(update={"nodes": [_node("i", "instrument", "PT-101", attachment="unattached")]})
    assert "R-INST-001" in _ids("R-INST-001", loose)

    assert "R-INST-002" not in _ids("R-INST-002", attached)
    low = attached.model_copy(update={"nodes": [_node("i", "instrument", "PT-101", attachment="on_pipe", certainty="uncertain", confidence=_confidence(0.4))]})
    assert "R-INST-002" in _ids("R-INST-002", low)

    complete = Pattern(
        id="loop-1",
        type="control_loop",
        member_node_ids=["s", "c", "f"],
        confidence=_confidence(0.8),
        sensor_id="s",
        controller_id="c",
        final_element_id="f",
    )
    assert "R-INST-003" not in _ids("R-INST-003", DiagramGraph(patterns=[complete]))
    incomplete = complete.model_copy(update={"sensor_id": "", "missing_parts": ["sensor"]})
    assert "R-INST-003" in _ids("R-INST-003", DiagramGraph(patterns=[incomplete]))

    found = _report([TagReportRow(tag="PT-101", status="found", confidence=_confidence(1))])
    assert not any(item.rule_id == "R-INST-004" for item in apply_checks(attached, found).findings)
    assert any(item.rule_id == "R-INST-004" for item in apply_checks(attached, _report()).findings)

    assert not any(item.rule_id == "R-INST-005" for item in apply_checks(DiagramGraph(), found).findings)
    missing_row = _report([TagReportRow(tag="LT-50", status="not_found", confidence=_confidence(0.4))])
    assert any(item.rule_id == "R-INST-005" for item in apply_checks(DiagramGraph(), missing_row).findings)

    assert "R-TAG-001" not in _ids("R-TAG-001", connected)
    same = DiagramGraph(nodes=[_node("a", tag="PT-101"), _node("b", "instrument", "PT-101")], edges=[])
    assert "R-TAG-001" in _ids("R-TAG-001", same)

    assert "R-PAT-001" not in _ids("R-PAT-001", DiagramGraph())
    group = Pattern(id="g", type="pump_group", member_node_ids=["p"], confidence=_confidence(0.7), needs_review=True, review_reasons=["The pumps share only one header."])
    assert "R-PAT-001" in _ids("R-PAT-001", DiagramGraph(patterns=[group]))
    named = group.model_copy(update={"role": "duty_standby", "review_reasons": []})
    assert "R-PAT-002" not in _ids("R-PAT-002", DiagramGraph(patterns=[named]))
    assert "R-PAT-002" in _ids("R-PAT-002", DiagramGraph(patterns=[group.model_copy(update={"role": "unknown", "review_reasons": []})]))


def test_ocr_rule_and_confidence_cap_and_registry() -> None:
    extraction = ExtractionResult(
        status="ok",
        message="fixture",
        meta=ExtractionMeta(pdf_sha256="0" * 64, page_count=1, duration_ms=1, pymupdf_version="test", coordinate_system="test"),
        pages=[
            PageExtraction(
                page=1,
                width=100,
                height=100,
                rotation=0,
                status="ok",
                message="ok",
                words=[WordItem(text="PT-1", bbox=[1, 1, 10, 8], block=0, line=0, word=0, font_size=8, source="raster", ocr_confidence=0.4)],
                polylines=[],
                shapes=[],
                circles=[],
                unused=[],
                counts=PageCounts(words=1, lines=0, polylines=0, shapes=0, circles=0, primitives_read=1, primitives_used=1, unused_primitives=0),
            )
        ],
        summary=ExtractionSummary(words=1, lines=0, polylines=0, shapes=0, circles=0, primitives_read=1, primitives_used=1, unused_primitives=0),
    )
    quiet = extraction.model_copy(deep=True)
    quiet.pages[0].words[0].ocr_confidence = 0.9
    assert apply_checks(DiagramGraph(), _report(), quiet).findings == [] or all(item.rule_id != "R-TAG-002" for item in apply_checks(DiagramGraph(), _report(), quiet).findings)
    noisy = apply_checks(DiagramGraph(), _report(), extraction)
    assert any(item.rule_id == "R-TAG-002" for item in noisy.findings)

    node = _node("n", confidence=_confidence(0.92))
    graph = DiagramGraph(nodes=[node], edges=[])

    class Boom:
        rule_id = "R-TEST-001"
        category = "test"
        severity = "error"
        title = "Boom"
        explanation = "test"

        def run(self, current: DiagramGraph, context: CheckContext) -> list[Finding]:
            _ = context
            return [Finding(id="fixed", rule_id=self.rule_id, category="test", severity="error", title="Boom", message="Capped by the test rule.", affected_ids=["n"], review_action="Read it.")]

    register(Boom())
    try:
        checked = apply_checks(graph, _report())
        updated = checked.nodes[0]
        assert updated.confidence.score <= 0.59
        assert updated.confidence.score <= 0.92
        assert updated.certainty == "uncertain"
        assert updated.needs_review is True
        assert any("Capped by the test rule." in reason for reason in updated.review_reasons)
        low = _node("low", confidence=_confidence(0.4))
        held = apply_checks(DiagramGraph(nodes=[low]), _report())
        assert held.nodes[0].confidence.score == 0.4
        again = apply_checks(DiagramGraph(nodes=[_node("n", confidence=_confidence(0.92))]), _report())
        first_ids = [item.id for item in checked.findings if item.rule_id == "R-TEST-001"]
        second_ids = [item.id for item in again.findings if item.rule_id == "R-TEST-001"]
        assert first_ids == second_ids
    finally:
        RULES.pop()
