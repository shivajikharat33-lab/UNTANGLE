"""The harness writes a real table and rejects a bad answer key."""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT))

import pytest
from pydantic import ValidationError

from eval.run import RESULTS, run, validate_key


def test_harness_writes_results_and_rejects_a_bad_key() -> None:
    body = run()
    assert body["drawing_count"] == 3
    assert (RESULTS / "latest.json").is_file()
    assert (RESULTS / "latest.csv").is_file()
    assert (RESULTS / "latest.md").is_file()
    row = body["rows"][0]
    assert row["tags_matched"] == 2
    assert row["connections_matched"] == 1
    assert row["verification_difference"] == 1
    assert "not a general accuracy" in row["limitations"]
    with pytest.raises(ValidationError):
        validate_key({"drawing_id": ""})
    stored = json.loads((RESULTS / "latest.json").read_text(encoding="utf-8"))
    assert stored["drawing_count"] == 3
    assert {item["category"] for item in stored["rows"]} == {"sample", "variant", "held-out"}
    _ = Path
