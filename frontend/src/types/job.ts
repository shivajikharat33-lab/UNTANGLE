import type { Direction, LineType } from "./graph";
import type { VerificationResult } from "./verification";

export type VersionStatus = "auto" | "accepted" | "edited";

export interface ChangeLogEntry {
  who: string;
  when: string;
  what: string;
  note: string;
}

export interface ConnectionSnapshotEntry {
  from: string;
  to: string;
  direction: Direction;
  line_type: LineType;
}

/**
 * Version number 0 is the original. It has no parent and is never overwritten.
 * A later version names its parent version id.
 */
export interface Version {
  id: string;
  number: number;
  parent: string | null;
  status: VersionStatus;
  connection_list_snapshot: ConnectionSnapshotEntry[];
  svg: string | null;
  verification: VerificationResult | null;
  change_log: ChangeLogEntry[];
}

import type { StageRecord } from "./stages";
import type { IntakeSummary } from "./intake";

export interface Job {
  id: string;
  versions: Version[];
  name: string;
  status: "uploaded";
  created_at: string | null;
  intake: IntakeSummary | null;
  stages: StageRecord[];
}
