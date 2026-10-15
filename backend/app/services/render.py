"""Draw a self-contained SVG from a layout. Text is escaped. Ledger items are omitted.

The word Verified appears only when the coverage state is verified and the
simplified-graph connectivity check passed.
"""

from __future__ import annotations

import html
from typing import Any

from pydantic import BaseModel, Field

from app import graph_config as cfg
from app.errors import AppError
from app.schemas.graph import SimplifiedGraph, VerificationStatus
from app.services.layout import LayoutResult
from app.services.storage import SKETCH_META_NAME, SKETCH_NAME, job_folder, read_json, write_json


class SketchMeta(BaseModel):
    hidden_count: int = 0
    verified_label: bool = False
    failed_check: bool = False
    route_clear: bool = True
    node_count: int = 0
    edge_count: int = 0
    crossing_count: int = 0
    bend_count: int = 0
    disclaimer: str = cfg.DISCLAIMER
    legend: list[str] = Field(default_factory=list)
    processing_version: str = ""


def render_sketch(
    simplified: SimplifiedGraph,
    layout: LayoutResult,
    verification: VerificationStatus | None,
    hidden_count: int | None = None,
    *,
    draft: bool = False,
    drafted_at: str = "",
) -> tuple[str, SketchMeta]:
    """Return SVG text and metadata. Nothing from the ledger is drawn."""
    hidden = simplified.ledger if hidden_count is None else None
    count = len(simplified.ledger) if hidden_count is None else hidden_count
    verified = bool(
        verification
        and verification.state == "verified"
        and simplified.connectivity_ok
        and not simplified.failed_check
        and not draft
    )
    placed = {node.id: node for node in layout.nodes}
    legend: list[str] = []
    parts = [
        _header(layout, count),
        '<g id="drawing" transform="translate(0,48)">',
        _draft_banner(draft, drafted_at),
        "<defs>",
        '<marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{cfg.PROCESS_COLOR}" />',
        "</marker>",
        '<marker id="arrow-signal" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{cfg.SIGNAL_COLOR}" />',
        "</marker>",
        "</defs>",
    ]
    seen_types: set[str] = set()
    for edge in layout.edges:
        if edge.id not in {item.id for item in simplified.edges}:
            continue
        parts.append(_edge(edge))
        seen_types.add(edge.line_type)
    for node in simplified.nodes:
        if node.id not in placed:
            continue
        parts.append(_symbol(node, placed[node.id]))
        seen_types.add(node.type if node.type in {"equipment", "valve", "instrument", "junction", "terminal", "endpoint"} else "unknown")
    if "process" in seen_types:
        legend.append("Process line")
    if "signal" in seen_types:
        legend.append("Signal line")
    if "other" in seen_types:
        legend.append("Other line")
    for kind in ("equipment", "valve", "instrument", "junction", "terminal", "unknown"):
        if kind in seen_types:
            legend.append(kind)
    parts.append("</g>")
    parts.append(_legend(legend, layout))
    parts.append(_footer(layout, verified, simplified.failed_check))
    parts.append("</svg>")
    meta = SketchMeta(
        hidden_count=count,
        verified_label=verified,
        failed_check=simplified.failed_check,
        route_clear=layout.route_clear,
        node_count=len(layout.nodes),
        edge_count=len(layout.edges),
        crossing_count=len(layout.crossings),
        bend_count=sum(edge.bends for edge in layout.edges),
        disclaimer=cfg.DISCLAIMER,
        legend=legend,
        processing_version=cfg.RENDER_VERSION,
    )
    return "\n".join(parts), meta


def write_sketch(upload_dir: str, job_id: str, svg: str, meta: SketchMeta) -> None:
    """Store the SVG and its metadata. Original uploads are not touched."""
    folder = job_folder(upload_dir, job_id)
    (folder / SKETCH_NAME).write_text(svg, encoding="utf-8")
    write_json(folder / SKETCH_META_NAME, meta.model_dump(mode="json"))


def load_sketch_meta(upload_dir: str, job_id: str) -> SketchMeta:
    """Read sketch metadata. A missing sketch is a 404."""
    path = job_folder(upload_dir, job_id) / SKETCH_META_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The sketch has not been drawn for this project.", {"job_id": job_id})
    return SketchMeta.model_validate(read_json(path))


def load_sketch_svg(upload_dir: str, job_id: str) -> str:
    """Read the SVG. A missing sketch is a 404."""
    path = job_folder(upload_dir, job_id) / SKETCH_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The sketch has not been drawn for this project.", {"job_id": job_id})
    return path.read_text(encoding="utf-8")


def _header(layout: LayoutResult, hidden: int) -> str:
    width = max([node.x + node.width for node in layout.nodes] + [120]) + 180
    height = max([node.y + node.height for node in layout.nodes] + [80]) + 160
    title = html.escape(f"Hidden items: {hidden}. {cfg.DISCLAIMER}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" data-hidden-count="{hidden}">'
        f'<title>{title}</title>'
        f'<rect width="100%" height="100%" fill="#f8f5f0" />'
        f'<text x="12" y="22" font-family="sans-serif" font-size="14">Hidden items: {hidden}</text>'
    )


def _draft_banner(draft: bool, drafted_at: str) -> str:
    if not draft:
        return ""
    when = html.escape(drafted_at or "time unavailable")
    return f'<text id="draft-banner" x="12" y="40" font-family="sans-serif" font-size="14" font-weight="700">DRAFT, not final, not verified. {when}</text>'


