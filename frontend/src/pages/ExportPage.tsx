import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { apiBaseUrl, ApiError } from "../api/client";
import { getJob, listJobs } from "../api/jobs";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import type { JobListItem } from "../types/intake";

const FORMATS = ["svg", "png", "pdf", "json", "excel"] as const;

export function ExportPage() {
  const { id } = useParams();
  const [projects, setProjects] = useState<JobListItem[] | null>(null);
  const [draft, setDraft] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [sizes, setSizes] = useState<Record<string, number>>({});
  const [finalReady, setFinalReady] = useState(false);

  useEffect(() => {
    if (id) {
      return;
    }
    listJobs().then(setProjects).catch(() => setProjects([]));
  }, [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    getJob(id)
      .then((job) => setFinalReady(job.stages.some((stage) => stage.name === "Report" && stage.status === "done")))
      .catch(() => setFinalReady(false));
  }, [id]);

  async function download(fmt: string) {
    if (!id) {
      return;
    }
    setBusy(fmt);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl()}/api/jobs/${encodeURIComponent(id)}/exports/${fmt}?draft=${draft ? "true" : "false"}`);
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { message?: string } | null;
        throw new ApiError(body?.message ?? "The export could not be downloaded.", response.status, null);
      }
      const blob = await response.blob();
      setSizes((current) => ({ ...current, [fmt]: blob.size }));
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const header = response.headers.get("Content-Disposition") ?? "";
      const match = header.match(/filename="([^"]+)"/);
      link.href = url;
      link.download = match?.[1] ?? `${id}.${fmt}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The export could not be downloaded.");
    } finally {
      setBusy("");
    }
  }

  if (!id) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl">Export</h1>
        {(projects ?? []).length === 0 ? <EmptyState title="No projects yet" description="Upload a drawing before exporting." /> : null}
        <ul>{(projects ?? []).map((project) => <li key={project.id}><Link className="underline" to={`/app/projects/${project.id}/export`}>{project.name}</Link></li>)}</ul>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Export</h1>
      <p className="text-sm">Passed the defined automated checks. This is not an engineering or safety certification.</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft} onChange={(event) => setDraft(event.target.checked)} />
        Download the draft. A draft file says draft and does not say Verified.
      </label>
      {error ? <Alert tone="error" title={error} /> : null}
      <div className="flex flex-wrap gap-2">
        {!draft && !finalReady ? <p className="text-sm">Final downloads stay off until coverage has finished. You can still download a draft if one was saved.</p> : null}
        {FORMATS.map((fmt) => (
          <Button key={fmt} variant="secondary" disabled={busy === fmt || (!draft && !finalReady)} title={!draft && !finalReady ? "Coverage has not finished" : undefined} onClick={() => void download(fmt)}>
            {busy === fmt ? `Preparing ${fmt}` : `Download ${fmt}`}{sizes[fmt] ? ` (${sizes[fmt]} bytes)` : ""}
          </Button>
        ))}
      </div>
    </div>
  );
}
