"""Shared settings that every part of UNTANGLE must agree on.

Confidence cutoffs stay here so a score always maps to the same level.
The API reads the database URL, upload folder, size limit, and frontend
origin from the environment when the process starts.
"""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
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
    # Ask the graph stays on stored facts unless this is turned on. It is off by default.
    ask_graph_llm_enabled: bool = False
    fewshot_symbols_enabled: bool = False
    # Stretch switches. Off means the extra control is not offered.
    dark_theme_enabled: bool = False
    flow_animation_enabled: bool = False
    batch_upload_enabled: bool = False
    # Upload and job limits. Defaults keep a local project usable.
    max_pdf_pages: int = Field(default=40, ge=1)
    job_timeout_seconds: int = Field(default=600, ge=1)
    inspect_timeout_seconds: int = Field(default=30, ge=1)
    zip_max_uncompressed_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    zip_max_entries: int = Field(default=2000, ge=1)
    upload_rate_limit: int = Field(default=30, ge=1)
    heavy_rate_limit: int = Field(default=120, ge=1)
    access_rate_limit: int = Field(default=8, ge=1)
    upload_rate_window_seconds: int = Field(default=60, ge=1)
    # Empty means local development has no gate. This value is never sent to the browser.
    demo_access_code: str = ""
    access_token_ttl_seconds: int = Field(default=12 * 60 * 60, ge=60)
    # When true, uploads and Modify are refused and one synthetic project is seeded.
    public_demo_mode: bool = False
    demo_seed_process: bool = True
    # Extra browser origins, comma-separated. FRONTEND_ORIGIN is always included.
    cors_origins: str = ""
    log_level: str = "INFO"
    # False in the vector-only image. The Windows app stays true and reports a missing program.
    ocr_in_build: bool = True
    # Accepted so a host can store them. This build does not call a model with them.
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""

    @model_validator(mode="after")
    def _required_settings(self) -> Self:
        if not self.database_url.strip():
            raise ValueError("DATABASE_URL is required")
        if not self.upload_dir.strip():
            raise ValueError("UPLOAD_DIR is required")
        if not self.cache_dir.strip():
            raise ValueError("CACHE_DIR is required")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR")
        origins = self.allowed_origins()
        if not origins:
            raise ValueError("At least one CORS origin is required")
        if any(item == "*" for item in origins):
            raise ValueError("CORS must list explicit origins and cannot be *")
        for item in origins:
            if not (item.startswith("http://") or item.startswith("https://")):
                raise ValueError("Each CORS origin must start with http:// or https://")
        return self

    def allowed_origins(self) -> list[str]:
        """Browser origins that may call the API. The list is never a wildcard.

        When the configured origin is 127.0.0.1 or localhost, the other form is
        also allowed so a browser opened on either host can reach the API.
        """
        found: list[str] = []
        for part in [self.frontend_origin, *self.cors_origins.split(",")]:
            item = part.strip().rstrip("/")
            if item and item not in found:
                found.append(item)
            companion = ""
            if "://127.0.0.1" in item:
                companion = item.replace("://127.0.0.1", "://localhost", 1)
            elif "://localhost" in item:
                companion = item.replace("://localhost", "://127.0.0.1", 1)
            if companion and companion not in found:
                found.append(companion)
        return found
