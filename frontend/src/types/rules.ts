/** The outcome of a single named check. */
export interface RuleResult {
  rule_id: string;
  passed: boolean;
  message: string;
}

export interface Finding {
  id: string;
  rule_id: string;
  category: string;
  severity: "error" | "warning" | "info";
  title: string;
  message: string;
  affected_ids: string[];
  evidence: { source: string; description: string; page?: number | null }[];
  review_action: string;
}
