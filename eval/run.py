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
        "limitations": "This table is one synthetic drawing. It is not a general accuracy or speed claim.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    body = {"generated_at": stamp, "drawing_count": 1, "rows": [row]}
    (RESULTS / "latest.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    with (RESULTS / "latest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    (RESULTS / "latest.md").write_text(
        "\n".join([
            f"# Evaluation {stamp}",
            "",
            f"Drawings: {body['drawing_count']}",
            "",
            "| drawing | category | tags | equipment | connections | verification difference |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| {row['drawing_id']} | {row['category']} | {row['tags_matched']}/{row['tags_expected']} | {row['equipment_matched']}/{row['equipment_expected']} | {row['connections_matched']}/{row['connections_expected']} | {row['verification_difference']} |",
            "",
            row["limitations"],
            "",
        ]),
        encoding="utf-8",
    )
    return body


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
