"""Read-only report tables. Tag matching is not run again."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.graph import DiagramGraph
from app.schemas.reports import TagReport
from app.services.pdf_extract import ExtractionResult


class ReportPage(BaseModel):
    items: list[dict] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


def tag_rows(report: TagReport, graph: DiagramGraph, extraction: ExtractionResult | None) -> list[dict]:
    """Tag check rows plus placement and OCR notes from stored data."""
    placed = {node.tag.upper() for node in graph.nodes if node.tag}
    duplicates = {tag for tag in placed if sum(1 for node in graph.nodes if node.tag.upper() == tag) > 1}
    ocr_tags = set()
    if extraction:
        for page in extraction.pages:
            for word in page.words:
                if word.ocr_confidence is not None and word.ocr_confidence < 0.60:
                    ocr_tags.add(word.text.upper())
    rows = []
    for row in report.rows:
        rows.append({
            "tag": row.tag,
            "status": row.status,
            "score": row.confidence.score,
            "placed_on_node": row.tag.upper() in placed,
            "ocr_uncertain": row.tag.upper() in ocr_tags,
            "duplicate": row.tag.upper() in duplicates,
            "signal": row.signal,
        })
    return rows


def connection_rows(graph: DiagramGraph) -> list[dict]:
    by_id = {node.id: node for node in graph.nodes}
    rows = []
    for edge in graph.edges:
        start = by_id.get(edge.from_id)
        end = by_id.get(edge.to_id)
        rows.append({
            "from": start.tag if start and start.tag else edge.from_id,
            "to": end.tag if end and end.tag else edge.to_id,
            "line_type": edge.line_type,
            "direction": edge.direction,
            "evidence": " ".join(item.description for item in edge.evidence),
            "confidence": edge.confidence.score,
            "needs_review": edge.needs_review,
            "segment_ids": list(edge.segment_ids),
            "id": edge.id,
        })
    return rows


def page_of(rows: list[dict], *, query: str, sort: str, offset: int, limit: int) -> ReportPage:
    """Filter, sort, and page rows. The query matches any string field."""
    filtered = rows
    if query:
        needle = query.lower()
        filtered = [row for row in rows if needle in " ".join(str(value) for value in row.values()).lower()]
    if sort:
        reverse = sort.startswith("-")
        key = sort[1:] if reverse else sort
        filtered = sorted(filtered, key=lambda row: str(row.get(key, "")), reverse=reverse)
    return ReportPage(items=filtered[offset:offset + limit], total=len(filtered), offset=offset, limit=limit)
