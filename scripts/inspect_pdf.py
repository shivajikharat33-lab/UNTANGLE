"""Print a vector / scanned / mixed verdict for one PDF.

Run from the repository root:

    python scripts/inspect_pdf.py data/samples/your-drawing.pdf

Customer drawings stay in data/samples/. Do not commit them.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pdf_verdict import inspect_pdf

SAMPLES = ROOT / "data" / "samples"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python scripts/inspect_pdf.py <path-to.pdf>")
        print(f"Put the real P&ID PDF in {SAMPLES}")
        print("That folder is gitignored. Do not commit the PDF or send it to a public cloud AI tool.")
        return 2

    path = Path(args[0])
    if not path.is_file():
        print(f"No PDF at {path}.")
        print(f"Put the file in {SAMPLES} and pass that path.")
        print("This script does not create a sample drawing.")
        return 1

    report = inspect_pdf(path)
    print(f"File: {path}")
    print(f"Pages: {report.page_count}")
    for index, (width, height) in enumerate(report.page_sizes, start=1):
        print(f"Page {index} size: {width} x {height}")
    print(f"Vector drawing operations: {report.vector_ops}")
    print(f"Text words with coordinates: {report.text_words}")
    print(f"Embedded images: {report.image_count}")
    if report.sample_text:
        print("Sample text: " + " ".join(report.sample_text))
    else:
        print("Sample text: (none)")
    print(f"Verdict: {report.verdict}")
    print(f"Reason: {report.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
