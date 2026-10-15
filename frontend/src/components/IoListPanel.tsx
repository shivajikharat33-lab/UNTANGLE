import { useEffect, useState } from "react";
import { getIoList, validateIoList } from "../api/jobs";
import { ApiError } from "../api/client";
import type { IoListResult } from "../types/ioList";
import { Alert } from "./Alert";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

export function IoListPanel({ jobId }: { jobId: string }) {
  const [result, setResult] = useState<IoListResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [sheet, setSheet] = useState("");
  const [tagColumn, setTagColumn] = useState("");
  const [signalColumn, setSignalColumn] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getIoList(jobId, controller.signal)
      .then((next) => {
        setResult(next);
        setMissing(false);
        setError(null);
        setSheet(next.sheet ?? next.sheets[0] ?? "");
        setTagColumn(next.tag_column ?? "");
        setSignalColumn(next.signal_column ?? "");
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setMissing(true);
          setResult(null);
          setError(null);
          return;
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The IO list could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId]);

  async function run(body: { sheet?: string; tag_column?: string; signal_column?: string } = {}) {
    setBusy(true);
    setError(null);
    try {
      const next = await validateIoList(jobId, body);
      setResult(next);
      setMissing(false);
      setSheet(next.sheet ?? "");
      setTagColumn(next.tag_column ?? "");
      setSignalColumn(next.signal_column ?? "");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("The IO list could not be checked.", 0, null));
    } finally {
      setBusy(false);
    }
  }

  const rows = (result?.rows ?? []).filter((row) => (issuesOnly ? row.issues.length > 0 : true));

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">IO list</h2>
      {loading ? <Spinner label="Loading the IO list check" /> : null}
      {error ? (
        <Alert tone="error" title={error.message}>
          {error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}
        </Alert>
      ) : null}
      {missing && !loading ? (
        <EmptyState
          title="IO list not checked"
          description="The workbook is stored. Checking it reads the tag and signal columns. Nothing has been checked yet."
          action={
            <Button onClick={() => void run({})} disabled={busy}>
              Check IO list
            </Button>
          }
        />
      ) : null}
      {result?.status === "needs_columns" ? (
        <div className="space-y-3">
          <Alert tone="warning" title="Choose the columns">
            {result.message}
          </Alert>
          <form
            className="grid gap-3 sm:grid-cols-3"
            onSubmit={(event) => {
              event.preventDefault();
              void run({ sheet, tag_column: tagColumn, signal_column: signalColumn });
            }}
          >
            <label className="text-sm font-semibold">
              Sheet
              <select className="mt-1 w-full rounded-control border border-line bg-paper px-2 py-2" value={sheet} onChange={(event) => setSheet(event.target.value)}>
                {result.sheets.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm font-semibold">
              Tag column
              <select className="mt-1 w-full rounded-control border border-line bg-paper px-2 py-2" value={tagColumn} onChange={(event) => setTagColumn(event.target.value)}>
                <option value="">Choose</option>
                {result.columns.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm font-semibold">
              Signal column
              <select className="mt-1 w-full rounded-control border border-line bg-paper px-2 py-2" value={signalColumn} onChange={(event) => setSignalColumn(event.target.value)}>
                <option value="">Choose</option>
                {result.columns.map((name) => (
                  <option key={`signal-${name}`} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={busy || !tagColumn || !signalColumn}>
              Use these columns
            </Button>
          </form>
        </div>
      ) : null}
      {result?.status === "validated" ? (
        <div className="space-y-3">
          <Alert tone="success" title="IO list checked">
            {result.summary.row_count} rows. {result.summary.ok_count} with no issues. {result.summary.error_count} with errors. {result.summary.warning_count} with warnings only. Flagged rows were kept.
          </Alert>
          <div className="flex gap-2">
            <Button variant={issuesOnly ? "secondary" : "primary"} onClick={() => setIssuesOnly(false)}>
              All rows
            </Button>
            <Button variant={issuesOnly ? "primary" : "secondary"} onClick={() => setIssuesOnly(true)}>
              Issues only
            </Button>
          </div>
          {rows.length === 0 ? (
            <EmptyState title="No rows in this filter" description="There are no rows to show for the current filter." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-ink-soft">
                    <th className="py-2 pr-3">Row</th>
                    <th className="py-2 pr-3">Original</th>
                    <th className="py-2 pr-3">Tag</th>
                    <th className="py-2 pr-3">Signal</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2">Issues</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.row} className="border-b border-line align-top">
                      <td className="py-2 pr-3">{row.row}</td>
                      <td className="py-2 pr-3">{row.original_tag || "—"}</td>
                      <td className="py-2 pr-3 font-mono">{row.tag || "—"}</td>
                      <td className="py-2 pr-3">{row.signal || "—"}</td>
                      <td className="py-2 pr-3">{row.instrument_type || "—"}</td>
                      <td className="py-2">
                        {row.issues.length === 0 ? (
                          <Badge tone="high">None</Badge>
                        ) : (
                          <ul className="space-y-1">
                            {row.issues.map((issue) => (
                              <li key={`${issue.row}-${issue.message}`}>
                                <Badge tone={issue.severity === "error" ? "low" : "medium"}>{issue.severity}</Badge>
                                <span className="ml-2">{issue.message}</span>
                              </li>
                            ))}
                          </ul>
                        )}
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
