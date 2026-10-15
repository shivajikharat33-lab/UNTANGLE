import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { acceptOriginal, getConfig, getExtraction, getGraph, getItem, getJob, getSketchMeta, getSketchText, getTrace, getVerification, listJobs, openDraft, pagePreviewUrl, type ItemDetail } from "../api/jobs";
import { EditBanner } from "../components/EditBanner";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { DrawingViewer } from "../components/DrawingViewer";
import { EmptyState } from "../components/EmptyState";
import { Spinner } from "../components/Spinner";
import { VERIFICATION_DISCLAIMER, type VerificationStatus } from "../types/coverage";
import type { JobListItem } from "../types/intake";
import type { SketchMeta } from "../types/sketch";
import type { ExtractionResult } from "../types/extraction";

function overlaySketch(markup: string): string {
  const style = `<style>
    g[data-certainty="confirmed"] { outline: 3px solid #15803d; outline-offset: 2px; }
    g[data-certainty="likely"] { outline: 3px dashed #1d4ed8; outline-offset: 2px; }
    g[data-certainty="uncertain"] { outline: 3px dotted #b45309; outline-offset: 2px; }
    g[data-review="true"] > text:first-of-type { font-weight: 700; }
  </style>`;
  return markup.includes("</svg>") ? markup.replace("</svg>", `${style}</svg>`) : markup;
}

