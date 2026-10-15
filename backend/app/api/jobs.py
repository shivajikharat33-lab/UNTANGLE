"""Create a project from two files, and read it back."""

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import JobRow
from app.schemas.intake import JobListItem, PublicConfig
from app.schemas.io_list import IoListResult, IoValidateRequest
from app.schemas.graph import CoverageMetric, DiagramGraph, Finding, GraphSummary, LedgerPage, Pattern, SimplifiedGraph, VerificationStatus
from app.schemas.job import Job
from app.services.io_list import load_saved_io_list, validate_job
from app.schemas.reports import TagReport
from app.services.pdf_extract import ExtractionResult, load_extraction
from app.services.pipeline import begin_process, finish_process
from app.services.detect import DetectionResult, load_detections
from app.services.geometry import GeometryResult, load_geometry
from app.services.graph_build import load_graph, summarize_graph
from app.services.checks import load_finding, load_findings
from app.services.coverage import load_coverage, load_ledger, load_verification
from app.services.layout import LayoutResult, load_layout
from app.services.render import SketchMeta, load_sketch_meta, load_sketch_svg
from app.services.simplify import load_simplified
from app.services.patterns import load_patterns
from app.services.tag_match import load_tag_report
from app.services.downloads import attachment_disposition
from app.services.export_files import cache_export, export_metadata, graph_json, guard_size, render_png_and_pdf, source_hash, workbook_bytes
from app.services.reports_view import ReportPage, connection_rows, page_of, tag_rows
from app.services.trace import ItemDetail, TraceResult, item_detail, trace_item
from app.services.uploads import create_uploaded_job, job_from_row

router = APIRouter()


def _engine_or_error(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "The database is not available.")
    return engine


@router.get("/api/config")
def public_config(request: Request) -> PublicConfig:
    """The upload size limit. Health stays a separate check."""
    settings = request.app.state.settings
    return PublicConfig(
        max_upload_mb=settings.max_upload_mb,
        ask_graph_llm_enabled=settings.ask_graph_llm_enabled,
        fewshot_symbols_enabled=settings.fewshot_symbols_enabled,
        dark_theme_enabled=settings.dark_theme_enabled,
        flow_animation_enabled=settings.flow_animation_enabled,
        batch_upload_enabled=settings.batch_upload_enabled,
        access_required=bool(settings.demo_access_code),
        public_demo_mode=settings.public_demo_mode,
        max_pdf_pages=settings.max_pdf_pages,
        modify_enabled=settings.modify_enabled and not settings.public_demo_mode,
    )


@router.post("/api/jobs")
async def create_job(
    request: Request,
    pid_pdf: UploadFile | None = File(default=None),
    io_list: UploadFile | None = File(default=None),
    name: str = Form(default=""),
) -> JSONResponse:
    """Store one PDF and one xlsx workbook and record Intake."""
    settings = request.app.state.settings
    if settings.public_demo_mode:
        raise AppError(403, "UPLOADS_DISABLED", "This public demo does not accept uploads. Open the synthetic project.")
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        job = await create_uploaded_job(
            settings=settings,
            session=session,
            pid_pdf=pid_pdf,
            io_list=io_list,
            name=name,
        )
    finally:
        session.close()
    return JSONResponse(status_code=201, content=job.model_dump(mode="json"))


@router.get("/api/jobs")
def list_jobs(request: Request) -> list[JobListItem]:
    """Newest project first. The list does not include file contents."""
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        rows = session.scalars(select(JobRow).order_by(JobRow.created_at.desc(), JobRow.id.desc())).all()
        items: list[JobListItem] = []
        for row in rows:
            job = job_from_row(row)
            if job.intake is None or job.created_at is None:
                continue
            items.append(
                JobListItem(
                    id=job.id,
                    name=job.name,
                    created_at=job.created_at.isoformat(),
                    status="uploaded",
                    pdf_verdict=job.intake.verdict,
                    page_count=job.intake.page_count,
                )
            )
        return items
    finally:
        session.close()


