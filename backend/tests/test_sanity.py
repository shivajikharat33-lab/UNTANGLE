"""Sanity warnings and detail levels do not change the stored graph."""

import hashlib
from pathlib import Path

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Node
from app.services.detail_view import filter_detail, graph_hash, render_detail
from app.services.graph_build import write_graph
from app.services.sanity import sanity_warnings
from app.services.simplify import simplify_graph


def _confidence(score: float = 0.9) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason="fixture")


def _graph() -> DiagramGraph:
    return DiagramGraph(
        nodes=[
            Node(id="a", type="equipment", tag="P-101A", subtype="pump", bbox=BBox(page=1, x=0, y=0, w=10, h=10), confidence=_confidence()),
            Node(id="b", type="equipment", tag="T-1", bbox=BBox(page=1, x=30, y=0, w=10, h=10), confidence=_confidence()),
            Node(id="i", type="instrument", tag="PT-101", attachment="unattached", bbox=BBox(page=1, x=10, y=20, w=8, h=8), confidence=_confidence()),
            Node(id="i2", type="instrument", tag="PT-101", bbox=BBox(page=1, x=12, y=20, w=8, h=8), confidence=_confidence()),
            Node(id="bad", type="equipment", tag="FT-9", bbox=BBox(page=1, x=50, y=0, w=10, h=10), confidence=_confidence()),
        ],
        edges=[Edge(id="e", from_id="a", to_id="b", direction="forward", line_type="process", confidence=_confidence())],
    )


def test_clean_graph_is_silent_and_dirty_graph_warns() -> None:
    clean = DiagramGraph(
        nodes=[
            Node(id="a", type="equipment", tag="T-1", bbox=BBox(page=1, x=0, y=0, w=8, h=8), confidence=_confidence()),
            Node(id="b", type="equipment", tag="T-2", bbox=BBox(page=1, x=20, y=0, w=8, h=8), confidence=_confidence()),
        ],
        edges=[Edge(id="e", from_id="a", to_id="b", direction="unknown", line_type="process", confidence=_confidence())],
    )
    before = clean.model_dump()
    assert sanity_warnings(clean) == []
    assert clean.model_dump() == before
    rules = {item.rule for item in sanity_warnings(_graph())}
    assert {"ab-symmetry", "unattached-instrument", "duplicate-tag", "prefix-mismatch"} <= rules


def test_detail_level_two_matches_simplify_and_graph_file_stays(tmp_path: Path) -> None:
    upload = tmp_path / "uploads"
    job = "jobdetail1"
    (upload / job).mkdir(parents=True)
    graph = _graph()
    write_graph(str(upload), job, graph)
    simplified = simplify_graph(graph)
    assert [node.id for node in filter_detail(simplified, 2).nodes] == [node.id for node in simplified.nodes]
    level_one = filter_detail(simplified, 1)
    assert all(node.type == "equipment" for node in level_one.nodes)
    before = graph_hash(str(upload), job)
    result = render_detail(str(upload), job, 1)
    after = graph_hash(str(upload), job)
    assert before == after
    assert result["graph_unchanged"] is True
    assert hashlib.sha256((upload / job / "graph.json").read_bytes()).hexdigest() == before
