export interface CoverageMetric {
  name: string;
  numerator: number;
  denominator: number;
  percentage: number | null;
  missing_ids: string[];
}

export interface LedgerEntry {
  item_id: string;
  item_type: string;
  page: number | null;
  position: number[];
  reason_code: string;
  reason_text: string;
  stage: string;
}

export interface LedgerPage {
  items: LedgerEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface VerificationStatus {
  state: "verified" | "not_verified" | "needs_review";
  failing: string[];
  disclaimer: string;
}

export const VERIFICATION_DISCLAIMER = "Passed the defined automated checks. This is not an engineering or safety certification.";
