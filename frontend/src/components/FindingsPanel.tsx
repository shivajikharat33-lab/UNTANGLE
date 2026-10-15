import { useEffect, useMemo, useState } from "react";
import { getFindings, getGraph } from "../api/jobs";
import { ApiError } from "../api/client";
import type { DiagramGraph } from "../types/graph";
import type { Finding } from "../types/rules";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

export function FindingsPanel({ jobId, checkStatus }: { jobId: string; checkStatus: string }) {
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [graph, setGraph] = useState<DiagramGraph | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [selectedItem, setSelectedItem] = useState<string>("");

  useEffect(() => {
    if (checkStatus === "pending" || checkStatus === "running") {
      setLoading(false);
      setFindings(null);
      setMissing(checkStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    Promise.all([getFindings(jobId, controller.signal), getGraph(jobId, controller.signal).catch(() => null)])
      .then(([nextFindings, nextGraph]) => {
        setFindings(nextFindings);
        setGraph(nextGraph);
        setMissing(false);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setFindings(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("Findings could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, checkStatus]);

  const categories = useMemo(() => Array.from(new Set((findings ?? []).map((item) => item.category))), [findings]);
  const shown = (findings ?? []).filter((item) => (severity === "all" || item.severity === severity) && (category === "all" || item.category === category));
  const counts = {
    error: (findings ?? []).filter((item) => item.severity === "error").length,
    warning: (findings ?? []).filter((item) => item.severity === "warning").length,
    info: (findings ?? []).filter((item) => item.severity === "info").length,
  };
  const detail = graph?.nodes.find((node) => node.id === selectedItem) ?? graph?.edges.find((edge) => edge.id === selectedItem) ?? null;

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Findings</h2>
      <p className="mb-3 text-sm text-ink-soft">Configured checks only. A clear list is not a verified drawing.</p>
      {loading || checkStatus === "running" ? <Spinner label="Loading findings" /> : null}
      {error ? <Alert tone="error" title={error.message}>{error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}</Alert> : null}
      {checkStatus === "failed" ? <Alert tone="error" title="Checks were not finished">The stage list has the reason. Earlier results were kept.</Alert> : null}
      {missing && checkStatus !== "running" ? <EmptyState title="Checks have not been run" description="They run after patterns." /> : null}
      {findings && findings.length === 0 ? (
        <EmptyState title="No issues found by the configured checks" description="This is not a verified drawing. The checks that are configured did not return a finding." />
      ) : null}
      {findings && findings.length > 0 ? (
        <div className="space-y-3">
          <p className="text-sm"><span className="font-semibold">Errors</span> {counts.error}. <span className="font-semibold">Warnings</span> {counts.warning}. <span className="font-semibold">Info</span> {counts.info}.</p>
          <div className="flex flex-wrap gap-2">
            {["all", "error", "warning", "info"].map((value) => (
              <button key={value} type="button" className={`rounded-full border px-3 py-1 text-xs font-semibold ${severity === value ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink"}`} onClick={() => setSeverity(value)}>{value}</button>
            ))}
            <button type="button" className={`rounded-full border px-3 py-1 text-xs font-semibold ${category === "all" ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink"}`} onClick={() => setCategory("all")}>all categories</button>
            {categories.map((value) => (
              <button key={value} type="button" className={`rounded-full border px-3 py-1 text-xs font-semibold ${category === value ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink"}`} onClick={() => setCategory(value)}>{value}</button>
            ))}
          </div>
          {shown.length === 0 ? <EmptyState title="No findings match these filters" description="The other severities are still in the summary above." /> : null}
          {shown.map((finding) => (
            <details key={finding.id} className="rounded-card border border-line px-3 py-2 text-sm">
              <summary className="cursor-pointer font-semibold">{finding.severity} · {finding.rule_id} · {finding.title}</summary>
              <div className="mt-2 space-y-1">
                <p>{finding.message}</p>
                <p>{finding.review_action}</p>
                <p className="flex flex-wrap gap-2">
                  {finding.affected_ids.map((itemId) => (
                    <button key={itemId} type="button" className="font-mono text-xs underline" onClick={() => setSelectedItem(itemId)}>{itemId}</button>
                  ))}
                </p>
                {finding.evidence.map((item) => <p key={item.description} className="text-ink-soft">{item.description}</p>)}
              </div>
            </details>
          ))}
          {selectedItem ? (
            <div className="rounded-card border border-line px-3 py-2 text-sm">
              <p className="font-semibold">Item {selectedItem}</p>
              {detail && "tag" in detail ? <p>Type {detail.type}. Tag {detail.tag || "none"}. {detail.reason}</p> : null}
              {detail && "direction" in detail ? <p>Direction {detail.direction}. {detail.confidence.reason}</p> : null}
              {!detail ? <p className="text-ink-soft">This id is not a graph node or edge. It may be an IO tag or an OCR word.</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
