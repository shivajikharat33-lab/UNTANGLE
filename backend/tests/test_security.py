"""Upload limits, the demo gate, and safe errors."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pydantic import ValidationError

from app.access_tokens import codes_match
from app.api.errors import scrub_details
from app.config import Settings
from app.main import create_app
from app.services.export_files import excel_cell
from tests.test_jobs import pdf_bytes, post_pair, settings_for, workbook_bytes


def test_codes_match_ignores_length_and_rejects_a_different_code() -> None:
    assert codes_match("same", "same") is True
    assert codes_match("short", "a-much-longer-code") is False


def test_wildcard_origin_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(frontend_origin="*")
    with pytest.raises(ValidationError):
        Settings(cors_origins="*")


def test_scrub_drops_paths_and_keeps_the_route() -> None:
    cleaned = scrub_details(
        {
            "path": "/api/jobs/abc",
            "note": r"C:\Users\Admin\secret.pdf",
            "trace": "Traceback (most recent call last):",
        }
    )
    assert cleaned is not None
    assert cleaned["path"] == "/api/jobs/abc"
    assert cleaned["note"] == "[redacted]"
    assert cleaned["trace"] == "[redacted]"


def test_excel_cell_prefixes_formula_starts() -> None:
    assert excel_cell("=cmd") == "'=cmd"
    assert excel_cell("+1") == "'+1"
    assert excel_cell("-1") == "'-1"
    assert excel_cell("@sum") == "'@sum"
    assert excel_cell("FT-101") == "FT-101"


def test_security_headers_and_cors(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path, cache_dir=str(tmp_path / "cache"), cors_origins="https://demo.example"))
    with TestClient(application) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
        extra = client.get("/health", headers={"Origin": "https://demo.example"})
        blocked = client.get("/api/health", headers={"Origin": "https://evil.example"})
        ready = client.get("/ready")
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert extra.headers["access-control-allow-origin"] == "https://demo.example"
    assert "access-control-allow-origin" not in blocked.headers
    assert allowed.headers["x-content-type-options"] == "nosniff"
    assert allowed.headers["referrer-policy"] == "no-referrer"
    assert allowed.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in allowed.headers["content-security-policy"]
    assert extra.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert "untangle" not in ready.text.lower() or ready.json()["status"] == "ready"


def test_access_gate_hides_the_code(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path, demo_access_code="correct-horse"))
    with TestClient(application) as client:
        health = client.get("/api/health")
        config = client.get("/api/config")
        blocked = client.get("/api/jobs")
        wrong = client.post("/api/access", json={"code": "nope"})
        opened = client.post("/api/access", json={"code": "correct-horse"})
    assert health.status_code == 200
    assert config.status_code == 200
    assert config.json()["access_required"] is True
    assert "correct-horse" not in config.text
    assert blocked.status_code == 401
    assert blocked.json()["error_code"] == "ACCESS_REQUIRED"
    assert wrong.status_code == 401
    assert wrong.json()["error_code"] == "ACCESS_DENIED"
    assert "nope" not in wrong.text
    token = opened.json()["token"]
    assert opened.status_code == 200
    assert "correct-horse" not in token
    with TestClient(application) as other:
        denied = other.get("/api/jobs")
        allowed = other.get("/api/jobs", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_rate_limit_is_per_process(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path, upload_rate_limit=1))
    with TestClient(application) as client:
        first = post_pair(client)
        second = post_pair(client)
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error_code"] == "RATE_LIMITED"
    assert "Traceback" not in second.text


def test_public_demo_seeds_a_synthetic_project_and_blocks_uploads(tmp_path: Path) -> None:
    application = create_app(
        settings_for(tmp_path, cache_dir=str(tmp_path / "cache"), public_demo_mode=True, demo_seed_process=False)
    )
    with TestClient(application) as client:
        listed = client.get("/api/jobs")
        blocked = post_pair(client)
        config = client.get("/api/config")
        job_id = listed.json()[0]["id"]
        modify = client.post(f"/api/jobs/{job_id}/draft")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["name"] == "Synthetic demo plant"
    assert blocked.status_code == 403
    assert blocked.json()["error_code"] == "UPLOADS_DISABLED"
    assert config.json()["public_demo_mode"] is True
    assert config.json()["modify_enabled"] is False
    assert modify.status_code == 403
    assert modify.json()["error_code"] == "MODIFY_DISABLED"


def _zip_with(member: str, content: bytes = b"hello") -> bytes:
    base = workbook_bytes()
    incoming = zipfile.ZipFile(io.BytesIO(base))
    outgoing = io.BytesIO()
    with zipfile.ZipFile(outgoing, "w") as archive:
        for item in incoming.infolist():
            archive.writestr(item, incoming.read(item.filename))
        archive.writestr(member, content)
    incoming.close()
    return outgoing.getvalue()


def _plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a workbook")
    return buffer.getvalue()


def test_archive_limits_macros_and_disguised_files(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path, max_pdf_pages=1))
    with TestClient(application) as client:
        disguised = post_pair(client, workbook=_plain_zip())
        macros = post_pair(client, workbook=_zip_with("xl/vbaProject.bin", b"macro"))
        links = post_pair(client, workbook=_zip_with("xl/externalLinks/externalLink1.xml", b"<link/>"))
        slip = post_pair(client, workbook=_zip_with("../evil.txt", b"x"))
        xlsm = post_pair(client, workbook_name="io.xlsm")
        pages = post_pair(client, pdf=_two_pages())
        bomb = None
    assert disguised.json()["error_code"] == "WRONG_FILE_TYPE"
    assert macros.json()["error_code"] == "MACROS_REFUSED"
    assert links.json()["error_code"] == "EXTERNAL_LINK_REFUSED"
    assert slip.json()["error_code"] == "UNSAFE_ARCHIVE"
    assert xlsm.json()["error_code"] == "WRONG_FILE_TYPE"
    assert pages.json()["error_code"] == "TOO_MANY_PAGES"
    assert "Traceback" not in pages.text
    crowded_app = create_app(settings_for(tmp_path / "entries", zip_max_entries=1))
    with TestClient(crowded_app) as client:
        crowded = post_pair(client)
    assert crowded.json()["error_code"] == "UNSAFE_ARCHIVE"
    small_app = create_app(settings_for(tmp_path / "small", zip_max_uncompressed_bytes=30))
    with TestClient(small_app) as client:
        bomb = post_pair(client)
    assert bomb is not None
    assert bomb.json()["error_code"] == "UNSAFE_ARCHIVE"


def _two_pages() -> bytes:
    document = fitz.open()
    document.new_page()
    document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


def test_password_and_empty_pdf_are_refused(tmp_path: Path) -> None:
    application = create_app(settings_for(tmp_path))
    document = fitz.open()
    document.new_page()
    locked = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    document.close()
    empty = fitz.open()
    try:
        blank = empty.tobytes()
    except Exception:
        blank = b"%PDF-1.4\n%%EOF"
    empty.close()
    with TestClient(application) as client:
        password = post_pair(client, pdf=locked)
        no_pages = post_pair(client, pdf=blank)
    assert password.status_code == 400
    assert password.json()["error_code"] == "PASSWORD_PROTECTED"
    assert no_pages.status_code == 400
    assert no_pages.json()["error_code"] in {"FILE_UNREADABLE", "WRONG_FILE_TYPE"}
    assert "secret" not in password.text
