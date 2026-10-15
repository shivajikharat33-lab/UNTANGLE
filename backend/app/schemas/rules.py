"""One recorded check and whether it passed."""

from pydantic import BaseModel, Field


class RuleResult(BaseModel):
    """The outcome of a single named check."""

    rule_id: str = Field(min_length=1)
    passed: bool
    message: str