def _edge(edge) -> str:
    color = cfg.SIGNAL_COLOR if edge.line_type == "signal" else cfg.OTHER_COLOR if edge.line_type == "other" else cfg.PROCESS_COLOR
    dash = ' stroke-dasharray="6 4"' if edge.line_type == "signal" else ""
    marker = ' marker-end="url(#arrow-signal)"' if edge.arrowhead and edge.line_type == "signal" else ' marker-end="url(#arrow)"' if edge.arrowhead else ""
    points = " ".join(f"{point[0]:.1f},{point[1]:.1f}" for point in edge.points)
    return (
        f'<polyline id="edge-{html.escape(edge.id)}" data-original-id="{html.escape(edge.id)}" '
        f'points="{points}" fill="none" stroke="{color}" stroke-width="2"{dash}{marker} />'
    )


def _symbol(node, box) -> str:
    x, y, w, h = box.x, box.y, box.width, box.height
    label = html.escape(node.tag or node.label or node.type)
    signal = html.escape(node.signal) if node.signal else ""
    review = " ".join(node.review_reasons)
    title = html.escape(review or node.reason or node.type)
    uncertain = node.certainty == "uncertain"
    dash = ' stroke-dasharray="3 2"' if uncertain else ""
    stroke = cfg.REVIEW_COLOR if node.needs_review else "#111827"
    element = _shape(node, x, y, w, h, stroke, dash)
    marker = ""
    if node.needs_review:
        marker = f'<circle cx="{x + w - 4:.1f}" cy="{y + 4:.1f}" r="4" fill="{cfg.REVIEW_COLOR}"><title>{title}</title></circle>'
    text = f'<text x="{x + 4:.1f}" y="{y + h / 2:.1f}" font-family="sans-serif" font-size="10">{label}</text>'
    signal_text = f'<text x="{x + 4:.1f}" y="{y + h - 4:.1f}" font-family="sans-serif" font-size="8" fill="{cfg.SIGNAL_COLOR}">{signal}</text>' if signal else ""
    return (
        f'<g id="node-{html.escape(node.id)}" data-original-id="{html.escape(",".join(node.original_ids) or node.id)}" data-type="{html.escape(node.type)}" data-certainty="{html.escape(node.certainty)}" data-review="{"true" if node.needs_review else "false"}">'
        f"<title>{title}</title>{element}{text}{signal_text}{marker}</g>"
    )


def _shape(node, x: float, y: float, w: float, h: float, stroke: str, dash: str) -> str:
    kind = node.type
    subtype = (node.subtype or "").lower()
    if kind == "instrument":
        return f'<circle cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" r="{min(w, h) / 2:.1f}" fill="white" stroke="{stroke}"{dash} />'
    if kind == "valve":
        return (
            f'<polygon points="{x:.1f},{y:.1f} {x + w / 2:.1f},{y + h / 2:.1f} {x:.1f},{y + h:.1f}" fill="white" stroke="{stroke}"{dash} />'
            f'<polygon points="{x + w:.1f},{y:.1f} {x + w / 2:.1f},{y + h / 2:.1f} {x + w:.1f},{y + h:.1f}" fill="white" stroke="{stroke}"{dash} />'
        )
    if kind == "junction":
        return f'<circle cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" r="4" fill="{stroke}" />'
    if kind == "equipment" and subtype == "pump":
        return f'<circle cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" r="{min(w, h) / 2:.1f}" fill="white" stroke="{stroke}"{dash} />'
    if kind in {"equipment", "terminal", "endpoint"}:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="white" stroke="{stroke}"{dash} />'
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="white" stroke="{stroke}"{dash} /><text x="{x + 4:.1f}" y="{y + 12:.1f}" font-size="8">unknown</text>'


def _legend(items: list[str], layout: LayoutResult) -> str:
    if not items:
        return ""
    x = max([node.x + node.width for node in layout.nodes] + [80]) + 24
    y = 70
    lines = [f'<g id="legend"><text x="{x:.0f}" y="58" font-family="sans-serif" font-size="12" font-weight="700">Legend</text>']
    for item in items:
        lines.append(f'<text x="{x:.0f}" y="{y}" font-family="sans-serif" font-size="11">{html.escape(item)}</text>')
        y += 16
    lines.append("</g>")
    return "\n".join(lines)


def _footer(layout: LayoutResult, verified: bool, failed_check: bool) -> str:
    y = max([node.y + node.height for node in layout.nodes] + [60]) + 72
    label = ""
    if verified and not failed_check:
        label = f'<text x="12" y="{y + 48:.0f}" font-family="sans-serif" font-size="12" font-weight="700">Verified</text>'
    status = "Connectivity check failed. This sketch is not verified." if failed_check else ""
    first, second = cfg.DISCLAIMER.split(". ", 1)
    return (
        f'<g id="sketch-footer">'
        f'<text x="12" y="{y:.0f}" font-family="sans-serif" font-size="11">{html.escape(first)}.</text>'
        f'<text x="12" y="{y + 16:.0f}" font-family="sans-serif" font-size="11">{html.escape(second)}</text>'
        f'<text x="12" y="{y + 32:.0f}" font-family="sans-serif" font-size="11">{html.escape(status)}</text>'
        f"{label}</g>"
    )
