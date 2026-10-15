"""Whether a version passed every defined check.

verified is allowed to be true only when rule_results is non-empty and every
entry has passed=true. A failing check, or no checks at all, cannot be labeled
verified.
"""

from pydantic import BaseModel, Field, model_validator

from app.schemas.rules import RuleResult


class VerificationResult(BaseModel):
    """Counts and rule outcomes for one version."""

    connections_added: int = Field(ge=0)
    connections_removed: int = Field(ge=0)
    tags_placed: int = Field(ge=0)
    tags_total: int = Field(ge=0)
    rule_results: list[RuleResult] = Field(default_factory=list)
    verified: bool = False
    tool_added: int = Field(default=0, ge=0)
    tool_removed: int = Field(default=0, ge=0)
    user_added: int = Field(default=0, ge=0)
    user_removed: int = Field(default=0, ge=0)
    user_reversed: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def verified_requires_every_check(self) -> "VerificationResult":
        if self.tags_placed > self.tags_total:
            raise ValueError("tags_placed cannot be greater than tags_total")
        if self.verified:
            all_passed = bool(self.rule_results) and all(
                item.passed for item in self.rule_results
            )
            if not all_passed:
                raise ValueError(
                    "verified may only be true if all defined checks pass"
                )
        return self
