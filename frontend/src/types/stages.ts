export type StageName =
  | "Intake"
  | "Read"
  | "Detect"
  | "MatchTags"
  | "Trace"
  | "SelfCheck"
  | "Simplify"
  | "Patterns"
  | "Layout"
  | "Report";

export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";

export const STAGE_ORDER: readonly StageName[] = [
  "Intake",
  "Read",
  "Detect",
  "MatchTags",
  "Trace",
  "SelfCheck",
  "Simplify",
  "Patterns",
  "Layout",
  "Report",
];

export interface StageRecord {
  name: StageName;
  status: StageStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  warnings: string[];
  error: string | null;
}

export interface ProcessingRun {
  stages: StageRecord[];
}
