"""Facts taken from the two source files before any drawing work starts."""

from typing import Literal

from pydantic import BaseModel, Field

PdfVerdict = Literal["VECTOR", "SCANNED", "MIXED"]


class StoredFile(BaseModel):
    """A source file saved under a generated name. The original name is metadata only."""

    stored_name: Literal["original.pdf", "io_list.xlsx"]
    original_name: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=1)


class SheetSummary(BaseModel):
    """One worksheet, without tag matching."""

    name: str
    columns: list[str]
    row_count: int = Field(ge=0)


class IntakeSummary(BaseModel):
    """What Intake could read. This is not a sketch and not a tag match."""

    pdf: StoredFile
    io_list: StoredFile
    page_count: int = Field(ge=1)
    verdict: PdfVerdict
    verdict_reason: str = Field(min_length=1)
    sheets: list[SheetSummary]
    warnings: list[str] = Field(default_factory=list)


class JobListItem(BaseModel):
    """One row on the dashboard."""

    id: str = Field(min_length=1)
    name: str
    created_at: str = Field(min_length=1)
    status: Literal["uploaded"]
    pdf_verdict: PdfVerdict
    page_count: int = Field(ge=1)


class PublicConfig(BaseModel):
    """Values the browser needs before an upload. This is not the health check."""

    max_upload_mb: int = Field(ge=1)
    modify_enabled: bool = True
