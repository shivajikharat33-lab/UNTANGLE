import { useCallback, useState } from "react";
import { apiBaseUrl } from "../api/client";
import { useHealthContext } from "../lib/useHealth";
import { Button } from "./Button";
import { Modal } from "./Modal";
import { Spinner } from "./Spinner";

export function HealthIndicator() {
  const { state, check } = useHealthContext();
  const [open, setOpen] = useState(false);
  const closeDetails = useCallback(() => setOpen(false), []);

  let label = "Offline";
  let dot = "bg-confidence-low-fg";
  let detail = "The API did not respond.";

  if (state.phase === "loading") {
    label = "Checking";
    dot = "bg-copper";
    detail = "Asking the API for a live health check.";
  } else if (state.phase === "offline") {
    label = "Offline";
    dot = "bg-confidence-low-fg";
    detail = state.message;
  } else if (state.health.database === "ok") {
    label = "Connected";
    dot = "bg-confidence-high-fg";
    detail = `API ${state.health.version} answered. Database check passed at ${state.health.time}.`;
  } else {
    label = "Database failed";
    dot = "bg-confidence-medium-fg";
    detail = "The API answered, and the database check failed. This is not a successful connection.";
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="flex items-center gap-2 rounded-full border border-line bg-paper-raised px-3 py-1.5 text-sm sm:cursor-default"
        onClick={() => setOpen(true)}
        aria-label={`${label}. Open health details`}
      >
        {state.phase === "loading" ? (
          <Spinner label="Checking" />
        ) : (
          <>
            <span className={`h-2.5 w-2.5 rounded-full ${dot}`} aria-hidden="true" />
            <span className="font-semibold text-ink">{label}</span>
          </>
        )}
      </button>
      <div className="hidden gap-2 sm:flex">
        <Button variant="ghost" onClick={() => void check()} disabled={state.phase === "loading"}>
          Check again
        </Button>
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Details
        </Button>
      </div>
      <Modal open={open} title="API health" onClose={closeDetails}>
        <p>{detail}</p>
        <p className="mt-2 font-mono text-xs text-ink">API: {apiBaseUrl()}</p>
        <p className="mt-2">
          Connected means GET /api/health returned status ok and the database check passed. Offline means the request
          failed. A failed database check is shown on its own and is not called Connected.
        </p>
        <div className="mt-4">
          <Button variant="secondary" onClick={() => void check()} disabled={state.phase === "loading"}>
            Check again
          </Button>
        </div>
      </Modal>
    </div>
  );
}
