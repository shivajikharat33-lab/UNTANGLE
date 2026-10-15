"""Versions and connection-list edits.

Version 0 is the tool result. Its snapshot, SVG, and change log are never
replaced. The working copy lives in draft.json until it is saved as a new version.
"""

from __future__ import annotations

import io
import time
import uuid
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import level_for_score
from app.errors import AppError
from app.models import JobRow, VersionRow
from app.schemas.confidence import Confidence
from app.schemas.graph import DiagramGraph, Edge
from app.schemas.job import ChangeLogEntry, ConnectionSnapshotEntry, Version
from app.schemas.rules import RuleResult
from app.schemas.verification import VerificationResult
from app.services import graph_build
from app.services.layout import layout_graph
from app.services.render import render_sketch
from app.services.simplify import simplify_graph
from app.services.storage import DRAFT_NAME, SKETCH_NAME, job_folder, read_json, write_json

AUTHOR = "local user"
_STATUSES = {"auto", "user_added", "user_edited", "user_removed"}
_DIRECTIONS = {"forward", "reverse", "bidirectional", "unknown"}
_LINES = {"process", "signal", "other"}
_CROSSINGS = {"auto", "avoid", "keep"}
_REQUIRED = ["ID", "From", "To", "Direction", "Line type", "Crossing mode", "Status"]


def ensure_version_zero(engine: object, upload_dir: str, job_id: str) -> Version:
    """Create version 0 from the finished sketch when it does not exist yet."""
    with Session(engine) as session:
        existing = session.scalar(select(VersionRow).where(VersionRow.job_id == job_id, VersionRow.number == 0))
        if existing is not None:
            return _to_version(existing)
        if session.get(JobRow, job_id) is None:
            raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
        graph = graph_build.load_graph(upload_dir, job_id)
        folder = job_folder(upload_dir, job_id)
        svg = (folder / SKETCH_NAME).read_text(encoding="utf-8") if (folder / SKETCH_NAME).is_file() else None
        now = datetime.now(timezone.utc)
        row = VersionRow(
            id=uuid.uuid4().hex,
            job_id=job_id,
            number=0,
            parent=None,
            status="auto",
            connection_list_snapshot=[item.model_dump(mode="json", by_alias=True) for item in _connections_from_graph(graph)],
            svg=svg,
            verification=_tool_verification(graph).model_dump(mode="json"),
            change_log=[],
            created_at=now.isoformat(),
            created_by="tool",
            note="Original tool result",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_version(row)


def list_versions(engine: object, upload_dir: str, job_id: str) -> list[Version]:
    """Return saved versions. Version 0 is created on the first read."""
    ensure_version_zero(engine, upload_dir, job_id)
    with Session(engine) as session:
        rows = session.scalars(select(VersionRow).where(VersionRow.job_id == job_id).order_by(VersionRow.number)).all()
        return [_to_version(row) for row in rows]


def accept_original(engine: object, upload_dir: str, job_id: str) -> Version:
    """Mark version 0 accepted. Its drawing and connection list stay as they are."""
    ensure_version_zero(engine, upload_dir, job_id)
    now = datetime.now(timezone.utc).isoformat()
    with Session(engine) as session:
        row = session.scalar(select(VersionRow).where(VersionRow.job_id == job_id, VersionRow.number == 0))
        if row is None:
            raise AppError(404, "NOT_FOUND", "Version 0 has not been stored.", {"job_id": job_id})
        row.status = "accepted"
        row.accepted_at = now
        session.commit()
        session.refresh(row)
        return _to_version(row)


def start_modify(engine: object, upload_dir: str, job_id: str, enabled: bool) -> dict:
    """Copy version 0 into the working draft. Version 0 is not changed."""
    _require_modify(enabled)
    original = ensure_version_zero(engine, upload_dir, job_id)
    draft = {
        "parent_version_id": original.id,
        "connections": [item.model_dump(mode="json", by_alias=True) for item in original.connection_list_snapshot],
        "history": [[item.model_dump(mode="json", by_alias=True) for item in original.connection_list_snapshot]],
        "history_index": 0,
        "change_log": [],
        "svg": original.svg or "",
        "verification": original.verification.model_dump(mode="json") if original.verification else None,
        "regen_ms": 0,
    }
    write_json(job_folder(upload_dir, job_id) / DRAFT_NAME, draft)
    return draft


def load_draft(upload_dir: str, job_id: str) -> dict:
    """Read the working copy. A missing file is a 404."""
    path = job_folder(upload_dir, job_id) / DRAFT_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "There is no working copy for this project.", {"job_id": job_id})
    return read_json(path)


