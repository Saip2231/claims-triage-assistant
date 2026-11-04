"""Template-based, plain-language explanations that cite the uploaded policy. No LLM.

Shape of every explanation:
    <claim> (member <id>): <decision sentence> <one plain sentence per fired rule>
    Policy basis: Section X.Y Title – "<quote from the uploaded policy>". [one per section]
    <next step> [+ appeal right on denials]
    Reviewer notes (do not change this decision): <advisories>

Privacy (Policy §3.8): only the claim ID, member ID, codes, dates, amounts and
record IDs appear. Never birth year, sex, age, names or addresses.
"""

from __future__ import annotations

from dataclasses import dataclass

from .advisories import compute_advisories
from .models import Claim, Decision, RuleResult, TriageResult
from .policy import PolicyIndex
from .reference import ReferenceData


@dataclass(frozen=True)
class Citation:
    section: str
    keyword: str | None  # sentence to quote from that section; None = cite without a quote


# Reason code -> the policy section(s) to cite, and the next step to tell the provider.
CITATIONS: dict[str, tuple[Citation, ...]] = {
    "R201": (Citation("3.1", "pend and return"),),
    "R202": (Citation("3.1", "infer"),),
    "R203": (Citation("3.1", "pend and return"),),
    "R101": (Citation("2.1", "termination date"),),
    "R102": (Citation("3.3", "paid claim"),),
    "R401": (Citation("2.5", "pended"),),
    "R801": (Citation("2.3", "out-of-network"),),
    "R901": (Citation("3.6", "Escalate to human"),),
    "R200": (Citation("3.1", "pend and return"),),
    "R204": (Citation("3.6", "conflicting documents"),),
}
EMERGENCY_CITATION = Citation("2.4", "require human review")
APPROVE_CITATION = Citation("3.2", None)

NEXT_STEPS: dict[str, str] = {
    "R201": "Please add the missing information and resubmit the claim.",
    "R202": "Please resubmit with a valid ICD-10-CM diagnosis code; codes are never corrected automatically.",
    "R203": "A reviewer will confirm the missing reference record before the claim can proceed.",
    "R401": "Please submit the prior authorization or the supporting clinical information.",
    "R801": "A reviewer will confirm network status and the correct payment.",
    "R901": "A senior reviewer must sign off before payment.",
    "R200": "Please re-upload a readable claim file (PDF or TXT).",
    "R204": "Please confirm which document is correct and resubmit a single version.",
}
APPEAL = "The member and provider may appeal this decision within 180 days ({cite})."

DECISION_SENTENCE: dict[str, str] = {
    "APPROVE": "Approved – all six checks passed.",
    "DENY": "Denied.",
    "NEEDS_HUMAN": "Sent for human review.",
}


def _ensure_period(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?", "…", '"')) else f"{text}."


class TemplateExplainer:
    """Builds explanations from rule results, the parsed policy and reviewer notes.

    It is callable as engine.Explainer: (claim, results, decision) -> (explanation, advisories).
    explain_intake() words the rows for files that never reached the checks.
    """

    def __init__(self, policy: PolicyIndex, ref: ReferenceData):
        self.policy = policy
        self.ref = ref

    # ---------------------------------------------------------------- pieces

    def _basis(self, citations: list[Citation]) -> list[str]:
        out, seen = [], set()
        for c in citations:
            if c.section in seen:
                continue
            seen.add(c.section)
            quote = self.policy.quote(c.section, c.keyword) if c.keyword else None
            cite = self.policy.cite(c.section)
            out.append(f'Policy basis: {cite} – "{quote}"' if quote else f"Policy basis: {cite}.")
        return [_ensure_period(s) for s in out]

    @staticmethod
    def _header(claim_id: str, member_id: str | None) -> str:
        return f"{claim_id} (member {member_id}):" if member_id else f"{claim_id}:"

    # ---------------------------------------------------------------- public

    def __call__(self, claim: Claim, results: list[RuleResult], decision: Decision) -> tuple[str, list[str]]:
        fired = sorted((r for r in results if r.fired), key=lambda r: r.check_no)
        parts = [self._header(claim.claim_id or claim.source_file, claim.member_id), DECISION_SENTENCE[decision]]

        citations: list[Citation] = []
        steps: list[str] = []
        if not fired:
            parts.append("Required fields are complete and valid, coverage was active on the date of service, "
                         "it is not a duplicate, no prior authorization is missing, the provider is in-network, "
                         "and the total is within the $10,000 limit.")
            citations.append(APPROVE_CITATION)
            steps.append("No action needed.")
        for r in fired:
            parts.append(_ensure_period(r.detail))
            citations.extend(CITATIONS.get(r.reason_code or "", ()))
            if r.rule_id == "EMR-01":
                citations.append(EMERGENCY_CITATION)
            step = NEXT_STEPS.get(r.reason_code or "")
            if step and step not in steps:
                steps.append(step)

        parts.extend(self._basis(citations))
        parts.extend(steps)
        if decision == "DENY":
            parts.append(APPEAL.format(cite=self.policy.cite("2.8")))

        advisories = compute_advisories(claim, self.ref)
        if advisories:
            parts.append("Reviewer notes (do not change this decision): " + " | ".join(advisories))
        return " ".join(parts), advisories

    def explain_intake(self, row: TriageResult) -> str:
        """Explanation for a file that could not go through the checks (R200 / R204)."""
        code = row.reason_codes[0] if row.reason_codes else "R200"
        parts = [self._header(row.claim_id, row.extracted.get("member_id") if row.extracted else None),
                 DECISION_SENTENCE["NEEDS_HUMAN"], _ensure_period(row.results[0].detail)]
        parts.extend(self._basis(list(CITATIONS.get(code, ()))))
        if code in NEXT_STEPS:
            parts.append(NEXT_STEPS[code])
        return " ".join(parts)
