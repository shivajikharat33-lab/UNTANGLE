"""SQLite tables for a job and its versions.

Column names follow the Job and Version contracts in app.schemas.job.
`job_id` is the database link that the nested `Job.versions` list implies.
Version number 0 cannot be updated or deleted; database.py installs that guard.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobRow(Base):
    """One customer drawing job."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    pdf_sha256: Mapped[str] = mapped_column(String, nullable=False, default="")
    io_sha256: Mapped[str] = mapped_column(String, nullable=False, default="")
    pdf_original_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    io_original_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    intake_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    stages_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    versions: Mapped[list[VersionRow]] = relationship(back_populates="job")


class VersionRow(Base):
    """One saved state of a job. Number 0 is the original."""

    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("job_id", "number", name="uq_versions_job_number"),
        CheckConstraint("number >= 0", name="ck_versions_number_non_negative"),
        CheckConstraint(
            "status IN ('auto', 'accepted', 'edited')",
            name="ck_versions_status",
        ),
        CheckConstraint(
            "(number = 0 AND parent IS NULL AND status != 'edited') "
            "OR (number > 0 AND parent IS NOT NULL)",
            name="ck_versions_original",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(nullable=False)
    parent: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    connection_list_snapshot: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    change_log: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    accepted_at: Mapped[str | None] = mapped_column(String, nullable=True)

    job: Mapped[JobRow] = relationship(back_populates="versions")
