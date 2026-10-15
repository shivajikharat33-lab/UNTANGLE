import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { compareVersions, listVersions } from "../api/jobs";
import { apiSend, ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { HistoryCompare } from "../components/HistoryCompare";
import { Spinner } from "../components/Spinner";

type VersionRow = { id: string; number: number; status: string; note?: string; created_by?: string; created_at?: string };

export function HistoryPage() {
  const { id } = useParams();
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [left, setLeft] = useState(0);
  const [right, setRight] = useState(1);
  const [changes, setChanges] = useState<Array<{ from: string; to: string; fields: string[] }>>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      return;
    }
    listVersions(id)
      .then((rows) => {
        setVersions(rows as VersionRow[]);
        setError(null);
      })
      .catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("Versions could not be loaded.", 0, null)))
      .finally(() => setLoading(false));
  }, [id]);

  if (!id) {
    return <EmptyState title="No project selected" description="Open a project before comparing versions." />;
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Version history</h1>
      <p className="text-sm text-ink-soft">Restoring a version creates a new version. Earlier versions are not rewritten.</p>
      {loading ? <Spinner label="Loading versions" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      {message ? <Alert tone="info" title={message} /> : null}
      {!loading && versions.length === 0 ? <EmptyState title="No versions yet" description="Finish extraction so version 0 can be stored." /> : null}
      <ul className="space-y-2 text-sm">
        {versions.map((version) => (
          <li key={version.id} className="rounded-card border border-line px-3 py-2">
            Version {version.number} · {version.status} · {version.created_by || "tool"} · {version.note || "no note"}
            <button
              type="button"
              className="ml-3 underline"
              onClick={() => {
                void apiSend(`/api/jobs/${encodeURIComponent(id)}/versions/${version.number}/restore`, "POST", {})
                  .then(() => setMessage(`Restored version ${version.number} as a new version.`))
                  .catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("Restore failed.", 0, null)));
              }}
            >
              Restore as new
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2 text-sm">
        <label>Left <input className="ml-1 w-16 border border-line px-2" value={left} onChange={(event) => setLeft(Number(event.target.value))} /></label>
        <label>Right <input className="ml-1 w-16 border border-line px-2" value={right} onChange={(event) => setRight(Number(event.target.value))} /></label>
        <button type="button" className="rounded-full border border-line px-3" onClick={() => void compareVersions(id, left, right).then((body) => setChanges((body.changed as Array<{ from: string; to: string; fields: string[] }>) ?? [])).catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("Compare failed.", 0, null)))}>Compare</button>
      </div>
      <HistoryCompare changes={changes} />
      <Link to={`/app/projects/${id}/results`} className="text-sm underline">Back to results</Link>
    </div>
  );
}
