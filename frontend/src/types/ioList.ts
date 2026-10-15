export type IoSeverity = "error" | "warning";

export interface IoIssue {
  sheet: string;
  row: number;
  original_value: string;
  severity: IoSeverity;
  message: string;
}

export interface IoRow {
  row: number;
  original_tag: string;
  tag: string;
  signal: string;
  instrument_type: string;
  issues: IoIssue[];
  suffix_hint: string | null;
}

export interface IoSummary {
  row_count: number;
  ok_count: number;
  error_count: number;
  warning_count: number;
}

export interface IoListResult {
  status: "validated" | "needs_columns";
  sheet: string | null;
  sheets: string[];
  columns: string[];
  tag_column: string | null;
  signal_column: string | null;
  message: string;
  rows: IoRow[];
  summary: IoSummary;
}

export interface IoValidateRequest {
  sheet?: string | null;
  tag_column?: string | null;
  signal_column?: string | null;
}
