import { useEffect, useState } from "react";
import { apiFetch, ApiError, readErrorBody } from "../api/client";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

interface SimplifiedSummary {
  nodes: number;
  edges: number;
  ledger: number;
  connectivity_ok: boolean;
  failed_check: boolean;
}

function isSummary(value: unknown): value is { nodes: unknown[]; edges: unknown[]; ledger: unknown[]; connectivity_ok: boolean; failed_check: boolean } {
  return typeof value === "object" && value !== null && Array.isArray((value as { nodes: unknown }).nodes) && Array.isArray((value as { edges: unknown }).edges);
}

export function SimplifiedPanel({ jobId, simplifyStatus }: { jobId: string; simplifyStatus: string }) {
  const [summary, setSummary] = useState<SimplifiedSummary | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (simplifyStatus !== "done") {
      setLoading(false);
      setSummary(null);
      setMissing(simplifyStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    apiFetch(`/api/jobs/${encodeURIComponent(jobId)}/simplified`, controller.signal)
      .then(async (response) => {
        if (!response.ok) {
          const body = await readErrorBody(response);
          throw new ApiError(body?.message ?? "The simplified graph could not be loaded.", response.status, body);
        }
        return response.json() as Promise<unknown>;
      })
      .then((payload) => {
        if (!isSummary(payload)) {
          throw new ApiError("The simplified graph could not be read.", 0, null);
        }
        setSummary({
          nodes: payload.nodes.length,
          edges: payload.edges.length,
          ledger: payload.ledger.length,
          connectivity_ok: payload.connectivity_ok,
          failed_check: payload.failed_check,
        });
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
        setError(caught instanceof ApiError ? caught : new ApiError("The simplified graph could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, simplifyStatus]);

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Simplified graph</h2>
      <p className="mb-3 text-sm text-ink-soft">A separate copy. The original graph file is not changed.</p>
      {loading || simplifyStatus === "running" ? <Spinner label="Simplifying graph" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      {simplifyStatus === "failed" ? <Alert tone="error" title="The simplified graph was not built">The original graph was kept.</Alert> : null}
      {missing && simplifyStatus !== "running" ? <EmptyState title="The simplified graph has not been built" description="It runs after coverage." /> : null}
      {summary ? (
        <div className="space-y-2 text-sm">
          <p>Nodes {summary.nodes}. Edges {summary.edges}. Ledger rows {summary.ledger}.</p>
          {summary.failed_check ? <Alert tone="warning" title="Connectivity check failed">This copy is not presented as verified.</Alert> : <p>Connectivity check passed. This is not an engineering certification.</p>}
        </div>
      ) : null}
    </section>
  );
}
