import type { ReactNode } from "react";
import { HealthContext, useHealth } from "./useHealth";

export function HealthProvider({ children }: { children: ReactNode }) {
  const health = useHealth();
  return <HealthContext.Provider value={health}>{children}</HealthContext.Provider>;
}
