import { useEffect, useMemo, useState } from "react";
import { getCoverage, getLedger, getVerification } from "../api/jobs";
import { ApiError } from "../api/client";
import { VERIFICATION_DISCLAIMER, type CoverageMetric, type LedgerEntry, type VerificationStatus } from "../types/coverage";
import { Alert } from "./Alert";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

function percent(metric: CoverageMetric): string {
  if (metric.denominator === 0 || metric.percentage === null) {
    return "0 / 0";
  }
  return `${metric.numerator} / ${metric.denominator} (${Math.round(metric.percentage * 100)}%)`;
}

export function CoveragePanel({ jobId, reportStatus }: { jobId: string; reportStatus: string }) {
  const [metrics, setMetrics] = useState<CoverageMetric[] | null>(null);
  const [verification, setVerification] = useState<VerificationStatus | null>(null);
  const [rows, setRows] = useState<LedgerEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [itemType, setItemType] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [sortKey, setSortKey] = useState<keyof LedgerEntry>("item_id");
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (reportStatus !== "done") {
      setLoading(false);
      setMetrics(null);
      setVerification(null);
      setRows([]);
      setMissing(reportStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    Promise.all([
      getCoverage(jobId, controller.signal),
      getVerification(jobId, controller.signal),
      getLedger(jobId, itemType, reasonCode, offset, controller.signal),
    ])
      .then(([nextMetrics, nextVerification, page]) => {
        setMetrics(nextMetrics);
        setVerification(nextVerification);
        setRows(page.items);
        setTotal(page.total);
        setMissing(false);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setMetrics(null);
          setVerification(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("Coverage could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, reportStatus, itemType, reasonCode, offset]);

  const sorted = useMemo(() => {
    return [...rows].sort((left, right) => String(left[sortKey] ?? "").localeCompare(String(right[sortKey] ?? "")));
  }, [rows, sortKey]);

  const showVerified = reportStatus === "done" && verification?.state === "verified";

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Coverage</h2>
      {loading || reportStatus === "running" ? <Spinner label="Computing coverage" /> : null}
      {error ? <Alert tone="error" title={error.message}>{error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}</Alert> : null}
      {reportStatus === "failed" ? <Alert tone="error" title="Coverage was not computed">The stage list has the reason. Earlier results were kept.</Alert> : null}
      {missing && reportStatus !== "running" ? <EmptyState title="Coverage has not been computed" description="It runs after the checks." /> : null}
      {reportStatus === "done" && verification ? (
        <div className="mb-4 space-y-2">
          <p>
            {showVerified ? <Badge tone="high">Verified</Badge> : null}
            {verification.state === "needs_review" ? <Badge tone="medium">Needs review</Badge> : null}
            {verification.state === "not_verified" ? <Badge tone="low">Not verified</Badge> : null}
          </p>
          {verification.failing.length > 0 ? <p className="text-sm">Failing criteria: {verification.failing.join(", ")}</p> : null}
          <p className="text-sm text-ink-soft">{verification.disclaimer || VERIFICATION_DISCLAIMER}</p>
        </div>
      ) : null}
      {metrics ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {metrics.map((metric) => (
            <p key={metric.name} className="rounded-card border border-line px-3 py-2 text-sm">
              <span className="font-semibold">{metric.name.replaceAll("_", " ")}</span> {percent(metric)}
            </p>
          ))}
        </div>
      ) : null}
      {metrics ? (
        <div className="space-y-3">
          <h3 className="font-display text-lg">Hidden items</h3>
          <div className="flex flex-wrap gap-2">
            <input className="rounded-control border border-line px-2 py-1 text-sm" placeholder="Type" value={itemType} onChange={(event) => { setOffset(0); setItemType(event.target.value); }} />
            <input className="rounded-control border border-line px-2 py-1 text-sm" placeholder="Reason" value={reasonCode} onChange={(event) => { setOffset(0); setReasonCode(event.target.value); }} />
          </div>
          {sorted.length === 0 ? <EmptyState title="No hidden items in this filter" description="Every extracted item in this filter is represented, or the ledger page is empty." /> : null}
          {sorted.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-ink-soft">
                    {(["item_id", "item_type", "reason_code", "stage"] as const).map((key) => (
                      <th key={key} className="py-2 pr-3">
                        <button type="button" className="font-semibold" onClick={() => setSortKey(key)}>{key.replaceAll("_", " ")}</button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((entry) => (
                    <tr key={entry.item_id} className="border-b border-line align-top">
                      <td className="py-2 pr-3 font-mono">{entry.item_id}</td>
                      <td className="py-2 pr-3">{entry.item_type}</td>
                      <td className="py-2 pr-3">{entry.reason_code}<p className="text-ink-soft">{entry.reason_text}</p></td>
                      <td className="py-2 pr-3">{entry.stage}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="flex items-center gap-2 text-sm">
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset((current) => Math.max(0, current - 25))}>Previous</Button>
            <span>{total === 0 ? "0" : `${offset + 1}–${Math.min(offset + rows.length, total)}`} of {total}</span>
            <Button variant="secondary" disabled={offset + 25 >= total} onClick={() => setOffset((current) => current + 25)}>Next</Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