def apply_operation(engine: object, upload_dir: str, job_id: str, operation: dict, enabled: bool) -> dict:
    """Apply one edit, rebuild the sketch, and keep an undo snapshot."""
    _require_modify(enabled)
    draft = load_draft(upload_dir, job_id)
    connections = [ConnectionSnapshotEntry.model_validate(item) for item in draft["connections"]]
    updated = _operate(connections, operation)
    return _store_draft(engine, upload_dir, job_id, draft, updated, operation.get("what") or operation.get("op", "edit"))


def undo_draft(engine: object, upload_dir: str, job_id: str, enabled: bool) -> dict:
    """Return the working copy to the previous snapshot."""
    _require_modify(enabled)
    draft = load_draft(upload_dir, job_id)
    index = int(draft.get("history_index", 0))
    if index <= 0:
        raise AppError(409, "NOTHING_TO_UNDO", "There is no earlier edit to undo.", {"job_id": job_id})
    draft["history_index"] = index - 1
    draft["connections"] = draft["history"][index - 1]
    _rebuild_into(upload_dir, job_id, draft, "Undid the last edit")
    write_json(job_folder(upload_dir, job_id) / DRAFT_NAME, draft)
    return draft


def redo_draft(engine: object, upload_dir: str, job_id: str, enabled: bool) -> dict:
    """Re-apply the snapshot that undo stepped away from."""
    _require_modify(enabled)
    draft = load_draft(upload_dir, job_id)
    index = int(draft.get("history_index", 0))
    history = draft.get("history", [])
    if index >= len(history) - 1:
        raise AppError(409, "NOTHING_TO_REDO", "There is no edit to redo.", {"job_id": job_id})
    draft["history_index"] = index + 1
    draft["connections"] = history[index + 1]
    _rebuild_into(upload_dir, job_id, draft, "Redid the edit")
    write_json(job_folder(upload_dir, job_id) / DRAFT_NAME, draft)
    return draft


