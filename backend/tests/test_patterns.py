"""Pump groups and control loops on hand-built graphs. No accuracy percentage is claimed."""

from pathlib import Path

import fitz

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Node
from app.schemas.reports import TagReport, TagReportRow, TagReportSummary
from app.schemas.graph import DiagramGraph as SchemaGraph
from app.services import detect, geometry as line_geometry
from app.services.graph_build import build_graph
from app.services.patterns import DETECTORS, PatternContext, apply_patterns, register
from app.services.pdf_extract import extract_pdf


def _confidence(score: float = 0.9) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _node(node_id: str, node_type: str, tag: str = "", subtype: str = "") -> Node:
    return Node(
        id=node_id,
        type=node_type,  # type: ignore[arg-type]
        tag=tag,
        subtype=subtype,
        bbox=BBox(page=1, x=0, y=0, w=10, h=10),
        confidence=_confidence(),
    )


def _edge(edge_id: str, from_id: str, to_id: str, line_type: str = "process") -> Edge:
    return Edge(
        id=edge_id,
        from_id=from_id,
        to_id=to_id,
        direction="unknown",
        line_type=line_type,  # type: ignore[arg-type]
        confidence=_confidence(0.8),
    )


def _empty_report() -> TagReport:
    return TagReport(rows=[], summary=TagReportSummary(total=0, found=0, fuzzy=0, not_found=0, extra=0))


def _pump_pair(shared: bool) -> DiagramGraph:
    nodes = [
        _node("p1", "equipment", "P-101A", "pump"),
        _node("p2", "equipment", "P-101B", "pump"),
        _node("js", "junction"),
        _node("jd", "junction"),
        _node("va", "valve", subtype="manual"),
        _node("vb", "valve", subtype="manual"),
        _node("vc", "valve", subtype="check"),
        _node("vd", "valve", subtype="check"),
        _node("tank", "equipment", "T-1", "tank"),
        _node("out", "endpoint"),
    ]
    edges = [
        _edge("e1", "js", "va"),
        _edge("e2", "va", "p1"),
        _edge("e3", "p1", "vc"),
        _edge("e4", "vc", "jd"),
        _edge("e5", "js", "vb"),
        _edge("e6", "vb", "p2"),
        _edge("e7", "p2", "vd"),
        _edge("e8", "vd", "jd"),
        _edge("e9", "js", "tank"),
        _edge("e10", "jd", "out"),
    ]
    if not shared:
        nodes.extend([_node("js2", "junction"), _node("jd2", "junction"), _node("tank2", "equipment", "T-2", "tank"), _node("out2", "endpoint")])
        edges = [
            _edge("e1", "js", "va"),
            _edge("e2", "va", "p1"),
            _edge("e3", "p1", "vc"),
            _edge("e4", "vc", "jd"),
            _edge("e9", "js", "tank"),
            _edge("e10", "jd", "out"),
            _edge("e5", "js2", "vb"),
            _edge("e6", "vb", "p2"),
            _edge("e7", "p2", "vd"),
            _edge("e8", "vd", "jd2"),
            _edge("e11", "js2", "tank2"),
            _edge("e12", "jd2", "out2"),
        ]
    return DiagramGraph(nodes=nodes, edges=edges)


def test_shared_headers_group_and_separate_headers_do_not() -> None:
    grouped = apply_patterns(_pump_pair(True), _empty_report())
    assert len(grouped.patterns) == 1
    assert grouped.patterns[0].type == "pump_group"
    assert set(grouped.patterns[0].header_ids) == {"js", "jd"}
    assert "vc" in grouped.patterns[0].check_valve_ids
    separate = apply_patterns(_pump_pair(False), _empty_report())
    assert separate.patterns == []


def test_roles_follow_evidence_and_ids_repeat() -> None:
    unknown = apply_patterns(
        _pump_pair(True).model_copy(update={
            "nodes": [
                node.model_copy(update={"tag": "P-1" if node.id == "p1" else "P-2" if node.id == "p2" else node.tag})
                for node in _pump_pair(True).nodes
            ]
        }),
        _empty_report(),
    )
    assert unknown.patterns[0].role == "unknown"
    assert unknown.patterns[0].role_certainty == "uncertain"

    suffix = apply_patterns(_pump_pair(True), _empty_report())
    assert suffix.patterns[0].role_certainty == "likely"
    assert suffix.patterns[0].member_roles["p1"] == "unknown"

    noted = apply_patterns(_pump_pair(True), _empty_report(), ["P-101A DUTY", "P-101B STANDBY"])
    assert noted.patterns[0].role_certainty == "confirmed"
    assert noted.patterns[0].member_roles["p1"] == "duty"
    assert noted.patterns[0].member_roles["p2"] == "standby"
    assert noted.patterns[0].confidence.score > suffix.patterns[0].confidence.score
    again = apply_patterns(_pump_pair(True), _empty_report(), ["P-101A DUTY", "P-101B STANDBY"])
    assert [pattern.id for pattern in noted.patterns] == [pattern.id for pattern in again.patterns]


