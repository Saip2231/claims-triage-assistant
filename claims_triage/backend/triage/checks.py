"""The six triage checks, written as pure functions that work like tools.

Each check has the signature `check_x(claim, ref) -> list[RuleResult]` and:
  * reads only its arguments: no I/O, no globals that change, no LLM;
  * always returns at least one result, a PASS with a readable detail when
    nothing is wrong, so the UI can show a full six-step timeline;
  * returns NOT_EVALUATED when a prerequisite is missing that another check
    already reports, so one root cause is reported once.

The decision is NOT made here. engine.combine() applies the priority order.
Semantics follow CLAUDE.md §4.2 and the policy sections noted on each check.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from .models import Claim, Outcome, RuleResult
from .reference import Member, ReferenceData

CHECK_NAMES: dict[int, str] = {
    1: "Required fields",
    2: "Eligibility",
    3: "Duplicate",
    4: "Prior authorization",
    5: "Network",
    6: "Amount",
}
AMOUNT_LIMIT = Decimal("10000")
NOT_FOUND = "R203"  # our own code: a reference record is missing from the workbook


# --------------------------------------------------------------------------- result helpers


def _pass(check_no: int, detail: str, evidence: tuple[str, ...] = ()) -> RuleResult:
    return RuleResult(check_no, CHECK_NAMES[check_no], "PASS", None, None, detail, evidence)


def _skip(check_no: int, detail: str) -> RuleResult:
    return RuleResult(check_no, CHECK_NAMES[check_no], "NOT_EVALUATED", None, None, detail)


def _fire(
    check_no: int, outcome: Outcome, rule_id: str, reason_code: str, detail: str,
    evidence: tuple[str, ...] = (),
) -> RuleResult:
    return RuleResult(check_no, CHECK_NAMES[check_no], outcome, rule_id, reason_code, detail, evidence)


def _money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _known_member(claim: Claim, ref: ReferenceData) -> Member | None:
    return ref.members.get(claim.member_id) if claim.member_id else None


def _cpts(claim: Claim) -> list[str]:
    """The claim's CPT codes in line order, without duplicates."""
    seen: list[str] = []
    for line in claim.lines:
        if line.cpt and line.cpt not in seen:
            seen.append(line.cpt)
    return seen


# --------------------------------------------------------------------------- check 1


