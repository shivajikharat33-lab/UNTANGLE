"""Find empty and duplicate tags in an IO workbook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TAG_NAMES = {
    "tag",
    "tags",
    "instrument tag",
    "tag no",
    "tag no.",
    "tag number",
    "io tag",
}


@dataclass(frozen=True)
class SheetFacts:
    """One worksheet, plus the tag problems that are obvious from the columns."""

    name: str
    columns: list[str]
    preview_rows: list[dict[str, str]]
    tag_column: str | None
    empty_tag_rows: list[int]
    duplicate_tags: list[str]


def tag_column_name(columns: list[str]) -> str | None:
    """Return the header that holds instrument tags, if the name is obvious."""
    for column in columns:
        normalized = " ".join(column.strip().lower().replace("_", " ").split())
        if normalized in TAG_NAMES:
            return column
    return None


def inspect_workbook(path: Path) -> list[SheetFacts]:
    """Read every sheet. Cell values are strings so tag text is not changed."""
    workbook = pd.ExcelFile(path, engine="openpyxl")
    sheets: list[SheetFacts] = []
    for name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=name, dtype=str)
        columns = [str(column) for column in frame.columns]
        preview = frame.head(5).fillna("").astype(str).to_dict(orient="records")
        chosen = tag_column_name(columns)
        empty_rows: list[int] = []
        duplicates: list[str] = []
        if chosen is not None:
            series = frame[chosen].fillna("").astype(str).str.strip()
            empty_rows = [index + 2 for index, value in series.items() if value == ""]
            filled = series[series != ""]
            duplicates = sorted(filled[filled.duplicated()].unique().tolist())
        sheets.append(
            SheetFacts(
                name=name,
                columns=columns,
                preview_rows=preview,
                tag_column=chosen,
                empty_tag_rows=empty_rows,
                duplicate_tags=duplicates,
            )
        )
    return sheets
