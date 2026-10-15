import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { getJob, processJob } from "../api/jobs";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";
import { DetectionsPanel } from "../components/DetectionsPanel";
import { GraphSummaryPanel } from "../components/GraphSummaryPanel";
import { CoveragePanel } from "../components/CoveragePanel";
import { SimplifiedPanel } from "../components/SimplifiedPanel";
import { FindingsPanel } from "../components/FindingsPanel";
import { PatternsPanel } from "../components/PatternsPanel";
import { ExtractionPanel } from "../components/ExtractionPanel";
import { IoListPanel } from "../components/IoListPanel";
import { StageList } from "../components/StageList";
import { TagReportPanel } from "../components/TagReportPanel";
import { buttonClass } from "../lib/buttonClass";
import { POLL_INTERVAL_MS, shouldPoll } from "../lib/stagePresentation";
import type { PdfVerdict } from "../types/intake";
import type { Job } from "../types/job";

const verdictTone: Record<PdfVerdict, "neutral" | "medium" | "low"> = {
  VECTOR: "neutral",
  MIXED: "medium",
  SCANNED: "low",
};

function failureTitle(error: ApiError): string {
  if (error.status === 0) {
    return "Offline";
  }
  if (error.status === 404) {
    return "Project not found";
  }
  return "Could not load this project";
}

