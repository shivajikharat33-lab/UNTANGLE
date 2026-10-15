"""Child process that inspects one uploaded file.

Stdout is a single JSON object. File bytes are not printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.errors import AppError
from app.services.file_guard import examine_pdf, examine_xlsx


def main(argv: list[str] | None = None) -> int:
    """Inspect the path given on the command line and print JSON."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 5:
        sys.stdout.write(json.dumps({"ok": False, "error_code": "FILE_UNREADABLE", "message": "The file could not be inspected."}))
        return 0
    kind, raw_path, max_pages, max_bytes, max_entries = args
    path = Path(raw_path)
    try:
        if kind == "pdf":
            facts = examine_pdf(path, int(max_pages))
            payload: dict[str, object] = {"ok": True, "pdf": facts}
        elif kind == "xlsx":
            sheets = examine_xlsx(path, int(max_bytes), int(max_entries))
            payload = {
                "ok": True,
                "sheets": [
                    {"name": sheet.name, "columns": sheet.columns, "row_count": sheet.row_count}
                    for sheet in sheets
                ],
            }
        else:
            payload = {"ok": False, "error_code": "FILE_UNREADABLE", "message": "The file could not be inspected."}
    except AppError as exc:
        payload = {"ok": False, "error_code": exc.error_code, "message": exc.message}
    except Exception:
        payload = {
            "ok": False,
            "error_code": "FILE_UNREADABLE",
            "message": "The file could not be opened. It may be damaged.",
        }
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