def check_required_fields(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 1 (Policy §3.1): required fields present (VAL-01) and diagnosis codes valid (VAL-02)."""
    missing: list[str] = []
    if not claim.member_id:
        missing.append("member ID")
    if not claim.provider_id:
        missing.append("billing provider ID")
    if not claim.rendering_npi:
        missing.append("rendering provider NPI")
    if not claim.dos:
        missing.append("date of service")
    if not claim.lines:
        missing.append("service lines")
    for line in claim.lines:
        if not line.cpt:
            missing.append(f"CPT code on line {line.line_no}")
        if line.charge is None:
            missing.append(f"charge on line {line.line_no}")
    if claim.total_billed is None:
        missing.append("total charge")

    results: list[RuleResult] = []
    if missing:
        results.append(_fire(
            1, "NEEDS_HUMAN", "VAL-01", "R201",
            f"Missing required field(s): {', '.join(missing)}.",
            ("claim file",),
        ))

    if not claim.primary_dx:
        results.append(_fire(
            1, "NEEDS_HUMAN", "VAL-02", "R202",
            "No primary diagnosis code on the claim.", ("claim file",),
        ))
    else:
        codes = [c for c in (claim.primary_dx, claim.secondary_dx) if c]
        invalid = [c for c in codes if c not in ref.icd10]
        if invalid:
            results.append(_fire(
                1, "NEEDS_HUMAN", "VAL-02", "R202",
                f"Diagnosis code(s) {', '.join(invalid)} not found in the ICD-10 table "
                "(codes are never auto-corrected).",
                ("ICD10_Codes.icd10_code",),
            ))

    return results or [_pass(
        1, f"All required fields present; diagnosis {claim.primary_dx} is valid.",
        ("ICD10_Codes.icd10_code",),
    )]


# --------------------------------------------------------------------------- check 2


def check_eligibility(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 2 (Policy §2.1): coverage in force on the date of service (ELIG-01 → DENY)."""
    if not claim.member_id or not claim.dos:
        return [_skip(2, "Not evaluated: member ID or date of service is missing (see required fields).")]
    member = ref.members.get(claim.member_id)
    if member is None:
        return [_fire(
            2, "NEEDS_HUMAN", "ELIG-01", NOT_FOUND,
            f"Member {claim.member_id} not found in reference data; eligibility cannot be confirmed.",
            ("Members.member_id",),
        )]
    if member.effective_date is None:
        return [_fire(
            2, "NEEDS_HUMAN", "ELIG-01", NOT_FOUND,
            f"Member {member.member_id} has no coverage effective date on record.",
            ("Members.effective_date",),
        )]

    dos: date = claim.dos
    problems: list[str] = []
    if member.effective_date > dos:
        problems.append(f"coverage starts {member.effective_date}, after the date of service")
    if member.termination_date and member.termination_date < dos:
        reason = f" ({member.termination_reason})" if member.termination_reason else ""
        problems.append(f"coverage ended {member.termination_date}{reason}")
    if member.premium_paid_through and member.premium_paid_through < dos:
        problems.append(f"premium paid only through {member.premium_paid_through}")

    evidence = ("Members.effective_date", "Members.termination_date", "Members.premium_paid_through")
    if problems:
        return [_fire(
            2, "DENY", "ELIG-01", "R101",
            f"Coverage not in force on the date of service {dos}: {'; '.join(problems)}.",
            evidence,
        )]
    return [_pass(2, f"Member {member.member_id} coverage in force on {dos} (plan {member.plan_id}).", evidence)]


# --------------------------------------------------------------------------- check 3


def check_duplicate(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 3 (Policy §3.3): not a duplicate of a PAID claim (DUP-01 → DENY)."""
    if not (claim.member_id and claim.provider_id and claim.dos and claim.lines):
        return [_skip(3, "Not evaluated: member, provider, date of service or service lines missing.")]
    if claim.freq_code in ("7", "8"):
        kind = "Replacement" if claim.freq_code == "7" else "Void"
        return [_pass(3, f"{kind} claim (frequency code {claim.freq_code}) – adjusts an original, not a duplicate.")]
    if claim.freq_code != "1":
        shown = claim.freq_code or "missing"
        return [_pass(3, f"Frequency code is {shown}; the duplicate rule applies only to original claims (code 1).")]

    cpts = set(_cpts(claim))
    same_member_provider = [
        h for h in ref.history
        if (h.status or "").lower() == "paid"
        and h.member_id == claim.member_id
        and h.billing_provider_id == claim.provider_id
    ]
    matches = [h for h in same_member_provider if h.dos == claim.dos and h.cpt_code in cpts]
    evidence = ("Claims_History",)
    if matches:
        cited = "; ".join(
            f"{h.history_claim_id} (CPT {h.cpt_code}, DOS {h.dos}, paid {h.paid_date})" for h in matches
        )
        return [_fire(3, "DENY", "DUP-01", "R102", f"Duplicate of previously paid claim {cited}.", evidence)]

    other_dates = [h.history_claim_id for h in same_member_provider if h.dos != claim.dos and h.cpt_code in cpts]
    note = f" ({', '.join(other_dates)} is on a different date of service, so not a duplicate)" if other_dates else ""
    return [_pass(3, f"No paid claim with the same member, provider, date of service and CPT{note}.", evidence)]


# --------------------------------------------------------------------------- check 4


def _why_not_valid(ref: ReferenceData, member_id: str, cpt: str, dos: date) -> list[str]:
    """Explain why nearby authorizations for this member do not satisfy the PA rule."""
    reasons = []
    for pa in ref.prior_auths:
        if pa.member_id != member_id:
            continue
        approved = (pa.status or "").lower() == "approved"
        if pa.cpt_code == cpt and not approved:
            reasons.append(f"{pa.pa_number} is {pa.status}")
        elif pa.cpt_code != cpt and approved:
            reasons.append(f"{pa.pa_number} covers CPT {pa.cpt_code}, not {cpt}")
        elif pa.cpt_code == cpt and approved:
            reasons.append(f"{pa.pa_number} is valid {pa.valid_from} to {pa.valid_to}, which does not cover {dos}")
    return reasons


def _covering_pa(ref: ReferenceData, member_id: str, cpt: str, dos: date):
    for pa in ref.prior_auths:
        if (
            pa.member_id == member_id
            and pa.cpt_code == cpt
            and (pa.status or "").lower() == "approved"
            and pa.valid_from is not None and pa.valid_to is not None
            and pa.valid_from <= dos <= pa.valid_to
        ):
            return pa
    return None


def check_prior_auth(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 4 (Policy §2.5): an approved PA covers each service that needs one (PA-01 → NEEDS_HUMAN)."""
    member = _known_member(claim, ref)
    if member is None or not claim.dos:
        return [_skip(4, "Not evaluated: member unknown or date of service missing (reported elsewhere).")]
    if not member.plan_id:
        return [_fire(4, "NEEDS_HUMAN", "PA-01", NOT_FOUND,
                      f"Member {member.member_id} has no plan on record.", ("Members.plan_id",))]

    no_rule: list[str] = []
    needs_pa: list[str] = []
    covered: list[str] = []
    why: list[str] = []
    for cpt in _cpts(claim):
        rule = ref.benefit_rules.get((member.plan_id, cpt))
        if rule is None:
            no_rule.append(cpt)
            continue
        if rule.prior_auth_required != "Y":
            continue
        pa = _covering_pa(ref, member.member_id, cpt, claim.dos)
        if pa:
            covered.append(f"{pa.pa_number} covers CPT {cpt}")
        else:
            needs_pa.append(cpt)
            why.extend(_why_not_valid(ref, member.member_id, cpt, claim.dos))

    results: list[RuleResult] = []
    if no_rule:
        results.append(_fire(
            4, "NEEDS_HUMAN", "PA-01", NOT_FOUND,
            f"No benefit rule for plan {member.plan_id} and CPT {', '.join(no_rule)}.",
            ("Benefit_Rules",),
        ))
    if needs_pa:
        detail = f"CPT {', '.join(needs_pa)} requires prior authorization under plan {member.plan_id}, " \
                 f"and no approved authorization covers {claim.dos}."
        if why:
            detail += f" On file: {'; '.join(why)}."
        results.append(_fire(4, "NEEDS_HUMAN", "PA-01", "R401", detail,
                             ("Benefit_Rules.prior_auth_required", "Prior_Auth_Log")))
    if results:
        return results
    if covered:
        return [_pass(4, f"Approved prior authorization on file: {'; '.join(covered)}.", ("Prior_Auth_Log",))]
    return [_pass(4, f"No prior authorization required for CPT {', '.join(_cpts(claim))} "
                     f"under plan {member.plan_id}.", ("Benefit_Rules.prior_auth_required",))]


# --------------------------------------------------------------------------- check 5


def network_column(plan_id: str) -> str:
    """'PLN-GLD-PPO' -> 'GLD_PPO' (the brief's hint for the in_network_* column)."""
    return plan_id.removeprefix("PLN-").replace("-", "_")


def check_network(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 5 (Policy §2.3/§2.4): provider in-network for the member's plan (R801 → NEEDS_HUMAN)."""
    member = _known_member(claim, ref)
    if member is None or not member.plan_id or not claim.provider_id:
        return [_skip(5, "Not evaluated: member plan or provider unknown (reported elsewhere).")]

    rule_id = "EMR-01" if claim.emergency is True else "NET-01"
    provider = ref.providers.get(claim.provider_id)
    if provider is None:
        return [_fire(5, "NEEDS_HUMAN", rule_id, NOT_FOUND,
                      f"Provider {claim.provider_id} not found in reference data.", ("Providers.provider_id",))]

    column = network_column(member.plan_id)
    evidence = (f"Providers.in_network_{column}",)
    flag = provider.network.get(column)
    if flag is None:
        return [_fire(5, "NEEDS_HUMAN", rule_id, NOT_FOUND,
                      f"No in_network_{column} column for plan {member.plan_id}.", evidence)]
    if flag == "Y":
        return [_pass(5, f"Provider {provider.provider_id} is in-network for plan {member.plan_id}.", evidence)]

    detail = f"Provider {provider.provider_id} is out-of-network for plan {member.plan_id}."
    if rule_id == "EMR-01":
        detail += (" Out-of-network emergency: in-network cost sharing applies, the member must not be "
                   "balance billed, and human review is required.")
    return [_fire(5, "NEEDS_HUMAN", rule_id, "R801", detail, evidence)]


# --------------------------------------------------------------------------- check 6


def check_amount(claim: Claim, ref: ReferenceData) -> list[RuleResult]:
    """Check 6 (Policy §3.6): total billed at most $10,000 (AMT-01 → NEEDS_HUMAN)."""
    if claim.total_billed is None:
        return [_skip(6, "Not evaluated: total charge missing (see required fields).")]
    if claim.total_billed > AMOUNT_LIMIT:
        return [_fire(6, "NEEDS_HUMAN", "AMT-01", "R901",
                      f"Total billed {_money(claim.total_billed)} exceeds the {_money(AMOUNT_LIMIT)} "
                      "automatic limit; senior review required.", ("claim file",))]
    return [_pass(6, f"Total billed {_money(claim.total_billed)} is within the {_money(AMOUNT_LIMIT)} limit.")]


ALL_CHECKS: tuple[Callable[[Claim, ReferenceData], list[RuleResult]], ...] = (
    check_required_fields,
    check_eligibility,
    check_duplicate,
    check_prior_auth,
    check_network,
    check_amount,
)
