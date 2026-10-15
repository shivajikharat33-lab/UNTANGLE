"""Run the stages that exist. A second run for the same job is refused."""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.errors import AppError
from app.models import JobRow
from app.schemas.io_list import IoListResult
from app.schemas.job import Job
from app.schemas.stages import StageRecord
from app.services import checks as check_service, coverage as coverage_service, detect, geometry as line_geometry, graph_build, layout as layout_service, patterns as pattern_service, pdf_extract, render as render_service, simplify as simplify_service, tag_match
from app.services.pdf_extract import ExtractionResult
from app.schemas.reports import TagReport
from app.services.storage import DETECTIONS_NAME, EXTRACTION_NAME, GEOMETRY_NAME, GRAPH_NAME, NORMALIZED_IO_NAME, PDF_NAME, SIMPLIFIED_NAME, TAG_REPORT_NAME, job_folder, read_json, write_json
from app.services.cache_store import cache_is_complete, cache_key, config_payload, restore_derived, store_file
from app.services.tag_match import PrerequisiteError
from app.services.uploads import job_from_row

logger = logging.getLogger("untangle.pipeline")

_GUARD = threading.Lock()
_JOB_LOCKS: dict[str, threading.Lock] = {}


def job_lock(job_id: str) -> threading.Lock:
    with _GUARD:
        lock = _JOB_LOCKS.get(job_id)
        if lock is None:
            lock = threading.Lock()
            _JOB_LOCKS[job_id] = lock
        return lock


def _replace_stage(row: JobRow, name: str, **changes: object) -> None:
    stages = [StageRecord.model_validate(item) for item in (row.stages_json or [])]
    replaced = False
    updated: list[StageRecord] = []
    for stage in stages:
        if stage.name == name:
            updated.append(stage.model_copy(update=changes))
            replaced = True
        else:
            updated.append(stage)
    if not replaced:
        raise AppError(500, "INTERNAL_ERROR", "The stage list is missing a required stage.")
    row.stages_json = [stage.model_dump(mode="json") for stage in updated]
    flag_modified(row, "stages_json")


def _stage(row: JobRow, name: str) -> StageRecord:
    for item in row.stages_json or []:
        stage = StageRecord.model_validate(item)
        if stage.name == name:
            return stage
    raise AppError(500, "INTERNAL_ERROR", "The stage list is missing a required stage.")


_RESUME_ORDER = ("Read", "MatchTags", "Detect", "Trace", "Patterns", "SelfCheck", "Report", "Simplify", "Layout")


def _failed_stage_name(row: JobRow) -> str | None:
    stages = {item.get("name"): item for item in (row.stages_json or [])}
    for name in _RESUME_ORDER:
        if stages.get(name, {}).get("status") == "failed":
            return name
    return None


def begin_process(engine: object, upload_dir: str, job_id: str, *, retry: bool = False, force: bool = False) -> Job:
    """Mark the next stage running and return that snapshot. The original files stay put."""
    lock = job_lock(job_id)
    if not lock.acquire(blocking=False):
        raise AppError(
            409,
            "JOB_ALREADY_RUNNING",
            "This project is already being processed.",
            {"job_id": job_id},
        )
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
        if row is None:
            raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
        folder = job_folder(upload_dir, job_id)
        if not (folder / PDF_NAME).is_file():
            raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
        now = datetime.now(timezone.utc)
        failed = _failed_stage_name(row) if retry and not force else None
        start_name = failed or "Read"
        _replace_stage(
            row,
            start_name,
            status="running",
            started_at=now,
            ended_at=None,
            duration_ms=None,
            warnings=[],
            error=None,
        )
        if start_name != "Read":
            session.commit()
            session.refresh(row)
            return job_from_row(row)
        for stage_name in ("MatchTags", "Detect", "Trace", "Patterns", "SelfCheck", "Simplify", "Layout", "Report"):
            _replace_stage(
                row,
                stage_name,
                status="pending",
                started_at=None,
                ended_at=None,
                duration_ms=None,
                warnings=[],
                error=None,
            )
        session.commit()
        session.refresh(row)
        return job_from_row(row)
    except Exception:
        session.rollback()
        lock.release()
        raise
    finally:
        session.close()


