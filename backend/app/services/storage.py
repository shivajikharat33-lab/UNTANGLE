"""Paths under a job folder. User filenames are never used as paths."""

from __future__ import annotations

import json
from pathlib import Path

from app.errors import AppError

PDF_NAME = "original.pdf"
IO_NAME = "io_list.xlsx"
NORMALIZED_IO_NAME = "io_list.normalized.json"
EXTRACTION_NAME = "extraction.json"
TAG_REPORT_NAME = "tag_report.json"
DETECTIONS_NAME = "detections.json"
GEOMETRY_NAME = "geometry.json"
DRAFT_NAME = "draft.json"
GRAPH_NAME = "graph.json"
SIMPLIFIED_NAME = "simplified.json"
LAYOUT_NAME = "layout.json"
SKETCH_NAME = "sketch.svg"
SKETCH_META_NAME = "sketch_meta.json"


def job_folder(upload_dir: str, job_id: str) -> Path:
    """Return the existing folder for a job id, or raise NOT_FOUND."""
    if not job_id.isalnum():
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    root = Path(upload_dir).resolve()
    folder = (root / job_id).resolve()
    if folder.parent != root or not folder.is_dir():
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    return folder


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
