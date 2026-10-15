"""Shared data contracts.

These models are the shape of UNTANGLE data. The matching TypeScript types
live in frontend/src/types. docs/CONTRACTS.md explains every field.
"""

from app.schemas.answer_key import (
    AnswerKey,
    ExpectedConnection,
    ExpectedDutyStandbyGroup,
    ExpectedEquipment,
    ExpectedTag,
)
from app.schemas.confidence import Confidence, ConfidenceLevel
from app.schemas.errors import ErrorResponse
from app.schemas.export import ExportFormat, ExportMetadata
from app.schemas.health import HealthResponse
from app.schemas.graph import (
    BBox,
    CrossingMode,
    DiagramGraph,
    Direction,
    Edge,
    EdgeStatus,
    Evidence,
    Group,
    GroupType,
    LineType,
    Node,
    NodeType,
    Point,
)
from app.schemas.job import ChangeLogEntry, Job, Version, VersionStatus
from app.schemas.reports import ConnectionReportRow, TagMatchStatus, TagReportRow
from app.schemas.rules import RuleResult
from app.schemas.stages import STAGE_ORDER, ProcessingRun, StageName, StageRecord, StageStatus
from app.schemas.verification import VerificationResult

__all__ = [
    "AnswerKey",
    "BBox",
    "ChangeLogEntry",
    "Confidence",
    "ConfidenceLevel",
    "ConnectionReportRow",
    "CrossingMode",
    "DiagramGraph",
    "Direction",
    "Edge",
    "EdgeStatus",
    "ErrorResponse",
    "Evidence",
    "ExpectedConnection",
    "ExpectedDutyStandbyGroup",
    "ExpectedEquipment",
    "ExpectedTag",
    "ExportFormat",
    "ExportMetadata",
    "Group",
    "GroupType",
    "HealthResponse",
    "Job",
    "LineType",
    "Node",
    "NodeType",
    "Point",
    "ProcessingRun",
    "RuleResult",
    "STAGE_ORDER",
    "StageName",
    "StageRecord",
    "StageStatus",
    "TagMatchStatus",
    "TagReportRow",
    "VerificationResult",
    "Version",
    "VersionStatus",
]
