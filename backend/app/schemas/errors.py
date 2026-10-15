"""The only error body the API returns."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """A failed request. request_id ties the message to one server log entry."""

    error_code: str = Field(min_length=1)
    message: str
    details: dict[str, Any] | None = None
    request_id: str = Field(min_length=1)
