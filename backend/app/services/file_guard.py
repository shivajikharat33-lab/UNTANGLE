"""Checks for uploaded PDFs and xlsx workbooks.

The original file name is never used as a path. Zip members are not extracted
until their declared sizes and names have been accepted.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import fitz

from app.errors import AppError
from app.services.excel_intake import SheetFacts, inspect_workbook
from app.services.pdf_inspect import inspect_pdf


def _reject(status: int, code: str, message: str) -> None:
    raise AppError(status, code, message)


def examine_pdf(path: Path, max_pages: int) -> dict[str, object]:
    """Open a PDF far enough to classify it. A password or a huge page count stops first."""
    document = fitz.open(path)
    try:
        if document.needs_pass:
            _reject(
                400,
                "PASSWORD_PROTECTED",
                "This PDF is password-protected. Remove the password and upload it again. Nothing was stored.",
            )
        if document.page_count < 1:
            _reject(400, "FILE_UNREADABLE", "The PDF opened, but it has no pages to read.")
        if document.page_count > max_pages:
            _reject(
                400,
                "TOO_MANY_PAGES",
                f"This PDF has {document.page_count} pages. The limit is {max_pages}. Nothing was stored.",
            )
    finally:
        document.close()
    report = inspect_pdf(path)
    if report.page_count < 1 or report.verdict not in {"VECTOR", "SCANNED", "MIXED"}:
        _reject(400, "FILE_UNREADABLE", "The PDF opened, but it has no pages to read.")
    return {"page_count": report.page_count, "verdict": report.verdict, "reason": report.reason}


def _unsafe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or normalized == "..":
        return True
    return "/../" in f"/{normalized}"


def examine_xlsx(path: Path, max_uncompressed_bytes: int, max_entries: int) -> list[SheetFacts]:
    """Accept a real xlsx workbook. Macros, external links, and oversized archives are refused."""
    data = path.read_bytes()
    if not data.startswith(b"PK"):
        _reject(400, "WRONG_FILE_TYPE", "That file is named like an Excel workbook, but its contents are not one.")
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        _reject(400, "FILE_UNREADABLE", "The Excel file could not be opened. It may be damaged.")
    try:
        infos = archive.infolist()
        if len(infos) > max_entries:
            _reject(400, "UNSAFE_ARCHIVE", "That workbook contains too many internal files. Nothing was stored.")
        total = 0
        names: list[str] = []
        for info in infos:
            if _unsafe_member(info.filename):
                _reject(400, "UNSAFE_ARCHIVE", "That workbook contains an unsafe internal path. Nothing was stored.")
            total += max(0, info.file_size)
            if total > max_uncompressed_bytes:
                _reject(400, "UNSAFE_ARCHIVE", "That workbook is too large when unpacked. Nothing was stored.")
            names.append(info.filename.replace("\\", "/"))
        lowered = [name.lower() for name in names]
        if "[content_types].xml" not in lowered or "xl/workbook.xml" not in lowered:
            _reject(400, "WRONG_FILE_TYPE", "That file is named like an Excel workbook, but its contents are not one.")
        if any("vbaproject" in name for name in lowered):
            _reject(400, "MACROS_REFUSED", "Macro workbooks are not accepted. Save the file as .xlsx without macros.")
        if any(name.startswith("xl/externallinks/") for name in lowered):
            _reject(400, "EXTERNAL_LINK_REFUSED", "Workbooks with external links are not accepted. Paste values and upload again.")
        content_name = next(name for name in names if name.lower() == "[content_types].xml")
        content = archive.read(content_name)
        if b"macroEnabled" in content or b"vbaProject" in content:
            _reject(400, "MACROS_REFUSED", "Macro workbooks are not accepted. Save the file as .xlsx without macros.")
        if b"externalLink" in content:
            _reject(400, "EXTERNAL_LINK_REFUSED", "Workbooks with external links are not accepted. Paste values and upload again.")
    finally:
        archive.close()
    return inspect_workbook(path)
