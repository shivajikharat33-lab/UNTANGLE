"""SQLite engine, table creation, and a real connectivity check."""

import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("untangle.database")


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the folder that holds the SQLite file so the first open can succeed."""
    if not database_url.startswith("sqlite"):
        return
    # sqlite:///relative.db  or  sqlite:////absolute/path.db
    raw = database_url.removeprefix("sqlite:///")
    if not raw or raw == ":memory:" or raw.startswith("file:"):
        return
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)


_DROP_UPDATE_GUARD = "DROP TRIGGER IF EXISTS versions_reject_update_of_original"
_UPDATE_GUARD = """
CREATE TRIGGER versions_reject_update_of_original
BEFORE UPDATE ON versions
FOR EACH ROW
WHEN OLD.number = 0 AND (
    NEW.id != OLD.id
    OR NEW.job_id != OLD.job_id
    OR NEW.number != OLD.number
    OR IFNULL(NEW.parent, '') != IFNULL(OLD.parent, '')
    OR NEW.connection_list_snapshot != OLD.connection_list_snapshot
    OR IFNULL(NEW.svg, '') != IFNULL(OLD.svg, '')
    OR IFNULL(CAST(NEW.verification AS TEXT), '') != IFNULL(CAST(OLD.verification AS TEXT), '')
    OR NEW.change_log != OLD.change_log
)
BEGIN
    SELECT RAISE(ABORT, 'version 0 is the original and is never overwritten');
END
"""

_DELETE_GUARD = """
CREATE TRIGGER IF NOT EXISTS versions_reject_delete_of_original
BEFORE DELETE ON versions
FOR EACH ROW
WHEN OLD.number = 0
BEGIN
    SELECT RAISE(ABORT, 'version 0 is the original and is never removed');
END
"""


class Base(DeclarativeBase):
    """Base class for the jobs and versions tables."""


def make_engine(database_url: str) -> Engine:
    """Open a SQLAlchemy engine. SQLite may be used from FastAPI's thread pool."""
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create jobs and versions, then install the version-0 guards.

    Version 0 is the original. SQLite triggers reject updates and deletes of
    that row even if a later caller bypasses the Python models.
    """
    from app import models  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        _add_job_columns(connection)
        connection.execute(text(_DROP_UPDATE_GUARD))
        connection.execute(text(_UPDATE_GUARD))
        connection.execute(text(_DELETE_GUARD))
        _add_version_columns(connection)


def _add_version_columns(connection) -> None:
    """Add history columns without rebuilding the versions table."""
    rows = connection.execute(text("PRAGMA table_info(versions)")).fetchall()
    if not rows:
        return
    present = {row[1] for row in rows}
    additions = (
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("created_by", "TEXT NOT NULL DEFAULT ''"),
        ("note", "TEXT NOT NULL DEFAULT ''"),
        ("accepted_at", "TEXT"),
    )
    for name, declaration in additions:
        if name not in present:
            connection.execute(text(f"ALTER TABLE versions ADD COLUMN {name} {declaration}"))


def _add_job_columns(connection) -> None:
    """Add upload columns to a database created before intake existed.

    create_all does not alter a table that is already there. New databases
    already have these columns, so each statement runs only when one is missing.
    """
    rows = connection.execute(text("PRAGMA table_info(jobs)")).fetchall()
    present = {row[1] for row in rows}
    additions = (
        ("name", "TEXT NOT NULL DEFAULT ''"),
        ("status", "TEXT NOT NULL DEFAULT 'uploaded'"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("pdf_sha256", "TEXT NOT NULL DEFAULT ''"),
        ("io_sha256", "TEXT NOT NULL DEFAULT ''"),
        ("pdf_original_name", "TEXT NOT NULL DEFAULT ''"),
        ("io_original_name", "TEXT NOT NULL DEFAULT ''"),
        ("intake_json", "TEXT"),
        ("stages_json", "TEXT"),
    )
    for column, column_type in additions:
        if column not in present:
            connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {column} {column_type}"))


def check_database(engine: Engine | None) -> str:
    """Return "ok" only when the database accepts SELECT 1."""
    if engine is None:
        return "failed"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("database check failed")
        return "failed"
