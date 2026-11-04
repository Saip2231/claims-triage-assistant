"""Runs the six checks, combines them into a decision, and triages a batch of files.

The flow for each claim file is:
    extract_claim -> run_checks (all six, always) -> combine (strict priority) -> explain

Robustness rules (CLAUDE.md §1.5, §4.2):
  * Every file is handled inside its own try/except, so one bad file never
    stops the batch. It becomes a NEEDS_HUMAN intake row instead.
  * The same claim ID uploaded twice (e.g. as PDF and TXT) becomes one row if
    the extracted fields are identical, or an INTAKE-02 / R204 row if they
    conflict.
  * Logs reference claims by claim ID only.
"""

from __future__ import annotations

import logging
from typing import Callable

from .checks import ALL_CHECKS
from .extract import ExtractionError, claim_fingerprint, extract_claim
from .models import Claim, Decision, RuleResult, TriageResult
from .reference import ReferenceData

log = logging.getLogger(__name__)

# (claim, results, decision) -> (explanation, advisories). The template explainer is plugged in in Stage 5.
Explainer = Callable[[Claim, list[RuleResult], Decision], tuple[str, list[str]]]

INTAKE_CHECK_NO = 0
INTAKE_NAME = "Intake"


# --------------------------------------------------------------------------- per claim


def run_checks(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Run ALL six checks in order and return every result, including passes."""
    return [result for check in ALL_CHECKS for result in check(claim, ref)]


def combine(results: list[RuleResult]) -> Decision:
    """Apply the brief's priority order to the full list of results.

    1. Check 1 (or intake) fired -> NEEDS_HUMAN
    2. else any DENY             -> DENY
    3. else any NEEDS_HUMAN      -> NEEDS_HUMAN
    4. else                      -> APPROVE
    """
    if any(r.fired and r.check_no in (INTAKE_CHECK_NO, 1) for r in results):
        return "NEEDS_HUMAN"
    if any(r.outcome == "DENY" for r in results):
        return "DENY"
    if any(r.outcome == "NEEDS_HUMAN" for r in results):
        return "NEEDS_HUMAN"
    return "APPROVE"


def placeholder_explainer(claim: Claim, results: list[RuleResult], decision: Decision) -> tuple[str, list[str]]:
    """Plain join of the fired details. Replaced by the policy-citing template explainer in Stage 5."""
    fired = [r.detail for r in results if r.fired]
    return (" ".join(fired) if fired else "All checks passed."), []


def triage_claim(claim: Claim, ref: ReferenceData, explainer: Explainer | None = None,
                 source_files: list[str] | None = None) -> TriageResult:
    """Run every check on one extracted claim and return the explained decision."""
    results = run_checks(claim, ref)
    decision = combine(results)
    explanation, advisories = (explainer or placeholder_explainer)(claim, results, decision)
    return TriageResult(
        claim_id=claim.claim_id or claim.source_file,
        decision=decision,
        results=results,
        explanation=explanation,
        advisories=advisories,
        source_files=source_files or [claim.source_file],
        extracted=claim_fingerprint(claim),
    )


def intake_result(claim_id: str, message: str, *, rule_id: str = "INTAKE-01", reason_code: str = "R200",
                  source_files: list[str] | None = None, extracted: dict | None = None) -> TriageResult:
    """A NEEDS_HUMAN row for a file or claim that could not go through the checks."""
    result = RuleResult(INTAKE_CHECK_NO, INTAKE_NAME, "NEEDS_HUMAN", rule_id, reason_code, message)
    return TriageResult(
        claim_id=claim_id,
        decision="NEEDS_HUMAN",
        results=[result],
        explanation=message,
        advisories=[],
        source_files=source_files or [claim_id],
        extracted=extracted or {},
    )


# --------------------------------------------------------------------------- batch


def _differing_fields(fingerprints: list[dict]) -> list[str]:
    first = fingerprints[0]
    return sorted({key for fp in fingerprints[1:] for key in first if fp.get(key) != first.get(key)})


def triage_files(files: list[tuple[str, bytes]], ref: ReferenceData,
                 explainer: Explainer | None = None) -> tuple[list[TriageResult], list[str]]:
    """Triage a batch of uploaded (filename, bytes) pairs.

    Returns the rows sorted by claim_id, plus user-facing warnings. Never
    raises because of a single bad file.
    """
    rows: list[TriageResult] = []
    warnings: list[str] = []
    by_claim_id: dict[str, list[Claim]] = {}

    # 1. Extract every file on its own.
    for name, data in files:
        try:
            claim = extract_claim(name, data)
        except ExtractionError as exc:
            warnings.append(str(exc))
            rows.append(intake_result(name, str(exc)))
            continue
        except Exception:
            log.exception("Unexpected error extracting %s", name)
            message = f"{name} could not be processed because of an unexpected error; please review it manually."
            warnings.append(message)
            rows.append(intake_result(name, message))
            continue
        if not claim.claim_id:
            message = f"No claim ID found in {name}; the file does not look like a claim form."
            warnings.append(message)
            rows.append(intake_result(name, message))
            continue
        by_claim_id.setdefault(claim.claim_id, []).append(claim)

    # 2. Dedupe by claim ID, then 3. triage each unique claim.
    for claim_id, claims in by_claim_id.items():
        names = [c.source_file for c in claims]
        fingerprints = [claim_fingerprint(c) for c in claims]
        if any(fp != fingerprints[0] for fp in fingerprints[1:]):
            fields = ", ".join(_differing_fields(fingerprints))
            message = (f"Claim {claim_id} was uploaded more than once ({', '.join(names)}) and the copies "
                       f"disagree on: {fields}. A reviewer must decide which document is correct.")
            warnings.append(message)
            rows.append(intake_result(claim_id, message, rule_id="INTAKE-02", reason_code="R204",
                                      source_files=names, extracted=fingerprints[0]))
            continue
        try:
            rows.append(triage_claim(claims[0], ref, explainer, source_files=names))
        except Exception:
            log.exception("Unexpected error triaging claim %s", claim_id)
            message = f"Claim {claim_id} could not be triaged because of an unexpected error; please review it manually."
            warnings.append(message)
            rows.append(intake_result(claim_id, message, source_files=names, extracted=fingerprints[0]))

    # Intake rows never reach the checks. If the explainer can word them (TemplateExplainer can), let it.
    explain_intake = getattr(explainer, "explain_intake", None)
    if explain_intake:
        for row in rows:
            if row.results and row.results[0].check_no == INTAKE_CHECK_NO:
                row.explanation = explain_intake(row)

    rows.sort(key=lambda r: r.claim_id)
    return rows, warnings
