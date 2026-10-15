import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { getCoverage, getFindings, getLedger, listJobs } from "../api/jobs";
import { apiFetch } from "../api/client";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { Spinner } from "../components/Spinner";
import type { CoverageMetric, LedgerEntry } from "../types/coverage";
import type { JobListItem } from "../types/intake";
import type { Finding } from "../types/rules";

type Row = Record<string, unknown>;

export function ReportsPage() {
  const { id } = useParams();
  const [projects, setProjects] = useState<JobListItem[] | null>(null);
  const [tab, setTab] = useState<"tags" | "connections" | "coverage" | "ledger" | "findings">("tags");
  const [rows, setRows] = useState<Row[]>([]);
  const [coverage, setCoverage] = useState<CoverageMetric[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      return;
    }
    const controller = new AbortController();
    listJobs(controller.signal).then(setProjects).catch((caught: unknown) => {
      if (!(caught instanceof DOMException)) {
        setError(caught instanceof ApiError ? caught : new ApiError("Projects could not be loaded.", 0, null));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const path = tab === "tags" ? "reports/tags" : tab === "connections" ? "reports/connections" : "";
    const tasks: Promise<void>[] = [];
    if (path) {
      tasks.push(apiFetch(`/api/jobs/${encodeURIComponent(id)}/${path}?q=${encodeURIComponent(query)}`, controller.signal).then(async (response) => {
        if (!response.ok) {
          throw new ApiError("The report could not be loaded.", response.status, null);
        }
        const body = await response.json() as { items: Row[] };
        setRows(body.items);
      }));
    }
    tasks.push(getCoverage(id, controller.signal).then(setCoverage).catch(() => setCoverage([])));
    tasks.push(getLedger(id, "", "", 0, controller.signal).then((page) => setLedger(page.items)).catch(() => setLedger([])));
    tasks.push(getFindings(id, controller.signal).then(setFindings).catch(() => setFindings(null)));
    Promise.all(tasks).catch((caught: unknown) => {
      if (!(caught instanceof DOMException)) {
        setError(caught instanceof ApiError ? caught : new ApiError("The report could not be loaded.", 0, null));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [id, tab, query]);

  if (!id) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl">Reports</h1>
        {loading ? <Spinner label="Loading projects" /> : null}
        <ul>{(projects ?? []).map((project) => <li key={project.id}><Link className="underline" to={`/app/projects/${project.id}/reports`}>{project.name}</Link></li>)}</ul>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Reports</h1>
      {loading ? <Spinner label="Loading report" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      <div className="flex flex-wrap gap-2">
        {(["tags", "connections", "coverage", "ledger", "findings"] as const).map((value) => (
          <button key={value} type="button" className="rounded-full border border-line px-3 py-1 text-xs font-semibold" onClick={() => setTab(value)}>{value}</button>
        ))}
      </div>
      <input aria-label="Search report" className="rounded-control border border-line px-3 py-2 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" />
      {tab === "findings" && findings && findings.length === 0 ? <EmptyState title="No issues found by the configured checks" description="This is not a verified drawing." /> : null}
      {tab === "coverage" && coverage.length === 0 && !loading ? <EmptyState title="Coverage has not been computed" description="Run extraction and wait until the coverage stage is done." /> : null}
      {tab === "coverage" && coverage.length > 0 ? (
        <ul className="text-sm">
          {coverage.map((metric) => (
            <li key={metric.name}>{metric.name}: {metric.numerator} / {metric.denominator}{metric.percentage === null ? "" : ` (${Math.round(metric.percentage * 1000) / 10}%)`}. Missing: {metric.missing_ids.join(", ") || "none"}.</li>
          ))}
        </ul>
      ) : null}
      {tab === "ledger" ? (
        <ul className="text-sm">
          {ledger.map((entry) => <li key={entry.item_id}><Link to={`/app/projects/${id}/results?select=${encodeURIComponent(entry.item_id)}`}>{entry.item_id}</Link> {entry.item_type} {entry.reason_code} {entry.stage}</li>)}
        </ul>
      ) : null}
      {tab === "tags" || tab === "connections" || tab === "findings" ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <tbody>
              {(tab === "findings" ? (findings ?? []).map((item) => ({ id: item.id, severity: item.severity, message: item.message })) : rows).map((row) => {
                const record = row as Record<string, unknown>;
                const label = String(record.tag ?? record.from ?? record.id ?? "");
                return (
                  <tr key={String(record.id ?? record.tag ?? record.message)} className="border-b border-line">
                    <td className="py-2"><Link to={`/app/projects/${id}/results?select=${encodeURIComponent(label)}`}>{label}</Link></td>
                    <td>{String(record.status ?? record.direction ?? record.severity ?? "")}</td>
                    <td>{String(record.to ?? record.message ?? record.score ?? "")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