export function ResultsPage() {
  const { id } = useParams();
  const [projects, setProjects] = useState<JobListItem[] | null>(null);
  const [svg, setSvg] = useState("");
  const [draft, setDraft] = useState(false);
  const [meta, setMeta] = useState<SketchMeta | null>(null);
  const [verification, setVerification] = useState<VerificationStatus | null>(null);
  const [version, setVersion] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [linked, setLinked] = useState(false);
  const [originalZoom, setOriginalZoom] = useState(1);
  const [sketchZoom, setSketchZoom] = useState(1);
  const [pane, setPane] = useState<"original" | "sketch" | "both">("both");
  const [params, setParams] = useSearchParams();
  const selected = params.get("select") ?? "";
  const [detail, setDetail] = useState<ItemDetail | null>(null);
  const [traceText, setTraceText] = useState("");
  const [miss, setMiss] = useState("");
  const [hits, setHits] = useState<Array<{ id: string; x: number; y: number; w: number; h: number }>>([]);
  const [confidenceOn, setConfidenceOn] = useState(false);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [modifyEnabled, setModifyEnabled] = useState(true);
  const [accepted, setAccepted] = useState(false);
  const [bannerError, setBannerError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    if (!id) {
      listJobs(controller.signal)
        .then((items) => {
          setProjects(items);
          setError(null);
        })
        .catch((caught: unknown) => {
          if (caught instanceof DOMException && caught.name === "AbortError") {
            return;
          }
          setError(caught instanceof ApiError ? caught : new ApiError("Projects could not be loaded.", 0, null));
        })
        .finally(() => setLoading(false));
      return () => controller.abort();
    }
    Promise.all([
      getJob(id, controller.signal),
      getSketchText(id, false, controller.signal).catch(async (caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 404) {
          return getSketchText(id, true, controller.signal);
        }
        throw caught;
      }),
      getSketchMeta(id, controller.signal).catch(() => null),
      getVerification(id, controller.signal).catch(() => null),
    ])
      .then(([job, markup, sketchMeta, check]) => {
        const finalReady = job.stages.some((stage) => stage.name === "Report" && stage.status === "done");
        setDraft(!finalReady);
        setSvg(markup);
        setMeta(sketchMeta);
        setVerification(check);
        setVersion(sketchMeta?.processing_version || "");
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("Results could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const controller = new AbortController();
    getExtraction(id, controller.signal).then(setExtraction).catch(() => setExtraction(null));
    getGraph(id, controller.signal)
      .then((graph) => {
        setHits(
          graph.nodes
            .filter((node) => node.bbox)
            .map((node) => ({ id: node.id, x: node.bbox!.x, y: node.bbox!.y, w: node.bbox!.w, h: node.bbox!.h })),
        );
      })
      .catch(() => setHits([]));
    return () => controller.abort();
  }, [id]);

  useEffect(() => {
    if (!id || !selected) {
      setDetail(null);
      setTraceText("");
      return;
    }
    const controller = new AbortController();
    getItem(id, selected, controller.signal)
      .then((item) => {
        setDetail(item);
        setMiss("");
      })
      .catch((caught: unknown) => {
        setDetail(null);
        setMiss(caught instanceof ApiError ? caught.message : "That item was not found.");
      });
    return () => controller.abort();
  }, [id, selected]);

  useEffect(() => {
    getConfig().then((config) => setModifyEnabled(config.modify_enabled !== false)).catch(() => setModifyEnabled(true));
  }, []);

  function choose(itemId: string) {
    const next = new URLSearchParams(params);
    next.set("select", itemId);
    setParams(next);
  }

  function clearSelection() {
    const next = new URLSearchParams(params);
    next.delete("select");
    setParams(next);
    setTraceText("");
    setMiss("");
  }

  async function runTrace(mode: string) {
    if (!id || !selected) {
      return;
    }
    const result = await getTrace(id, selected, mode);
    const stop = result.stopped.length > 0 ? ` ${result.stopped.join(" ")}` : "";
    setTraceText(`${result.note} Depth ${result.depth}. Items: ${result.traced_ids.join(", ") || "none"}.${stop}`);
  }

  function onSketchClick(event: React.MouseEvent<HTMLDivElement>) {
    const element = (event.target as Element).closest("[id^='node-'], [id^='edge-']");
    if (!element) {
      return;
    }
    choose(element.id.replace(/^(node|edge)-/, ""));
  }

  function onOriginalClick(event: React.MouseEvent<HTMLDivElement>) {
    const target = event.currentTarget.getBoundingClientRect();
    if (!page) {
      setMiss("The page size is not available, so the click was not matched.");
      return;
    }
    const x = ((event.clientX - target.left) / target.width) * page.width;
    const y = ((event.clientY - target.top) / target.height) * page.height;
    const hit = hits.find((item) => x >= item.x && x <= item.x + item.w && y >= item.y && y <= item.y + item.h);
    if (!hit) {
      setMiss("Nothing matched that click.");
      return;
    }
    choose(hit.id);
    setMiss("");
  }

  function setZoom(next: number, side: "original" | "sketch") {
    if (linked) {
      setOriginalZoom(next);
      setSketchZoom(next);
      return;
    }
    if (side === "original") {
      setOriginalZoom(next);
    } else {
      setSketchZoom(next);
    }
  }

  const page = extraction?.pages?.find((item) => item.page === pageNumber) ?? extraction?.pages?.[0];
  const verified = Boolean(verification?.state === "verified" && meta && meta.failed_check === false && !draft);
  const badge = draft ? "DRAFT, not final, not verified" : verified ? "verified" : verification?.state || "not_verified";

  if (!id) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl">Results</h1>
        {loading ? <Spinner label="Loading projects" /> : null}
        {error ? <Alert tone="error" title={error.message} /> : null}
        {projects && projects.length === 0 ? <EmptyState title="No projects yet" description="Upload a drawing and an IO list, then run extraction." /> : null}
        <ul className="space-y-2">
          {(projects ?? []).map((project) => (
            <li key={project.id}>
              <Link className="font-semibold underline" to={`/app/projects/${project.id}/results`}>{project.name}</Link>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Results</h1>
      {bannerError ? <Alert tone="error" title={bannerError} /> : null}
      <EditBanner
        modifyEnabled={modifyEnabled}
        accepted={accepted}
        onKeep={() => {
          void acceptOriginal(id).then(() => setAccepted(true)).catch((caught: unknown) => setBannerError(caught instanceof ApiError ? caught.message : "Version 0 could not be accepted."));
        }}
        onModify={() => {
          void openDraft(id).then(() => { window.location.assign(`/app/projects/${id}/edit`); }).catch((caught: unknown) => setBannerError(caught instanceof ApiError ? caught.message : "The working copy could not be opened."));
        }}
      />
      {loading ? <Spinner label="Loading results" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      <section className="rounded-card border border-line p-4 text-sm">
        <p>Processing version: {version || "not recorded"}</p>
        <p className="font-semibold">{badge}</p>
        {draft ? <p>DRAFT, not final, not verified</p> : null}
        <p>Hidden items: {meta?.hidden_count ?? "not recorded"}</p>
        {meta?.failed_check ? <p>Connectivity check failed. This sketch is not verified.</p> : null}
        {verification && verification.failing.length > 0 ? <p>Failing criteria: {verification.failing.join(", ")}</p> : null}
        <p>{verification?.disclaimer || meta?.disclaimer || VERIFICATION_DISCLAIMER}</p>
      </section>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={linked} onChange={(event) => setLinked(event.target.checked)} />
        Link views {linked ? "on" : "off"}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={confidenceOn} onChange={(event) => setConfidenceOn(event.target.checked)} />
        Confidence overlay {confidenceOn ? "on" : "off"}. Solid outline is confirmed or likely. Dashed outline is uncertain.
      </label>
      {miss ? <p className="text-sm">{miss}</p> : null}
      {detail ? (
        <section className="rounded-card border border-line p-4 text-sm">
          <p className="font-semibold">{detail.type} {detail.tag || detail.id}</p>
          <p>Id {detail.id}. Confidence {detail.certainty} {detail.confidence.score}. IO {detail.io_status || "none"}.</p>
          <p>Original ids: {detail.original_ids.join(", ") || "none"}.</p>
          <p>Evidence: {detail.evidence.map((item) => item.description).join(" ") || "none"}.</p>
          <p>Findings: {detail.findings.join(" ") || "none"}.</p>
          <p>Needs review: {detail.needs_review ? detail.review_reasons.join(" ") : "no"}.</p>
          <p>Patterns: {detail.patterns.join(", ") || "none"}.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className="rounded-full border border-line px-3 py-1" onClick={() => void runTrace("downstream")}>Trace downstream</button>
            <button type="button" className="rounded-full border border-line px-3 py-1" onClick={() => void runTrace("upstream")}>Trace upstream</button>
            <button type="button" className="rounded-full border border-line px-3 py-1" onClick={() => void runTrace("connected")}>Show connected items</button>
            <button type="button" className="rounded-full border border-line px-3 py-1" onClick={clearSelection}>Clear selection</button>
          </div>
          {traceText ? <p className="mt-2">{traceText}</p> : null}
        </section>
      ) : null}
      {confidenceOn ? (
        <p className="text-sm">Legend: confirmed is a solid green outline, likely is a dashed blue outline, uncertain is a dotted copper outline, and a needs-review item is also marked “review”.</p>
      ) : null}
      {(extraction?.pages?.length ?? 0) > 1 ? (
        <div className="flex flex-wrap gap-2">
          {extraction?.pages?.map((item) => (
            <button key={item.page} type="button" className={`rounded-full border px-3 py-1 text-xs font-semibold ${item.page === pageNumber ? "border-ink bg-ink text-paper" : "border-line"}`} onClick={() => setPageNumber(item.page)}>
              Page {item.page}
            </button>
          ))}
        </div>
      ) : null}
      <div className="flex gap-2 md:hidden">
        {(["original", "sketch", "both"] as const).map((value) => (
          <button key={value} type="button" className="rounded-full border border-line px-3 py-1 text-xs font-semibold" onClick={() => setPane(value)}>{value}</button>
        ))}
      </div>
      <div className={`grid gap-4 ${pane === "both" ? "md:grid-cols-2" : "grid-cols-1"}`}>
        {pane !== "sketch" ? (
          <DrawingViewer label="Original drawing" zoom={originalZoom} onZoom={(next) => setZoom(next, "original")}>
            <div className="relative inline-block" onClick={onOriginalClick}>
              <img src={pagePreviewUrl(id, pageNumber)} alt={`Original drawing page ${pageNumber}`} />
              {detail?.bbox ? (
                <span
                  className="pointer-events-none absolute border-2 border-copper"
                  style={{
                    left: `${(detail.bbox.x / (extraction?.pages?.[0]?.width || 1)) * 100}%`,
                    top: `${(detail.bbox.y / (extraction?.pages?.[0]?.height || 1)) * 100}%`,
                    width: `${(detail.bbox.w / (extraction?.pages?.[0]?.width || 1)) * 100}%`,
                    height: `${(detail.bbox.h / (extraction?.pages?.[0]?.height || 1)) * 100}%`,
                  }}
                />
              ) : null}
            </div>
          </DrawingViewer>
        ) : null}
        {pane !== "original" ? (
          <DrawingViewer label="Sketch" zoom={sketchZoom} onZoom={(next) => setZoom(next, "sketch")}>
            {svg ? <div onClick={onSketchClick} dangerouslySetInnerHTML={{ __html: confidenceOn ? overlaySketch(svg) : svg }} /> : <EmptyState title="No sketch yet" description="Run extraction. A draft appears after the graph is built." />}
          </DrawingViewer>
        ) : null}
      </div>
    </div>
  );
}
