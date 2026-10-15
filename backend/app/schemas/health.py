"""Response body for GET /api/health."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """The process is up. `database` is a live check, not a stored flag."""

    status: Literal["ok"]
    version: str = Field(min_length=1)
    database: Literal["ok", "failed"]
    time: datetime
