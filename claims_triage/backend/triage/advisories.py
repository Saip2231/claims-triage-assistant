"""Reviewer notes from the wider policy. They NEVER change the decision.

The brief defines six checks, and the decision follows only those. The policy
pack has more rules that matter for these claims (bundling, E/M pattern,
behavioral-health limits, cosmetic exclusion, medical necessity, charge
outliers). We surface them as deterministic notes for the human reviewer,
which is honest about what the six checks miss without silently changing the
required behaviour.

Each note starts with its rule ID followed by ':' (e.g. 'BUN-01: ...').
A missing optional workbook sheet just means that note is skipped.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .models import Claim, ServiceLine
from .reference import ReferenceData

PANEL, PANEL_COMPONENTS = "80053", ("82947", "82565")
LEVEL5_EM = "99215"
PSYCHOTHERAPY = ("90834", "90837")
COSMETIC_DX = "Z41.1"
_ICD_CODE = re.compile(r"^[A-Z]\d{2}(\.[A-Z0-9]{1,4})?$")


def _money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _line_dx(claim: Claim, line: ServiceLine) -> str | None:
    """The diagnosis a line points to: A = primary, B = secondary."""
    return claim.secondary_dx if line.dx_pointer == "B" else claim.primary_dx


def bundling(claim: Claim, ref: ReferenceData) -> list[str]:
    cpts = [line.cpt for line in claim.lines]
    components = [c for c in PANEL_COMPONENTS if c in cpts]
    if PANEL not in cpts or not components:
        return []
    return [f"BUN-01: Line(s) {', '.join(components)} are components of the comprehensive metabolic panel "
            f"{PANEL} billed by the same provider on the same date and are not separately payable "
            "(Section 3.4 Bundling); only those lines would be denied."]


def em_pattern(claim: Claim, ref: ReferenceData) -> list[str]:
    if not any(line.cpt == LEVEL5_EM for line in claim.lines):
        return []
    provider = ref.providers.get(claim.provider_id or "")
    if provider is None or provider.level5_pct is None or not provider.peer_median_level5_pct:
        return []
    rate, peer = provider.level5_pct, provider.peer_median_level5_pct
    if rate >= 0.40 and rate >= 3 * peer:
        return [f"EM-01: Provider {provider.provider_id} bills level-5 visits ({LEVEL5_EM}) in {rate:.0%} of "
                f"office visits vs a peer median of {peer:.0%}; route to Payment Integrity "
                "(Section 3.5 E/M Level Review). Any down-coding is a human decision."]
    return []


def behavioral_limit(claim: Claim, ref: ReferenceData) -> list[str]:
    if not any(line.cpt in PSYCHOTHERAPY for line in claim.lines):
        return []
    usage = ref.benefit_usage.get(claim.member_id or "")
    if usage is None:
        return []
    used, limit = usage
    if limit is not None and used >= limit:
        return [f"LIM-01: Psychotherapy visits already used this plan year: {used} of {limit}, so this visit "
                "exceeds the annual limit. It must go to Clinical/Compliance parity review and must not be "
                "denied automatically (Section 2.7 Behavioral Health)."]
    return []


def cosmetic(claim: Claim, ref: ReferenceData) -> list[str]:
    if COSMETIC_DX not in (claim.primary_dx, claim.secondary_dx):
        return []
    return [f"EXC-01: Diagnosis {COSMETIC_DX} (encounter for cosmetic surgery) indicates a cosmetic service, "
            "which the policy excludes (Section 2.6 Exclusions); a clear exclusion of $10,000 or less may be "
            "denied automatically under Section 3.6."]


def medical_necessity(claim: Claim, ref: ReferenceData) -> list[str]:
    notes = []
    for line in claim.lines:
        mapped = ref.med_necessity.get(line.cpt or "")
        if not mapped:
            continue
        codes = [c.strip() for c in mapped.split(";") if c.strip()]
        # Entries such as "Any" or free text are not a code list, so they are not checked.
        if not codes or not all(_ICD_CODE.match(c) for c in codes):
            continue
        dx = _line_dx(claim, line)
        if dx and dx not in codes:
            notes.append(f"MN-01: Diagnosis {dx} does not support CPT {line.cpt} under the medical necessity map "
                         f"(supporting: {', '.join(codes)}); a licensed clinician must review, never an automatic denial.")
    return notes


def charge_outliers(claim: Claim, ref: ReferenceData) -> list[str]:
    parts = []
    for line in claim.lines:
        allowed = ref.cpt_allowed.get(line.cpt or "")
        if allowed is None or line.charge is None:
            continue
        units = line.units or 1
        limit = allowed * units * 3
        if line.charge > limit:
            parts.append(f"{line.cpt} billed {_money(line.charge)} vs {_money(allowed * units)} allowed")
    if not parts:
        return []
    return [f"CHG-01: Billed charge is more than 3x the in-network allowed amount ({'; '.join(parts)}); "
            "informational only, cost sharing always uses the allowed amount (Section 2.2)."]


ADVISORY_RULES = (bundling, em_pattern, behavioral_limit, cosmetic, medical_necessity, charge_outliers)


def compute_advisories(claim: Claim, ref: ReferenceData) -> list[str]:
    """All reviewer notes for a claim, in a fixed order."""
    return [note for rule in ADVISORY_RULES for note in rule(claim, ref)]


def advisory_ids(advisories: list[str]) -> set[str]:
    """{'BUN-01', ...}: the rule IDs of a list of notes."""
    return {note.split(":", 1)[0] for note in advisories}
