import { useEffect, useState } from "react";
import { getPatterns } from "../api/jobs";
import { ApiError } from "../api/client";
import type { Pattern } from "../types/graph";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

export function PatternsPanel({ jobId, patternStatus }: { jobId: string; patternStatus: string }) {
  const [patterns, setPatterns] = useState<Pattern[] | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (patternStatus === "pending" || patternStatus === "running") {
      setLoading(false);
      setPatterns(null);
      setMissing(patternStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getPatterns(jobId, controller.signal)
      .then((next) => {
        setPatterns(next);
        setMissing(false);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setPatterns(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("Patterns could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, patternStatus]);

  const groups = (patterns ?? []).filter((pattern) => pattern.type === "pump_group").length;
  const loops = (patterns ?? []).filter((pattern) => pattern.type === "control_loop").length;

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Patterns</h2>
      <p className="mb-3 text-sm text-ink-soft">Pump groups and control loops found by rules. A role is unknown when the drawing does not say it.</p>
      {loading || patternStatus === "running" ? <Spinner label="Loading patterns" /> : null}
      {error ? <Alert tone="error" title={error.message}>{error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}</Alert> : null}
      {patternStatus === "failed" ? <Alert tone="error" title="Patterns were not finished">The stage list has the reason. The graph was kept.</Alert> : null}
      {missing && patternStatus !== "running" ? (
        <EmptyState title="Patterns have not been run" description="They run after the graph is built." />
      ) : null}
      {patterns && patterns.length === 0 ? (
        <EmptyState title="No pump groups or control loops were found" description="The rules did not find a shared header pair or a loop. Nothing was added to fill the gap." />
      ) : null}
      {patterns && patterns.length > 0 ? (
        <div className="space-y-3">
          <p className="text-sm"><span className="font-semibold">Pump groups</span> {groups}. <span className="font-semibold">Control loops</span> {loops}.</p>
          {patterns.map((pattern) => (
            <details key={pattern.id} className="rounded-card border border-line px-3 py-2 text-sm" open>
              <summary className="cursor-pointer font-semibold">
                {pattern.type === "pump_group" ? "Pump group" : "Control loop"} · {pattern.role_certainty} · {pattern.needs_review ? "Needs review" : "No review flag"}
              </summary>
              <div className="mt-2 space-y-1 text-ink-soft">
                <p>Role: {pattern.role}. Members: {pattern.member_node_ids.join(", ") || "none"}.</p>
                {pattern.type === "pump_group" ? (
                  <p>Headers: {pattern.header_ids.join(", ") || "none"}. Valves: {pattern.valve_ids.join(", ") || "none"}. Check valves: {pattern.check_valve_ids.join(", ") || "none"}.</p>
                ) : (
                  <p>Sensor: {pattern.sensor_id || "missing"}. Controller: {pattern.controller_id || "missing"}. Final element: {pattern.final_element_id || "missing"}.</p>
                )}
                {pattern.missing_parts.length > 0 ? <p>Missing: {pattern.missing_parts.join(", ")}.</p> : null}
                {pattern.review_reasons.map((reason) => <p key={reason}>{reason}</p>)}
                {pattern.evidence.map((item) => <p key={item.description}>{item.description}</p>)}
              </div>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
