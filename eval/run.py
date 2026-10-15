"""Run python -m eval.run from the repository root.

Results land in eval/results. Metrics are n/a when a drawing has no answer key.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.answer_key import AnswerKey
from app.schemas.graph import DiagramGraph
from app.services.score import score_graph

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
FIXTURE = ROOT / "eval" / "fixtures" / "synthetic_plant.json"


def validate_key(payload: dict) -> AnswerKey:
    """Reject a key that does not match the answer-key contract."""
    return AnswerKey.model_validate(payload)


def run() -> dict:
    """Score the committed synthetic fixture and write CSV, JSON, and Markdown."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    key = validate_key(raw["answer_key"])
    graph = DiagramGraph.model_validate(raw["graph"])
    scored = score_graph(graph, key)
    broken = raw.get("broken_user_removed", 0)
    limitations = "This table uses synthetic drawings only. Variants are not independent customer drawings. Unmeasured metrics are n/a. This is not a general accuracy or speed claim."
    row = {
        "drawing_id": key.drawing_id,
        "category": raw.get("category", "sample"),
        "tags_matched": scored.tags_matched,
        "tags_expected": scored.tags_expected,
        "equipment_matched": scored.equipment_matched,
        "equipment_expected": scored.equipment_expected,
        "connections_matched": scored.connections_matched,
        "connections_expected": scored.connections_expected,
        "verification_difference": broken,
        "stage_time": "n/a",
        "warning_usefulness": "not labeled",
        "limitations": limitations,
    }
    blank = {
        "tags_matched": "n/a",
        "tags_expected": "n/a",
        "equipment_matched": "n/a",
        "equipment_expected": "n/a",
        "connections_matched": "n/a",
        "connections_expected": "n/a",
        "verification_difference": "n/a",
        "stage_time": "n/a",
        "warning_usefulness": "not labeled",
        "limitations": limitations,
    }
    rows = [
        row,
        {"drawing_id": "synthetic-eval-rotated", "category": "variant", **blank},
        {"drawing_id": "synthetic-eval-heldout", "category": "held-out", **blank},
    ]
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    body = {"generated_at": stamp, "drawing_count": len(rows), "rows": rows}
    (RESULTS / "latest.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    with (RESULTS / "latest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        f"# Evaluation {stamp}",
        "",
        f"Drawings: {body['drawing_count']}",
        "",
        "| drawing | category | tags | equipment | connections | verification difference |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        tags = item["tags_matched"] if item["tags_matched"] == "n/a" else f"{item['tags_matched']}/{item['tags_expected']}"
        equipment = item["equipment_matched"] if item["equipment_matched"] == "n/a" else f"{item['equipment_matched']}/{item['equipment_expected']}"
        connections = item["connections_matched"] if item["connections_matched"] == "n/a" else f"{item['connections_matched']}/{item['connections_expected']}"
        lines.append(f"| {item['drawing_id']} | {item['category']} | {tags} | {equipment} | {connections} | {item['verification_difference']} |")
    lines.extend(["", limitations, ""])
    (RESULTS / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    return body


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
