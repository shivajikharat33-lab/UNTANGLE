import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { getHealth } from "../api/health";
import type { HealthResponse } from "../types/health";

export type HealthView =
  | { phase: "loading" }
  | { phase: "online"; health: HealthResponse }
  | { phase: "offline"; message: string };

export function useHealth() {
  const [state, setState] = useState<HealthView>({ phase: "loading" });
  const abortRef = useRef<AbortController | null>(null);

  const check = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ phase: "loading" });
    try {
      const health = await getHealth(controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setState({ phase: "online", health });
    } catch (error) {
      if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
        return;
      }
      const message = error instanceof ApiError ? error.message : "The API is not reachable.";
      setState({ phase: "offline", message });
    }
  }, []);

  useEffect(() => {
    void check();
    return () => abortRef.current?.abort();
  }, [check]);

  return { state, check };
}

type HealthContextValue = ReturnType<typeof useHealth>;

export const HealthContext = createContext<HealthContextValue | null>(null);

export function useHealthContext(): HealthContextValue {
  const value = useContext(HealthContext);
  if (value === null) {
    throw new Error("useHealthContext must be used inside HealthProvider");
  }
  return value;
}