export function ProcessingPage() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [runError, setRunError] = useState<ApiError | null>(null);
  const [runningRequest, setRunningRequest] = useState(false);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      setError(new ApiError("No project exists with that id.", 404, null));
      return;
    }
    const controller = new AbortController();
    let timer = 0;
    let cancelled = false;

    async function load(projectId: string) {
      try {
        const next = await getJob(projectId, controller.signal);
        if (cancelled) {
          return;
        }
        setJob(next);
        setError(null);
        setLoading(false);
        if (shouldPoll(next.stages)) {
          timer = window.setTimeout(() => {
            void load(projectId);
          }, POLL_INTERVAL_MS);
        }
      } catch (caught) {
        if (cancelled || (caught instanceof DOMException && caught.name === "AbortError")) {
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The project could not be loaded.", 0, null));
        setLoading(false);
      }
    }

    setLoading(true);
    setError(null);
    void load(id);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [id, attempt]);

  useEffect(() => {
    setJob(null);
    setRunError(null);
  }, [id]);

  async function runExtraction() {
    if (!id) {
      return;
    }
    setRunningRequest(true);
    setRunError(null);
    try {
      const next = await processJob(id);
      setJob(next);
      setAttempt((value) => value + 1);
    } catch (caught) {
      setRunError(caught instanceof ApiError ? caught : new ApiError("Extraction could not be started.", 0, null));
    } finally {
      setRunningRequest(false);
    }
  }

  const projectName = job?.name.trim() ?? "";
  const pageTitle = projectName
    ? projectName
    : loading
      ? "Loading project"
      : error?.status === 404
        ? "Project not found"
        : error
          ? "Project unavailable"
          : "Untitled project";
  const warnings = [
    ...(job?.intake?.warnings ?? []),
    ...(job?.stages ?? []).flatMap((stage) => stage.warnings),
  ].filter((warning, index, all) => warning.trim().length > 0 && all.indexOf(warning) === index);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Processing"
        title={pageTitle}
        description="Run extraction to build the graph and the sketch. Open the sketch when a stage has finished."
      />

      {loading && !job ? <Spinner label="Loading project" /> : null}

      {error ? (
        <Alert tone="error" title={failureTitle(error)}>
          <p>{error.message}</p>
          {error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}
          <div className="mt-3">
            <Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>
              Try again
            </Button>
          </div>
        </Alert>
      ) : null}

      {job && !job.intake ? (
        <Alert tone="error" title="Intake was not recorded">
          This project has no intake summary, so there is nothing to show from the files.
        </Alert>
      ) : null}

      {job?.intake ? (
        <Card title="Files">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={verdictTone[job.intake.verdict]}>{job.intake.verdict}</Badge>
            <p className="text-sm text-ink-soft">{job.intake.page_count} {job.intake.page_count === 1 ? "page" : "pages"}</p>
          </div>
          <p className="mt-3 text-sm leading-6 text-ink">{job.intake.verdict_reason}</p>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-semibold">P&amp;ID</dt>
              <dd className="text-ink-soft">{job.intake.pdf.original_name}</dd>
            </div>
            <div>
              <dt className="font-semibold">IO list</dt>
              <dd className="text-ink-soft">{job.intake.io_list.original_name}</dd>
            </div>
          </dl>
          <h3 className="mt-4 font-semibold">Excel</h3>
          {job.intake.sheets.length === 0 ? (
            <p className="mt-2 text-sm text-ink-soft">The workbook opened, but it has no sheets.</p>
          ) : (
            <ul className="mt-2 space-y-3">
              {job.intake.sheets.map((sheet) => (
                <li key={sheet.name} className="text-sm leading-6">
                  <p className="font-semibold">{sheet.name}</p>
                  <p className="text-ink-soft">{sheet.row_count} {sheet.row_count === 1 ? "row" : "rows"}</p>
                  <p className="text-ink-soft">Columns: {sheet.columns.filter((column) => column.length > 0).join(", ") || "No column names"}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {job ? (
        <section>
          <h2 className="mb-3 font-display text-xl">Stages</h2>
          <StageList stages={job.stages} />
        </section>
      ) : null}

      {job ? <IoListPanel jobId={job.id} /> : null}

      {job ? <ExtractionPanel jobId={job.id} readStatus={job.stages.find((stage) => stage.name === "Read")?.status ?? "pending"} /> : null}

      {job ? <TagReportPanel jobId={job.id} matchStatus={job.stages.find((stage) => stage.name === "MatchTags")?.status ?? "pending"} /> : null}

      {job ? <DetectionsPanel jobId={job.id} detectStatus={job.stages.find((stage) => stage.name === "Detect")?.status ?? "pending"} /> : null}

      {job ? <GraphSummaryPanel jobId={job.id} traceStatus={job.stages.find((stage) => stage.name === "Trace")?.status ?? "pending"} /> : null}

      {job ? <PatternsPanel jobId={job.id} patternStatus={job.stages.find((stage) => stage.name === "Patterns")?.status ?? "pending"} /> : null}

      {job ? <FindingsPanel jobId={job.id} checkStatus={job.stages.find((stage) => stage.name === "SelfCheck")?.status ?? "pending"} /> : null}

      {job ? <CoveragePanel jobId={job.id} reportStatus={job.stages.find((stage) => stage.name === "Report")?.status ?? "pending"} /> : null}

      {job ? <SimplifiedPanel jobId={job.id} simplifyStatus={job.stages.find((stage) => stage.name === "Simplify")?.status ?? "pending"} /> : null}

      <section>
        <h2 className="mb-3 font-display text-xl">Warnings</h2>
        {job && warnings.length === 0 ? (
          <EmptyState title="No warnings" description="Intake did not record a warning for these files." />
        ) : null}
        {warnings.length > 0 ? (
          <div className="space-y-3">
            {warnings.map((warning) => (
              <Alert key={warning} tone="warning" title="Intake warning">
                {warning}
              </Alert>
            ))}
          </div>
        ) : null}
        {!job && !loading ? (
          <EmptyState title="No warnings" description="There is no project loaded, so there are no intake warnings to show." />
        ) : null}
      </section>

      <section className="flex flex-wrap items-center gap-3">
        <Button
          disabled={!job || job.stages.every((stage) => stage.name !== "Intake" || stage.status !== "done") || shouldPoll(job.stages) || runningRequest}
          onClick={() => void runExtraction()}
        >
          Run extraction
        </Button>
        <Button
          variant="secondary"
          disabled={!job || shouldPoll(job.stages) || runningRequest}
          onClick={() => void processJob(job?.id ?? "", { retry: true }).then(() => setAttempt((value) => value + 1)).catch((caught: unknown) => setRunError(caught instanceof ApiError ? caught : new ApiError("Retry could not start.", 0, null)))}
        >
          Retry from the failed stage
        </Button>
        <Button
          variant="secondary"
          disabled={!job || shouldPoll(job.stages) || runningRequest}
          onClick={() => void processJob(job?.id ?? "", { force: true }).then(() => setAttempt((value) => value + 1)).catch((caught: unknown) => setRunError(caught instanceof ApiError ? caught : new ApiError("A full rerun could not start.", 0, null)))}
        >
          Force a full rerun
        </Button>
        {job ? <Link to={`/app/projects/${job.id}/sketch`} className={buttonClass("secondary")}>Open sketch</Link> : null}
        {runError ? <p className="text-sm text-alert-error-fg">{runError.message}</p> : null}
      </section>

      <section className="rounded-card border border-line px-4 py-6">
        <h2 className="font-display text-2xl">Sketch</h2>
        <p className="mt-2 text-sm text-ink-soft">A draft appears after the graph is built and is labeled DRAFT, not final, not verified. The final sketch appears after layout. Results, reports, and exports use the stored files.</p>
        {job ? (
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to={`/app/projects/${job.id}/results`} className={buttonClass("secondary")}>Open results</Link>
            <Link to={`/app/projects/${job.id}/reports`} className={buttonClass("ghost")}>Open reports</Link>
          </div>
        ) : null}
      </section>

      <Link to="/app" className={buttonClass("ghost")}>
        Back to projects
      </Link>
    </div>
  );
}
