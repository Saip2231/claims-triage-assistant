"""In-memory builders for check tests, so no Excel or claim file is needed.

The defaults describe a clean claim that passes all six checks.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from triage.models import Claim, ServiceLine
from triage.reference import (
    BenefitRule, HistoryClaim, Member, Plan, PriorAuth, Provider, ReferenceData,
)

DOS = date(2026, 10, 14)
PLAN = "PLN-SLV-PPO"


def make_line(line_no: int = 1, cpt: str = "99213", charge: str = "140.00", **overrides) -> ServiceLine:
    line = ServiceLine(line_no=line_no, dos=DOS, pos="11", cpt=cpt, modifier=None,
                       dx_pointer="A", units=1, charge=Decimal(charge))
    return replace(line, **overrides)


def make_claim(**overrides) -> Claim:
    claim = Claim(
        claim_id="CLM-TEST-0001", source_file="test.txt", source_format="txt",
        received_date=date(2026, 10, 20), freq_code="1",
        member_id="MBR-1", provider_id="P-1", billing_npi="9000000001", rendering_npi="9000000001",
        place_of_service="11", dos=DOS, primary_dx="J06.9", secondary_dx=None,
        prior_auth_number=None, emergency=False, attachments=[],
        lines=[make_line()], total_billed=Decimal("140.00"),
    )
    return replace(claim, **overrides)


def make_member(**overrides) -> Member:
    member = Member(member_id="MBR-1", plan_id=PLAN, effective_date=date(2026, 1, 1),
                    termination_date=None, premium_paid_through=date(2026, 10, 31), status="Active")
    return replace(member, **overrides)


def make_provider(**overrides) -> Provider:
    provider = Provider(provider_id="P-1", npi="9000000001",
                        network={"BRZ_HMO": "Y", "SLV_PPO": "Y", "GLD_PPO": "Y", "PLT_EPO": "Y"})
    return replace(provider, **overrides)


def make_ref(**overrides) -> ReferenceData:
    ref = ReferenceData(
        members={"MBR-1": make_member()},
        providers={"P-1": make_provider()},
        history=[],
        prior_auths=[],
        benefit_rules={
            (PLAN, "99213"): BenefitRule(PLAN, "99213", "Covered", "N"),
            (PLAN, "29881"): BenefitRule(PLAN, "29881", "Covered with prior authorization", "Y"),
        },
        icd10=frozenset({"J06.9", "M25.561", "I10"}),
        plans={PLAN: Plan(PLAN, "Synthetic Silver PPO", "PPO", "30")},
    )
    return replace(ref, **overrides)


def paid(history_id: str = "H-1", dos: date = DOS, cpt: str = "99213", **overrides) -> HistoryClaim:
    row = HistoryClaim(history_claim_id=history_id, member_id="MBR-1", billing_provider_id="P-1",
                       dos=dos, cpt_code=cpt, status="Paid", paid_date=date(2026, 10, 18))
    return replace(row, **overrides)


def approved_pa(pa_number: str = "PA-1", cpt: str = "29881", **overrides) -> PriorAuth:
    pa = PriorAuth(pa_number=pa_number, member_id="MBR-1", cpt_code=cpt, status="Approved",
                   valid_from=date(2026, 10, 1), valid_to=date(2026, 12, 1))
    return replace(pa, **overrides)
