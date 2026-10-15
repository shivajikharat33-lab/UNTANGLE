"""Coverage, ledger conservation, and the automated verified state."""

from pathlib import Path

import fitz

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Node
from app.schemas.reports import TagReport, TagReportRow, TagReportSummary
from app.schemas.graph import DiagramGraph as SchemaGraph
from app.services import detect
from app.services.checks import apply_checks
from app.services.coverage import apply_coverage, conservation_holds, list_extracted
from app.services.geometry import build_geometry
from app.services.graph_build import build_graph
from app.services.patterns import apply_patterns
from app.services.pdf_extract import extract_pdf
from app.services.detect import DetectionCensus, DetectionItem, DetectionResult
from app.services.geometry import Coverage, GeometryLine, GeometryResult
from app.services.pdf_extract import (
    ExtractionMeta,
    ExtractionResult,
    ExtractionSummary,
    PageCounts,
    PageExtraction,
    WordItem,
)
from app import graph_config as cfg


def _confidence(score: float = 0.9) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")  # type: ignore[arg-type]


def _counts(**kwargs: int) -> PageCounts:
    base = dict(words=0, lines=0, polylines=0, shapes=0, circles=0, primitives_read=0, primitives_used=0, unused_primitives=0)
    base.update(kwargs)
    return PageCounts(**base)


def _passing() -> tuple[DiagramGraph, ExtractionResult, DetectionResult, GeometryResult, TagReport]:
    node = Node(
        id="tank",
        type="equipment",
        tag="T-101",
        source_id="d-tank",
        bbox=BBox(page=1, x=0, y=0, w=10, h=10),
        confidence=_confidence(),
        needs_review=False,
        certainty="confirmed",
    )
    other = Node(
        id="far",
        type="equipment",
        tag="E-1",
        source_id="d-ex",
        bbox=BBox(page=1, x=40, y=0, w=10, h=10),
        confidence=_confidence(),
        needs_review=False,
        certainty="confirmed",
    )
    edge = Edge(
        id="e1",
        from_id="tank",
        to_id="far",
        direction="forward",
        line_type="process",
        segment_ids=["g1"],
        confidence=_confidence(0.8),
        needs_review=False,
        certainty="likely",
    )
    graph = DiagramGraph(nodes=[node, other], edges=[edge])
    extraction = ExtractionResult(
        status="ok",
        message="fixture",
        meta=ExtractionMeta(pdf_sha256="1" * 64, page_count=1, duration_ms=1, pymupdf_version="test", coordinate_system="test"),
        pages=[
            PageExtraction(
                page=1,
                width=100,
                height=100,
                rotation=0,
                status="ok",
                message="ok",
                words=[WordItem(text="T-101", bbox=[1, 1, 20, 8], block=0, line=0, word=0, font_size=8)],
                polylines=[],
                shapes=[],
                circles=[],
                unused=[],
                counts=_counts(words=1),
            )
        ],
        summary=ExtractionSummary(words=1, lines=0, polylines=0, shapes=0, circles=0, primitives_read=0, primitives_used=0, unused_primitives=0),
    )
    detections = DetectionResult(
        items=[
            DetectionItem(id="d-tank", kind="equipment", subtype="tank", page=1, bbox=[0, 0, 10, 10], tag="T-101", label="T-101", confidence=_confidence(), evidence=[], source="vector"),
            DetectionItem(id="d-ex", kind="equipment", subtype="exchanger", page=1, bbox=[40, 0, 50, 10], tag="E-1", label="E-1", confidence=_confidence(), evidence=[], source="vector"),
        ],
        census=DetectionCensus(),
    )
    geometry = GeometryResult(lines=[GeometryLine(id="g1", page=1, points=[[0, 5], [40, 5]], line_type="process", reason="fixture", source="vector", length=40)], coverage=Coverage())
    report = TagReport(
        rows=[
            TagReportRow(tag="T-101", status="found", confidence=_confidence(1)),
            TagReportRow(tag="E-1", status="found", confidence=_confidence(1)),
        ],
        summary=TagReportSummary(total=2, found=2, fuzzy=0, not_found=0, extra=0),
    )
    return graph, extraction, detections, geometry, report