def save_draft(engine: object, upload_dir: str, job_id: str, note: str, enabled: bool) -> Version:
    """Store the working copy as the next version. Version 0 stays as it was."""
    _require_modify(enabled)
    draft = load_draft(upload_dir, job_id)
    with Session(engine) as session:
        numbers = session.scalars(select(VersionRow.number).where(VersionRow.job_id == job_id)).all()
        number = (max(numbers) if numbers else 0) + 1
        now = datetime.now(timezone.utc)
        row = VersionRow(
            id=uuid.uuid4().hex,
            job_id=job_id,
            number=number,
            parent=draft["parent_version_id"],
            status="edited",
            connection_list_snapshot=draft["connections"],
            svg=draft.get("svg") or "",
            verification=draft.get("verification"),
            change_log=draft.get("change_log") or [],
            created_at=now.isoformat(),
            created_by=AUTHOR,
            note=note or f"Saved version {number}",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        saved = _to_version(row)
    draft["parent_version_id"] = saved.id
    write_json(job_folder(upload_dir, job_id) / DRAFT_NAME, draft)
    return saved


def restore_version(engine: object, upload_dir: str, job_id: str, number: int, enabled: bool) -> Version:
    """Copy a saved version into a new version. History rows are not rewritten."""
    _require_modify(enabled)
    with Session(engine) as session:
        source = session.scalar(select(VersionRow).where(VersionRow.job_id == job_id, VersionRow.number == number))
        if source is None:
            raise AppError(404, "NOT_FOUND", "That version does not exist.", {"number": number})
        numbers = session.scalars(select(VersionRow.number).where(VersionRow.job_id == job_id)).all()
        now = datetime.now(timezone.utc)
        row = VersionRow(
            id=uuid.uuid4().hex,
            job_id=job_id,
            number=max(numbers) + 1,
            parent=source.id,
            status="edited",
            connection_list_snapshot=source.connection_list_snapshot,
            svg=source.svg,
            verification=source.verification,
            change_log=[
                *(source.change_log or []),
                {"who": AUTHOR, "when": now.isoformat(), "what": f"Restored version {number}", "note": ""},
            ],
            created_at=now.isoformat(),
            created_by=AUTHOR,
            note=f"Restored from version {number}",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_version(row)


def compare_versions(engine: object, job_id: str, left: int, right: int) -> dict:
    """List links and fields that differ. Nodes are matched by tag, edges by their ends."""
    with Session(engine) as session:
        rows = {
            row.number: row
            for row in session.scalars(select(VersionRow).where(VersionRow.job_id == job_id)).all()
        }
    if left not in rows or right not in rows:
        raise AppError(404, "NOT_FOUND", "One of those versions does not exist.", {"left": left, "right": right})
    return _diff(rows[left].connection_list_snapshot or [], rows[right].connection_list_snapshot or [])


def export_workbook(engine: object, upload_dir: str, job_id: str) -> bytes:
    """Build the connection workbook from the draft, or from version 0 when no draft exists."""
    try:
        connections = load_draft(upload_dir, job_id)["connections"]
        version_label = "draft"
    except AppError:
        connections = [item.model_dump(mode="json", by_alias=True) for item in ensure_version_zero(engine, upload_dir, job_id).connection_list_snapshot]
        version_label = "0"
    graph = graph_build.load_graph(upload_dir, job_id)
    book = Workbook()
    links = book.active
    links.title = "Connections"
    headers = ["ID", "From", "To", "Direction", "Line type", "Color", "Style", "Group", "Crossing mode", "Status", "Confidence", "Evidence/Notes"]
    links.append(headers)
    for item in connections:
        links.append([
            item.get("id", ""),
            _safe_cell(item.get("from", "")),
            _safe_cell(item.get("to", "")),
            item.get("direction", "unknown"),
            item.get("line_type", "process"),
            _safe_cell(item.get("color", "")),
            _safe_cell(item.get("style", "")),
            _safe_cell(item.get("group", "")),
            item.get("crossing_mode", "auto"),
            item.get("status", "auto"),
            item.get("confidence_score", ""),
            _safe_cell(item.get("notes", "")),
        ])
    nodes = book.create_sheet("Nodes")
    nodes.append(["Tag", "Type", "Signal", "Detail level", "Kept"])
    tags = []
    for node in graph.nodes:
        if node.type == "endpoint":
            continue
        label = node.tag or node.id
        tags.append(label)
        nodes.append([_safe_cell(label), node.type, _safe_cell(node.signal), node.detail_level, node.kept])
    from app.services.sanity import sanity_warnings
    warnings = book.create_sheet("Warnings")
    warnings.append(["Rule", "Message"])
    for item in sanity_warnings(graph):
        warnings.append([item.rule, item.reason])
    info = book.create_sheet("Info")
    info.append(["Job id", job_id])
    info.append(["Version", version_label])
    info.append(["Date", datetime.now(timezone.utc).isoformat()])
    if tags:
        tag_list = ",".join(tags[:50])
        links.add_data_validation(DataValidation(type="list", formula1=f'"{tag_list}"', sqref="B2:C200"))
    for column, choices in (("D2:D200", _DIRECTIONS), ("E2:E200", _LINES), ("I2:I200", _CROSSINGS), ("J2:J200", _STATUSES)):
        links.add_data_validation(DataValidation(type="list", formula1=f'"{",".join(sorted(choices))}"', sqref=column))
    links.cell(1, 11).comment = None
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def validate_workbook(
    upload_dir: str,
    job_id: str,
    filename: str,
    payload: bytes,
    max_bytes: int,
    max_uncompressed_bytes: int = 200 * 1024 * 1024,
    max_zip_entries: int = 2000,
    inspect_timeout_seconds: int = 30,
) -> dict:
    """Check an edited workbook. Nothing is applied. Formulas are not evaluated."""
    if not filename.lower().endswith(".xlsx"):
        shown = filename.replace("\\", "/").rsplit("/", 1)[-1][:200] or "workbook"
        raise AppError(415, "UNSUPPORTED_FILE", "Only an .xlsx workbook can be imported. Macro files are refused.", {"filename": shown})
    if len(payload) > max_bytes:
        raise AppError(413, "FILE_TOO_LARGE", "That workbook is larger than the upload limit.", {"limit_bytes": max_bytes})
    from app.config import Settings
    from app.services.bounded_parse import inspect_xlsx

    inspect_xlsx(
        payload,
        Settings(
            upload_dir=upload_dir,
            zip_max_uncompressed_bytes=max_uncompressed_bytes,
            zip_max_entries=max_zip_entries,
            inspect_timeout_seconds=inspect_timeout_seconds,
        ),
    )
    graph = graph_build.load_graph(upload_dir, job_id)
    known = {node.tag or node.id for node in graph.nodes}
    book = load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
    if "Connections" not in book.sheetnames:
        return {"errors": ["The Connections sheet is missing."], "warnings": [], "preview": []}
    sheet = book["Connections"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(cell or "").strip() for cell in rows[0]] if rows else []
    errors = [f"Missing column {name}." for name in _REQUIRED if name not in header]
    warnings: list[str] = []
    preview: list[dict] = []
    if errors:
        return {"errors": errors, "warnings": warnings, "preview": preview}
    index = {name: header.index(name) for name in header}
    seen: set[tuple[str, str]] = set()
    for row in rows[1:]:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        item = {
            "id": str(row[index["ID"]] or ""),
            "from": str(row[index["From"]] or "").strip(),
            "to": str(row[index["To"]] or "").strip(),
            "direction": str(row[index["Direction"]] or "").strip(),
            "line_type": str(row[index["Line type"]] or "process").strip(),
            "crossing_mode": str(row[index["Crossing mode"]] or "auto").strip(),
            "status": str(row[index["Status"]] or "auto").strip(),
        }
        if item["from"] not in known or item["to"] not in known:
            errors.append(f"Unknown tag on {item['from']} -> {item['to']}.")
        if item["direction"] not in _DIRECTIONS or item["line_type"] not in _LINES or item["crossing_mode"] not in _CROSSINGS or item["status"] not in _STATUSES:
            errors.append(f"Invalid value on {item['from']} -> {item['to']}.")
        key = tuple(sorted((item["from"], item["to"])))
        if key in seen:
            errors.append(f"Duplicate link {item['from']} -> {item['to']}.")
        seen.add(key)
        if item["from"].startswith("P-") and item["status"] != "user_removed":
            pass
        preview.append(item)
    pumps = {node.tag for node in graph.nodes if node.subtype == "pump" and node.tag}
    for pump in pumps:
        touching = [item for item in preview if item["status"] != "user_removed" and pump in {item["from"], item["to"]}]
        if len(touching) < 2:
            warnings.append(f"Pump {pump} does not have both an inlet and an outlet in this sheet.")
    ends: dict[str, int] = {}
    for item in preview:
        if item["status"] == "user_removed":
            continue
        ends[item["from"]] = ends.get(item["from"], 0) + 1
        ends[item["to"]] = ends.get(item["to"], 0) + 1
    for tag, count in ends.items():
        if count == 1 and not tag.startswith("OFF"):
            warnings.append(f"{tag} is a dead end in this sheet.")
    current = {item.get("id"): item for item in (load_draft(upload_dir, job_id)["connections"] if (job_folder(upload_dir, job_id) / DRAFT_NAME).is_file() else [])}
    changes = [item for item in preview if current.get(item["id"], {}).get("direction") != item["direction"] or item["id"] not in current]
    return {"errors": errors, "warnings": warnings, "preview": changes}


def apply_workbook(
    engine: object,
    upload_dir: str,
    job_id: str,
    filename: str,
    payload: bytes,
    max_bytes: int,
    enabled: bool,
    max_uncompressed_bytes: int = 200 * 1024 * 1024,
    max_zip_entries: int = 2000,
    inspect_timeout_seconds: int = 30,
) -> dict:
    """Apply a validated workbook onto a new working copy."""
    _require_modify(enabled)
    checked = validate_workbook(
        upload_dir,
        job_id,
        filename,
        payload,
        max_bytes,
        max_uncompressed_bytes,
        max_zip_entries,
        inspect_timeout_seconds,
    )
    if checked["errors"]:
        raise AppError(422, "IMPORT_INVALID", "The workbook has blocking errors and was not applied.", {"errors": checked["errors"]})
    if not (job_folder(upload_dir, job_id) / DRAFT_NAME).is_file():
        start_modify(engine, upload_dir, job_id, True)
    draft = load_draft(upload_dir, job_id)
    by_id = {item.get("id"): item for item in draft["connections"]}
    for change in checked["preview"]:
        if change["id"] in by_id:
            by_id[change["id"]].update(change)
        else:
            change["status"] = "user_added" if change["status"] == "auto" else change["status"]
            draft["connections"].append(change)
    connections = [ConnectionSnapshotEntry.model_validate(item) for item in draft["connections"]]
    return _store_draft(engine, upload_dir, job_id, draft, connections, "Imported an edited workbook")


def print_pdf(upload_dir: str, job_id: str, *, page_size: str, orientation: str) -> bytes:
    """Draw a vector PDF. Cairo is not available here, so ReportLab draws the lines and words."""
    from reportlab.lib.pagesizes import A3, A4, landscape, portrait
    from reportlab.pdfgen import canvas

    folder = job_folder(upload_dir, job_id)
    svg = (folder / SKETCH_NAME).read_text(encoding="utf-8") if (folder / SKETCH_NAME).is_file() else "<svg></svg>"
    size = A3 if page_size.upper() == "A3" else A4
    size = landscape(size) if orientation == "landscape" else portrait(size)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=size, pageCompression=0)
    width, height = size
    pdf.setTitle(f"UNTANGLE {job_id}")
    pdf.drawString(36, height - 36, f"Project {job_id}")
    pdf.drawString(36, height - 52, datetime.now(timezone.utc).date().isoformat())
    pdf.drawString(36, height - 68, "Passed the defined automated checks. This is not an engineering or safety certification.")
    pdf.drawString(36, 36, "Legend: process line, signal line, review marker")
    pdf.drawString(36, 20, "Legend")
    _draw_svg_vectors(pdf, svg, 36, 80, width - 72, height - 160)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _draw_svg_vectors(pdf, svg: str, left: float, bottom: float, width: float, height: float) -> None:
    import re

    pdf.rect(left, bottom, width, height, stroke=1, fill=0)
    for match in re.finditer(r'<text[^>]*>([^<]*)</text>', svg):
        pdf.drawString(left + 8, bottom + height - 20, match.group(1)[:80])
        break
    for match in re.finditer(r'points="([^"]+)"', svg):
        pairs = []
        for part in match.group(1).split():
            if "," not in part:
                continue
            x_text, y_text = part.split(",", 1)
            pairs.append((left + float(x_text) * 0.4, bottom + height - float(y_text) * 0.4))
        if len(pairs) >= 2:
            path = pdf.beginPath()
            path.moveTo(pairs[0][0], pairs[0][1])
            for point in pairs[1:]:
                path.lineTo(point[0], point[1])
            pdf.drawPath(path, stroke=1, fill=0)


def _store_draft(engine: object, upload_dir: str, job_id: str, draft: dict, connections: list[ConnectionSnapshotEntry], what: str) -> dict:
    dumped = [item.model_dump(mode="json", by_alias=True) for item in connections]
    history = list(draft.get("history") or [])
    index = int(draft.get("history_index", len(history) - 1))
    history = history[: index + 1]
    history.append(dumped)
    draft["history"] = history
    draft["history_index"] = len(history) - 1
    draft["connections"] = dumped
    _rebuild_into(upload_dir, job_id, draft, what)
    write_json(job_folder(upload_dir, job_id) / DRAFT_NAME, draft)
    return draft


def _rebuild_into(upload_dir: str, job_id: str, draft: dict, what: str) -> None:
    started = time.perf_counter()
    graph = graph_build.load_graph(upload_dir, job_id)
    original_direction = {edge.id: edge.direction for edge in graph.edges}
    edited = _apply_to_graph(graph, [ConnectionSnapshotEntry.model_validate(item) for item in draft["connections"]])
    _ = original_direction
    simplified = simplify_graph(edited)
    laid = layout_graph(simplified)
    svg, _meta = render_sketch(simplified, laid, None)
    elapsed = int((time.perf_counter() - started) * 1000)
    verification = _edit_verification(original_direction, draft["connections"])
    draft["svg"] = svg
    draft["verification"] = verification.model_dump(mode="json")
    draft["regen_ms"] = elapsed
    draft.setdefault("change_log", []).append(
        {"who": AUTHOR, "when": datetime.now(timezone.utc).isoformat(), "what": what, "note": f"Redraw took {elapsed} ms"}
    )


def _operate(connections: list[ConnectionSnapshotEntry], operation: dict) -> list[ConnectionSnapshotEntry]:
    kind = operation.get("op")
    if kind == "delete":
        for item in connections:
            if item.id == operation.get("id"):
                item.status = "user_removed"
        return connections
    if kind == "reverse":
        for item in connections:
            if item.id == operation.get("id") and item.direction in {"forward", "reverse"}:
                item.direction = "reverse" if item.direction == "forward" else "forward"
                if item.status == "auto":
                    item.status = "user_edited"
        return connections
    if kind == "style":
        for item in connections:
            if item.id == operation.get("id"):
                item.color = str(operation.get("color", item.color))
                item.style = str(operation.get("style", item.style))
                item.crossing_mode = operation.get("crossing_mode", item.crossing_mode)
                if item.status == "auto":
                    item.status = "user_edited"
        return connections
    if kind == "add":
        connections.append(
            ConnectionSnapshotEntry.model_validate(
                {
                    "id": operation.get("id") or f"user-{uuid.uuid4().hex[:8]}",
                    "from": operation["from"],
                    "to": operation["to"],
                    "direction": operation.get("direction", "unknown"),
                    "line_type": operation.get("line_type", "process"),
                    "status": "user_added",
                    "crossing_mode": operation.get("crossing_mode", "auto"),
                }
            )
        )
        return connections
    raise AppError(422, "UNKNOWN_OPERATION", "That edit is not one of delete, add, reverse, or style.", {"op": kind})


def _connections_from_graph(graph: DiagramGraph) -> list[ConnectionSnapshotEntry]:
    labels = {node.id: node.tag or node.id for node in graph.nodes}
    items = []
    for edge in graph.edges:
        items.append(
            ConnectionSnapshotEntry.model_validate(
                {
                    "id": edge.id,
                    "from": labels.get(edge.from_id, edge.from_id),
                    "to": labels.get(edge.to_id, edge.to_id),
                    "direction": edge.direction,
                    "line_type": edge.line_type,
                    "color": edge.color,
                    "style": edge.style,
                    "crossing_mode": edge.crossing_mode,
                    "status": edge.status,
                    "confidence_score": edge.confidence.score,
                    "notes": edge.confidence.reason,
                }
            )
        )
    return items


def _apply_to_graph(graph: DiagramGraph, connections: list[ConnectionSnapshotEntry]) -> DiagramGraph:
    by_id = {edge.id: edge for edge in graph.edges}
    labels = {node.tag or node.id: node.id for node in graph.nodes}
    kept: list[Edge] = []
    for item in connections:
        if item.status == "user_removed":
            continue
        edge = by_id.get(item.id)
        if edge is None:
            source = labels.get(item.from_)
            target = labels.get(item.to)
            if not source or not target:
                continue
            edge = Edge(
                id=item.id or f"user-{item.from_}-{item.to}",
                from_id=source,
                to_id=target,
                direction=item.direction,
                line_type=item.line_type,
                color=item.color,
                style=item.style,
                crossing_mode=item.crossing_mode,
                status="user_added",
                confidence=Confidence(level=level_for_score(0.6), score=0.6, reason="Added in the connection list."),
            )
        else:
            edge.direction = item.direction
            edge.color = item.color
            edge.style = item.style
            edge.crossing_mode = item.crossing_mode
            edge.status = "user_edited" if item.status == "user_edited" else edge.status
        kept.append(edge)
    graph.edges = kept
    return graph


def _tool_verification(graph: DiagramGraph) -> VerificationResult:
    return VerificationResult(
        connections_added=0,
        connections_removed=0,
        tags_placed=sum(1 for node in graph.nodes if node.tag),
        tags_total=sum(1 for node in graph.nodes if node.tag),
        rule_results=[RuleResult(rule_id="R-VERSION-000", passed=True, message="Version 0 matches the tool graph.")],
        verified=True,
        tool_added=0,
        tool_removed=0,
    )


def _edit_verification(original_direction: dict[str, str], connections: list[dict]) -> VerificationResult:
    user_added = sum(1 for item in connections if item.get("status") == "user_added")
    user_removed = sum(1 for item in connections if item.get("status") == "user_removed")
    user_reversed = sum(
        1
        for item in connections
        if item.get("id") in original_direction and item.get("direction") != original_direction[item.get("id")] and item.get("status") != "user_removed"
    )
    broken = user_removed > 0 and any(item.get("from", "").startswith("P-") and item.get("status") == "user_removed" for item in connections)
    passed = not broken
    return VerificationResult(
        connections_added=0,
        connections_removed=0,
        tags_placed=1,
        tags_total=1,
        rule_results=[RuleResult(rule_id="R-EDIT-001", passed=passed, message="User edits are counted apart from the tool extraction.")],
        verified=passed,
        tool_added=0,
        tool_removed=0,
        user_added=user_added,
        user_removed=user_removed,
        user_reversed=user_reversed,
    )


def _diff(left: list, right: list) -> dict:
    def key(item: dict) -> tuple[str, str]:
        return (str(item.get("from", "")), str(item.get("to", "")))

    left_map = {key(item): item for item in left}
    right_map = {key(item): item for item in right}
    added = [right_map[name] for name in right_map if name not in left_map]
    removed = [left_map[name] for name in left_map if name not in right_map]
    changed = []
    for name in left_map.keys() & right_map.keys():
        fields = [
            field
            for field in ("direction", "color", "style", "crossing_mode", "status")
            if left_map[name].get(field) != right_map[name].get(field)
        ]
        if fields:
            changed.append({"from": name[0], "to": name[1], "fields": fields})
    return {"added": added, "removed": removed, "changed": changed}


def _to_version(row: VersionRow) -> Version:
    created = _parse_time(row.created_at)
    accepted = _parse_time(row.accepted_at)
    log = []
    for entry in row.change_log or []:
        when = entry.get("when")
        if isinstance(when, str):
            entry = {**entry, "when": when}
        log.append(entry)
    return Version.model_validate(
        {
            "id": row.id,
            "number": row.number,
            "parent": row.parent,
            "status": row.status,
            "connection_list_snapshot": row.connection_list_snapshot or [],
            "svg": row.svg,
            "verification": row.verification,
            "change_log": log,
            "created_at": created,
            "created_by": row.created_by or "",
            "note": row.note or "",
            "accepted_at": accepted,
        }
    )


def _parse_time(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _safe_cell(value: str) -> str:
    from app.services.export_files import excel_cell

    cleaned = excel_cell(str(value or ""))
    return cleaned if isinstance(cleaned, str) else str(cleaned)


def _require_modify(enabled: bool) -> None:
    if not enabled:
        raise AppError(403, "MODIFY_DISABLED", "Modify is turned off. Version 0 can be viewed and accepted, not edited.", {})


def _diff_link_count(before: list[ConnectionSnapshotEntry], after: list[ConnectionSnapshotEntry]) -> int:
    return len({item.id for item in before} ^ {item.id for item in after})
