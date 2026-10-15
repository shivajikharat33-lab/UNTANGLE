"""Shared settings that every part of UNTANGLE must agree on.

Confidence cutoffs stay here so a score always maps to the same level.
The API reads the database URL, upload folder, size limit, and frontend
origin from the environment when the process starts.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

HIGH_CONFIDENCE_MIN = 0.85
MEDIUM_CONFIDENCE_MIN = 0.60

APP_VERSION = "0.1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "untangle.db"
DEFAULT_UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def level_for_score(score: float) -> str:
    """Return the confidence level for a score between 0 and 1."""
    if score >= HIGH_CONFIDENCE_MIN:
        return "high"
    if score >= MEDIUM_CONFIDENCE_MIN:
        return "medium"
    return "low"


def default_database_url() -> str:
    """SQLite file under the repository data folder, independent of the shell cwd."""
    return "sqlite:///" + DEFAULT_DATABASE_PATH.resolve().as_posix()


class Settings(BaseSettings):
    """Values read from the environment or from backend/.env when that file exists."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default_factory=default_database_url)
    upload_dir: str = str(DEFAULT_UPLOAD_DIR)
    max_upload_mb: int = Field(default=50, ge=1)
    frontend_origin: str = Field(default="http://127.0.0.1:5173", min_length=1)
    tag_fuzzy_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    process_min_stroke: float = Field(default=1.0, ge=0)
    signal_max_stroke: float = Field(default=0.75, ge=0)
    snap_tolerance: float = Field(default=4.0, ge=0)
    # How close a pipe end must be to a symbol or junction before it is attached.
    node_attach_tolerance: float = Field(default=8.0, ge=0)
    # Derived JSON and SVG copies. This is not a temp directory and it is not the upload folder.
    cache_dir: str = str(REPO_ROOT / "data" / "cache")
    # When false, the edit API rejects changes and the website hides Modify.
    modify_enabled: bool = True
