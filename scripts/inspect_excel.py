"""Print sheets, columns, first rows, and obvious tag problems.

Run from the repository root:

    python scripts/inspect_excel.py data/samples/your-io-list.xlsx

Customer workbooks stay in data/samples/. Do not commit them.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.excel_checks import inspect_workbook

SAMPLES = ROOT / "data" / "samples"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python scripts/inspect_excel.py <path-to.xlsx>")
        print(f"Put the real IO list workbook in {SAMPLES}")
        print("That folder is gitignored. Do not commit the workbook or send it to a public cloud AI tool.")
        return 2

    path = Path(args[0])
    if not path.is_file():
        print(f"No workbook at {path}.")
        print(f"Put the Excel file in {SAMPLES} and pass that path.")
        print("This script does not create a sample workbook.")
        return 1

    print(f"File: {path}")
    for sheet in inspect_workbook(path):
        print(f"Sheet: {sheet.name}")
        print("Columns: " + ", ".join(sheet.columns))
        if not sheet.preview_rows:
            print("First rows: (the sheet has no data rows)")
        else:
            print("First rows:")
            for row in sheet.preview_rows:
                print(f"  {row}")
        if sheet.tag_column is None:
            print("Problem: no obvious tag column. Expected a header such as Tag or Instrument Tag.")
            continue
        print(f"Tag column: {sheet.tag_column}")
        if sheet.empty_tag_rows:
            listed = ", ".join(str(number) for number in sheet.empty_tag_rows)
            print(f"Problem: empty tags on sheet row(s) {listed}.")
        if sheet.duplicate_tags:
            print("Problem: duplicate tags: " + ", ".join(sheet.duplicate_tags))
        if not sheet.empty_tag_rows and not sheet.duplicate_tags:
            print("Tag check: no empty tags and no duplicate tags in this sheet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
