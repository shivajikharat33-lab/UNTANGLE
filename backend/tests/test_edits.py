"""Version 0 stays put. Edits, import checks, compare, and print are exercised here."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, level_for_score
from app.database import init_db, make_engine
from app.models import JobRow
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, DiagramGraph, Edge, Node
from app.services import edits
from app.services.graph_build import write_graph
from app.services.storage import job_folder


def _confidence() -> Confidence:
    return Confidence(level=level_for_score(0.9), score=0.9, reason="fixture")


def _ready(tmp_path: Path):
    upload = tmp_path / "uploads"
    job_id = "jobedit01"
    folder = job_folder_make(upload, job_id)
    graph = DiagramGraph(
        nodes=[
            Node(id="tank", type="equipment", tag="T-101", bbox=BBox(page=1, x=0, y=0, w=10, h=10), confidence=_confidence()),
            Node(id="pump", type="equipment", tag="P-101A", subtype="pump", bbox=BBox(page=1, x=40, y=0, w=10, h=10), confidence=_confidence()),
        ],
        edges=[
            Edge(id="e1", from_id="tank", to_id="pump", direction="forward", line_type="process", confidence=_confidence()),
        ],
    )
    write_graph(str(upload), job_id, graph)
    (folder / "sketch.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>T-101</text><polyline points="0,0 10,0" /></svg>', encoding="utf-8")
    engine = make_engine("sqlite:///" + (tmp_path / "edit.db").as_posix())
    init_db(engine)
    with Session(engine) as session:
        session.add(JobRow(id=job_id, name="edit"))
        session.commit()
    return engine, str(upload), job_id


def job_folder_make(upload: Path, job_id: str) -> Path:
    folder = upload / job_id
    folder.mkdir(parents=True)
    return folder


def test_version_zero_cannot_be_rewritten_and_keep_only_marks_it(tmp_path: Path) -> None:
    engine, upload, job_id = _ready(tmp_path)
    original = edits.ensure_version_zero(engine, upload, job_id)
    again = edits.ensure_version_zero(engine, upload, job_id)
    assert original.id == again.id
    accepted = edits.accept_original(engine, upload, job_id)
    assert accepted.status == "accepted"
    assert accepted.svg == original.svg
    with pytest.raises(SQLAlchemyError):
        with engine.begin() as connection:
            connection.execute(text("UPDATE versions SET svg = '<svg/>' WHERE number = 0"))


def test_modify_operation_undo_and_disabled(tmp_path: Path) -> None:
    engine, upload, job_id = _ready(tmp_path)
    draft = edits.start_modify(engine, upload, job_id, True)
    assert draft["connections"][0]["status"] == "auto"
    edited = edits.apply_operation(engine, upload, job_id, {"op": "reverse", "id": "e1"}, True)
    assert edited["connections"][0]["direction"] == "reverse"
    assert edited["verification"]["user_reversed"] == 1
    assert edited["verification"]["tool_added"] == 0
    restored = edits.undo_draft(engine, upload, job_id, True)
    assert restored["connections"][0]["direction"] == "forward"
    redone = edits.redo_draft(engine, upload, job_id, True)
    assert redone["connections"][0]["direction"] == "reverse"
    saved = edits.save_draft(engine, upload, job_id, "reversed the pump line", True)
    assert saved.number == 1
    assert saved.parent
    try:
        edits.apply_operation(engine, upload, job_id, {"op": "delete", "id": "e1"}, False)
        raise AssertionError("modify should be blocked")
    except Exception as exc:
        assert getattr(exc, "error_code", "") == "MODIFY_DISABLED"


def test_import_rejects_bad_rows_and_formula_text(tmp_path: Path) -> None:
    engine, upload, job_id = _ready(tmp_path)
    edits.start_modify(engine, upload, job_id, True)
    try:
        edits.validate_workbook(upload, job_id, "bad.xlsm", b"not", 1000)
        raise AssertionError("xlsm should be refused")
    except Exception as exc:
        assert getattr(exc, "error_code", "") == "UNSUPPORTED_FILE"
    from openpyxl import Workbook
    import io
    book = Workbook()
    sheet = book.active
    sheet.title = "Connections"
    sheet.append(["ID", "From", "To", "Direction", "Line type", "Color", "Style", "Group", "Crossing mode", "Status", "Confidence", "Evidence/Notes"])
    sheet.append(["e1", "NO-TAG", "P-101A", "sideways", "process", "=cmd", "", "", "auto", "auto", "", ""])
    buffer = io.BytesIO()
    book.save(buffer)
    checked = edits.validate_workbook(upload, job_id, "ok.xlsx", buffer.getvalue(), 2_000_000)
    assert any("Unknown tag" in error for error in checked["errors"])
    assert any("Invalid value" in error for error in checked["errors"])
    safe = edits._safe_cell("=cmd")
    assert safe.startswith("'")


def test_compare_restore_crossing_and_print(tmp_path: Path) -> None:
    engine, upload, job_id = _ready(tmp_path)
    edits.start_modify(engine, upload, job_id, True)
    edits.apply_operation(engine, upload, job_id, {"op": "style", "id": "e1", "crossing_mode": "keep", "color": "#111"}, True)
    before = {item["id"] for item in edits.load_draft(upload, job_id)["connections"]}
    edits.apply_operation(engine, upload, job_id, {"op": "style", "id": "e1", "crossing_mode": "avoid"}, True)
    after = {item["id"] for item in edits.load_draft(upload, job_id)["connections"]}
    assert before == after
    saved = edits.save_draft(engine, upload, job_id, "crossing", True)
    diff = edits.compare_versions(engine, job_id, 0, saved.number)
    assert any("crossing_mode" in item["fields"] for item in diff["changed"])
    restored = edits.restore_version(engine, upload, job_id, 0, True)
    assert restored.number == saved.number + 1
    pdf = edits.print_pdf(upload, job_id, page_size="A4", orientation="landscape")
    assert pdf.startswith(b"%PDF")
    assert b"Legend" in pdf
    assert b"Project" in pdf
