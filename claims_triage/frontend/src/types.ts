// Mirrors backend/schemas.py exactly (CLAUDE.md §4.4). Change both together.

export type Decision = "APPROVE" | "DENY" | "NEEDS_HUMAN";
export type Outcome = "PASS" | "DENY" | "NEEDS_HUMAN" | "NOT_EVALUATED";

export interface CheckOut {
  check_no: number;
  check_name: string;
  outcome: Outcome;
  rule_id: string | null;
  reason_code: string | null;
  detail: string;
}

export interface ResultOut {
  claim_id: string;
  decision: Decision;
  rules_fired: string[];
  reason_codes: string[];
  explanation: string;
  advisories: string[];
  source_files: string[];
  extracted: Record<string, unknown>;
  checks: CheckOut[];
}

export interface Summary {
  total: number;
  APPROVE: number;
  DENY: number;
  NEEDS_HUMAN: number;
}

export interface TriageResponse {
  summary: Summary;
  results: ResultOut[];
  warnings: string[];
  csv: string;
}

export interface ApiErrorBody {
  error: string;
  detail: string;
}

export const DECISIONS: Decision[] = ["APPROVE", "DENY", "NEEDS_HUMAN"];

export const DECISION_LABEL: Record<Decision, string> = {
  APPROVE: "Approve",
  DENY: "Deny",
  NEEDS_HUMAN: "Needs human",
};
