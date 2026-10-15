import type { RuleResult } from "./rules";

/**
 * verified may be true only when rule_results is non-empty and every check passed.
 * The backend rejects a payload that breaks this rule.
 */
export interface VerificationResult {
  connections_added: number;
  connections_removed: number;
  tags_placed: number;
  tags_total: number;
  rule_results: RuleResult[];
  verified: boolean;
}
