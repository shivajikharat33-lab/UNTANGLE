"""A job and its versions.

Version number 0 is the original. It has no parent. Later versions name the
version they were copied from. Replacing the contents of version 0 is not
allowed by this contract; a change is a new version.
"""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.graph import Direction, LineType
from app.schemas.verification import VerificationResult

VersionStatus = Literal["auto", "accepted", "edited"]


class ChangeLogEntry(BaseModel):
    """One recorded change. who, when, and what are required."""

    who: str = Field(min_length=1)
    when: datetime
    what: str = Field(min_length=1)
    note: str = ""


class ConnectionSnapshotEntry(BaseModel):
    """One line in a version's saved connection list.

    JSON uses "from" and "to". The Python attribute is from_.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    direction: Direction
    line_type: LineType


class Version(BaseModel):
    """One saved state of a job. Number 0 is never overwritten."""

    id: str = Field(min_length=1)
    number: int = Field(ge=0)
    parent: str | None = None
    status: VersionStatus
    connection_list_snapshot: list[ConnectionSnapshotEntry] = Field(default_factory=list)
    svg: str | None = None
    verification: VerificationResult | None = None
    change_log: list[ChangeLogEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def version_zero_is_the_original(self) -> "Version":
        if self.number == 0:
            if self.parent is not None:
                raise ValueError("version 0 is the original and has no parent")
            if self.status == "edited":
                raise ValueError(
                    "version 0 is the original and cannot be marked edited; "
                    "save the change as a new version"
                )
        elif self.parent is None:
            raise ValueError("a version after 0 must name its parent version id")
        return self


class Job(BaseModel):
    """One customer drawing job. versions is empty until version 0 is stored."""

    id: str = Field(min_length=1)
    versions: list[Version] = Field(default_factory=list)

    @model_validator(mode="after")
    def version_numbers_are_unique_and_zero_is_kept(self) -> "Job":
        numbers = [version.number for version in self.versions]
        if len(numbers) != len(set(numbers)):
            raise ValueError("version numbers must be unique inside a job")
        if self.versions and 0 not in numbers:
            raise ValueError(
                "version 0 must remain in the job; it is never overwritten or removed"
            )
        return self
