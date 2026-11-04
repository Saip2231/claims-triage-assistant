"""Data contracts shared by every stage of the triage pipeline (CLAUDE.md §4.1).

Money is Decimal, dates are datetime.date, and codes and IDs are str. A field
that could not be extracted is None and is never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

Outcome = Literal["PASS", "DENY", "NEEDS_HUMAN", "NOT_EVALUATED"]
Decision = Literal["APPROVE", "DENY", "NEEDS_HUMAN"]
SourceFormat = Literal["pdf", "txt"]

# Outcomes that count as "the rule fired". NOT_EVALUATED does not: it means a
# prerequisite was missing and is already reported by another check.
FIRING_OUTCOMES: frozenset[str] = frozenset({"DENY", "NEEDS_HUMAN"})


@dataclass(frozen=True)
class ServiceLine:
    """One billed service line on a claim."""

    line_no: int
    dos: date | None = None
    pos: str | None = None
    cpt: str | None = None
    modifier: str | None = None
    dx_pointer: str | None = None
    units: int | None = None
    charge: Decimal | None = None


@dataclass
class Claim:
    """A claim extracted from one uploaded PDF or TXT file."""

    claim_id: str | None
    source_file: str
    source_format: SourceFormat
    received_date: date | None = None
    freq_code: str | None = None
    member_id: str | None = None
    provider_id: str | None = None
    billing_npi: str | None = None
    rendering_npi: str | None = None
    place_of_service: str | None = None
    dos: date | None = None
    primary_dx: str | None = None
    secondary_dx: str | None = None
    prior_auth_number: str | None = None
    emergency: bool | None = None
    attachments: list[str] = field(default_factory=list)
    lines: list[ServiceLine] = field(default_factory=list)
    total_billed: Decimal | None = None


@dataclass(frozen=True)
class RuleResult:
    """The outcome of one check (or of intake, which uses check_no 0)."""

    check_no: int
    check_name: str
    outcome: Outcome
    rule_id: str | None = None
    reason_code: str | None = None
    detail: str = ""
    evidence: tuple[str, ...] = ()

    @property
    def fired(self) -> bool:
        """True when this result pushes the claim away from APPROVE."""
        return self.outcome in FIRING_OUTCOMES


def _unique_in_order(values: list[str | None]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


@dataclass
class TriageResult:
    """The final, explained decision for one claim."""

    claim_id: str
    decision: Decision
    results: list[RuleResult]
    explanation: str = ""
    advisories: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)

    @property
    def fired_results(self) -> list[RuleResult]:
        """Fired results in check order."""
        return sorted((r for r in self.results if r.fired), key=lambda r: r.check_no)

    @property
    def rules_fired(self) -> list[str]:
        """Rule IDs that fired, in check order, without duplicates."""
        return _unique_in_order([r.rule_id for r in self.fired_results])

    @property
    def reason_codes(self) -> list[str]:
        """Reason codes that fired, in check order, without duplicates."""
        return _unique_in_order([r.reason_code for r in self.fired_results])
