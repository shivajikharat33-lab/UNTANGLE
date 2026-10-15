"""Graph builder rules. Fixtures are synthetic. No answer-key accuracy is claimed."""

from pathlib import Path

import fitz

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import DiagramGraph, Evidence
from app.schemas.reports import TagReport, TagReportSummary
from app.services.detect import DetectionItem, DetectionResult
from app.services.geometry import Coverage, GeometryLine, GeometryResult, Meeting
from app.services.graph_build import build_graph, stable_id
from app.services.pdf_extract import extract_pdf
from app.services import detect, geometry as line_geometry


def _confidence(score: float, reason: str = "fixture") -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason=reason)  # type: ignore[arg-type]


def _report() -> TagReport:
    return TagReport(rows=[], summary=TagReportSummary(total=0, found=0, fuzzy=0, not_found=0, extra=0))


def _line(line_id: str, points: list[list[float]], line_type: str = "process") -> GeometryLine:
    return GeometryLine(
        id=line_id,
        page=1,
        points=points,
        line_type=line_type,
        reason="fixture",
        source="vector",
        length=1,
    )


def _meeting(decision: str, position: list[float], line_ids: list[str]) -> Meeting:
    return Meeting(
        id=f"m-{decision}-{position[0]}",
        page=1,
        position=position,
        line_ids=line_ids,
        decision=decision,
        reason=f"fixture {decision}",
        confidence=_confidence(0.9, "fixture junction" if decision == "junction" else "fixture"),
    )


def _geometry(lines: list[GeometryLine], meetings: list[Meeting] | None = None) -> GeometryResult:
    return GeometryResult(lines=lines, meetings=meetings or [], coverage=Coverage())


def _item(
    kind: str,
    box: list[float],
    tag: str = "",
    label: str = "",
    subtype: str = "",
    direction: str | None = None,
    evidence: list[Evidence] | None = None,
    score: float = 0.9,
) -> DetectionItem:
    return DetectionItem(
        id=f"d-{kind}-{tag or label or box[0]}",
        kind=kind,
        subtype=subtype,
        page=1,
        bbox=box,
        label=label,
        tag=tag,
        confidence=_confidence(score, "fixture symbol"),
        evidence=evidence or [Evidence(source="fixture", description="shape and label", page=1)],
        source="vector",
        direction=direction,
    )


def _detections(*items: DetectionItem) -> DetectionResult:
    return DetectionResult(items=list(items), census={})  # type: ignore[arg-type]


def _build(geometry: GeometryResult, items: list[DetectionItem] | None = None) -> DiagramGraph:
    return build_graph(_detections(*(items or [])), geometry, _report(), source_sha256="abc")


def test_ids_stay_the_same_on_a_second_run() -> None:
    geometry = _geometry([_line("g1", [[0, 10], [40, 10]]), _line("g2", [[40, 10], [90, 10]])])
    first = _build(geometry)
    second = _build(geometry)
    assert first.model_dump() == second.model_dump()
    assert stable_id("equipment", 1, 10, 10, "T-101") == stable_id("equipment", 1, 10, 10, "T-101")


def test_crossing_does_not_connect_and_junction_does() -> None:
    crossing = _build(
        _geometry(
            [_line("a", [[0, 10], [80, 10]]), _line("b", [[40, 0], [40, 40]])],
            [_meeting("crossing", [40, 10], ["a", "b"])],
        )
    )
    assert crossing.crossings
    used_a = {node_id for edge in crossing.edges if "a" in edge.segment_ids for node_id in (edge.from_id, edge.to_id)}
    used_b = {node_id for edge in crossing.edges if "b" in edge.segment_ids for node_id in (edge.from_id, edge.to_id)}
    assert used_a.isdisjoint(used_b)
    assert not any(node.type == "junction" for node in crossing.nodes)

    junction = _build(
        _geometry(
            [_line("h", [[0, 20], [60, 20]]), _line("v", [[30, 20], [30, 70]])],
            [_meeting("junction", [30, 20], ["h", "v"])],
        )
    )
    junction_ids = {node.id for node in junction.nodes if node.type == "junction"}
    assert len(junction_ids) == 1
    horizontal = {node_id for edge in junction.edges if "h" in edge.segment_ids for node_id in (edge.from_id, edge.to_id)}
    vertical = {node_id for edge in junction.edges if "v" in edge.segment_ids for node_id in (edge.from_id, edge.to_id)}
    assert junction_ids <= horizontal
    assert junction_ids <= vertical


def test_collinear_segments_merge_and_keep_their_ids() -> None:
    graph = _build(_geometry([_line("g1", [[0, 10], [40, 10]]), _line("g2", [[40, 10], [90, 10]])]))
    process = [edge for edge in graph.edges if edge.line_type == "process"]
    assert len(process) == 1
    assert process[0].segment_ids == ["g1", "g2"]


