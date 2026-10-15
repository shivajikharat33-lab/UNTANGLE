"""Facts the settings page and the approach note can both use."""

from __future__ import annotations

from app.config import Settings
from app.graph_config import DISCLAIMER

LIBRARIES = [
    "FastAPI",
    "SQLite via SQLAlchemy",
    "PyMuPDF",
    "OpenCV",
    "Shapely",
    "openpyxl",
    "pandas",
    "ReportLab",
    "pytesseract",
    "elkjs",
]


def transparency_report(settings: Settings) -> dict[str, object]:
    """Describe this process. API keys are not included."""
    return {
        "libraries": list(LIBRARIES),
        "models": [],
        "external_apis": [],
        "llm_enabled": bool(settings.ask_graph_llm_enabled),
        "llm_configured": bool(settings.llm_api_key.strip()),
        "llm_called": False,
        "ocr_in_build": bool(settings.ocr_in_build),
        "modify_enabled": bool(settings.modify_enabled) and not bool(settings.public_demo_mode),
        "public_demo_mode": bool(settings.public_demo_mode),
        "disclaimer": DISCLAIMER,
        "note": (
            "Ask-the-graph does not call a model in this build. "
            "A key, if one is set in the environment, is not sent anywhere and is not shown here."
        ),
    }
