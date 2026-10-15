import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { getDraft, listJobs, openDraft, postDraftOperation, redoDraft, saveDraft, undoDraft } from "../api/jobs";
import type { JobListItem } from "../types/intake";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { Spinner } from "../components/Spinner";
import { uploadsHidden } from "../lib/access";
import { useAppConfig } from "../lib/appConfig";

type LinkRow = { id: string; from: string; to: string; direction: string; status: string; crossing_mode: string };

export function EditPage() {
  const { id } = useParams();
  const [rows, setRows] = useState<LinkRow[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState("");
  const [projects, setProjects] = useState<JobListItem[] | null>(null);
  const demo = uploadsHidden(useAppConfig());

  async function reload(projectId: string) {
    const draft = await getDraft(projectId);
    const connections = Array.isArray(draft.connections) ? draft.connections as LinkRow[] : [];
    setRows(connections);
  }

  useEffect(() => {
    if (!id) {
      listJobs()
        .then(setProjects)
        .catch(() => setProjects([]))
        .finally(() => setLoading(false));
      return;
    }
    reload(id)
      .catch(async (caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 404) {
          try {
            await openDraft(id);
            await reload(id);
            return;
          } catch (opened) {
            if (opened instanceof ApiError && opened.body?.error_code === "MODIFY_DISABLED") {
              setRows([]);
              return;
            }
            throw opened;
          }
        }
        if (caught instanceof ApiError && caught.body?.error_code === "MODIFY_DISABLED") {
          setRows([]);
          return;
        }
        throw caught;
      })
      .then(() => setError(null))
      .catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("The working copy could not be loaded.", 0, null)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const projectId = id;
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key === "z") {
        event.preventDefault();
        void undoDraft(projectId).then(() => reload(projectId)).then(() => setMessage("Undid the last edit."));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id]);

  async function run(body: Record<string, unknown>, success: string) {
    if (!id) {
      return;
    }
    setError(null);
    try {
      await postDraftOperation(id, body);
      await reload(id);
      setMessage(success);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("The edit could not be applied.", 0, null));
    }
  }

  if (!id) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl">Edit</h1>
        <p className="text-sm text-ink-soft">Choose a project. Version 0 stays unchanged. Edits happen on a working copy.</p>
        {loading ? <Spinner label="Loading projects" /> : null}
        {projects && projects.length === 0 ? <EmptyState title="No projects yet" description="Upload a drawing and run extraction first." /> : null}
        <ul className="space-y-2">
          {(projects ?? []).map((project) => (
            <li key={project.id}><Link className="font-semibold underline" to={`/app/projects/${project.id}/edit`}>{project.name}</Link></li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Connection list</h1>
      <p className="text-sm text-ink-soft">Version 0 stays unchanged. These edits are on the working copy. Passed the defined automated checks. This is not an engineering or safety certification.</p>
      {demo ? <Alert tone="info" title="Modify is off in this public demo. Version 0 can be viewed. It is not edited." /> : null}
      {loading ? <Spinner label="Loading working copy" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      {message ? <Alert tone="info" title={message} /> : null}
      {!loading && rows.length === 0 ? <EmptyState title="No links in the working copy" description="Run extraction so version 0 has connections, then choose Modify." /> : null}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded-full border border-line px-3 py-1" disabled={demo || !selected} onClick={() => void run({ op: "delete", id: selected }, "The link was marked removed. It stays in the list.")}>Delete link</button>
        <button type="button" className="rounded-full border border-line px-3 py-1" disabled={demo || !selected} onClick={() => void run({ op: "reverse", id: selected }, "The direction was reversed.")}>Reverse</button>
        <button type="button" className="rounded-full border border-line px-3 py-1" disabled={demo} onClick={() =>         void undoDraft(id).then(() => reload(id)).then(() => setMessage("Undid the last edit.")).catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("Nothing to undo.", 0, null)))}>Undo</button>
        <button type="button" className="rounded-full border border-line px-3 py-1" disabled={demo} onClick={() => void redoDraft(id).then(() => reload(id)).then(() => setMessage("Redid the edit.")).catch((caught: unknown) => setError(caught instanceof ApiError ? caught : new ApiError("Nothing to redo.", 0, null)))}>Redo</button>
        <button type="button" className="rounded-full border border-ink px-3 py-1" disabled={demo} onClick={() => void saveDraft(id, "Saved from the connection list").then(() => setMessage("Saved a new version. Version 0 was not changed."))}>Save version</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr><th>ID</th><th>From</th><th>To</th><th>Direction</th><th>Status</th><th>Crossing</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className={selected === row.id ? "bg-paper-raised" : ""} onClick={() => setSelected(row.id)}>
                <td className="py-1 font-mono">{row.id}</td>
                <td>{row.from}</td>
                <td>{row.to}</td>
                <td>{row.direction}</td>
                <td>{row.status}</td>
                <td>{row.crossing_mode}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Link to={`/app/projects/${id}/versions`} className="text-sm underline">Version history</Link>
    </div>
  );
}