def finish_process(
    engine: object,
    upload_dir: str,
    job_id: str,
    fuzzy_threshold: float = 0.80,
    process_min_stroke: float = 1.0,
    signal_max_stroke: float = 0.75,
    snap_tolerance: float = 4.0,
    node_attach_tolerance: float = 8.0,
    force: bool = False,
    retry: bool = False,
    cache_dir: str = "",
    resume_from: str = "Read",
) -> None:
    """Read the PDF, then match tags. A failed stage leaves earlier files in place."""
    lock = job_lock(job_id)
    key = ""
    folder = None
    try:
        folder = job_folder(upload_dir, job_id)
        if cache_dir and (folder / PDF_NAME).is_file():
            pdf_sha = hashlib.sha256((folder / PDF_NAME).read_bytes()).hexdigest()
            io_sha = hashlib.sha256((folder / "io_list.xlsx").read_bytes()).hexdigest() if (folder / "io_list.xlsx").is_file() else ""
            key = cache_key(pdf_sha, io_sha, config_payload())
            if not force and not retry and cache_is_complete(cache_dir, key):
                restore_derived(cache_dir, key, folder)
                for name in _RESUME_ORDER:
                    _finish_stage(engine, job_id, name, status="done", warnings=["Loaded from the local cache."], error=None)
                return
        if resume_from != "Read":
            _resume(engine, upload_dir, job_id, resume_from, fuzzy_threshold, process_min_stroke, signal_max_stroke, snap_tolerance, node_attach_tolerance)
            return
        try:
            result = pdf_extract.extract_pdf(folder / PDF_NAME)
            write_json(folder / EXTRACTION_NAME, result.model_dump(mode="json"))
            warnings = [] if result.status == "ok" else [result.message]
            _finish_stage(engine, job_id, "Read", status="done", warnings=warnings, error=None)
        except Exception as exc:
            logger.info("read failed for job %s (%s)", job_id, type(exc).__name__)
            _finish_stage(
                engine,
                job_id,
                "Read",
                status="failed",
                warnings=[],
                error="The drawing could not be read. The original files were not changed.",
            )
            return
        _run_match(
            engine,
            upload_dir,
            job_id,
            fuzzy_threshold,
            process_min_stroke,
            signal_max_stroke,
            snap_tolerance,
            node_attach_tolerance,
        )
    finally:
        if cache_dir and key and folder is not None:
            for name in ("extraction.json", "tag_report.json", "detections.json", "geometry.json", "graph.json", "simplified.json", "layout.json", "sketch.svg", "sketch_meta.json", "sketch_draft.svg"):
                store_file(cache_dir, key, name, folder / name)
        lock.release()


def _resume(
    engine: object,
    upload_dir: str,
    job_id: str,
    resume_from: str,
    fuzzy_threshold: float,
    process_min_stroke: float,
    signal_max_stroke: float,
    snap_tolerance: float,
    node_attach_tolerance: float,
) -> None:
    """Continue at a failed stage. Earlier output files stay in place."""
    if resume_from == "MatchTags":
        _run_match(engine, upload_dir, job_id, fuzzy_threshold, process_min_stroke, signal_max_stroke, snap_tolerance, node_attach_tolerance)
    elif resume_from == "Detect":
        _run_detect(engine, upload_dir, job_id, process_min_stroke, signal_max_stroke, snap_tolerance, node_attach_tolerance)
    elif resume_from == "Trace":
        _run_trace(engine, upload_dir, job_id, snap_tolerance, node_attach_tolerance)
    elif resume_from == "Patterns":
        _run_patterns(engine, upload_dir, job_id)
    elif resume_from == "SelfCheck":
        _run_checks(engine, upload_dir, job_id)
    elif resume_from == "Report":
        _run_coverage(engine, upload_dir, job_id)
    elif resume_from == "Simplify":
        _run_simplify(engine, upload_dir, job_id)
    elif resume_from == "Layout":
        _run_layout(engine, upload_dir, job_id)


