"""Rows shown in the Tag Check Report and the Connection Report."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.confidence import Confidence
from app.schemas.graph import BBox, Direction, Evidence, LineType

TagMatchStatus = Literal["found", "fuzzy", "not_found", "extra"]


class TagReportRow(BaseModel):
    """One tag compared with the instrument IO list."""

    tag: str = Field(min_length=1)
    signal: str = ""
    status: TagMatchStatus
    confidence: Confidence
    location: BBox | None = None
    suggestion: str | None = None
    suffix_hint: str | None = None


class TagReportSummary(BaseModel):
    """Counts for one Tag Check Report. found + fuzzy + not_found equals total."""

    total: int = Field(ge=0)
    found: int = Field(ge=0)
    fuzzy: int = Field(ge=0)
    not_found: int = Field(ge=0)
    extra: int = Field(ge=0)


class TagReport(BaseModel):
    """Every IO tag once, plus extra tag-like text from the drawing."""

    rows: list[TagReportRow] = Field(default_factory=list)
    summary: TagReportSummary


class ConnectionReportRow(BaseModel):
    """One connection the trace claims, with the evidence and the rules.

    JSON uses "from" and "to". Python cannot use "from" as a field name,
    so the Python attribute is from_.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    direction: Direction
    line_type: LineType
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    source_location: BBox | None = None
