"""Report paging and export safety. A formula is not left executable."""

from app.services.export_files import excel_cell, render_png_and_pdf, workbook_bytes
from app.services.reports_view import page_of


def test_report_page_filters_and_excel_escapes_formulas() -> None:
    page = page_of(
        [{"tag": "PT-101", "status": "found"}, {"tag": "LT-50", "status": "not_found"}],
        query="LT",
        sort="tag",
        offset=0,
        limit=10,
    )
    assert page.total == 1
    assert page.items[0]["tag"] == "LT-50"
    assert excel_cell("=SUM(A1)") == "'=SUM(A1)"
    payload = workbook_bytes({"Tags": [["tag"], ["=bad"]]})
    assert payload[:2] == b"PK"


def test_svg_becomes_png_and_pdf() -> None:
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40"><text x="4" y="20">DRAFT, not final, not verified</text></svg>'
    png, pdf = render_png_and_pdf(svg)
    assert png.startswith(b"\x89PNG")
    assert pdf.startswith(b"%PDF")
    assert b"Verified" not in pdf or b"not verified" in pdf.lower() or b"not an engineering" in pdf.lower()
