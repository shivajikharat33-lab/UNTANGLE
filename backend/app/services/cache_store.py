"""File cache for derived results. The key changes when the inputs or rules change.

The cache directory is configured. It is not an undocumented temp folder.
Original uploads are never deleted from here.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from app import graph_config as cfg


DERIVED_NAMES = (
    "extraction.json",
    "tag_report.json",
    "detections.json",
    "geometry.json",
    "graph.json",
    "simplified.json",
    "layout.json",
    "sketch.svg",
    "sketch_meta.json",
    "sketch_draft.svg",
)


def cache_key(pdf_sha256: str, io_sha256: str, config_payload: dict) -> str:
    """Hash the PDF, the IO workbook, the processing version, and the named settings."""
    raw = json.dumps(
        {
            "pdf": pdf_sha256,
            "io": io_sha256,
            "versions": {
                "graph": cfg.PROCESSING_VERSION,
                "patterns": cfg.PATTERN_VERSION,
                "checks": cfg.CHECK_VERSION,
                "coverage": cfg.COVERAGE_VERSION,
                "simplify": cfg.SIMPLIFY_VERSION,
                "layout": cfg.LAYOUT_VERSION,
                "render": cfg.RENDER_VERSION,
            },
            "config": config_payload,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def config_payload() -> dict:
    """The settings that change derived results. Add a new entry when a cutoff changes."""
    return {
        "snap": cfg.DEFAULT_SNAP_TOLERANCE,
        "attach": cfg.DEFAULT_NODE_ATTACH_TOLERANCE,
        "tag_recall_min": cfg.TAG_RECALL_MIN,
        "max_layout_nodes": cfg.MAX_LAYOUT_NODES,
        "process_color": cfg.PROCESS_COLOR,
        "signal_color": cfg.SIGNAL_COLOR,
    }


def store_file(cache_dir: str, key: str, name: str, source: Path) -> None:
    """Copy one derived file into the cache. Missing sources are skipped."""
    if name not in DERIVED_NAMES or not source.is_file():
        return
    folder = Path(cache_dir) / key
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, folder / name)


def fetch_file(cache_dir: str, key: str, name: str, destination: Path) -> bool:
    """Copy a cached file into the job folder. Returns False when it is absent."""
    source = Path(cache_dir) / key / name
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return True


def cache_is_complete(cache_dir: str, key: str) -> bool:
    """True when every derived artifact for this key is present."""
    folder = Path(cache_dir) / key
    return all((folder / name).is_file() for name in DERIVED_NAMES if name != "sketch_draft.svg")


def restore_derived(cache_dir: str, key: str, job_folder: Path) -> list[str]:
    """Copy derived files only. original.pdf and io_list.xlsx are never removed or replaced."""
    restored = []
    for name in DERIVED_NAMES:
        if fetch_file(cache_dir, key, name, job_folder / name):
            restored.append(name)
    return restored
