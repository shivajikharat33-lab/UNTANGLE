import { useEffect, useState } from "react";
import { getExtraction } from "../api/jobs";
import { ApiError } from "../api/client";
import type { ExtractionResult } from "../types/extraction";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { Spinner } from "./Spinner";

export function ExtractionPanel({ jobId, readStatus }: { jobId: string; readStatus: string }) {
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (readStatus === "running" || readStatus === "pending") {
      setLoading(false);
      setResult(null);
      setMissing(readStatus === "pending");
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getExtraction(jobId, controller.signal)
      .then((next) => {
        setResult(next);
        setMissing(false);
        setError(null);
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
        setError(caught instanceof ApiError ? caught : new ApiError("The extraction could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [jobId, readStatus]);

  return (
    <section>
      <h2 className="mb-3 font-display text-xl">Read</h2>
      {loading ? <Spinner label="Loading extraction" /> : null}
      {readStatus === "running" ? <Spinner label="Reading the drawing" /> : null}
      {error ? (
        <Alert tone="error" title={error.message}>
          {error.body?.request_id ? <p>Request id: {error.body.request_id}</p> : null}
        </Alert>
      ) : null}
      {missing && readStatus !== "running" ? (
        <EmptyState
          title="Extraction has not been run"
          description="Run extraction reads text and vector geometry from the PDF. Scanned pages are reported as having no vector content."
        />
      ) : null}
      {result ? (
        <div className="space-y-3">
          <Alert tone={result.status === "ok" && result.summary.raster_items === 0 ? "success" : "warning"} title={result.status === "ocr_unavailable" ? "OCR is not installed" : result.summary.raster_items > 0 ? "Raster read is less reliable" : result.status === "ok" ? "Extraction finished" : "Extraction finished with a limit"}>
            {result.message}
            {result.summary.raster_items > 0 ? " Raster items are not an exact vector read." : ""}
          </Alert>
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="font-semibold">Pages</dt>
              <dd>{result.meta.page_count}</dd>
            </div>
            <div>
              <dt className="font-semibold">Words</dt>
              <dd>{result.summary.words}</dd>
            </div>
            <div>
              <dt className="font-semibold">Lines</dt>
              <dd>{result.summary.lines}</dd>
            </div>
            <div>
              <dt className="font-semibold">Shapes</dt>
              <dd>{result.summary.shapes}</dd>
            </div>
            <div>
              <dt className="font-semibold">Circles</dt>
              <dd>{result.summary.circles}</dd>
            </div>
            <div>
              <dt className="font-semibold">Unused primitives</dt>
              <dd>{result.summary.unused_primitives}</dd>
            </div>
            <div>
              <dt className="font-semibold">Vector items</dt>
              <dd>{result.summary.vector_items}</dd>
            </div>
            <div>
              <dt className="font-semibold">Raster items</dt>
              <dd>{result.summary.raster_items}</dd>
            </div>
            <div>
              <dt className="font-semibold">Duration</dt>
              <dd>{result.meta.duration_ms} ms</dd>
            </div>
          </dl>
          <p className="text-sm text-ink-soft">{result.meta.coordinate_system}</p>
        </div>
      ) : null}
    </section>
  );
}
