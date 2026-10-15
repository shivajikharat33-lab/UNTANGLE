import { useEffect, useState } from "react";
import { getGraph, getGraphSummary } from "../api/jobs";
import { ApiError } from "../api/client";
import type { GraphSummary } from "../types/graph";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

const COUNTS: Array<[keyof GraphSummary, string]> = [
  ["nodes", "Nodes"],
  ["edges", "Edges"],
  ["junctions", "Junctions"],
  ["crossings", "Crossings kept apart"],
  ["orphans", "Orphan nodes"],
  ["dead_ends", "Dead ends"],
  ["unattached_instruments", "Unattached instruments"],
  ["disconnected_components", "Disconnected components"],
  ["duplicates", "Duplicate nodes"],
  ["unknown_direction", "Unknown direction"],
  ["needs_review", "Needs review"],
];

export function GraphSummaryPanel({ jobId, traceStatus }: { jobId: string; traceStatus: string }) {
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadError, setDownloadError] = useState<string>("");

  useEffect(() => {
    if (traceStatus === "pending" || traceStatus === "running") {
      setLoading(false);
      setSummary(null);
      setMissing(traceStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getGraphSummary(jobId, controller.signal)
      .then((next) => {
        setSummary(next);
        setMissing(false);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setSummary(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The graph summary could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, traceStatus]);

  async function download() {
    setDownloadError("");
    try {
      const graph = await getGraph(jobId);
      const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "graph.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setDownloadError(caught instanceof ApiError ? caught.message : "The graph file could not be downloaded.");
    }
  }

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Graph summary</h2>
      <p className="mb-3 text-sm text-ink-soft">Connections found by the rules. This is not a checked engineering drawing.</p>
      {loading || traceStatus === "running" ? <Spinner label="Loading graph summary" /> : null}
      {error ? <Alert tone="error" title={error.message}>{error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}</Alert> : null}
      {traceStatus === "failed" ? <Alert tone="error" title="The graph was not built">The stage list has the reason. Earlier results were kept.</Alert> : null}
      {missing && traceStatus !== "running" ? (
        <EmptyState title="The graph has not been built" description="Run extraction after the IO list is checked. Building the graph runs after line geometry." />
      ) : null}
      {summary ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {COUNTS.map(([key, label]) => (
              <p key={key} className="rounded-card border border-line px-3 py-2 text-sm">
                <span className="font-semibold">{label}</span> {summary[key]}
              </p>
            ))}
          </div>
          <Button variant="secondary" onClick={() => void download()}>Download graph JSON</Button>
          {downloadError ? <p className="text-sm text-alert-error-fg">{downloadError}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
