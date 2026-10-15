import { useEffect, useState } from "react";
import { Link } from "react-router";
import { listJobs } from "../api/jobs";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { Badge } from "../components/Badge";
import { buttonClass } from "../lib/buttonClass";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";
import { formatWhen } from "../lib/format";
import { uploadsHidden } from "../lib/access";
import { useAppConfig } from "../lib/appConfig";
import type { JobListItem, PdfVerdict } from "../types/intake";

const verdictTone: Record<PdfVerdict, "neutral" | "medium" | "low"> = {
  VECTOR: "neutral",
  MIXED: "medium",
  SCANNED: "low",
};

export function DashboardPage() {
  const [jobs, setJobs] = useState<JobListItem[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const demo = uploadsHidden(useAppConfig());

  useEffect(() => {
    const controller = new AbortController();
    listJobs(controller.signal)
      .then((items) => {
        setJobs(items);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The project list could not be loaded.", 0, null));
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader
          eyebrow="Projects"
          title="Dashboard"
          description="Each project is one P&ID and one IO workbook. Opening a project shows the intake that was actually read."
        />
        {demo ? null : (
          <Link to="/app/new" className={buttonClass("primary")}>
            New project
          </Link>
        )}
      </div>

      {error ? (
        <Alert tone="error" title={error.message}>
          {error.status === 0 ? (
            <p>
              Start the API on port 8000, then open the site at http://127.0.0.1:5173 (not a closed tab). Click Check again in the header when it is up.
            </p>
          ) : null}
          {error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}
        </Alert>
      ) : null}

      {jobs === null && !error ? <Spinner label="Loading projects" /> : null}

      {jobs && jobs.length === 0 ? (
        <EmptyState
          title={demo ? "The synthetic project is not loaded" : "No projects yet"}
          description={
            demo
              ? "This public demo should already contain one synthetic project. Refresh the page. Uploads stay off."
              : "Upload a P&ID PDF and an IO workbook to create the first project."
          }
          action={
            demo ? undefined : (
              <Link to="/app/new" className={buttonClass("primary")}>
                New project
              </Link>
            )
          }
        />
      ) : null}

      {jobs && jobs.length > 0 ? (
        <ul className="grid gap-3">
          {jobs.map((job) => (
            <li key={job.id}>
              <Link
                to={`/app/projects/${job.id}/processing`}
                className="block rounded-card border border-line bg-paper-raised p-4 shadow-card hover:border-ink"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-display text-2xl">{job.name.trim() || "Untitled project"}</h2>
                  <Badge tone={verdictTone[job.pdf_verdict]}>{job.pdf_verdict}</Badge>
                </div>
                <p className="mt-2 text-sm text-ink-soft">
                  {formatWhen(job.created_at)} · {job.status} · {job.page_count} {job.page_count === 1 ? "page" : "pages"}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
