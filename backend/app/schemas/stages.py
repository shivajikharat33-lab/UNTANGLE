"""The ten processing stages and the record kept for each one."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

StageName = Literal[
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
]
StageStatus = Literal["pending", "running", "done", "failed", "skipped"]

STAGE_ORDER: tuple[StageName, ...] = (
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


class StageRecord(BaseModel):
    """Status of one stage. Warnings are kept. Stages do not drop them."""

    name: StageName
    status: StageStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    @model_validator(mode="after")
    def end_is_not_before_start(self) -> "StageRecord":
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise ValueError("ended_at cannot be earlier than started_at")
        return self


class ProcessingRun(BaseModel):
    """The stage list for one pass over a drawing."""

    stages: list[StageRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def stage_names_are_unique(self) -> "ProcessingRun":
        names = [stage.name for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("each stage name can appear only once in a run")
        return self