def test_metrics_conservation_and_verified_state() -> None:
    graph, extraction, detections, geometry, report = _passing()
    items = list_extracted(graph, extraction, detections, geometry, report)
    assert conservation_holds(items)
    updated = apply_coverage(graph, extraction, detections, geometry, report)
    by_name = {metric.name: metric for metric in updated.coverage}
    assert by_name["tags_on_nodes"].denominator == by_name["tags_on_nodes"].numerator
    assert by_name["segments_in_edges"].numerator == 1
    assert by_name["segments_in_edges"].denominator == 1
    assert by_name["text_assigned"].numerator == 1
    assert updated.verification is not None
    assert updated.verification.state == "verified"
    assert updated.verification.failing == []
    assert updated.verification.disclaimer == cfg.VERIFICATION_DISCLAIMER
    again = apply_coverage(*_passing())
    assert [entry.item_id for entry in updated.ledger] == [entry.item_id for entry in again.ledger]


def test_each_failing_criterion_is_named() -> None:
    graph, extraction, detections, geometry, report = _passing()
    graph.nodes[0].tag = "OTHER"
    missed = apply_coverage(graph, extraction, detections, geometry, report)
    assert missed.verification is not None
    assert missed.verification.state == "not_verified"
    assert "tag_recall" in missed.verification.failing

    graph, extraction, detections, geometry, report = _passing()
    report.rows[0].status = "not_found"
    unmatched = apply_coverage(graph, extraction, detections, geometry, report)
    assert unmatched.verification is not None and "unmatched_io" in unmatched.verification.failing

    graph, extraction, detections, geometry, report = _passing()
    from app.schemas.graph import Finding

    graph.findings = [Finding(id="f1", rule_id="R-TEST", category="test", severity="error", title="Error", message="error", review_action="Look")]
    errored = apply_coverage(graph, extraction, detections, geometry, report)
    assert errored.verification is not None and "error_findings" in errored.verification.failing

    graph, extraction, detections, geometry, report = _passing()
    graph.nodes[0].needs_review = True
    review = apply_coverage(graph, extraction, detections, geometry, report)
    assert review.verification is not None
    assert review.verification.state == "needs_review"
    assert review.verification.failing == ["unresolved_needs_review"]

    graph, extraction, detections, geometry, report = _passing()
    graph.nodes.append(
        Node(id="pt", type="instrument", tag="PT-101", attachment="unattached", bbox=BBox(page=1, x=1, y=1, w=4, h=4), confidence=_confidence(0.4), needs_review=False, certainty="uncertain")
    )
    loose = apply_coverage(graph, extraction, detections, geometry, report)
    assert loose.verification is not None and "unattached_instruments" in loose.verification.failing

    graph, extraction, detections, geometry, report = _passing()
    graph.edges[0].segment_ids = []
    dropped = apply_coverage(graph, extraction, detections, geometry, report)
    assert dropped.verification is not None
    assert "unexplained_ledger" in dropped.verification.failing
    assert any(entry.reason_code == "segment_not_in_edge" for entry in dropped.ledger)


def test_ledger_reason_for_an_unclassified_shape() -> None:
    graph, extraction, detections, geometry, report = _passing()
    detections.items.append(
        DetectionItem(id="d-blob", kind="unclassified", subtype="", page=1, bbox=[5, 5, 8, 8], confidence=_confidence(0.4), evidence=[], source="vector")
    )
    updated = apply_coverage(graph, extraction, detections, geometry, report)
    entry = next(item for item in updated.ledger if item.item_id == "d-blob")
    assert entry.reason_code == "unclassified_shape"
    assert entry.stage == "detect"
    items = list_extracted(updated, extraction, detections, geometry, report)
    assert conservation_holds(items)


def test_sample_drawing_coverage_validates(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page(width=220, height=160)
    page.draw_line((10, 30), (80, 30), width=1.5)
    page.draw_line((40, 30), (40, 100), width=1.5)
    document.save(path)
    document.close()
    extraction = extract_pdf(path)
    report = TagReport(rows=[], summary=TagReportSummary(total=0, found=0, fuzzy=0, not_found=0, extra=0))
    detections = detect.build_detections(extraction, report)
    geometry = build_geometry(extraction, detections)
    graph = build_graph(detections, geometry, report, source_sha256=extraction.meta.pdf_sha256)
    graph = apply_patterns(graph, report)
    graph = apply_checks(graph, report, extraction)
    updated = apply_coverage(graph, extraction, detections, geometry, report)
    validated = SchemaGraph.model_validate(updated.model_dump())
    assert validated.processing_version == "D4"
    assert validated.verification is not None
    assert validated.verification.disclaimer.startswith("Passed the defined automated checks.")
    items = list_extracted(updated, extraction, detections, geometry, report)
    assert conservation_holds(items)
