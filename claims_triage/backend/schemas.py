"""HTTP response shapes for the API (CLAUDE.md §4.4).

These are mirrored exactly in frontend/src/types.ts. Change both together.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from triage.models import TriageResult


class CheckOut(BaseModel):
    check_no: int
    check_name: str
    outcome: Literal["PASS", "DENY", "NEEDS_HUMAN", "NOT_EVALUATED"]
    rule_id: str | None
    reason_code: str | None
    detail: str


class ResultOut(BaseModel):
    claim_id: str
    decision: Literal["APPROVE", "DENY", "NEEDS_HUMAN"]
    rules_fired: list[str]
    reason_codes: list[str]
    explanation: str
    advisories: list[str]
    source_files: list[str]
    extracted: dict[str, Any]
    checks: list[CheckOut]

    @classmethod
    def from_result(cls, r: TriageResult) -> "ResultOut":
        return cls(
            claim_id=r.claim_id,
            decision=r.decision,
            rules_fired=r.rules_fired,
            reason_codes=r.reason_codes,
            explanation=r.explanation,
            advisories=r.advisories,
            source_files=r.source_files,
            extracted=r.extracted,
            checks=[
                CheckOut(check_no=c.check_no, check_name=c.check_name, outcome=c.outcome,
                         rule_id=c.rule_id, reason_code=c.reason_code, detail=c.detail)
                for c in r.results
            ],
        )


class SummaryOut(BaseModel):
    total: int
    APPROVE: int
    DENY: int
    NEEDS_HUMAN: int


class TriageResponse(BaseModel):
    summary: SummaryOut
    results: list[ResultOut]
    warnings: list[str]
    csv: str


class ErrorOut(BaseModel):
    error: str
    detail: str
