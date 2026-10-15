import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch, clearAccessToken, setAccessToken } from "../api/client";
import { getConfig } from "../api/jobs";
import type { PublicConfig } from "../types/intake";
import { gateNeeded } from "../lib/access";
import { Button } from "./Button";

const AppConfigContext = createContext<PublicConfig | null>(null);

export function useAppConfig(): PublicConfig | null {
  return useContext(AppConfigContext);
}

type Phase = "loading" | "open" | "locked";

export function AccessGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getConfig(controller.signal)
      .then(async (next) => {
        setConfig(next);
        if (!gateNeeded(next)) {
          setPhase("open");
          return;
        }
        const check = await apiFetch("/api/jobs", controller.signal);
        setPhase(check.ok ? "open" : "locked");
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setPhase("open");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    function lock() {
      setPhase("locked");
    }
    window.addEventListener("untangle-locked", lock);
    return () => window.removeEventListener("untangle-locked", lock);
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${(await import("../api/client")).apiBaseUrl()}/api/access`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const payload: unknown = await response.json().catch(() => null);
      const token = payload && typeof payload === "object" && "token" in payload ? String((payload as { token?: string }).token ?? "") : "";
      if (!response.ok || !token) {
        clearAccessToken();
        setError("That code was not accepted.");
        return;
      }
      setAccessToken(token);
      setCode("");
      setPhase("open");
    } catch {
      setError("The API is not reachable.");
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return (
      <div className="grid min-h-screen place-items-center bg-paper text-ink">
        <p className="text-sm text-ink-soft">Checking the server…</p>
      </div>
    );
  }

  if (phase === "locked") {
    return (
      <div className="grid min-h-screen place-items-center bg-paper px-4 text-ink">
        <form onSubmit={(event) => void submit(event)} className="w-full max-w-md rounded-card border border-line bg-paper-raised p-6 shadow-card">
          <p className="font-display text-3xl">UNTANGLE</p>
          <h1 className="mt-2 font-display text-2xl">Demo access</h1>
          <p className="mt-3 text-sm leading-6 text-ink-soft">
            This is a shared passcode for the demo. It is not a user account. The code is not stored in the website.
          </p>
          <label className="mt-4 block text-sm font-semibold" htmlFor="demo-access-code">
            Access code
          </label>
          <input
            id="demo-access-code"
            type="password"
            autoComplete="off"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="mt-1 w-full rounded-control border border-line bg-paper px-3 py-2 text-sm"
          />
          {error ? <p className="mt-3 text-sm text-confidence-low-fg">{error}</p> : null}
          <div className="mt-4">
            <Button type="submit" disabled={submitting || code.trim() === ""}>
              {submitting ? "Checking" : "Continue"}
            </Button>
          </div>
        </form>
      </div>
    );
  }

  return <AppConfigContext.Provider value={config}>{children}</AppConfigContext.Provider>;
}
