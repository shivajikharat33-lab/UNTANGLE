import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProgressSteps } from "./ProgressSteps";
import { presentStage } from "../lib/stagePresentation";
import type { StageRecord } from "../types/stages";

const base: Omit<StageRecord, "name" | "status"> = {
  started_at: null,
  ended_at: null,
  duration_ms: null,
  warnings: [],
  error: null,
};

describe("stage rendering", () => {
  it("shows a spinner and elapsed time while a stage is running", () => {
    const started = "2026-10-15T09:00:00.000Z";
    const view = presentStage(
      { ...base, name: "Read", status: "running", started_at: started },
      Date.parse(started) + 5000,
    );
    const html = renderToStaticMarkup(<ProgressSteps steps={[view]} />);
    expect(view.showSpinner).toBe(true);
    expect(view.durationLabel).toBe("5 s elapsed");
    expect(html).toContain("animate-spin");
    expect(html).toContain("5 s elapsed");
  });

  it("shows the failure text when a stage has failed", () => {
    const view = presentStage({
      ...base,
      name: "Detect",
      status: "failed",
      error: "Example failure. This is not a real job.",
    });
    const html = renderToStaticMarkup(<ProgressSteps steps={[view]} />);
    expect(view.state).toBe("failed");
    expect(html).toContain("Example failure. This is not a real job.");
  });

  it("greys out a skipped stage", () => {
    const view = presentStage({ ...base, name: "MatchTags", status: "skipped" });
    const html = renderToStaticMarkup(<ProgressSteps steps={[view]} />);
    expect(view.state).toBe("skipped");
    expect(html).toContain("opacity-50");
    expect(html).toContain("Skipped");
  });

  it("labels a pending stage as waiting", () => {
    const view = presentStage({ ...base, name: "Layout", status: "pending" });
    const html = renderToStaticMarkup(<ProgressSteps steps={[view]} />);
    expect(view.showSpinner).toBe(false);
    expect(html).toContain("Waiting to run");
    expect(html).toContain("Laying out the sketch");
  });
});
