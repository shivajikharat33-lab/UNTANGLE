import type { ReactNode } from "react";
import type { ConfidenceLevel } from "../lib/confidence";

type BadgeTone = "neutral" | ConfidenceLevel;

const tones: Record<BadgeTone, string> = {
  neutral: "bg-ink/5 text-ink",
  high: "bg-confidence-high-bg text-confidence-high-fg",
  medium: "bg-confidence-medium-bg text-confidence-medium-fg",
  low: "bg-confidence-low-bg text-confidence-low-fg",
};

type BadgeProps = {
  tone?: BadgeTone;
  children: ReactNode;
};

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  const label = level === "high" ? "High confidence" : level === "medium" ? "Medium confidence" : "Low confidence";
  return <Badge tone={level}>{label}</Badge>;
}
