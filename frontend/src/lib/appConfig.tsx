import { createContext, useContext } from "react";
import type { PublicConfig } from "../types/intake";

export const AppConfigContext = createContext<PublicConfig | null>(null);

export function useAppConfig(): PublicConfig | null {
  return useContext(AppConfigContext);
}
