"""Line geometry on synthetic drawings."""

import time
from pathlib import Path

import fitz

from app.services.geometry import build_geometry
from app.services.pdf_extract import (
    CircleItem,
    ExtractionResult,
    ExtractionMeta,
    ExtractionSummary,
    PageCounts,
    PageExtraction,
    PolylineItem,
    extract_pdf,
)


def _page_from_pdf(path: Path) -> ExtractionResult:
    return extract_pdf(path)


def _pdf(draw) -> bytes:
    document = fitz.open()
    page = document.new_page(width=220, height=160)
    draw(page)
    payload = document.tobytes()
    document.close()
    return payload


def _write(tmp_path: Path, name: str, draw) -> ExtractionResult:
    path = tmp_path / name
    path.write_bytes(_pdf(draw))
    return extract_pdf(path)


def _decision(result, kind: str) -> list[str]:
    return [meeting.decision for meeting in result.meetings if meeting.decision == kind]


def test_tee_is_a_junction(tmp_path: Path) -> None:
    result = build_geometry(
        _write(tmp_path, "tee.pdf", lambda page: (
            page.draw_line((20, 40), (140, 40), width=1.5),
            page.draw_line((80, 40), (80, 120), width=1.5),
        ))
    )
    assert result.coverage.junctions >= 1
    assert any(meeting.decision == "junction" for meeting in result.meetings)


def test_plain_crossing_and_dotted_junction_and_hop(tmp_path: Path) -> None:
    plain = build_geometry(
        _write(tmp_path, "cross.pdf", lambda page: (
            page.draw_line((20, 20), (140, 100), width=1.5),
            page.draw_line((20, 100), (140, 20), width=1.5),
        ))
    )
    assert any(meeting.decision == "crossing" and "without a junction dot" in meeting.reason for meeting in plain.meetings)

    dotted = build_geometry(
        _write(tmp_path, "dot.pdf", lambda page: (
            page.draw_line((20, 20), (140, 100), width=1.5),
            page.draw_line((20, 100), (140, 20), width=1.5),
            page.draw_circle(fitz.Point(80, 60), 3, color=(0, 0, 0), fill=(0, 0, 0)),
        ))
    )
    assert any(meeting.decision == "junction" and "filled dot" in meeting.reason for meeting in dotted.meetings)

    hop = build_geometry(
        _write(tmp_path, "hop.pdf", lambda page: (
            page.draw_line((20, 40), (160, 40), width=1.5),
            page.draw_line((90, 10), (90, 90), width=1.5),
            page.draw_polyline([(78, 40), (90, 24), (102, 40)]),
        ))
    )
    assert any(meeting.decision == "crossing" and "hop" in meeting.reason for meeting in hop.meetings)


def test_three_lines_are_ambiguous(tmp_path: Path) -> None:
    result = build_geometry(
        _write(tmp_path, "amb.pdf", lambda page: (
            page.draw_line((20, 60), (160, 60), width=1.5),
            page.draw_line((90, 20), (90, 120), width=1.5),
            page.draw_line((30, 20), (150, 100), width=1.5),
        ))
    )
    ambiguous = [meeting for meeting in result.meetings if meeting.decision == "ambiguous"]
    assert ambiguous
    assert any("Needs Review" in meeting.reason for meeting in ambiguous)
    assert result.coverage.ambiguous == len(ambiguous)


def test_snap_signal_free_end_and_coverage(tmp_path: Path) -> None:
    result = build_geometry(
        _write(tmp_path, "snap.pdf", lambda page: (
            page.draw_line((10, 20), (40, 20), width=1.5),
            page.draw_line((43.5, 20), (80, 20), width=1.5),
            page.draw_line((10, 80), (70, 80), width=0.4, dashes="[2 2] 0"),
            page.draw_line((20, 120), (50, 120), width=1.5),
        )),
        snap_tolerance=4,
    )
    assert result.snaps
    assert result.snaps[0].original != result.snaps[0].snapped
    signal = [line for line in result.lines if line.line_type == "signal"]
    assert signal
    assert "dashed" in signal[0].reason
    assert result.coverage.free_endpoints >= 2
    assert abs(result.coverage.explained_length + result.coverage.unexplained_length - result.coverage.total_length) < 1e-6


def test_thousands_of_segments_stay_within_a_few_seconds() -> None:
    polylines = [
        PolylineItem(points=[[float(index), 0], [float(index) + 5, 0]], segment_count=1, stroke_width=1.2, dashes="[] 0")
        for index in range(0, 9000, 3)
    ]
    counts = PageCounts(
        words=0,
        lines=len(polylines),
        polylines=len(polylines),
        shapes=0,
        circles=0,
        primitives_read=len(polylines),
        primitives_used=len(polylines),
        unused_primitives=0,
    )
    extraction = ExtractionResult(
        status="ok",
        message="synthetic",
        meta=ExtractionMeta(
            pdf_sha256="0" * 64,
            page_count=1,
            duration_ms=0,
            pymupdf_version="test",
            coordinate_system="test",
        ),
        pages=[
            PageExtraction(
                page=1,
                width=10000,
                height=20,
                rotation=0,
                status="ok",
                message="synthetic",
                words=[],
                polylines=polylines,
                shapes=[],
                circles=[],
                unused=[],
                counts=counts,
            )
        ],
        summary=ExtractionSummary(
            words=0,
            lines=len(polylines),
            polylines=len(polylines),
            shapes=0,
            circles=0,
            primitives_read=len(polylines),
            primitives_used=len(polylines),
            unused_primitives=0,
        ),
    )
    started = time.perf_counter()
    result = build_geometry(extraction)
    elapsed = time.perf_counter() - started
    assert elapsed < 5
    assert abs(result.coverage.explained_length + result.coverage.unexplained_length - result.coverage.total_length) < 1e-3
    assert result.coverage.ambiguous == 0
