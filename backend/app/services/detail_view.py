"""Detail levels for the sketch. Level 2 is the current simplified graph.

Only layout and render run again. The stored graph file is not rewritten.
"""

from __future__ import annotations

import hashlib
import json

from app.schemas.graph import SimplifiedGraph
from app.services.layout import layout_graph
from app.services.render import render_sketch
from app.services.simplify import simplify_graph
from app.services.storage import GRAPH_NAME, SKETCH_NAME, job_folder


def graph_hash(upload_dir: str, job_id: str) -> str:
    """Hash the stored graph file. Callers use this to prove a read-only step."""
    path = job_folder(upload_dir, job_id) / GRAPH_NAME
    return hashlib.sha256(path.read_bytes()).hexdigest()


def filter_detail(simplified: SimplifiedGraph, level: int) -> SimplifiedGraph:
    """Return a copy. Level 2 is unchanged."""
    if level == 2:
        return simplified.model_copy(deep=True)
    if level == 1:
        keep_types = {"equipment", "terminal"}
        nodes = [node for node in simplified.nodes if node.type in keep_types]
        ids = {node.id for node in nodes}
        edges = [edge for edge in simplified.edges if edge.from_id in ids and edge.to_id in ids and edge.line_type == "process"]
        return simplified.model_copy(deep=True, update={"nodes": nodes, "edges": edges})
    nodes = list(simplified.nodes)
    edges = list(simplified.edges)
    return simplified.model_copy(deep=True, update={"nodes": nodes, "edges": edges})


def render_detail(upload_dir: str, job_id: str, level: int) -> dict:
    """Lay out and draw one detail level. graph.json is not opened for writing."""
    before = graph_hash(upload_dir, job_id)
    from app.services.graph_build import load_graph

    graph = load_graph(upload_dir, job_id)
    simplified = filter_detail(simplify_graph(graph), level)
    laid = layout_graph(simplified)
    svg, meta = render_sketch(simplified, laid, None)
    folder = job_folder(upload_dir, job_id)
    (folder / SKETCH_NAME).write_text(svg, encoding="utf-8")
    meta_path = folder / "sketch_meta.json"
    body = meta.model_dump(mode="json")
    body["detail_level"] = level
    meta_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    after = graph_hash(upload_dir, job_id)
    return {"level": level, "nodes": len(simplified.nodes), "graph_unchanged": before == after}
