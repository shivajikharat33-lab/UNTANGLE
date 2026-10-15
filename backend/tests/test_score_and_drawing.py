"""Score one drawn page against its answer key, and lay that graph out with ELK."""

from pathlib import Path

import fitz

from app.schemas.answer_key import AnswerKey, ExpectedConnection, ExpectedEquipment, ExpectedTag
from app.schemas.graph import SimplifiedEdge, SimplifiedGraph, SimplifiedNode
from app.schemas.reports import TagReport, TagReportSummary
from app.services import detect, geometry as line_geometry
from app.services.graph_build import build_graph
from app.services.layout import _clear_route, layout_graph
from app.services.layout import LayoutEdge, LayoutNode
from app.services.pdf_extract import extract_pdf
from app.services.score import score_graph
from app.services.simplify import simplify_graph
from app.config import level_for_score
from app.schemas.confidence import Confidence


def _empty_report() -> TagReport:
    return TagReport(rows=[], summary=TagReportSummary(total=0, found=0, fuzzy=0, not_found=0, extra=0))


def _drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=420, height=240)
    page.draw_rect(fitz.Rect(20, 30, 120, 110), width=1.5)
    page.insert_text((36, 78), "T-101", fontsize=12)
    page.draw_circle(fitz.Point(280, 70), 18, width=1.2)
    page.draw_polyline([(280, 54), (298, 70), (280, 86)], closePath=True)
    page.insert_text((266, 74), "P-201", fontsize=10)
    page.draw_line((120, 70), (262, 70), width=1.5)
    page.draw_circle(fitz.Point(190, 160), 16, width=1)
    page.insert_text((172, 164), "PT-101", fontsize=8)
    page.draw_line((190, 144), (190, 70), width=0.4, dashes="[2 2] 0")
    document.save(path)
    document.close()


def test_answer_key_counts_name_every_miss_and_elk_lays_out_the_page(tmp_path: Path) -> None:
    path = tmp_path / "plant.pdf"
    _drawing(path)
    extraction = extract_pdf(path)
    report = _empty_report()
    detections = detect.build_detections(extraction, report)
    geometry = line_geometry.build_geometry(extraction, detections)
    graph = build_graph(detections, geometry, report, source_sha256=extraction.meta.pdf_sha256)
    key = AnswerKey(
        drawing_id="synthetic-plant",
        expected_tags=[ExpectedTag(tag="T-101"), ExpectedTag(tag="P-201"), ExpectedTag(tag="PT-101")],
        expected_equipment=[ExpectedEquipment(tag="T-101", label="tank"), ExpectedEquipment(tag="P-201", label="pump")],
        expected_connections=[ExpectedConnection.model_validate({"from": "T-101", "to": "P-201", "direction": "unknown"})],
    )
    scored = score_graph(graph, key)
    assert scored.tags_matched + len(scored.tags_missing) == scored.tags_expected
    assert scored.equipment_matched + len(scored.equipment_missing) == scored.equipment_expected
    assert scored.connections_matched + len(scored.connections_missing) == scored.connections_expected
    assert scored.note.startswith("These counts are for this drawing only")
    simplified = simplify_graph(graph)
    laid = layout_graph(simplified)
    assert len(laid.nodes) > 2
    assert len(laid.edges) >= 1
    assert laid.route_clear is True
    assert laid.status == "ok"
    assert all(edge.points for edge in laid.edges)


def test_a_line_through_another_box_is_moved_outside() -> None:
    confidence = Confidence(level=level_for_score(0.8), score=0.8, reason="fixture")
    graph = SimplifiedGraph(
        nodes=[
            SimplifiedNode(id="a", type="equipment", confidence=confidence, original_ids=["a"]),
            SimplifiedNode(id="b", type="equipment", confidence=confidence, original_ids=["b"]),
            SimplifiedNode(id="c", type="equipment", confidence=confidence, original_ids=["c"]),
        ],
        edges=[SimplifiedEdge(id="e", from_id="a", to_id="b", direction="unknown", line_type="process", confidence=confidence, original_ids=["e"])],
    )
    nodes = [
        LayoutNode(id="a", x=0, y=0, width=20, height=20),
        LayoutNode(id="c", x=40, y=0, width=20, height=20),
        LayoutNode(id="b", x=80, y=0, width=20, height=20),
    ]
    edge = LayoutEdge(id="e", points=[[10, 10], [90, 10]], direction="unknown")
    cleared = _clear_route(edge, graph, nodes)
    assert all(not (40 < point[0] < 60 and 0 < point[1] < 20) for point in cleared.points[1:-1])