def _write_draft(upload_dir: str, job_id: str) -> list[str]:
    """Draw an early sketch. It is never labeled verified."""
    try:
        from datetime import datetime, timezone

        from app.schemas.graph import SimplifiedEdge, SimplifiedGraph, SimplifiedNode

        graph = graph_build.load_graph(upload_dir, job_id)
        simplified = SimplifiedGraph(
            nodes=[SimplifiedNode(**node.model_dump(), original_ids=[node.id]) for node in graph.nodes],
            edges=[SimplifiedEdge(**edge.model_dump(), original_ids=[edge.id]) for edge in graph.edges],
            connectivity_ok=False,
            failed_check=False,
        )
        laid = layout_service.layout_graph(simplified)
        svg, _meta = render_service.render_sketch(
            simplified,
            laid,
            None,
            draft=True,
            drafted_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        (job_folder(upload_dir, job_id) / "sketch_draft.svg").write_text(svg, encoding="utf-8")
        return []
    except Exception as exc:
        logger.info("draft failed for job %s (%s)", job_id, type(exc).__name__)
        return ["The draft sketch could not be drawn. The graph was kept."]


def _run_match(
    engine: object,
    upload_dir: str,
    job_id: str,
    fuzzy_threshold: float,
    process_min_stroke: float,
    signal_max_stroke: float,
    snap_tolerance: float,
    node_attach_tolerance: float,
) -> None:
    _mark_running(engine, job_id, "MatchTags")
    try:
        folder = job_folder(upload_dir, job_id)
        extraction_path = folder / EXTRACTION_NAME
        io_path = folder / NORMALIZED_IO_NAME
        if not extraction_path.is_file():
            raise PrerequisiteError("Prerequisite missing: MatchTags needs a finished Read.")
        if not io_path.is_file():
            raise PrerequisiteError("Prerequisite missing: MatchTags needs a checked IO list.")
        extraction = ExtractionResult.model_validate(read_json(extraction_path))
        io_list = IoListResult.model_validate(read_json(io_path))
        report = tag_match.build_report(extraction, io_list, fuzzy_threshold)
        tag_match.write_tag_report(upload_dir, job_id, report)
        _finish_stage(engine, job_id, "MatchTags", status="done", warnings=[], error=None)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "MatchTags", status="failed", warnings=[], error=exc.message)
        _finish_stage(
            engine,
            job_id,
            "Detect",
            status="failed",
            warnings=[],
            error="Prerequisite missing: Detect needs a finished Read and a finished tag check.",
        )
        return
    except Exception as exc:
        logger.info("tag match failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "MatchTags",
            status="failed",
            warnings=[],
            error="Tag matching could not be finished. Earlier results were kept.",
        )
        _finish_stage(
            engine,
            job_id,
            "Detect",
            status="failed",
            warnings=[],
            error="Prerequisite missing: Detect needs a finished Read and a finished tag check.",
        )
        return
    _run_detect(engine, upload_dir, job_id, process_min_stroke, signal_max_stroke, snap_tolerance, node_attach_tolerance)


def _run_detect(
    engine: object,
    upload_dir: str,
    job_id: str,
    process_min_stroke: float,
    signal_max_stroke: float,
    snap_tolerance: float,
    node_attach_tolerance: float,
) -> None:
    _mark_running(engine, job_id, "Detect")
    try:
        folder = job_folder(upload_dir, job_id)
        extraction_path = folder / EXTRACTION_NAME
        report_path = folder / TAG_REPORT_NAME
        if not extraction_path.is_file() or not report_path.is_file():
            raise PrerequisiteError("Prerequisite missing: Detect needs a finished Read and a finished tag check.")
        extraction = ExtractionResult.model_validate(read_json(extraction_path))
        report = TagReport.model_validate(read_json(report_path))
        result = detect.build_detections(extraction, report)
        detect.write_detections(upload_dir, job_id, result)
        _finish_stage(engine, job_id, "Detect", status="done", warnings=[], error=None)
        _run_geometry(engine, upload_dir, job_id, process_min_stroke, signal_max_stroke, snap_tolerance, node_attach_tolerance)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Detect", status="failed", warnings=[], error=exc.message)
    except Exception as exc:
        logger.info("detect failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Detect",
            status="failed",
            warnings=[],
            error="Symbol detection could not be finished. Earlier results were kept.",
        )


