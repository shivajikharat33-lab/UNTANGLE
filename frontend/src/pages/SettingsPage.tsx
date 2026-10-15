import { useEffect, useState } from "react";
import { apiBaseUrl } from "../api/client";
import { getConfig } from "../api/jobs";
import { ThemeToggle } from "../components/ThemeToggle";
import type { PublicConfig } from "../types/intake";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";
import { HIGH_CONFIDENCE_MIN, MEDIUM_CONFIDENCE_MIN } from "../lib/confidence";
import { useHealthContext } from "../lib/useHealth";

export function SettingsPage() {
  const { state } = useHealthContext();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [theme, setTheme] = useState<"light" | "dark" | "system">("light");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getConfig().then(setConfig).catch(() => setLoadError("The API settings could not be loaded."));
  }, []);

  useEffect(() => {
    const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [theme]);

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
            High starts at {HIGH_CONFIDENCE_MIN}. Medium starts at {MEDIUM_CONFIDENCE_MIN}. Simulation values stay in the browser and are not exported.
          </p>
        </Card>
        <Card title="Transparency declaration">
          {loadError ? <p className="text-sm text-confidence-low-fg">{loadError}</p> : null}
          {!config && !loadError ? <Spinner label="Loading flags" /> : null}
          {config ? (
            <ul className="space-y-1 text-sm text-ink-soft">
              <li>API: {apiBaseUrl()}. No drawing is sent anywhere else.</li>
              <li>Modify: {config.modify_enabled ? "on" : "off"}.</li>
              <li>Ask-the-graph model: {config.ask_graph_llm_enabled ? "on" : "off"}. Default is off. Only graph JSON would be sent, never the PDF.</li>
              <li>Few-shot suggestions: {config.fewshot_symbols_enabled ? "on" : "off"}. This is not a trained model.</li>
              <li>Dark theme control: {config.dark_theme_enabled ? "on" : "off"}.</li>
              <li>Flow marks: {config.flow_animation_enabled ? "on" : "off"}.</li>
              <li>Batch upload: {config.batch_upload_enabled ? "on" : "off"}.</li>
              <li>Libraries in this app: FastAPI, PyMuPDF, OpenCV, Shapely, elkjs, ReportLab. CairoSVG is installed but the Cairo DLL is not available, so print uses ReportLab.</li>
            </ul>
          ) : null}
          <ThemeToggle enabled={Boolean(config?.dark_theme_enabled)} mode={theme} onChange={setTheme} />
        </Card>
      </div>
    </div>
  );
}
