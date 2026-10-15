/**
 * Confidence cutoffs. These two numbers must match backend/app/config.py.
 * A score of 0.85 or higher is high. A score of 0.60 up to but not including
 * 0.85 is medium. Anything lower is low.
 */
export const HIGH_CONFIDENCE_MIN = 0.85;
export const MEDIUM_CONFIDENCE_MIN = 0.60;

export type ConfidenceLevel = "high" | "medium" | "low";

export function levelForScore(score: number): ConfidenceLevel {
  if (score >= HIGH_CONFIDENCE_MIN) {
    return "high";
  }
  if (score >= MEDIUM_CONFIDENCE_MIN) {
    return "medium";
  }
  return "low";
}