def _run_geometry(
    engine: object,
    upload_dir: str,
    job_id: str,
    process_min_stroke: float,
    signal_max_stroke: float,
    snap_tolerance: float,
    node_attach_tolerance: float,
) -> None:
    try:
        folder = job_folder(upload_dir, job_id)
        extraction = ExtractionResult.model_validate(read_json(folder / EXTRACTION_NAME))
        detections = detect.DetectionResult.model_validate(read_json(folder / DETECTIONS_NAME))
        result = line_geometry.build_geometry(
            extraction,
            detections,
            process_min_stroke=process_min_stroke,
            signal_max_stroke=signal_max_stroke,
            snap_tolerance=snap_tolerance,
        )
        line_geometry.write_geometry(upload_dir, job_id, result)
    except Exception as exc:
        logger.info("geometry failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Detect",
            status="done",
            warnings=["Line geometry could not be saved. The detections were kept."],
            error=None,
        )
        _finish_stage(
            engine,
            job_id,
            "Trace",
            status="failed",
            warnings=[],
            error="Prerequisite missing: Building the graph needs saved line geometry.",
        )
        _finish_stage(
            engine,
            job_id,
            "Patterns",
            status="failed",
            warnings=[],
            error="Prerequisite missing: Detecting patterns needs a graph.",
        )
        return
    _run_trace(engine, upload_dir, job_id, snap_tolerance, node_attach_tolerance)


