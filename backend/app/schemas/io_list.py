"""A checked IO list. Invalid rows stay in the list with their issues."""

from typing import Literal

from pydantic import BaseModel, Field


class IoIssue(BaseModel):
    """One problem on a kept row."""

    sheet: str
    row: int = Field(ge=1)
    original_value: str = ""
    severity: Literal["error", "warning"]
    message: str = Field(min_length=1)


class IoRow(BaseModel):
    """One spreadsheet row after checking. original_tag is the cell text."""

    row: int = Field(ge=1)
    original_tag: str = ""
    tag: str = ""
    signal: str = ""
    instrument_type: str = ""
    issues: list[IoIssue] = Field(default_factory=list)
    suffix_hint: str | None = None


class IoSummary(BaseModel):
    """Counts for the checked sheet. They include the flagged rows."""

    row_count: int = Field(ge=0)
    ok_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class IoListResult(BaseModel):
    """Saved result of checking one sheet."""

    status: Literal["validated", "needs_columns"]
    sheet: str | None = None
    sheets: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    tag_column: str | None = None
    signal_column: str | None = None
    message: str
    rows: list[IoRow] = Field(default_factory=list)
    summary: IoSummary


class IoValidateRequest(BaseModel):
    """Optional column choice. Empty means try the header names."""

    sheet: str | None = None
    tag_column: str | None = None
    signal_column: str | None = None
