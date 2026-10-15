import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { getSketchMeta, getSketchText } from "../api/jobs";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { Spinner } from "../components/Spinner";
import { buttonClass } from "../lib/buttonClass";
import { VERIFICATION_DISCLAIMER } from "../types/coverage";
import type { SketchMeta } from "../types/sketch";

export function SketchPage() {
  const { id } = useParams();
  const [svg, setSvg] = useState("");
  const [meta, setMeta] = useState<SketchMeta | null>(null);
  const [draft, setDraft] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      setMissing(true);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    getSketchText(id, false, controller.signal)
      .then(async (markup) => {
        setSvg(markup);
        setDraft(false);
        setMeta(await getSketchMeta(id, controller.signal));
        setMissing(false);
        setError(null);
      })
      .catch(async (caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          try {
            const markup = await getSketchText(id, true, controller.signal);
            setSvg(markup);
            setDraft(true);
            setMeta(null);
            setMissing(false);
            setError(null);
            return;
          } catch {
            setMissing(true);
            setSvg("");
            setError(null);
            return;
          }
        }
        setError(caught instanceof ApiError ? caught : new ApiError("The sketch could not be loaded.", 0, null));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [id]);

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl">Sketch</h1>
      {loading ? <Spinner label="Loading sketch" /> : null}
      {error ? <Alert tone="error" title={error.message} /> : null}
      {missing ? <EmptyState title="No sketch yet" description="Run extraction. A draft appears after the graph is built. The final sketch appears after layout." /> : null}
      {draft ? <Alert tone="warning" title="DRAFT, not final, not verified">This drawing was made from the graph before the later checks. It is not a verified sketch.</Alert> : null}
      {meta?.failed_check ? <Alert tone="warning" title="A check failed">This sketch is not labeled verified.</Alert> : null}
      {meta && meta.route_clear === false ? <Alert tone="warning" title="A route still meets a symbol">The line was moved outside the symbol box and still touches one. It is not drawn as a junction.</Alert> : null}
      {meta ? (
        <p className="text-sm">
          Nodes {meta.node_count ?? 0}. Edges {meta.edge_count ?? 0}. Crossings {meta.crossing_count ?? 0}. Bends {meta.bend_count ?? 0}. Hidden items {meta.hidden_count}.
        </p>
      ) : null}
      {svg ? <div className="overflow-auto rounded-card border border-line bg-paper p-2 [&_svg]:h-auto [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} /> : null}
      {meta && meta.legend.length > 0 ? (
        <ul className="text-sm text-ink-soft">
          {meta.legend.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
      <p className="text-sm text-ink-soft">{meta?.disclaimer || VERIFICATION_DISCLAIMER}</p>
      {id ? <Link to={`/app/projects/${id}/processing`} className={buttonClass("ghost")}>Back to processing</Link> : null}
    </div>
  );
}
