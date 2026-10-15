"""Confidence score shared by nodes, edges, and report rows."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.config import level_for_score

ConfidenceLevel = Literal["high", "medium", "low"]


class Confidence(BaseModel):
    """A score, the level that score maps to, and why it was given.

    The level is not free text. It has to match the cutoffs in app.config.
    """

    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0)
    reason: str

    @model_validator(mode="after")
    def level_matches_configured_thresholds(self) -> "Confidence":
        expected = level_for_score(self.score)
        if self.level != expected:
            raise ValueError(
                f"level '{self.level}' does not match score {self.score}; "
                f"configured thresholds require '{expected}'"
            )
        return self
