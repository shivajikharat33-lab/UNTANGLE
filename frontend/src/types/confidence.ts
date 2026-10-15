import type { ConfidenceLevel } from "../lib/confidence";

export type { ConfidenceLevel };

/** A score, the level that score maps to, and why it was given. */
export interface Confidence {
  level: ConfidenceLevel;
  score: number;
  reason: string;
}
