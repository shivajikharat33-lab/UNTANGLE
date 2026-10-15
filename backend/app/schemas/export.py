"""Metadata stored with a downloadable file. The file bytes are separate."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ExportFormat = Literal["svg", "pdf", "png", "json", "excel"]


class ExportMetadata(BaseModel):
    """Describes one export. It does not contain the file itself."""

    id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    version_number: int = Field(ge=0)
    format: ExportFormat
    filename: str = Field(min_length=1)
    created_at: datetime
    media_type: str = Field(min_length=1)
    byte_size: int | None = Field(default=None, ge=0)
    source_pdf_name: str = ""
    source_pdf_sha256: str = ""
    source_io_name: str = ""
    source_io_sha256: str = ""
    processing_version: str = ""
    draft: bool = False
    verification_state: str = ""
    failed_check: bool = False
    hidden_count: int = 0
    disclaimer: str = "Passed the defined automated checks. This is not an engineering or safety certification."
    certification_warning: str = "This file is not an engineering or safety certification."
