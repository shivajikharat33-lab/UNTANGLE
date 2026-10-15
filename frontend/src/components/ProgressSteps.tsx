import { Spinner } from "./Spinner";
import type { PresentedStage } from "../lib/stagePresentation";

export type StepState = PresentedStage["state"] | "current";

export type ProgressStep = {
  id: string;
  label: string;
  state: StepState;
  note?: string;
  durationLabel?: string | null;
  showSpinner?: boolean;
};

const marker: Record<StepState, string> = {
  pending: "border-line bg-paper text-ink-soft",
  current: "border-teal bg-teal text-paper",
  done: "border-copper-deep bg-copper-deep text-paper",
  running: "border-teal bg-paper text-teal",
  failed: "border-alert-error-fg bg-alert-error-bg text-alert-error-fg",
  skipped: "border-line bg-paper text-ink-soft",
};

export function ProgressSteps({ steps }: { steps: ProgressStep[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {steps.map((step, index) => (
        <li
          key={step.id}
          className={`flex items-start gap-3 rounded-control border border-line bg-paper-raised px-3 py-2 ${step.state === "skipped" ? "opacity-50" : ""}`}
        >
          <span
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${marker[step.state]}`}
            aria-hidden="true"
          >
            {index + 1}
          </span>
          <span className="min-w-0 text-sm font-semibold text-ink">
            {step.label}
            <span className="mt-0.5 block text-xs font-normal uppercase tracking-wide text-ink-soft">{step.state}</span>
            {step.showSpinner ? <span className="mt-1 block"><Spinner label="Running" /></span> : null}
            {step.durationLabel ? (
              <span className="mt-0.5 block text-xs font-normal normal-case tracking-normal text-ink-soft">{step.durationLabel}</span>
            ) : null}
            {step.note ? (
              <span className="mt-0.5 block text-xs font-normal normal-case tracking-normal text-ink-soft">{step.note}</span>
            ) : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
