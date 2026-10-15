"""Database tables. Importing this package registers them on the SQLAlchemy base."""

from app.models.tables import JobRow, VersionRow

__all__ = ["JobRow", "VersionRow"]
