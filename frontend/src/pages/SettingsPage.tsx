import { apiBaseUrl } from "../api/client";
import { Alert } from "../components/Alert";
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
        description="The values below are the ones this browser is actually using. There is no form here yet, so nothing is saved from this page."
      />
      <Alert tone="info" title="Not built yet">
        Changing the API address, upload limit, or theme from this screen is not built yet.
      </Alert>
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
            High starts at {HIGH_CONFIDENCE_MIN}. Medium starts at {MEDIUM_CONFIDENCE_MIN}. These match the backend
            config. Scores are not being calculated yet.
          </p>
        </Card>
      </div>
    </div>
  );
}
