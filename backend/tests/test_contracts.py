"""Checks that the shared contracts reject impossible data."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import HIGH_CONFIDENCE_MIN, MEDIUM_CONFIDENCE_MIN, level_for_score
from app.schemas.answer_key import AnswerKey
from app.schemas.confidence import Confidence
from app.schemas.errors import ErrorResponse
from app.schemas.export import ExportMetadata
from app.schemas.graph import DiagramGraph, Edge, Node
from app.schemas.job import Job, Version
from app.schemas.reports import ConnectionReportRow, TagReportRow
from app.schemas.stages import STAGE_ORDER, ProcessingRun, StageRecord
from app.schemas.verification import VerificationResult

ROOT = Path(__file__).resolve().parents[2]
HIGH = {"level": "high", "score": 0.91, "reason": "tag text matched the IO list exactly"}
MEDIUM = {"level": "medium", "score": 0.70, "reason": "tag matched after a small spelling difference"}
LOW = {"level": "low", "score": 0.40, "reason": "line was traced with little supporting text"}


def test_confidence_thresholds_are_ordered() -> None:
    assert 0.0 < MEDIUM_CONFIDENCE_MIN < HIGH_CONFIDENCE_MIN <= 1.0
    assert level_for_score(HIGH_CONFIDENCE_MIN) == "high"
    assert level_for_score(MEDIUM_CONFIDENCE_MIN) == "medium"
    assert level_for_score(HIGH_CONFIDENCE_MIN - 0.01) == "medium"
    assert level_for_score(MEDIUM_CONFIDENCE_MIN - 0.01) == "low"


def test_confidence_level_must_match_score() -> None:
    Confidence.model_validate(HIGH)
    with pytest.raises(ValidationError):
        Confidence.model_validate(
            {"level": "high", "score": 0.10, "reason": "claimed high without support"}
        )


def test_frontend_thresholds_match_backend() -> None:
    text = (ROOT / "frontend" / "src" / "lib" / "confidence.ts").read_text(encoding="utf-8")
    high = re.search(r"export const HIGH_CONFIDENCE_MIN = ([0-9.]+);", text)
    medium = re.search(r"export const MEDIUM_CONFIDENCE_MIN = ([0-9.]+);", text)
    assert high is not None and medium is not None
    assert float(high.group(1)) == HIGH_CONFIDENCE_MIN
    assert float(medium.group(1)) == MEDIUM_CONFIDENCE_MIN


def test_node_keeps_an_uncertain_item_instead_of_dropping_it() -> None:
    node = Node.model_validate(
        {
            "id": "n1",
            "type": "instrument",
            "tag": "FT-101",
            "label": "Flow transmitter",
            "signal": "FT",
            "bbox": {"page": 1, "x": 10, "y": 20, "w": 30, "h": 12},
            "kept": False,
            "detail_level": 1,
            "confidence": LOW,
            "reason": "symbol outline was incomplete, so it stays in the graph and is hidden",
        }
    )
    assert node.kept is False
    with pytest.raises(ValidationError):
        Node.model_validate(
            {
                "id": "n2",
                "type": "widget",
                "confidence": HIGH,
            }
        )


def test_detail_level_is_only_one_to_three() -> None:
    with pytest.raises(ValidationError):
        Node.model_validate(
            {"id": "n1", "type": "valve", "detail_level": 4, "confidence": HIGH}
        )


def test_edge_round_trip_keeps_evidence_and_rules() -> None:
    edge = Edge.model_validate(
        {
            "id": "e1",
            "from_id": "pump",
            "to_id": "ft",
            "direction": "forward",
            "line_type": "process",
            "color": "#1d4e89",
            "style": "solid",
            "crossing_mode": "avoid",
            "status": "auto",
            "polyline": [{"x": 0, "y": 0}, {"x": 40, "y": 0}],
            "confidence": MEDIUM,
            "evidence": [
                {"source": "vector_line", "description": "continuous process line", "page": 1}
            ],
            "rule_results": [
                {"rule_id": "direction_from_arrow", "passed": True, "message": "arrow points downstream"}
            ],
        }
    )
    assert edge.polyline[1].x == 40
    DiagramGraph.model_validate({"nodes": [], "edges": [edge.model_dump()], "groups": []})


def test_stage_order_and_timing() -> None:
    assert STAGE_ORDER == (
        "Intake",
        "Read",
        "Detect",
        "MatchTags",
        "Trace",
        "SelfCheck",
        "Simplify",
        "Patterns",
        "Layout",
        "Report",
    )
    started = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    StageRecord.model_validate(
        {
            "name": "Read",
            "status": "done",
            "started_at": started,
            "ended_at": started,
            "duration_ms": 12,
            "warnings": ["one text object had no unicode mapping"],
        }
    )
    with pytest.raises(ValidationError):
        StageRecord.model_validate(
            {
                "name": "Read",
                "status": "done",
                "started_at": started,
                "ended_at": datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc),
            }
        )
    with pytest.raises(ValidationError):
        ProcessingRun.model_validate(
            {
                "stages": [
                    {"name": "Intake", "status": "pending"},
                    {"name": "Intake", "status": "running"},
                ]
            }
        )


def test_error_response_requires_a_request_id() -> None:
    body = ErrorResponse.model_validate(
        {
            "error_code": "NOT_FOUND",
            "message": "That job does not exist.",
            "details": {"job_id": "missing"},
            "request_id": "req-1",
        }
    )
    assert body.request_id == "req-1"
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate(
            {"error_code": "NOT_FOUND", "message": "missing id", "details": None, "request_id": ""}
        )


def test_tag_and_connection_reports_use_public_json_names() -> None:
    tag_row = TagReportRow.model_validate(
        {
            "tag": "FT-101",
            "signal": "FT",
            "status": "fuzzy",
            "confidence": MEDIUM,
            "location": {"page": 1, "x": 1, "y": 2, "w": 3, "h": 4},
            "suggestion": "FT-101A",
        }
    )
    assert tag_row.suggestion == "FT-101A"

    row = ConnectionReportRow.model_validate(
        {
            "from": "P-101",
            "to": "FT-101",
            "direction": "forward",
            "line_type": "signal",
            "confidence": HIGH,
            "evidence": [],
            "rules_passed": ["tag_on_both_ends"],
            "rules_failed": [],
            "source_location": None,
        }
    )
    dumped = row.model_dump(by_alias=True)
    assert dumped["from"] == "P-101"
    assert "from_" not in dumped


def test_verified_is_true_only_when_every_defined_check_passes() -> None:
    VerificationResult.model_validate(
        {
            "connections_added": 1,
            "connections_removed": 0,
            "tags_placed": 2,
            "tags_total": 2,
            "rule_results": [
                {"rule_id": "coverage", "passed": True, "message": "every IO tag was placed"}
            ],
            "verified": True,
        }
    )
    with pytest.raises(ValidationError, match="verified may only be true"):
        VerificationResult.model_validate(
            {
                "connections_added": 0,
                "connections_removed": 0,
                "tags_placed": 1,
                "tags_total": 2,
                "rule_results": [
                    {"rule_id": "coverage", "passed": False, "message": "FT-102 was not placed"}
                ],
                "verified": True,
            }
        )
    with pytest.raises(ValidationError, match="verified may only be true"):
        VerificationResult.model_validate(
            {
                "connections_added": 0,
                "connections_removed": 0,
                "tags_placed": 0,
                "tags_total": 0,
                "rule_results": [],
                "verified": True,
            }
        )
    unverified = VerificationResult.model_validate(
        {
            "connections_added": 0,
            "connections_removed": 1,
            "tags_placed": 1,
            "tags_total": 2,
            "rule_results": [
                {"rule_id": "coverage", "passed": False, "message": "one tag is missing"}
            ],
            "verified": False,
        }
    )
    assert unverified.verified is False
    with pytest.raises(ValidationError):
        VerificationResult.model_validate(
            {
                "connections_added": 0,
                "connections_removed": 0,
                "tags_placed": 3,
                "tags_total": 2,
                "rule_results": [],
                "verified": False,
            }
        )


def test_version_zero_is_original_and_later_versions_need_a_parent() -> None:
    original = Version.model_validate(
        {
            "id": "ver-0",
            "number": 0,
            "parent": None,
            "status": "auto",
            "connection_list_snapshot": [
                {"from": "P-101", "to": "V-101", "direction": "forward", "line_type": "process"}
            ],
            "svg": None,
            "verification": None,
            "change_log": [],
        }
    )
    assert original.number == 0
    with pytest.raises(ValidationError):
        Version.model_validate(
            {"id": "ver-0", "number": 0, "parent": "other", "status": "auto"}
        )
    with pytest.raises(ValidationError):
        Version.model_validate(
            {"id": "ver-0", "number": 0, "parent": None, "status": "edited"}
        )
    with pytest.raises(ValidationError):
        Version.model_validate({"id": "ver-1", "number": 1, "parent": None, "status": "auto"})

    edited = Version.model_validate(
        {
            "id": "ver-1",
            "number": 1,
            "parent": "ver-0",
            "status": "edited",
            "change_log": [
                {
                    "who": "student",
                    "when": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
                    "what": "reversed the line out of P-101",
                    "note": "arrow on the drawing points the other way",
                }
            ],
        }
    )
    job = Job.model_validate({"id": "job-1", "versions": [original, edited]})
    assert [item.number for item in job.versions] == [0, 1]
    with pytest.raises(ValidationError, match="version 0 must remain"):
        Job.model_validate({"id": "job-1", "versions": [edited]})


def test_export_metadata_and_answer_key_json() -> None:
    meta = ExportMetadata.model_validate(
        {
            "id": "exp-1",
            "job_id": "job-1",
            "version_number": 0,
            "format": "svg",
            "filename": "untangle-job-1.svg",
            "created_at": datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc),
            "media_type": "image/svg+xml",
            "byte_size": 2048,
        }
    )
    assert meta.format == "svg"

    key = AnswerKey.model_validate(
        {
            "drawing_id": "sample-a",
            "expected_tags": [{"tag": "FT-101", "signal": "FT"}],
            "expected_equipment": [{"tag": "P-101", "label": "Feed pump"}],
            "expected_connections": [
                {"from": "P-101", "to": "FT-101", "direction": "forward", "line_type": "process"}
            ],
            "expected_duty_standby_groups": [
                {
                    "id": "pumps",
                    "member_tags": ["P-101", "P-102"],
                    "shared_upstream": ["TK-101"],
                    "shared_downstream": ["FT-101"],
                }
            ],
        }
    )
    dumped = key.model_dump(by_alias=True)
    assert dumped["expected_connections"][0]["from"] == "P-101"
    assert dumped["expected_duty_standby_groups"][0]["member_tags"] == ["P-101", "P-102"]
