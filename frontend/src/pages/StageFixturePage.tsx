import { Alert } from "../components/Alert";
import { StageList } from "../components/StageList";
import { PageHeader } from "../components/PageHeader";
import { STAGE_ORDER, type StageRecord } from "../types/stages";

function fixtureStages(now: number): StageRecord[] {
  const stamp = new Date(now).toISOString();
  const runningStart = new Date(now - 5000).toISOString();
  return STAGE_ORDER.map((name) => {
    if (name === "Intake") {
      return { name, status: "done", started_at: stamp, ended_at: stamp, duration_ms: 12, warnings: [], error: null };
    }
    if (name === "Read") {
      return { name, status: "running", started_at: runningStart, ended_at: null, duration_ms: null, warnings: [], error: null };
    }
    if (name === "Detect") {
      return {
        name,
        status: "failed",
        started_at: stamp,
        ended_at: stamp,
        duration_ms: 4,
        warnings: [],
        error: "Example failure. This is not a real job.",
      };
    }
    if (name === "MatchTags") {
      return { name, status: "skipped", started_at: null, ended_at: null, duration_ms: null, warnings: [], error: null };
    }
    return { name, status: "pending", started_at: null, ended_at: null, duration_ms: null, warnings: [], error: null };
  });
}

export function StageFixturePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Dev only"
        title="Stage states"
        description="This is a fixture for looking at running, failed, and skipped stages. It is not a project, it is not stored, and this route is left out of production."
      />
      <Alert tone="info" title="Not a real run">
        Nothing on this page came from an uploaded file. Do not treat it as a result.
      </Alert>
      <StageList stages={fixtureStages(Date.now())} />
    </div>
  );
}
