"""The inspection script and the API share one PDF verdict.

The decision lives in backend/app/services/pdf_inspect.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.pdf_inspect import PdfReport, classify_counts, inspect_pdf

__all__ = ["PdfReport", "classify_counts", "inspect_pdf"]
