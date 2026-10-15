import type { Confidence } from "./confidence";
import type { BBox, Direction, Evidence, LineType } from "./graph";

export type TagMatchStatus = "found" | "fuzzy" | "not_found" | "extra";

export interface TagReportRow {
  tag: string;
  signal: string;
  status: TagMatchStatus;
  confidence: Confidence;
  location: BBox | null;
  suggestion: string | null;
  suffix_hint?: string | null;
}

export interface TagReportSummary {
  total: number;
  found: number;
  fuzzy: number;
  not_found: number;
  extra: number;
}

export interface TagReport {
  rows: TagReportRow[];
  summary: TagReportSummary;
}

export interface ConnectionReportRow {
  from: string;
  to: string;
  direction: Direction;
  line_type: LineType;
  confidence: Confidence;
  evidence: Evidence[];
  rules_passed: string[];
  rules_failed: string[];
  source_location: BBox | null;
}
