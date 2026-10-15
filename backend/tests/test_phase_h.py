"""Phase H read-only checks. The stored graph hash must stay the same."""

import hashlib
from pathlib import Path

from app.config import level_for_score
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Node
from app.services.ask_graph import UNSUPPORTED, ask_graph, validate_cited_ids
from app.services.graph_build import write_graph
from app.services.fewshot import symbol_suggestions
from app.services.job_compare import compare_jobs


def _confidence() -> Confidence:
    return Confidence(level=level_for_score(0.9), score=0.9, reason="fixture")


def _node(node_id: str, tag: str, node_type: str = "equipment") -> Node:
    return Node(id=node_id, type=node_type, tag=tag, bbox=BBox(page=1, x=0, y=0, w=8, h=8), confidence=_confidence())


def test_job_compare_and_ask_do_not_change_the_graph(tmp_path: Path) -> None:
    left = DiagramGraph(
        nodes=[_node("t", "T-1"), _node("p", "P-101A", ), _node("i", "PT-1", "instrument")],
        edges=[
            Edge(id="e", from_id="t", to_id="p", direction="forward", line_type="process", confidence=_confidence()),
            Edge(id="s", from_id="p", to_id="i", direction="unknown", line_type="signal", confidence=_confidence()),
        ],
    )
    right = DiagramGraph(
        nodes=[_node("t", "T-1"), _node("p", "P-101A"), _node("v", "V-1")],
        edges=[Edge(id="e2", from_id="t", to_id="v", direction="unknown", line_type="process", confidence=_confidence())],
    )
    before = hashlib.sha256(left.model_dump_json().encode()).hexdigest()
    report = compare_jobs(left, right)
    assert hashlib.sha256(left.model_dump_json().encode()).hexdigest() == before
    assert report["note"] == "Jobs were compared and not merged."
    assert "PT-1" in report["removed_instruments"]
    answer = ask_graph(left, "instruments on P-101A")
    assert "PT-1" in answer["answer"] or answer["cited_ids"]
    refused = ask_graph(left, "what is the weather")
    assert refused["answer"] == UNSUPPORTED
    rejected = validate_cited_ids(left, ["missing-node"])
    assert rejected["answer"] == UNSUPPORTED
    assert rejected["rejected"] == ["missing-node"]
    folder = tmp_path / "uploads" / "jobh1"
    folder.mkdir(parents=True)
    write_graph(str(tmp_path / "uploads"), "jobh1", left)
    digest = hashlib.sha256((folder / "graph.json").read_bytes()).hexdigest()
    ask_graph(left, "downstream of T-1")
    assert hashlib.sha256((folder / "graph.json").read_bytes()).hexdigest() == digest
    assert symbol_suggestions(False)["available"] is False
