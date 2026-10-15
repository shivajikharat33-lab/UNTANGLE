"""Answer a fixed list of questions from the graph. No model is called."""

from __future__ import annotations

from app.schemas.graph import DiagramGraph

UNSUPPORTED = "That is not in the extracted graph."


def validate_cited_ids(graph: DiagramGraph, cited_ids: list[str]) -> dict:
    """Drop a model answer that names an id the graph does not contain."""
    known = {node.id for node in graph.nodes} | {edge.id for edge in graph.edges} | {pattern.id for pattern in graph.patterns}
    invalid = [item for item in cited_ids if item not in known]
    if invalid or not cited_ids:
        return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": [], "rejected": invalid}
    return {"answer": "Cited ids are in the graph.", "cited_ids": cited_ids, "highlight": cited_ids, "rejected": []}


def ask_graph(graph: DiagramGraph, question: str) -> dict:
    """Answer one supported question. The graph is not changed."""
    text = " ".join(question.lower().split())
    if text.startswith("instruments on "):
        tag = question.split(" ", 2)[-1].strip()
        return _instruments_on(graph, tag)
    if text.startswith("upstream of ") or text.startswith("downstream of "):
        return _direction_of(graph, question)
    if "not found" in text or text.startswith("tags not found"):
        return {"answer": "Use the tag check for tags that were not found.", "cited_ids": [], "highlight": []}
    if "low confidence" in text or "low-confidence" in text:
        ids = [edge.id for edge in graph.edges if edge.certainty == "uncertain" or edge.confidence.score < 0.6]
        return {"answer": "These links are uncertain." if ids else "No low-confidence links are stored.", "cited_ids": ids, "highlight": ids}
    if "duty" in text or "standby" in text:
        ids = [pattern.id for pattern in graph.patterns if pattern.type == "pump_group"]
        return {"answer": "These pump groups are stored." if ids else "No duty or standby group is stored.", "cited_ids": ids, "highlight": ids}
    if text.startswith("path "):
        parts = question.replace("path", "", 1).strip().split()
        if len(parts) >= 2:
            return _path(graph, parts[0], parts[-1])
    return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": []}


def _instruments_on(graph: DiagramGraph, tag: str) -> dict:
    pumps = [node for node in graph.nodes if node.tag.upper() == tag.upper()]
    if not pumps:
        return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": []}
    pump_ids = {node.id for node in pumps}
    neighbor_ids = set()
    for edge in graph.edges:
        if edge.from_id in pump_ids:
            neighbor_ids.add(edge.to_id)
        if edge.to_id in pump_ids:
            neighbor_ids.add(edge.from_id)
    instruments = [node for node in graph.nodes if node.id in neighbor_ids and node.type == "instrument"]
    ids = [node.id for node in instruments]
    names = ", ".join(node.tag or node.id for node in instruments) or "none"
    return {"answer": f"Instruments next to {tag}: {names}.", "cited_ids": ids, "highlight": ids}


def _direction_of(graph: DiagramGraph, question: str) -> dict:
    downstream = question.lower().startswith("downstream")
    tag = question.split("of", 1)[-1].strip()
    start = next((node for node in graph.nodes if node.tag.upper() == tag.upper()), None)
    if start is None:
        return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": []}
    found = []
    for edge in graph.edges:
        if downstream and edge.direction == "forward" and edge.from_id == start.id:
            found.append(edge.to_id)
        if not downstream and edge.direction == "forward" and edge.to_id == start.id:
            found.append(edge.from_id)
        if edge.direction == "unknown" and start.id in {edge.from_id, edge.to_id}:
            return {"answer": "direction unknown, trace stopped here", "cited_ids": [edge.id], "highlight": [edge.id]}
    return {"answer": "Cited nodes follow known direction." if found else "No known-direction neighbor is stored.", "cited_ids": found, "highlight": found}


def _path(graph: DiagramGraph, start_tag: str, end_tag: str) -> dict:
    labels = {node.id: node.tag or node.id for node in graph.nodes}
    starts = [node.id for node in graph.nodes if (node.tag or node.id).upper() == start_tag.upper()]
    ends = {node.id for node in graph.nodes if (node.tag or node.id).upper() == end_tag.upper()}
    if not starts or not ends:
        return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": []}
    neighbors: dict[str, list[str]] = {}
    for edge in graph.edges:
        neighbors.setdefault(edge.from_id, []).append(edge.to_id)
        neighbors.setdefault(edge.to_id, []).append(edge.from_id)
    seen = {starts[0]}
    queue = [starts[0]]
    while queue:
        current = queue.pop(0)
        if current in ends:
            return {"answer": f"A connection exists between {start_tag} and {end_tag}.", "cited_ids": [current], "highlight": [current]}
        for nxt in neighbors.get(current, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    _ = labels
    return {"answer": UNSUPPORTED, "cited_ids": [], "highlight": []}
