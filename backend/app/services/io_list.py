"""Check an IO workbook. Do not guess a column, and do not drop a row."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from openpyxl import load_workbook

from app.errors import AppError
from app.schemas.io_list import IoIssue, IoListResult, IoRow, IoSummary, IoValidateRequest
from app.services.storage import IO_NAME, NORMALIZED_IO_NAME, job_folder, read_json, write_json

logger = logging.getLogger("untangle.io_list")

_TAG_HEADERS = {
    "tag",
    "tag no",
    "tag number",
    "instrument tag",
    "instrument",
    "tag name",
    "tagname",
}
_SIGNAL_HEADERS = {"signal", "description", "service", "desc", "service description"}

# Longest prefix first so PT is not read as P, and FV is not read as V.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("PT", "pressure transmitter"),
    ("FT", "flow transmitter"),
    ("LT", "level transmitter"),
    ("TT", "temperature transmitter"),
    ("FV", "control valve"),
    ("LV", "control valve"),
    ("M", "pump motor"),
    ("T", "tank"),
    ("V", "vessel"),
    ("P", "pump"),
    ("E", "exchanger"),
)

_TAG_PATTERN = re.compile(r"^([A-Z]+)(?:[\s]*[-/][\s]*|[\s]+)?(\d+)[\s]*([A-Z]*)$")


def normalize_tag(raw: str) -> str | None:
    """Return LETTERS-DIGITS plus an optional suffix, or None when the text is not a tag."""
    text = re.sub(r"\s+", " ", (raw or "").strip()).upper()
    if not text:
        return None
    match = _TAG_PATTERN.match(text)
    if match is None:
        compact = re.sub(r"[\s\-/]+", "", text)
        match = re.match(r"^([A-Z]+)(\d+)([A-Z]*)$", compact)
    if match is None:
        return None
    prefix, digits, suffix = match.group(1), match.group(2), match.group(3)
    return f"{prefix}-{digits}{suffix}"


def suffix_hint_for(normalized: str) -> str | None:
    """A or B at the end of a tag is only a hint for later duty/standby checks."""
    suffix = normalized.split("-", 1)[1] if "-" in normalized else ""
    match = re.search(r"([A-Z]+)$", suffix)
    if match and match.group(1) in {"A", "B"}:
        return match.group(1)
    return None


def normalize_tag_confusion(raw: str) -> str | None:
    """Normalize a tag after mapping O/0, I/1, S/5, and B/8 in digit positions only."""
    text = re.sub(r"\s+", " ", (raw or "").strip()).upper()
    if not text:
        return None
    compact = re.sub(r"[\s\-/]+", "", text)
    match = re.match(r"^([A-Z]+)(.*)$", compact)
    if match is None or not match.group(2):
        return None
    prefix, rest = match.group(1), match.group(2)
    confusion = {"O": "0", "I": "1", "S": "5", "B": "8"}
    number: list[str] = []
    index = 0
    chars = list(rest)
    while index < len(chars):
        char = chars[index]
        if char.isdigit():
            number.append(char)
            index += 1
            continue
        remaining = chars[index:]
        if char in confusion and not (number and all(item.isalpha() for item in remaining)):
            number.append(confusion[char])
            index += 1
            continue
        break
    suffix = "".join(chars[index:])
    if not number or (suffix and not suffix.isalpha()):
        return None
    return f"{prefix}-{''.join(number)}{suffix}"


def decode_prefix(normalized: str) -> tuple[str, str]:
    """Return the prefix and its instrument type. Unknown prefixes stay unknown."""
    letters = normalized.split("-", 1)[0]
    for code, label in _PREFIXES:
        if letters == code:
            return code, label
    return letters, "unknown"


def _header_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(".")


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _matches(headers: list[str], names: set[str]) -> list[str]:
    found: list[str] = []
    for header in headers:
        if header and _header_key(header) in names:
            found.append(header)
    return found


def _sheet_rows(path: Path, sheet_name: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        logger.info("io workbook could not be opened (%s)", type(exc).__name__)
        raise AppError(400, "FILE_UNREADABLE", "The Excel file could not be opened. It may be damaged.") from None
    try:
        if sheet_name not in workbook.sheetnames:
            raise AppError(400, "SHEET_NOT_FOUND", "That sheet is not in the workbook.", {"sheet": sheet_name})
        worksheet = workbook[sheet_name]
        headers: list[str] = []
        data: list[tuple[int, list[str]]] = []
        for index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
            values = [_cell(cell) for cell in row]
            if index == 1:
                headers = values
                continue
            if any(values):
                data.append((index, values))
        return headers, data
    finally:
        workbook.close()


def _sheet_names(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def _column_index(headers: list[str], name: str) -> int | None:
    wanted = _header_key(name)
    for index, header in enumerate(headers):
        if _header_key(header) == wanted:
            return index
    return None


def _value_at(values: list[str], index: int | None) -> str:
    if index is None or index >= len(values):
        return ""
    return values[index]


def validate_workbook(path: Path, choice: IoValidateRequest | None = None) -> IoListResult:
    """Check one sheet. Ambiguous headers come back as needs_columns and no guessed rows."""
    choice = choice or IoValidateRequest()
    names = _sheet_names(path)
    if not names:
        raise AppError(400, "FILE_UNREADABLE", "The workbook has no sheets.")
    sheet_name = choice.sheet or names[0]
    headers, data = _sheet_rows(path, sheet_name)
    visible_headers = [header for header in headers if header]

    tag_column = choice.tag_column
    signal_column = choice.signal_column
    if tag_column or signal_column:
        if not tag_column or not signal_column:
            return IoListResult(
                status="needs_columns",
                sheet=sheet_name,
                sheets=names,
                columns=visible_headers,
                tag_column=tag_column,
                signal_column=signal_column,
                message="Choose both the tag column and the signal column.",
                summary=IoSummary(row_count=0, ok_count=0, error_count=0, warning_count=0),
            )
        if _header_key(tag_column) == _header_key(signal_column):
            raise AppError(400, "COLUMN_CONFLICT", "The tag column and the signal column must be different.")
        if _column_index(headers, tag_column) is None or _column_index(headers, signal_column) is None:
            raise AppError(
                400,
                "COLUMN_NOT_FOUND",
                "One of the chosen columns is not on that sheet.",
                {"columns": visible_headers},
            )
    else:
        tag_hits = _matches(headers, _TAG_HEADERS)
        signal_hits = _matches(headers, _SIGNAL_HEADERS)
        if len(tag_hits) != 1 or len(signal_hits) != 1:
            return IoListResult(
                status="needs_columns",
                sheet=sheet_name,
                sheets=names,
                columns=visible_headers,
                message=(
                    "The tag column and the signal column could not be chosen from the headers. "
                    "Pick them below. Nothing was guessed."
                ),
                summary=IoSummary(row_count=0, ok_count=0, error_count=0, warning_count=0),
            )
        tag_column = tag_hits[0]
        signal_column = signal_hits[0]

    tag_index = _column_index(headers, tag_column or "")
    signal_index = _column_index(headers, signal_column or "")
    rows: list[IoRow] = []
    seen: dict[str, list[int]] = {}
    for row_number, values in data:
        original = _value_at(values, tag_index)
        signal = _value_at(values, signal_index)
        issues: list[IoIssue] = []
        normalized = normalize_tag(original) if original else None
        instrument_type = ""
        suffix_hint = None
        if not original:
            issues.append(
                IoIssue(
                    sheet=sheet_name,
                    row=row_number,
                    original_value=original,
                    severity="error",
                    message="This row has an empty tag. The row is kept.",
                )
            )
        elif normalized is None:
            issues.append(
                IoIssue(
                    sheet=sheet_name,
                    row=row_number,
                    original_value=original,
                    severity="warning",
                    message="This text does not match a tag pattern. The original text is kept.",
                )
            )
        else:
            _prefix, instrument_type = decode_prefix(normalized)
            suffix_hint = suffix_hint_for(normalized)
            if instrument_type == "unknown":
                issues.append(
                    IoIssue(
                        sheet=sheet_name,
                        row=row_number,
                        original_value=original,
                        severity="warning",
                        message=f"The prefix {_prefix} is not in the instrument table, so the type is unknown.",
                    )
                )
            seen.setdefault(normalized, []).append(row_number)
        if not signal:
            issues.append(
                IoIssue(
                    sheet=sheet_name,
                    row=row_number,
                    original_value=signal,
                    severity="warning",
                    message="This row has no signal text. The row is kept.",
                )
            )
        rows.append(
            IoRow(
                row=row_number,
                original_tag=original,
                tag=normalized or "",
                signal=signal,
                instrument_type=instrument_type,
                issues=issues,
                suffix_hint=suffix_hint,
            )
        )

    duplicated = {tag for tag, numbers in seen.items() if len(numbers) > 1}
    if duplicated:
        for row in rows:
            if row.tag in duplicated:
                row.issues.append(
                    IoIssue(
                        sheet=sheet_name,
                        row=row.row,
                        original_value=row.original_tag,
                        severity="error",
                        message="This tag is duplicated after normalization. Both rows are kept.",
                    )
                )

    error_count = sum(1 for row in rows if any(issue.severity == "error" for issue in row.issues))
    warning_count = sum(
        1
        for row in rows
        if any(issue.severity == "warning" for issue in row.issues)
        and not any(issue.severity == "error" for issue in row.issues)
    )
    ok_count = sum(1 for row in rows if not row.issues)
    return IoListResult(
        status="validated",
        sheet=sheet_name,
        sheets=names,
        columns=visible_headers,
        tag_column=tag_column,
        signal_column=signal_column,
        message="The IO list was checked. Flagged rows were kept.",
        rows=rows,
        summary=IoSummary(
            row_count=len(rows),
            ok_count=ok_count,
            error_count=error_count,
            warning_count=warning_count,
        ),
    )


def validate_job(upload_dir: str, job_id: str, choice: IoValidateRequest | None = None) -> IoListResult:
    """Read the stored workbook and replace only the normalized JSON."""
    folder = job_folder(upload_dir, job_id)
    source = folder / IO_NAME
    if not source.is_file():
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    result = validate_workbook(source, choice)
    write_json(folder / NORMALIZED_IO_NAME, result.model_dump(mode="json"))
    logger.info("io list checked for job %s status=%s rows=%s", job_id, result.status, result.summary.row_count)
    return result


def load_saved_io_list(upload_dir: str, job_id: str) -> IoListResult:
    """Return the saved check, or 404 when it has not been run."""
    folder = job_folder(upload_dir, job_id)
    path = folder / NORMALIZED_IO_NAME
    if not path.is_file():
        raise AppError(
            404,
            "NOT_FOUND",
            "The IO list has not been checked for this project.",
            {"job_id": job_id},
        )
    return IoListResult.model_validate(read_json(path))