@router.post("/api/jobs/{job_id}/io-list/validate")
def validate_io_list(
    job_id: str,
    request: Request,
    body: IoValidateRequest | None = Body(default=None),
) -> IoListResult:
    """Check the stored workbook. Replacing this file does not change the original xlsx."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return validate_job(settings.upload_dir, job_id, body)


@router.get("/api/jobs/{job_id}/io-list")
def get_io_list(job_id: str, request: Request) -> IoListResult:
    """Return the saved IO check. A missing check is a 404, not an empty success."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_saved_io_list(settings.upload_dir, job_id)


def _require_job(request: Request, job_id: str) -> JobRow:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
    finally:
        session.close()
    if row is None:
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    return row


@router.post("/api/jobs/{job_id}/process", status_code=202)
def process_job(
    job_id: str,
    request: Request,
    background: BackgroundTasks,
    force: bool = Query(default=False),
    retry: bool = Query(default=False),
) -> Job:
    """Start processing. force ignores the cache. retry continues from the failed stage."""
    settings = request.app.state.settings
    engine = _engine_or_error(request)
    _require_job(request, job_id)
    snapshot = begin_process(engine, settings.upload_dir, job_id, retry=retry, force=force)
    resume_from = next((stage.name for stage in snapshot.stages if stage.status == "running"), "Read")
    background.add_task(
        finish_process,
        engine,
        settings.upload_dir,
        job_id,
        settings.tag_fuzzy_threshold,
        settings.process_min_stroke,
        settings.signal_max_stroke,
        settings.snap_tolerance,
        settings.node_attach_tolerance,
        force,
        retry,
        settings.cache_dir,
        resume_from,
        settings.job_timeout_seconds,
    )
    return snapshot