def test_endpoint_snaps_inside_tolerance_and_stays_free_outside_it() -> None:
    tank = _item("equipment", [0, 0, 12, 12], tag="T-101", label="T-101", subtype="tank")
    near = _build(_geometry([_line("near", [[14, 6], [80, 6]])]), [tank])
    assert any(edge.from_id == near.nodes[0].id or edge.to_id == near.nodes[0].id for edge in near.edges)

    far = _build(_geometry([_line("far", [[40, 6], [90, 6]])]), [tank])
    tank_id = next(node.id for node in far.nodes if node.tag == "T-101")
    assert all(tank_id not in {edge.from_id, edge.to_id} for edge in far.edges)
    assert any(note.kind == "orphan" and tank_id in note.item_ids for note in far.structure)


def test_tied_candidates_are_not_chosen() -> None:
    left = _item("equipment", [0, -10, 10, 20], tag="T-1", label="T-1")
    right = _item("equipment", [10, -10, 10, 20], tag="T-2", label="T-2")
    graph = _build(_geometry([_line("pipe", [[10, 0], [10, 80]])]), [left, right])
    edge = graph.edges[0]
    assert edge.needs_review
    assert len(edge.candidate_ids) == 2
    equipment_ids = {node.id for node in graph.nodes if node.type == "equipment"}
    assert edge.from_id not in equipment_ids
    assert edge.to_id not in equipment_ids


def test_each_direction_source_and_a_conflict() -> None:
    arrow = _build(
        _geometry([_line("pipe", [[0, 10], [80, 10]])]),
        [_item("arrow", [36, 6, 8, 8], direction="right")],
    )
    assert arrow.edges[0].direction == "forward"
    assert any(item.source == "arrow" for item in arrow.edges[0].direction_evidence)

    conflict = _build(
        _geometry([_line("pipe", [[0, 10], [80, 10]])]),
        [
            _item("arrow", [20, 6, 8, 8], direction="right"),
            _item("arrow", [50, 6, 8, 8], direction="left"),
        ],
    )
    assert conflict.edges[0].direction == "unknown"
    assert conflict.edges[0].needs_review
    assert len(conflict.edges[0].direction_evidence) == 2

    check = _build(
        _geometry([_line("pipe", [[0, 20], [100, 20]])]),
        [_item("valve", [45, 14, 10, 12], tag="CV-1", subtype="check", direction="right")],
    )
    assert check.edges
    assert {edge.direction for edge in check.edges} == {"forward"}
    assert any(item.source == "check_valve" for edge in check.edges for item in edge.direction_evidence)

    nozzle = _build(
        _geometry([_line("pipe", [[16, 20], [80, 20]])]),
        [
            _item(
                "equipment",
                [0, 10, 20, 20],
                tag="P-201",
                subtype="pump",
                direction="right",
                evidence=[Evidence(source="detect", description="discharge nozzle points right", page=1)],
            )
        ],
    )
    pump_edge = next(edge for edge in nozzle.edges if any(node.id in {edge.from_id, edge.to_id} and node.tag == "P-201" for node in nozzle.nodes))
    assert pump_edge.direction == "forward"
    assert any(item.source == "nozzle" for item in pump_edge.direction_evidence)

    terminal = _build(
        _geometry([_line("pipe", [[0, 40], [70, 40]])]),
        [_item("equipment", [64, 34, 20, 14], label="OFF-PAGE FLOW OUT")],
    )
    terminal_node = next(node for node in terminal.nodes if node.type == "terminal")
    terminal_edge = next(edge for edge in terminal.edges if terminal_node.id in {edge.from_id, edge.to_id})
    assert terminal_edge.direction == "forward"
    assert any(item.source == "terminal" for item in terminal_edge.direction_evidence)


def test_unattached_instrument_orphan_and_dead_end_are_kept() -> None:
    graph = _build(
        _geometry([_line("pipe", [[0, 0], [30, 0]])]),
        [
            _item("instrument", [200, 200, 20, 20], tag="PT-101"),
            _item("equipment", [200, 20, 30, 30], tag="T-9", label="T-9"),
        ],
    )
    instrument = next(node for node in graph.nodes if node.tag == "PT-101")
    assert instrument.attachment == "unattached"
    assert instrument.needs_review
    assert any(note.kind == "unattached_instrument" and instrument.id in note.item_ids for note in graph.structure)
    assert any(note.kind == "orphan" for note in graph.structure)
    assert any(note.kind == "dead_end" for note in graph.structure)
    assert any(node.type == "endpoint" for node in graph.nodes)


def test_sample_drawing_graph_validates_against_the_schema(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page(width=220, height=160)
    page.draw_line((10, 30), (80, 30), width=1.5)
    page.draw_line((40, 30), (40, 100), width=1.5)
    page.draw_line((120, 20), (200, 80), width=1.5)
    page.draw_line((120, 80), (200, 20), width=1.5)
    document.save(path)
    document.close()
    extraction = extract_pdf(path)
    report = _report()
    detections = detect.build_detections(extraction, report)
    geometry = line_geometry.build_geometry(extraction, detections)
    graph = build_graph(detections, geometry, report, source_sha256=extraction.meta.pdf_sha256)
    validated = DiagramGraph.model_validate(graph.model_dump())
    assert validated.source_sha256 == extraction.meta.pdf_sha256
    assert validated.processing_version == "D1"
    assert any(node.type == "junction" for node in validated.nodes)
    assert validated.crossings
