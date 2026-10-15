import type { Direction, LineType } from "./graph";

export interface ExpectedTag {
  tag: string;
  signal: string;
}

export interface ExpectedEquipment {
  tag: string;
  label: string;
}

export interface ExpectedConnection {
  from: string;
  to: string;
  direction: Direction;
  line_type: LineType;
}

export interface ExpectedDutyStandbyGroup {
  id: string;
  member_tags: string[];
  shared_upstream: string[];
  shared_downstream: string[];
}

export interface AnswerKey {
  drawing_id: string;
  expected_tags: ExpectedTag[];
  expected_equipment: ExpectedEquipment[];
  expected_connections: ExpectedConnection[];
  expected_duty_standby_groups: ExpectedDutyStandbyGroup[];
}