def _run_trace(
    engine: object,
    upload_dir: str,
    job_id: str,
    snap_tolerance: float,
    node_attach_tolerance: float,
) -> None:
    """Trace is the Building graph stage. The stored stage name stays Trace."""
    _mark_running(engine, job_id, "Trace")
    folder = job_folder(upload_dir, job_id)
    graph_path = folder / GRAPH_NAME
    if graph_path.is_file():
        graph_path.unlink()
    try:
        if not (folder / GEOMETRY_NAME).is_file() or not (folder / DETECTIONS_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Building the graph needs detections and line geometry.")
        extraction = ExtractionResult.model_validate(read_json(folder / EXTRACTION_NAME))
        detections = detect.DetectionResult.model_validate(read_json(folder / DETECTIONS_NAME))
        report = TagReport.model_validate(read_json(folder / TAG_REPORT_NAME))
        geometry = line_geometry.GeometryResult.model_validate(read_json(folder / GEOMETRY_NAME))
        graph = graph_build.build_graph(
            detections,
            geometry,
            report,
            source_sha256=extraction.meta.pdf_sha256,
            snap_tolerance=snap_tolerance,
            node_tolerance=node_attach_tolerance,
        )
        graph_build.write_graph(upload_dir, job_id, graph)
        _finish_stage(engine, job_id, "Trace", status="done", warnings=_write_draft(upload_dir, job_id), error=None)
        _run_patterns(engine, upload_dir, job_id)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Trace", status="failed", warnings=[], error=exc.message)
        _finish_stage(engine, job_id, "Patterns", status="failed", warnings=[], error="Prerequisite missing: Detecting patterns needs a graph.")
    except Exception as exc:
        logger.info("graph failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Trace",
            status="failed",
            warnings=[],
            error="The graph could not be built. Earlier results were kept.",
        )
        _finish_stage(engine, job_id, "Patterns", status="failed", warnings=[], error="Prerequisite missing: Detecting patterns needs a graph.")


def _run_patterns(engine: object, upload_dir: str, job_id: str) -> None:
    """Patterns is the Detecting patterns stage. The stored name stays Patterns."""
    _mark_running(engine, job_id, "Patterns")
    try:
        folder = job_folder(upload_dir, job_id)
        if not (folder / GRAPH_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Detecting patterns needs a graph.")
        graph = graph_build.load_graph(upload_dir, job_id)
        report = TagReport.model_validate(read_json(folder / TAG_REPORT_NAME))
        extraction = ExtractionResult.model_validate(read_json(folder / EXTRACTION_NAME))
        notes = [word.text for page in extraction.pages for word in page.words]
        updated = pattern_service.apply_patterns(graph, report, notes)
        pattern_service.write_graph(upload_dir, job_id, updated)
        _finish_stage(engine, job_id, "Patterns", status="done", warnings=[], error=None)
        _run_checks(engine, upload_dir, job_id)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Patterns", status="failed", warnings=[], error=exc.message)
        _finish_stage(engine, job_id, "SelfCheck", status="failed", warnings=[], error="Prerequisite missing: Running checks needs patterns.")
        _finish_stage(engine, job_id, "Report", status="failed", warnings=[], error="Prerequisite missing: Computing coverage needs finished checks.")
    except Exception as exc:
        logger.info("patterns failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Patterns",
            status="failed",
            warnings=[],
            error="Patterns could not be finished. The graph was kept.",
        )
        _finish_stage(engine, job_id, "SelfCheck", status="failed", warnings=[], error="Prerequisite missing: Running checks needs patterns.")
        _finish_stage(engine, job_id, "Report", status="failed", warnings=[], error="Prerequisite missing: Computing coverage needs finished checks.")
        return


def _run_checks(engine: object, upload_dir: str, job_id: str) -> None:
    """SelfCheck is the Running checks stage. The stored name stays SelfCheck."""
    _mark_running(engine, job_id, "SelfCheck")
    try:
        folder = job_folder(upload_dir, job_id)
        if not (folder / GRAPH_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Running checks needs a graph.")
        graph = graph_build.load_graph(upload_dir, job_id)
        report = TagReport.model_validate(read_json(folder / TAG_REPORT_NAME))
        extraction = ExtractionResult.model_validate(read_json(folder / EXTRACTION_NAME))
        updated = check_service.apply_checks(graph, report, extraction)
        check_service.write_graph(upload_dir, job_id, updated)
        _finish_stage(engine, job_id, "SelfCheck", status="done", warnings=[], error=None)
        _run_coverage(engine, upload_dir, job_id)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "SelfCheck", status="failed", warnings=[], error=exc.message)
        _finish_stage(engine, job_id, "Report", status="failed", warnings=[], error="Prerequisite missing: Computing coverage needs finished checks.")
    except Exception as exc:
        logger.info("checks failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "SelfCheck",
            status="failed",
            warnings=[],
            error="The checks could not be finished. Earlier results were kept.",
        )
        _finish_stage(engine, job_id, "Report", status="failed", warnings=[], error="Prerequisite missing: Computing coverage needs finished checks.")


def _run_coverage(engine: object, upload_dir: str, job_id: str) -> None:
    """Report is the Computing coverage stage. The stored name stays Report."""
    _mark_running(engine, job_id, "Report")
    try:
        folder = job_folder(upload_dir, job_id)
        if not (folder / GRAPH_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Computing coverage needs a graph.")
        graph = graph_build.load_graph(upload_dir, job_id)
        extraction = ExtractionResult.model_validate(read_json(folder / EXTRACTION_NAME))
        detections = detect.DetectionResult.model_validate(read_json(folder / DETECTIONS_NAME))
        geometry = line_geometry.GeometryResult.model_validate(read_json(folder / GEOMETRY_NAME))
        report = TagReport.model_validate(read_json(folder / TAG_REPORT_NAME))
        updated = coverage_service.apply_coverage(graph, extraction, detections, geometry, report)
        coverage_service.write_graph(upload_dir, job_id, updated)
        _finish_stage(engine, job_id, "Report", status="done", warnings=[], error=None)
        _run_simplify(engine, upload_dir, job_id)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Report", status="failed", warnings=[], error=exc.message)
        _finish_stage(engine, job_id, "Simplify", status="failed", warnings=[], error="Prerequisite missing: Simplifying the graph needs coverage.")
    except Exception as exc:
        logger.info("coverage failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Report",
            status="failed",
            warnings=[],
            error="Coverage could not be computed. Earlier results were kept.",
        )
        _finish_stage(engine, job_id, "Simplify", status="failed", warnings=[], error="Prerequisite missing: Simplifying the graph needs coverage.")


def _run_simplify(engine: object, upload_dir: str, job_id: str) -> None:
    """Simplify is stored as simplified.json. graph.json is not replaced."""
    _mark_running(engine, job_id, "Simplify")
    try:
        folder = job_folder(upload_dir, job_id)
        if not (folder / GRAPH_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Simplifying the graph needs a graph.")
        graph = graph_build.load_graph(upload_dir, job_id)
        before = graph.model_dump()
        simplified = simplify_service.simplify_graph(graph)
        if graph.model_dump() != before:
            raise RuntimeError("graph changed")
        simplify_service.write_simplified(upload_dir, job_id, simplified)
        warnings = ["The simplified graph failed its connectivity check and is not verified."] if simplified.failed_check else []
        _finish_stage(engine, job_id, "Simplify", status="done", warnings=warnings, error=None)
        _run_layout(engine, upload_dir, job_id)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Simplify", status="failed", warnings=[], error=exc.message)
    except Exception as exc:
        logger.info("simplify failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Simplify",
            status="failed",
            warnings=[],
            error="The simplified graph could not be built. The original graph was kept.",
        )
        _finish_stage(engine, job_id, "Layout", status="failed", warnings=[], error="Prerequisite missing: Layout needs a simplified graph.")


def _run_layout(engine: object, upload_dir: str, job_id: str) -> None:
    """Layout uses ELK. A graph over the limit fails with no invented coordinates."""
    _mark_running(engine, job_id, "Layout")
    try:
        folder = job_folder(upload_dir, job_id)
        if not (folder / SIMPLIFIED_NAME).is_file():
            raise PrerequisiteError("Prerequisite missing: Layout needs a simplified graph.")
        simplified = simplify_service.load_simplified(upload_dir, job_id)
        groups = {}
        graph = graph_build.load_graph(upload_dir, job_id)
        for pattern in graph.patterns:
            if pattern.type == "pump_group" and len(pattern.member_node_ids) >= 2:
                groups[pattern.id] = list(pattern.member_node_ids)
        result = layout_service.layout_with_groups(simplified, groups)
        layout_service.write_layout(upload_dir, job_id, result)
        graph = graph_build.load_graph(upload_dir, job_id)
        svg, meta = render_service.render_sketch(simplified, result, graph.verification, hidden_count=len(graph.ledger) + len(simplified.ledger))
        render_service.write_sketch(upload_dir, job_id, svg, meta)
        warnings = [result.message] if result.status == "degraded" and result.message else []
        if meta.failed_check:
            warnings.append("The sketch failed a check and is not labeled verified.")
        _finish_stage(engine, job_id, "Layout", status="done", warnings=warnings, error=None)
    except AppError as exc:
        _finish_stage(engine, job_id, "Layout", status="failed", warnings=[], error=exc.message)
    except PrerequisiteError as exc:
        _finish_stage(engine, job_id, "Layout", status="failed", warnings=[], error=exc.message)
    except Exception as exc:
        logger.info("layout failed for job %s (%s)", job_id, type(exc).__name__)
        _finish_stage(
            engine,
            job_id,
            "Layout",
            status="failed",
            warnings=[],
            error="The layout could not be computed. Earlier results were kept.",
        )


def _mark_running(engine: object, job_id: str, name: str) -> None:
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
        if row is None:
            return
        _replace_stage(
            row,
            name,
            status="running",
            started_at=datetime.now(timezone.utc),
            ended_at=None,
            duration_ms=None,
            warnings=[],
            error=None,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.info("stage %s was not marked running for job %s (%s)", name, job_id, type(exc).__name__)
    finally:
        session.close()


def _finish_stage(
    engine: object,
    job_id: str,
    name: str,
    *,
    status: str,
    warnings: list[str],
    error: str | None,
) -> None:
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
        if row is None:
            return
        current = _stage(row, name)
        ended = datetime.now(timezone.utc)
        started = current.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        duration_ms = 0
        if started is not None:
            duration_ms = max(0, int((ended - started).total_seconds() * 1000))
        _replace_stage(
            row,
            name,
            status=status,
            ended_at=ended,
            duration_ms=duration_ms,
            warnings=warnings,
            error=error,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.info("read status was not stored for job %s (%s)", job_id, type(exc).__name__)
    finally:
        session.close()
