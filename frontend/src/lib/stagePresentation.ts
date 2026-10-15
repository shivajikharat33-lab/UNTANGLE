import type { StageRecord } from "../types/stages";

export const POLL_INTERVAL_MS = 2000;

export type PresentedStage = {
  id: string;
  label: string;
  state: StageRecord["status"];
  note: string;
  durationLabel: string | null;
  showSpinner: boolean;
};

export function shouldPoll(stages: Array<{ status: string }>): boolean {
  return stages.some((stage) => stage.status === "running");
}

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function formatElapsed(startedAt: string | null, now: number): string {
  if (!startedAt) {
    return "Elapsed time unavailable";
  }
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) {
    return "Elapsed time unavailable";
  }
  const elapsed = Math.max(0, now - started);
  if (elapsed < 1000) {
    return `${elapsed} ms elapsed`;
  }
  return `${Math.floor(elapsed / 1000)} s elapsed`;
}

function joinWarnings(warnings: string[]): string {
  return warnings.map((warning) => warning.trim()).filter((warning) => warning.length > 0).join(" ");
}

const BUILT_STAGES = new Set(["Intake", "Read", "MatchTags", "Detect", "Trace", "Patterns", "SelfCheck", "Simplify", "Layout", "Report"]);

const STAGE_LABELS: Partial<Record<StageRecord["name"], string>> = {
  Trace: "Building graph",
  Patterns: "Detecting patterns",
  SelfCheck: "Running checks",
  Simplify: "Simplifying graph",
  Layout: "Laying out the sketch",
  Report: "Computing coverage",
};

export function presentStage(stage: StageRecord, now = Date.now()): PresentedStage {
  const warnings = joinWarnings(stage.warnings);
  if (stage.status === "done") {
    return {
      id: stage.name,
      label: STAGE_LABELS[stage.name] ?? stage.name,
      state: "done",
      note: warnings,
      durationLabel: stage.duration_ms === null ? null : formatDuration(stage.duration_ms),
      showSpinner: false,
    };
  }
  if (stage.status === "running") {
    return {
      id: stage.name,
      label: STAGE_LABELS[stage.name] ?? stage.name,
      state: "running",
      note: warnings,
      durationLabel: formatElapsed(stage.started_at, now),
      showSpinner: true,
    };
  }
  if (stage.status === "failed") {
    return {
      id: stage.name,
      label: STAGE_LABELS[stage.name] ?? stage.name,
      state: "failed",
      note: stage.error?.trim() || warnings || "This stage failed.",
      durationLabel: stage.duration_ms === null ? null : formatDuration(stage.duration_ms),
      showSpinner: false,
    };
  }
  if (stage.status === "skipped") {
    return {
      id: stage.name,
      label: STAGE_LABELS[stage.name] ?? stage.name,
      state: "skipped",
      note: warnings || "Skipped",
      durationLabel: null,
      showSpinner: false,
    };
  }
  return {
    id: stage.name,
    label: STAGE_LABELS[stage.name] ?? stage.name,
    state: "pending",
    note: warnings || (BUILT_STAGES.has(stage.name) ? "Waiting to run" : "Waiting: processing engine not built yet"),
    durationLabel: null,
    showSpinner: false,
  };
}
