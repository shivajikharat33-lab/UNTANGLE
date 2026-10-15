import { useEffect, useState } from "react";
import { getTagReport } from "../api/jobs";
import { ApiError } from "../api/client";
import type { TagMatchStatus, TagReport } from "../types/reports";
import { Alert } from "./Alert";
import { Badge, ConfidenceBadge } from "./Badge";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

const filters: Array<{ id: "all" | TagMatchStatus; label: string }> = [
  { id: "all", label: "All" },
  { id: "found", label: "Found" },
  { id: "fuzzy", label: "Fuzzy" },
  { id: "not_found", label: "Not found" },
  { id: "extra", label: "Extra" },
];

export function TagReportPanel({ jobId, matchStatus }: { jobId: string; matchStatus: string }) {
  const [report, setReport] = useState<TagReport | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<(typeof filters)[number]["id"]>("all");

  useEffect(() => {
    if (matchStatus === "pending" || matchStatus === "running") {
      setLoading(false);
      setReport(null);
      setMissing(matchStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getTagReport(jobId, controller.signal)
      .then((next) => {
        setReport(next);
        setMissing(false);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setReport(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The tag check could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, matchStatus]);

  const rows = (report?.rows ?? []).filter((row) => (filter === "all" ? true : row.status === filter));

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Tag Check Report</h2>
      {loading || matchStatus === "running" ? <Spinner label="Loading the tag check" /> : null}
      {error ? (
        <Alert tone="error" title={error.message}>
          {error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}
        </Alert>
      ) : null}
      {matchStatus === "failed" ? (
        <Alert tone="error" title="Tag check failed">
          The stage list has the reason. Earlier extraction was kept.
        </Alert>
      ) : null}
      {missing && matchStatus !== "running" ? (
        <EmptyState
          title="Tag check has not been run"
          description="Run extraction after the IO list is checked. This report is empty until MatchTags finishes."
        />
      ) : null}
      {report ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-5">
            <p className="rounded-card border border-line px-3 py-2 text-sm"><span className="font-semibold">IO tags</span> {report.summary.total}</p>
            <p className="rounded-card border border-line px-3 py-2 text-sm"><span className="font-semibold">Found</span> {report.summary.found}</p>
            <p className="rounded-card border border-line px-3 py-2 text-sm"><span className="font-semibold">Fuzzy</span> {report.summary.fuzzy}</p>
            <p className="rounded-card border border-line px-3 py-2 text-sm"><span className="font-semibold">Not found</span> {report.summary.not_found}</p>
            <p className="rounded-card border border-line px-3 py-2 text-sm"><span className="font-semibold">Extra</span> {report.summary.extra}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {filters.map((item) => (
              <Button key={item.id} variant={filter === item.id ? "primary" : "secondary"} onClick={() => setFilter(item.id)}>
                {item.label}
              </Button>
            ))}
          </div>
          {rows.length === 0 ? (
            <EmptyState title="No rows in this filter" description="There are no tag rows for the current filter." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-ink-soft">
                    <th className="py-2 pr-3">Tag</th>
                    <th className="py-2 pr-3">Signal</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Confidence</th>
                    <th className="py-2 pr-3">Page</th>
                    <th className="py-2">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.status}-${row.tag}-${row.location?.x ?? "none"}-${row.suggestion ?? ""}`} className="border-b border-line align-top">
                      <td className="py-2 pr-3 font-mono">{row.tag}</td>
                      <td className="py-2 pr-3">{row.signal || "—"}</td>
                      <td className="py-2 pr-3"><Badge tone={row.status === "found" ? "high" : row.status === "not_found" ? "low" : "medium"}>{row.status}</Badge></td>
                      <td className="py-2 pr-3"><ConfidenceBadge level={row.confidence.level} /></td>
                      <td className="py-2 pr-3">{row.location ? row.location.page : "—"}</td>
                      <td className="py-2">
                        <p>{row.confidence.reason}</p>
                        {row.suggestion ? <p className="text-ink-soft">{row.suggestion}</p> : null}
                        {row.suffix_hint ? <p className="text-ink-soft">Suffix hint: {row.suffix_hint}</p> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
