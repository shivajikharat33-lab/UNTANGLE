import { useEffect, useState } from "react";
import { getDetections, getGeometry, pagePreviewUrl } from "../api/jobs";
import type { GeometryResult } from "../types/geometry";
import { ApiError } from "../api/client";
import type { DetectionItem, DetectionResult } from "../types/detections";
import { Alert } from "./Alert";
import { ConfidenceBadge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

export function DetectionsPanel({ jobId, detectStatus }: { jobId: string; detectStatus: string }) {
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [geometry, setGeometry] = useState<GeometryResult | null>(null);
  const [layers, setLayers] = useState({ process: true, signal: true, junction: true, crossing: true, ambiguous: true, free: true });
  const [meetingId, setMeetingId] = useState<string | null>(null);

  useEffect(() => {
    if (detectStatus === "pending" || detectStatus === "running") {
      setLoading(false);
      setResult(null);
      setMissing(detectStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getDetections(jobId, controller.signal)
      .then((next) => {
        setResult(next);
        setMissing(false);
        setError(null);
        setPageNumber(next.pages[0]?.page ?? 1);
        return getGeometry(jobId, controller.signal).catch((caught: unknown) => {
          if (caught instanceof ApiError && caught.status === 404) {
            return null;
          }
          throw caught;
        });
      })
      .then((nextGeometry) => {
        if (nextGeometry) {
          setGeometry(nextGeometry);
        }
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
        setError(caught instanceof ApiError ? caught : new ApiError("Detections could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, detectStatus]);

  const page = result?.pages.find((item) => item.page === pageNumber) ?? result?.pages[0];
  const pageItems = (result?.items ?? []).filter((item) => item.page === (page?.page ?? pageNumber));
  const chosen = pageItems.find((item) => item.id === selected) ?? null;
  const pageLines = (geometry?.lines ?? []).filter((line) => line.page === (page?.page ?? pageNumber));
  const pageMeetings = (geometry?.meetings ?? []).filter((meeting) => meeting.page === (page?.page ?? pageNumber));
  const pageFree = (geometry?.free_endpoints ?? []).filter((endpoint) => endpoint.page === (page?.page ?? pageNumber));
  const chosenMeeting = pageMeetings.find((meeting) => meeting.id === meetingId) ?? null;

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Detections</h2>
      <p className="mb-3 text-sm text-ink-soft">Extracted items, not the final sketch.</p>
      {loading || detectStatus === "running" ? <Spinner label="Loading detections" /> : null}
      {error ? <Alert tone="error" title={error.message}>{error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}</Alert> : null}
      {detectStatus === "failed" ? <Alert tone="error" title="Detection failed">The stage list has the reason. Earlier results were kept.</Alert> : null}
      {missing && detectStatus !== "running" ? (
        <EmptyState title="Detections have not been run" description="Run extraction after the IO list is checked. Detect runs after the tag check." />
      ) : null}
      {result && page ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {(["instrument", "equipment", "valve", "arrow", "unclassified", "linked_to_io"] as const).map((key) => (
              <p key={key} className="rounded-card border border-line px-3 py-2 text-sm">
                <span className="font-semibold">{key.replaceAll("_", " ")}</span> {result.census[key]}
              </p>
            ))}
          </div>
          <p className="text-sm text-ink-soft">Extracted geometry, not verified connections.</p>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["process", "Process lines"],
                ["signal", "Signal lines"],
                ["junction", "Junctions"],
                ["crossing", "Crossings"],
                ["ambiguous", "Ambiguous"],
                ["free", "Free endpoints"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${layers[key] ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink"}`}
                onClick={() => setLayers((current) => ({ ...current, [key]: !current[key] }))}
              >
                {label}
              </button>
            ))}
          </div>
          {geometry ? (
            <dl className="grid gap-3 text-sm sm:grid-cols-4">
              <div><dt className="font-semibold">Line length</dt><dd>{geometry.coverage.total_length.toFixed(1)}</dd></div>
              <div><dt className="font-semibold">Explained</dt><dd>{geometry.coverage.explained_length.toFixed(1)}</dd></div>
              <div><dt className="font-semibold">Unexplained</dt><dd>{geometry.coverage.unexplained_length.toFixed(1)}</dd></div>
              <div><dt className="font-semibold">Ambiguous</dt><dd>{geometry.coverage.ambiguous}</dd></div>
            </dl>
          ) : (
            <p className="text-sm text-ink-soft">Line geometry has not been saved for this project.</p>
          )}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <div>
              <div className="relative mx-auto w-full max-w-3xl" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
                <img src={pagePreviewUrl(jobId, page.page)} alt={`Page ${page.page} of the uploaded drawing`} className="absolute inset-0 h-full w-full object-fill" />
                <svg viewBox={`0 0 ${page.width} ${page.height}`} className="absolute inset-0 h-full w-full">
                  {pageLines.map((line) =>
                    layers[line.line_type === "signal" ? "signal" : line.line_type === "process" ? "process" : "process"] ? (
                      <polyline
                        key={line.id}
                        points={line.points.map((point) => point.join(",")).join(" ")}
                        fill="none"
                        stroke={line.line_type === "signal" ? "#1d4ed8" : line.line_type === "other" ? "#4b5563" : "#0f766e"}
                        strokeWidth={line.line_type === "signal" ? 1 : 2}
                        strokeDasharray={line.line_type === "signal" ? "4 3" : undefined}
                      />
                    ) : null,
                  )}
                  {pageItems.map((item) => (
                    <rect
                      key={item.id}
                      x={item.bbox[0]}
                      y={item.bbox[1]}
                      width={item.bbox[2]}
                      height={item.bbox[3]}
                      fill={item.id === selected ? "rgba(180, 83, 9, 0.25)" : "transparent"}
                      stroke={item.kind === "unclassified" ? "#6b7280" : "#9a3412"}
                      strokeWidth={1.2}
                      className="cursor-pointer"
                      onClick={() => setSelected(item.id)}
                    />
                  ))}
                  {pageMeetings.map((meeting) => {
                    const key = meeting.decision === "junction" ? "junction" : meeting.decision === "crossing" ? "crossing" : "ambiguous";
                    if (!layers[key]) {
                      return null;
                    }
                    const color = meeting.decision === "junction" ? "#b45309" : meeting.decision === "crossing" ? "#7c3aed" : "#b91c1c";
                    return (
                      <circle
                        key={meeting.id}
                        cx={meeting.position[0]}
                        cy={meeting.position[1]}
                        r={4}
                        fill={color}
                        className="cursor-pointer"
                        role="button"
                        aria-label={`${meeting.decision}: ${meeting.reason}`}
                        onClick={() => setMeetingId(meeting.id)}
                      >
                        <title>{meeting.reason}</title>
                      </circle>
                    );
                  })}
                  {layers.free
                    ? pageFree.map((endpoint) => (
                        <circle key={`${endpoint.line_id}-${endpoint.position.join("-")}`} cx={endpoint.position[0]} cy={endpoint.position[1]} r={3} fill="none" stroke="#111827" strokeWidth={1.2} />
                      ))
                    : null}
                </svg>
              </div>
              <p className="mt-2 text-xs text-ink-soft">Copper outlines are rule matches. Grey outlines are unclassified shapes that were kept. Teal is a process line, blue is a signal line, brown is a junction, purple is a crossing, red is ambiguous, and an open circle is a free endpoint.</p>
            </div>
            <aside className="text-sm">
              {chosenMeeting ? (
                <div className="space-y-2">
                  <p className="font-semibold">{chosenMeeting.decision}</p>
                  <p>{chosenMeeting.reason}</p>
                </div>
              ) : null}
              {chosen ? <ItemDetail item={chosen} /> : <p className="text-ink-soft">Click an outline or an ambiguous point to see why it was kept.</p>}
            </aside>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-line text-ink-soft">
                  <th className="py-2 pr-3">Kind</th>
                  <th className="py-2 pr-3">Label</th>
                  <th className="py-2 pr-3">Confidence</th>
                  <th className="py-2 pr-3">Page</th>
                  <th className="py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.id} role="button" tabIndex={0} aria-label={`${item.kind} ${item.tag || item.label || "unlabeled"}`} className="cursor-pointer border-b border-line align-top" onClick={() => { setPageNumber(item.page); setSelected(item.id); }}>
                    <td className="py-2 pr-3">{item.kind}{item.subtype ? ` / ${item.subtype}` : ""}</td>
                    <td className="py-2 pr-3 font-mono">{item.tag || item.label || "—"}</td>
                    <td className="py-2 pr-3"><ConfidenceBadge level={item.confidence.level} /></td>
                    <td className="py-2 pr-3">{item.page}</td>
                    <td className="py-2">{item.evidence.map((entry) => entry.description).join(" ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ItemDetail({ item }: { item: DetectionItem }) {
  return (
    <div className="space-y-2">
      <p className="font-semibold">{item.kind}{item.tag ? ` ${item.tag}` : ""}</p>
      <ConfidenceBadge level={item.confidence.level} />
      <p>{item.confidence.reason}</p>
      {item.direction ? <p>Pointing {item.direction}. Flow is not decided.</p> : null}
      <ul className="list-disc pl-4">
        {item.evidence.map((entry) => (
          <li key={entry.description}>{entry.description}</li>
        ))}
      </ul>
    </div>
  );
}
