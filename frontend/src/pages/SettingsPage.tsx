import { apiBaseUrl } from "../api/client";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";
import { HIGH_CONFIDENCE_MIN, MEDIUM_CONFIDENCE_MIN } from "../lib/confidence";
import { useHealthContext } from "../lib/useHealth";

export function SettingsPage() {
  const { state } = useHealthContext();

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="These values are read from the running API and this browser. Changing the API address still happens in the env file, not in a saved form."
      />
      <div className="mt-6 grid gap-4">
        <Card title="API address">
          <p className="font-mono text-sm text-ink">{apiBaseUrl()}</p>
          <p className="mt-2 text-sm text-ink-soft">Set VITE_API_URL in frontend/.env. The example file uses http://127.0.0.1:8000.</p>
        </Card>
        <Card title="Live health">
          {state.phase === "loading" ? <Spinner label="Checking the API" /> : null}
          {state.phase === "offline" ? <p className="text-sm text-confidence-low-fg">Offline. {state.message}</p> : null}
          {state.phase === "online" ? (
            <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
              <dt className="text-ink-soft">Status</dt>
              <dd>{state.health.status}</dd>
              <dt className="text-ink-soft">Version</dt>
              <dd>{state.health.version}</dd>
              <dt className="text-ink-soft">Database</dt>
              <dd>{state.health.database}</dd>
              <dt className="text-ink-soft">Time</dt>
              <dd>{state.health.time}</dd>
            </dl>
          ) : null}
        </Card>
        <Card title="Confidence cutoffs">
          <p className="text-sm leading-6 text-ink-soft">
            High starts at {HIGH_CONFIDENCE_MIN}. Medium starts at {MEDIUM_CONFIDENCE_MIN}. Ask-the-graph models are off unless ASK_GRAPH_LLM_ENABLED is set. Few-shot symbol suggestions are off unless FEWSHOT_SYMBOLS_ENABLED is set. Simulation is not exported.
          </p>
        </Card>
      </div>
    </div>
  );
}
