"""IO list checking."""

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.services.io_list import decode_prefix, normalize_tag
from tests.test_jobs import pdf_bytes, post_pair, settings_for
from app.main import create_app


def workbook_with(headers: list[str], data_rows: list[list[object]], sheet: str = "IO") -> bytes:
    book = Workbook()
    worksheet = book.active
    assert worksheet is not None
    worksheet.title = sheet
    worksheet.append(headers)
    for row in data_rows:
        worksheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def uploaded(tmp_path: Path, workbook: bytes) -> tuple[TestClient, str]:
    application = create_app(settings_for(tmp_path))
    client = TestClient(application)
    client.__enter__()
    response = post_pair(client, pdf=pdf_bytes(), workbook=workbook)
    assert response.status_code == 201
    return client, response.json()["id"]


def test_normalization_variants() -> None:
    assert normalize_tag("pt101a") == "PT-101A"
    assert normalize_tag("PT 101A") == "PT-101A"
    assert normalize_tag("PT-101A") == "PT-101A"
    assert normalize_tag("PT - 101 A") == "PT-101A"
    assert normalize_tag("not a tag") is None


def test_prefix_decoding_including_unknown() -> None:
    assert decode_prefix("PT-101")[1] == "pressure transmitter"
    assert decode_prefix("FV-12")[1] == "control valve"
    assert decode_prefix("T-10")[1] == "tank"
    assert decode_prefix("P-10")[1] == "pump"
    assert decode_prefix("XY-10") == ("XY", "unknown")


def test_ambiguous_headers_ask_for_columns_and_keep_invalid_rows(tmp_path: Path) -> None:
    workbook = workbook_with(
        ["Foo", "Bar"],
        [["pt101a", "Flow"], ["", "Level"], ["PT 101A", ""], ["nope", "Pressure"], ["XY-9", "Other"]],
    )
    client, job_id = uploaded(tmp_path, workbook)
    try:
        missing = client.get(f"/api/jobs/{job_id}/io-list")
        assert missing.status_code == 404
        assert missing.json()["error_code"] == "NOT_FOUND"
        assert missing.json()["request_id"]

        ambiguous = client.post(f"/api/jobs/{job_id}/io-list/validate", json={})
        assert ambiguous.status_code == 200
        body = ambiguous.json()
        assert body["status"] == "needs_columns"
        assert body["rows"] == []
        assert "guessed" in body["message"].lower() or "Pick" in body["message"]

        chosen = client.post(
            f"/api/jobs/{job_id}/io-list/validate",
            json={"sheet": "IO", "tag_column": "Foo", "signal_column": "Bar"},
        )
        assert chosen.status_code == 200
        checked = chosen.json()
        assert checked["status"] == "validated"
        assert checked["summary"]["row_count"] == 5
        tags = {row["original_tag"]: row for row in checked["rows"]}
        assert tags["pt101a"]["tag"] == "PT-101A"
        assert tags[""]["tag"] == ""
        assert any(issue["severity"] == "error" and "empty" in issue["message"].lower() for issue in tags[""]["issues"])
        assert any(issue["severity"] == "error" and "duplicated" in issue["message"].lower() for issue in tags["PT 101A"]["issues"])
        assert any(issue["severity"] == "error" and "duplicated" in issue["message"].lower() for issue in tags["pt101a"]["issues"])
        assert tags["nope"]["tag"] == ""
        assert any("pattern" in issue["message"].lower() for issue in tags["nope"]["issues"])
        assert tags["XY-9"]["instrument_type"] == "unknown"
        assert tags["XY-9"]["tag"] == "XY-9"
        saved = client.get(f"/api/jobs/{job_id}/io-list")
        assert saved.status_code == 200
        assert saved.json()["summary"]["row_count"] == 5
        unknown = client.get("/api/jobs/missing-project/io-list")
        assert unknown.status_code == 404
        assert unknown.json()["error_code"] == "NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_recognized_headers_do_not_need_a_picker(tmp_path: Path) -> None:
    workbook = workbook_with(["Tag", "Description"], [["FT-101", "Flow transmitter"]])
    client, job_id = uploaded(tmp_path, workbook)
    try:
        response = client.post(f"/api/jobs/{job_id}/io-list/validate", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "validated"
        assert body["tag_column"] == "Tag"
        assert body["rows"][0]["tag"] == "FT-101"
        assert body["rows"][0]["instrument_type"] == "flow transmitter"
        assert body["rows"][0]["issues"] == []
    finally:
        client.__exit__(None, None, None)
