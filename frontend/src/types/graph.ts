import type { Confidence } from "./confidence";
import type { RuleResult } from "./rules";

export type NodeType =
  | "equipment"
  | "instrument"
  | "valve"
  | "junction"
  | "endpoint";

/** "forward" means flow runs from from_id to to_id. */
export type Direction = "forward" | "reverse" | "bidirectional" | "unknown";

export type LineType = "process" | "signal" | "other";

export type CrossingMode = "auto" | "avoid" | "keep";

export type EdgeStatus = "auto" | "user_added" | "user_edited" | "user_removed";

export type GroupType = "duty_standby" | "control_loop";

export interface BBox {
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Evidence {
  source: string;
  description: string;
  page?: number | null;
}

export interface Node {
  id: string;
  type: NodeType;
  tag: string;
  label: string;
  signal: string;
  bbox: BBox | null;
  kept: boolean;
  detail_level: 1 | 2 | 3;
  confidence: Confidence;
  reason: string;
}

export interface Edge {
  id: string;
  from_id: string;
  to_id: string;
  direction: Direction;
  line_type: LineType;
  color: string;
  style: string;
  crossing_mode: CrossingMode;
  status: EdgeStatus;
  polyline: Point[];
  confidence: Confidence;
  evidence: Evidence[];
  rule_results: RuleResult[];
}

export interface Group {
  id: string;
  type: GroupType;
  member_node_ids: string[];
  shared_upstream: string[];
  shared_downstream: string[];
}

export interface DiagramGraph {
  nodes: Node[];
  edges: Edge[];
  groups: Group[];
}
