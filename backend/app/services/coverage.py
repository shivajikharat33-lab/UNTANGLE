"""Coverage, the hidden-item ledger, and the automated verified state.

Every extracted item is either represented in the graph or listed in the ledger.
verified means the configured checks passed. It is not a certification.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import graph_config as cfg
from app.errors import AppError
from app.schemas.graph import CoverageMetric, DiagramGraph, LedgerEntry, LedgerPage, VerificationStatus
from app.schemas.reports import TagReport
from app.services.detect import DetectionResult
from app.services.geometry import GeometryResult
from app.services.io_list import normalize_tag
from app.services.pdf_extract import ExtractionResult
from app.services.storage import GRAPH_NAME, job_folder, read_json, write_json


@dataclass
class ExtractedItem:
    """One thing an earlier stage produced."""

    item_id: str
    item_type: str
    page: int | None
    position: list[float]
    stage: str
    represented: bool
    reason_code: str
    reason_text: str


def apply_coverage(
    graph: DiagramGraph,
    extraction: ExtractionResult,
    detections: DetectionResult,
    geometry: GeometryResult,
    report: TagReport,
    *,
    tag_recall_min: float = cfg.TAG_RECALL_MIN,
) -> DiagramGraph:
    """Fill coverage, ledger, and verification. Nothing already stored is deleted."""
    items = list_extracted(graph, extraction, detections, geometry, report)
    graph.ledger = [
        LedgerEntry(
            item_id=item.item_id,
            item_type=item.item_type,
            page=item.page,
            position=item.position,
            reason_code=item.reason_code,
            reason_text=item.reason_text,
            stage=item.stage,
        )
        for item in items
        if not item.represented
    ]
    graph.ledger.sort(key=lambda entry: entry.item_id)
    graph.coverage = _metrics(graph, extraction, detections, geometry, report)
    graph.verification = evaluate_verification(graph, items, tag_recall_min=tag_recall_min)
    graph.processing_version = cfg.COVERAGE_VERSION
    return graph


def list_extracted(
    graph: DiagramGraph,
    extraction: ExtractionResult,
    detections: DetectionResult,
    geometry: GeometryResult,
    report: TagReport,
) -> list[ExtractedItem]:
    """Classify every extracted item as represented or ledgered."""
    represented_sources = {node.source_id for node in graph.nodes if node.source_id}
    represented_segments = {segment_id for edge in graph.edges for segment_id in edge.segment_ids}
    node_tags = {node.tag.upper() for node in graph.nodes if node.tag}
    items: list[ExtractedItem] = []
    for detection in detections.items:
        kept = detection.id in represented_sources
        if kept:
            code, text = "in_graph", "This detection is a graph node."
        elif detection.kind == "arrow":
            code, text = "arrow_not_a_node", "The arrow was kept as direction evidence and was not made into a node."
        elif detection.kind == "unclassified":
            code, text = "unclassified_shape", "The shape matched no symbol rule, so it was not made into a node."
        else:
            code, text = "detection_not_in_graph", "This detection is not a graph node and has no other reason."
        items.append(ExtractedItem(detection.id, detection.kind, detection.page, _center(detection.bbox), "detect", kept, code, text))
    for line in geometry.lines:
        kept = line.id in represented_segments
        code = "in_graph" if kept else "segment_not_in_edge"
        text = "This segment is part of an edge." if kept else "This segment is not in any edge."
        position = list(line.points[0]) if line.points else []
        items.append(ExtractedItem(line.id, "segment", line.page, position, "geometry", kept, code, text))
    for page in extraction.pages:
        for index, word in enumerate(page.words):
            normalized = normalize_tag(word.text) or ""
            kept = bool(normalized) and normalized.upper() in node_tags
            code = "text_assigned" if kept else "text_unassigned"
            text = "This word matches a node tag." if kept else "This word is not a tag on a node."
            items.append(ExtractedItem(f"word-{page.page}-{index}-{word.text}", "text", page.page, list(word.bbox[:2]), "read", kept, code, text))
    for row in report.rows:
        kept = row.status in {"found", "fuzzy"}
        code = "io_matched" if kept else "unmatched_io" if row.status == "not_found" else "io_extra"
        text = f"The tag check status is {row.status}."
        items.append(ExtractedItem(f"io-{row.tag}", "io_row", None, [], "match", kept, code, text))
    return items


def conservation_holds(items: list[ExtractedItem]) -> bool:
    """True when every extracted item is represented or ledgered, and not both."""
    if not items:
        return True
    seen: set[str] = set()
    for item in items:
        if item.item_id in seen:
            return False
        seen.add(item.item_id)
        if item.represented and item.reason_code not in {"in_graph", "text_assigned", "io_matched"}:
            return False
        if not item.represented and item.reason_code in {"in_graph", "text_assigned", "io_matched"}:
            return False
    return True


def evaluate_verification(graph: DiagramGraph, items: list[ExtractedItem], *, tag_recall_min: float) -> VerificationStatus:
    """Name every failing criterion. verified is only for an empty failing list."""
    failing: list[str] = []
    by_name = {metric.name: metric for metric in graph.coverage}
    tags = by_name.get("tags_on_nodes")
    if tags and tags.denominator > 0 and (tags.numerator / tags.denominator) < tag_recall_min:
        failing.append("tag_recall")
    io_rows = by_name.get("io_rows_matched")
    if io_rows and io_rows.numerator != io_rows.denominator:
        failing.append("unmatched_io")
    if any(finding.severity == "error" for finding in graph.findings):
        failing.append("error_findings")
    if any(item.needs_review for item in [*graph.nodes, *graph.edges]):
        failing.append("unresolved_needs_review")
    if any(node.type == "instrument" and node.attachment == "unattached" for node in graph.nodes):
        failing.append("unattached_instruments")
    if any(entry.reason_code in cfg.UNEXPLAINED_REASON_CODES for entry in graph.ledger):
        failing.append("unexplained_ledger")
    segment_ids = {item.item_id for item in items if item.item_type == "segment"}
    in_edges = {segment_id for edge in graph.edges for segment_id in edge.segment_ids}
    in_ledger = {entry.item_id for entry in graph.ledger if entry.item_type == "segment"}
    if any(segment_id not in in_edges and segment_id not in in_ledger for segment_id in segment_ids):
        failing.append("segment_connectivity")
    if not failing:
        state = "verified"
    elif failing == ["unresolved_needs_review"]:
        state = "needs_review"
    else:
        state = "not_verified"
    return VerificationStatus(state=state, failing=failing, disclaimer=cfg.VERIFICATION_DISCLAIMER)


def load_coverage(upload_dir: str, job_id: str) -> list[CoverageMetric]:
    """Return coverage metrics. A missing run is a 404."""
    return _checked(upload_dir, job_id).coverage


def load_ledger(upload_dir: str, job_id: str, *, item_type: str | None, reason_code: str | None, offset: int, limit: int) -> LedgerPage:
    """Return one page of the ledger."""
    entries = _checked(upload_dir, job_id).ledger
    if item_type:
        entries = [entry for entry in entries if entry.item_type == item_type]
    if reason_code:
        entries = [entry for entry in entries if entry.reason_code == reason_code]
    return LedgerPage(items=entries[offset : offset + limit], total=len(entries), offset=offset, limit=limit)


def load_verification(upload_dir: str, job_id: str) -> VerificationStatus:
    """Return the automated state. A missing run is a 404."""
    status = _checked(upload_dir, job_id).verification
    if status is None:
        raise AppError(404, "NOT_FOUND", "Coverage has not been computed for this project.", {"job_id": job_id})
    return status


def write_graph(upload_dir: str, job_id: str, graph: DiagramGraph) -> None:
    """Replace graph.json. The original PDF and workbook are not changed."""
    write_json(job_folder(upload_dir, job_id) / GRAPH_NAME, graph.model_dump(mode="json"))


def _checked(upload_dir: str, job_id: str) -> DiagramGraph:
    path = job_folder(upload_dir, job_id) / GRAPH_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "Coverage has not been computed for this project.", {"job_id": job_id})
    graph = DiagramGraph.model_validate(read_json(path))
    if graph.processing_version != cfg.COVERAGE_VERSION:
        raise AppError(404, "NOT_FOUND", "Coverage has not been computed for this project.", {"job_id": job_id})
    return graph


def _metrics(
    graph: DiagramGraph,
    extraction: ExtractionResult,
    detections: DetectionResult,
    geometry: GeometryResult,
    report: TagReport,
) -> list[CoverageMetric]:
    node_tags = {node.tag.upper() for node in graph.nodes if node.tag}
    extracted_tags = {item.tag.upper() for item in detections.items if item.tag}
    for page in extraction.pages:
        for word in page.words:
            normalized = normalize_tag(word.text)
            if normalized:
                extracted_tags.add(normalized.upper())
    placed = extracted_tags & node_tags
    degree = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        degree[edge.from_id] = degree.get(edge.from_id, 0) + 1
        degree[edge.to_id] = degree.get(edge.to_id, 0) + 1
    source_nodes = {node.source_id: node for node in graph.nodes if node.source_id}
    segment_ids = {segment_id for edge in graph.edges for segment_id in edge.segment_ids}
    metrics = [
        _metric("tags_on_nodes", len(placed), len(extracted_tags), sorted(extracted_tags - placed)),
        _metric(
            "io_rows_matched",
            sum(row.status in {"found", "fuzzy"} for row in report.rows),
            len(report.rows),
            [row.tag for row in report.rows if row.status not in {"found", "fuzzy"}],
        ),
    ]
    for kind, node_type in (("equipment", "equipment"), ("valve", "valve"), ("instrument", "instrument")):
        detected = [item for item in detections.items if item.kind == kind]
        present = [item.id for item in detected if item.id in source_nodes]
        connected = [item_id for item_id in present if degree.get(source_nodes[item_id].id, 0) > 0]
        metrics.append(_metric(f"{kind}_nodes", len(present), len(detected), [item.id for item in detected if item.id not in source_nodes]))
        metrics.append(_metric(f"{kind}_connected", len(connected), len(present), [item_id for item_id in present if item_id not in connected]))
        _ = node_type
    instruments = [node for node in graph.nodes if node.type == "instrument"]
    attached = [node.id for node in instruments if node.attachment not in {"", "unattached"}]
    metrics.append(_metric("instruments_attached", len(attached), len(instruments), [node.id for node in instruments if node.id not in attached]))
    metrics.append(_metric("segments_in_edges", len(segment_ids), len(geometry.lines), [line.id for line in geometry.lines if line.id not in segment_ids]))
    words = [(page.page, word) for page in extraction.pages for word in page.words]
    assigned = [f"word-{page}-{index}-{word.text}" for index, (page, word) in enumerate(words) if (normalize_tag(word.text) or "").upper() in node_tags]
    # enumerate above restarts per the flat list, matching list_extracted's per-page index only if one page.
    assigned_ids = []
    missing_words = []
    for page in extraction.pages:
        for index, word in enumerate(page.words):
            word_id = f"word-{page.page}-{index}-{word.text}"
            if (normalize_tag(word.text) or "").upper() in node_tags:
                assigned_ids.append(word_id)
            else:
                missing_words.append(word_id)
    metrics.append(_metric("text_assigned", len(assigned_ids), len(words), missing_words))
    _ = assigned
    return metrics


def _metric(name: str, numerator: int, denominator: int, missing: list[str]) -> CoverageMetric:
    percentage = None if denominator == 0 else numerator / denominator
    return CoverageMetric(name=name, numerator=numerator, denominator=denominator, percentage=percentage, missing_ids=missing)


def _center(box: list[float]) -> list[float]:
    if len(box) < 4:
        return []
    return [box[0] + box[2] / 2, box[1] + box[3] / 2]
