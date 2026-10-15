"""SQLite engine, table creation, and a real connectivity check."""

import logging

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("untangle.database")

_UPDATE_GUARD = """
CREATE TRIGGER IF NOT EXISTS versions_reject_update_of_original
BEFORE UPDATE ON versions
FOR EACH ROW
WHEN OLD.number = 0
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
        connection.execute(text(_UPDATE_GUARD))
        connection.execute(text(_DELETE_GUARD))


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