@router.get("/api/jobs/{job_id}/tag-report")
def get_tag_report(job_id: str, request: Request) -> TagReport:
    """Return the saved Tag Check Report. A missing report is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_tag_report(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/sketch/draft")
def get_sketch_draft(job_id: str, request: Request) -> Response:
    """Return the early draft SVG. A missing draft is a 404."""
    from app.services.storage import job_folder

    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    path = job_folder(settings.upload_dir, job_id) / "sketch_draft.svg"
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The draft sketch has not been drawn for this project.", {"job_id": job_id})
    return Response(content=path.read_text(encoding="utf-8"), media_type="image/svg+xml")


@router.get("/api/jobs/{job_id}/sketch/meta")
def get_sketch_meta(job_id: str, request: Request) -> SketchMeta:
    """Return sketch metadata. A missing sketch is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_sketch_meta(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/sketch")
def get_sketch(job_id: str, request: Request, draft: bool = False) -> Response:
    """Return the final SVG, or the draft when draft=true. A missing file is a 404."""
    from app.services.storage import job_folder

    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    if draft:
        path = job_folder(settings.upload_dir, job_id) / "sketch_draft.svg"
        if not path.is_file():
            raise AppError(404, "NOT_FOUND", "The draft sketch has not been drawn for this project.", {"job_id": job_id})
        return Response(content=path.read_text(encoding="utf-8"), media_type="image/svg+xml")
    svg = load_sketch_svg(settings.upload_dir, job_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/jobs/{job_id}/layout")
def get_layout(job_id: str, request: Request) -> LayoutResult:
    """Return ELK coordinates. A missing layout is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_layout(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/trace")
def get_trace(job_id: str, request: Request, item_id: str, mode: str = "connected", depth: int | None = None) -> TraceResult:
    """Trace from one item. Unknown direction stops a flow trace."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return trace_item(load_graph(settings.upload_dir, job_id), item_id, mode, depth)


@router.get("/api/jobs/{job_id}/items/{item_id}")
def get_item(job_id: str, item_id: str, request: Request) -> ItemDetail:
    """Return stored facts for one node or edge. An unknown id is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    graph = load_graph(settings.upload_dir, job_id)
    try:
        simplified = load_simplified(settings.upload_dir, job_id)
    except AppError:
        simplified = None
    try:
        report = load_tag_report(settings.upload_dir, job_id)
    except AppError:
        report = None
    return item_detail(graph, simplified, report, item_id)


@router.get("/api/jobs/{job_id}/simplified")
def get_simplified(job_id: str, request: Request) -> SimplifiedGraph:
    """Return the simplified copy. The original graph is a different file."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_simplified(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/reports/tags")
def report_tags(job_id: str, request: Request, q: str = "", sort: str = "tag", offset: int = 0, limit: int = 50) -> ReportPage:
    """Tag check rows already stored. Matching is not run again."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    graph = load_graph(settings.upload_dir, job_id)
    report = load_tag_report(settings.upload_dir, job_id)
    try:
        extraction = load_extraction(settings.upload_dir, job_id)
    except AppError:
        extraction = None
    return page_of(tag_rows(report, graph, extraction), query=q, sort=sort, offset=offset, limit=min(limit, 200))


@router.get("/api/jobs/{job_id}/reports/connections")
def report_connections(job_id: str, request: Request, q: str = "", sort: str = "from", offset: int = 0, limit: int = 50) -> ReportPage:
    """Connections already in the graph. Direction unknown stays unknown."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return page_of(connection_rows(load_graph(settings.upload_dir, job_id)), query=q, sort=sort, offset=offset, limit=min(limit, 200))


def _export_context(request: Request, job_id: str, draft: bool):
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    folder = __import__("app.services.storage", fromlist=["job_folder"]).job_folder(settings.upload_dir, job_id)
    svg_name = "sketch_draft.svg" if draft else "sketch.svg"
    svg_path = folder / svg_name
    if not svg_path.is_file():
        raise AppError(404, "NOT_FOUND", "The sketch has not been drawn for this project.", {"job_id": job_id})
    svg = svg_path.read_text(encoding="utf-8")
    if draft and "Verified" in svg and "not verified" not in svg.lower():
        raise AppError(409, "EXPORT_DRAFT", "The draft file contains a Verified label. It was not exported.", {"job_id": job_id})
    return settings, folder, svg


@router.get("/api/jobs/{job_id}/exports/{fmt}")
def download_export(job_id: str, fmt: str, request: Request, draft: bool = False) -> Response:
    """Download one format. A draft file name and its content say draft, never Verified."""
    from app.services.storage import IO_NAME

    settings, folder, svg = _export_context(request, job_id, draft)
    graph = load_graph(settings.upload_dir, job_id)
    version = graph.processing_version or "unknown"
    label = "draft" if draft else "final"
    filename = f"{job_id}-{version}-{label}.{ 'xlsx' if fmt == 'excel' else fmt }"
    pdf_hash = source_hash(settings.upload_dir, job_id)
    io_path = folder / IO_NAME
    io_hash = hashlib_file(io_path) if io_path.is_file() else ""
    key = f"{pdf_hash}-{io_hash}-{version}-{label}-{fmt}"
    if fmt == "svg":
        payload = guard_size(svg.encode("utf-8"))
        media = "image/svg+xml"
    elif fmt == "json":
        import json
        from app.services.sanity import sanity_warnings
        body = {"graph": json.loads(graph_json(graph)), "sanity_warnings": [item.model_dump() for item in sanity_warnings(graph)], "detail_level": 2}
        payload = guard_size(json.dumps(body).encode("utf-8"))
        media = "application/json"
    elif fmt in {"png", "pdf"}:
        png, pdf = render_png_and_pdf(svg)
        payload = guard_size(png if fmt == "png" else pdf)
        media = "image/png" if fmt == "png" else "application/pdf"
    elif fmt == "excel":
        payload = guard_size(workbook_bytes({
            "Tags": [["tag", "status"], *[[node.tag, node.type] for node in graph.nodes if node.tag]],
            "Connections": [["from", "to", "direction"], *[[edge.from_id, edge.to_id, edge.direction] for edge in graph.edges]],
        }))
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise AppError(404, "NOT_FOUND", "That export format is not available.", {"format": fmt})
    if draft and b"Verified" in payload and b"not verified" not in payload.lower() and fmt in {"svg", "pdf"}:
        raise AppError(409, "EXPORT_DRAFT", "A draft export must not say Verified.", {"job_id": job_id})
    cache_export(settings.cache_dir, key, filename, payload)
    meta = export_metadata(job_id, "original.pdf", pdf_hash, "io_list.xlsx", io_hash, version, draft, graph.verification.state if graph.verification else "", graph.verification.failing != [] if graph.verification else False, len(graph.ledger), fmt, filename, media, len(payload))
    return Response(
        content=payload,
        media_type=media,
        headers={
            "Content-Disposition": attachment_disposition(filename),
            "X-Export-Meta": meta.model_dump_json(),
        },
    )


def hashlib_file(path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


@router.get("/api/jobs/{job_id}/coverage")
def get_coverage(job_id: str, request: Request) -> list[CoverageMetric]:
    """Return coverage counts. A missing run is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_coverage(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/ledger")
def get_ledger(
    job_id: str,
    request: Request,
    item_type: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=200),
) -> LedgerPage:
    """Return one page of hidden items. Filters are exact."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_ledger(settings.upload_dir, job_id, item_type=item_type, reason_code=reason_code, offset=offset, limit=limit)


@router.get("/api/jobs/{job_id}/verification")
def get_verification(job_id: str, request: Request) -> VerificationStatus:
    """Return the automated state. This is not an engineering certification."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_verification(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/findings/{finding_id}")
def get_finding(job_id: str, finding_id: str, request: Request) -> Finding:
    """Return one finding. An unknown id is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_finding(settings.upload_dir, job_id, finding_id)


@router.get("/api/jobs/{job_id}/findings")
def get_findings(
    job_id: str,
    request: Request,
    severity: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> list[Finding]:
    """List check findings. Filters are exact matches. A missing run is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    findings = load_findings(settings.upload_dir, job_id)
    if severity:
        findings = [item for item in findings if item.severity == severity]
    if rule_id:
        findings = [item for item in findings if item.rule_id == rule_id]
    if category:
        findings = [item for item in findings if item.category == category]
    return findings


@router.get("/api/jobs/{job_id}/patterns")
def get_patterns(job_id: str, request: Request) -> list[Pattern]:
    """Return pump groups and control loops. A missing run is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_patterns(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/graph")
def get_graph(job_id: str, request: Request) -> DiagramGraph:
    """Return the saved graph. A missing file is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_graph(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/graph/summary")
def get_graph_summary(job_id: str, request: Request) -> GraphSummary:
    """Counts from the saved graph. This does not rebuild it."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return summarize_graph(load_graph(settings.upload_dir, job_id))


@router.get("/api/jobs/{job_id}/geometry")
def get_geometry(job_id: str, request: Request) -> GeometryResult:
    """Return saved line geometry. A missing file is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_geometry(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/detections")
def get_detections(job_id: str, request: Request) -> DetectionResult:
    """Return saved symbol candidates. A missing file is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_detections(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}/pages/{page_number}")
def page_preview(job_id: str, page_number: int, request: Request, zoom: float = 1.5) -> Response:
    """A cached PNG of one PDF page. The original PDF is not modified."""
    from app.services.page_image import page_png

    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    payload, width, height = page_png(settings.upload_dir, settings.cache_dir, job_id, page_number, zoom)
    return Response(
        content=payload,
        media_type="image/png",
        headers={
            "X-Page-Width": str(width),
            "X-Page-Height": str(height),
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="page-{page_number}.png"',
        },
    )


@router.get("/api/jobs/{job_id}/extraction")
def get_extraction(job_id: str, request: Request) -> ExtractionResult:
    """Return the saved Read output. A missing read is a 404."""
    settings = request.app.state.settings
    _engine_or_error(request)
    _require_job(request, job_id)
    return load_extraction(settings.upload_dir, job_id)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> Job:
    """Full project, including Intake and the stage list."""
    engine = _engine_or_error(request)
    session = Session(engine)
    try:
        row = session.get(JobRow, job_id)
    finally:
        session.close()
    if row is None:
        raise AppError(404, "NOT_FOUND", "No project exists with that id.", {"job_id": job_id})
    return job_from_row(row)