def test_loops_keep_missing_parts_and_ignore_letters_alone() -> None:
    nodes = [
        _node("pt", "instrument", "PT-101"),
        _node("fic", "instrument", "FIC-101"),
        _node("fv", "valve", "FV-101"),
    ]
    complete = apply_patterns(DiagramGraph(nodes=nodes, edges=[]), _empty_report())
    loop = next(pattern for pattern in complete.patterns if pattern.type == "control_loop")
    assert loop.sensor_id == "pt"
    assert loop.controller_id == "fic"
    assert loop.final_element_id == "fv"
    assert loop.needs_review is False

    missing = apply_patterns(DiagramGraph(nodes=[nodes[0], nodes[2]], edges=[]), _empty_report())
    partial = missing.patterns[0]
    assert partial.needs_review is True
    assert "controller" in partial.missing_parts
    assert partial.controller_id == ""

    letters = apply_patterns(
        DiagramGraph(nodes=[_node("a", "instrument", "PT-101"), _node("b", "valve", "FV-202")], edges=[]),
        _empty_report(),
    )
    assert letters.patterns == []


def test_partial_headers_odd_count_and_missing_valve_are_flagged() -> None:
    partial = DiagramGraph(
        nodes=[
            _node("p1", "equipment", "P-1", "pump"),
            _node("p2", "equipment", "P-2", "pump"),
            _node("js", "junction"),
            _node("va", "valve"),
            _node("vb", "valve"),
            _node("tank", "equipment", "T-1", "tank"),
        ],
        edges=[
            _edge("e1", "js", "va"),
            _edge("e2", "va", "p1"),
            _edge("e3", "js", "vb"),
            _edge("e4", "vb", "p2"),
            _edge("e5", "js", "tank"),
        ],
    )
    flagged = apply_patterns(partial, _empty_report())
    assert flagged.patterns[0].needs_review is True
    assert any("one header" in reason for reason in flagged.patterns[0].review_reasons)

    third = _pump_pair(True)
    third.nodes.append(_node("p3", "equipment", "P-101C", "pump"))
    third.nodes.extend([_node("ve", "valve"), _node("vf", "valve")])
    third.edges.extend([_edge("e13", "js", "ve"), _edge("e14", "ve", "p3"), _edge("e15", "p3", "vf"), _edge("e16", "vf", "jd")])
    odd = apply_patterns(third, _empty_report())
    assert any("odd number" in reason for reason in odd.patterns[0].review_reasons)

    bare = _pump_pair(True)
    bare.edges = [edge for edge in bare.edges if edge.id not in {"e1", "e2"}]
    bare.edges.append(_edge("direct", "js", "p1"))
    missing = apply_patterns(bare, _empty_report())
    assert any("no valve" in reason for reason in missing.patterns[0].review_reasons)


def test_registry_runs_an_added_detector() -> None:
    class Dummy:
        name = "dummy"

        def detect(self, graph: DiagramGraph, context: PatternContext) -> list:
            return []

    register(Dummy())
    try:
        assert DETECTORS[-1].name == "dummy"
        result = apply_patterns(DiagramGraph(), _empty_report())
        assert result.patterns == []
    finally:
        DETECTORS.pop()


def test_sample_drawing_patterns_validate(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page(width=220, height=160)
    page.draw_line((10, 30), (80, 30), width=1.5)
    page.draw_line((40, 30), (40, 100), width=1.5)
    document.save(path)
    document.close()
    extraction = extract_pdf(path)
    report = _empty_report()
    detections = detect.build_detections(extraction, report)
    geometry = line_geometry.build_geometry(extraction, detections)
    graph = build_graph(detections, geometry, report, source_sha256=extraction.meta.pdf_sha256)
    updated = apply_patterns(graph, report, [word.text for page in extraction.pages for word in page.words])
    validated = SchemaGraph.model_validate(updated.model_dump())
    assert validated.processing_version == "D2"
    assert isinstance(validated.patterns, list)


def test_io_field_can_name_a_role() -> None:
    report = TagReport(
        rows=[
            TagReportRow(tag="P-101A", signal="duty", status="found", confidence=_confidence()),
            TagReportRow(tag="P-101B", signal="standby", status="found", confidence=_confidence()),
        ],
        summary=TagReportSummary(total=2, found=2, fuzzy=0, not_found=0, extra=0),
    )
    result = apply_patterns(_pump_pair(True), report)
    assert result.patterns[0].member_roles["p1"] == "duty"
    assert result.patterns[0].role_certainty == "confirmed"
