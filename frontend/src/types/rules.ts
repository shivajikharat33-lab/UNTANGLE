/** The outcome of a single named check. */
export interface RuleResult {
  rule_id: string;
  passed: boolean;
  message: string;
}
