import { useEffect, useState } from "react";
import { ProgressSteps } from "./ProgressSteps";
import { presentStage } from "../lib/stagePresentation";
import type { StageRecord } from "../types/stages";

export function StageList({ stages }: { stages: StageRecord[] }) {
  const running = stages.some((stage) => stage.status === "running");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  return <ProgressSteps steps={stages.map((stage) => presentStage(stage, now))} />;
}
