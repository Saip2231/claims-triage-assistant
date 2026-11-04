"""Stage 3: the six checks, tested in isolation with in-memory data.

The last section also runs each check against the real sample files as a spot
check. The full decision table is tested in Stage 4.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.factories import DOS, approved_pa, make_claim, make_line, make_member, make_provider, make_ref, paid
from triage.checks import (
    ALL_CHECKS,
    check_amount,
    check_duplicate,
    check_eligibility,
    check_network,
    check_prior_auth,
    check_required_fields,
    network_column,
)
from triage.extract import extract_claim
from triage.reference import load_reference


def outcomes(results):
    return [(r.outcome, r.rule_id, r.reason_code) for r in results]


def test_clean_claim_passes_all_six_checks():
    claim, ref = make_claim(), make_ref()
    for check in ALL_CHECKS:
        results = check(claim, ref)
        assert len(results) == 1 and results[0].outcome == "PASS", check.__name__
        assert results[0].detail


# ------------------------------------------------------------------ check 1


def test_required_fields_missing_npi_fires_val01():
    results = check_required_fields(make_claim(rendering_npi=None), make_ref())
    assert outcomes(results) == [("NEEDS_HUMAN", "VAL-01", "R201")]
    assert "rendering provider NPI" in results[0].detail


def test_required_fields_invalid_dx_fires_val02_without_correcting():
    results = check_required_fields(make_claim(primary_dx="J06.99"), make_ref())
    assert outcomes(results) == [("NEEDS_HUMAN", "VAL-02", "R202")]
    assert "J06.99" in results[0].detail


def test_required_fields_can_fire_both_rules():
    results = check_required_fields(make_claim(rendering_npi=None, primary_dx="J06.99"), make_ref())
    assert [r.rule_id for r in results] == ["VAL-01", "VAL-02"]


def test_required_fields_invalid_secondary_dx():
    results = check_required_fields(make_claim(secondary_dx="ZZZ.9"), make_ref())
    assert outcomes(results) == [("NEEDS_HUMAN", "VAL-02", "R202")]


def test_required_fields_missing_line_charge_and_total():
    claim = make_claim(lines=[replace(make_line(), charge=None)], total_billed=None)
    detail = check_required_fields(claim, make_ref())[0].detail
    assert "charge on line 1" in detail and "total charge" in detail


# ------------------------------------------------------------------ check 2


def test_eligibility_terminated_before_dos_denies():
    ref = make_ref(members={"MBR-1": make_member(termination_date=date(2026, 9, 28),
                                                  premium_paid_through=date(2026, 9, 28))})
    results = check_eligibility(make_claim(dos=date(2026, 9, 30)), ref)
    assert outcomes(results) == [("DENY", "ELIG-01", "R101")]
    assert "2026-09-28" in results[0].detail


def test_eligibility_termination_on_dos_still_covered():
    ref = make_ref(members={"MBR-1": make_member(termination_date=DOS)})
    assert check_eligibility(make_claim(), ref)[0].outcome == "PASS"


def test_eligibility_premium_not_paid_through_dos_denies():
    ref = make_ref(members={"MBR-1": make_member(premium_paid_through=date(2026, 9, 30))})
    results = check_eligibility(make_claim(), ref)
    assert outcomes(results) == [("DENY", "ELIG-01", "R101")]
    assert "premium" in results[0].detail


def test_eligibility_not_yet_effective_denies():
    ref = make_ref(members={"MBR-1": make_member(effective_date=date(2026, 11, 1))})
    assert check_eligibility(make_claim(), ref)[0].outcome == "DENY"


def test_unknown_member_reported_once():
    claim, ref = make_claim(member_id="MBR-999999"), make_ref()
    assert outcomes(check_eligibility(claim, ref)) == [("NEEDS_HUMAN", "ELIG-01", "R203")]
    assert check_prior_auth(claim, ref)[0].outcome == "NOT_EVALUATED"
    assert check_network(claim, ref)[0].outcome == "NOT_EVALUATED"


def test_missing_dos_is_not_evaluated():
    assert check_eligibility(make_claim(dos=None), make_ref())[0].outcome == "NOT_EVALUATED"


# ------------------------------------------------------------------ check 3


def test_duplicate_of_paid_claim_denies_and_cites_original():
    results = check_duplicate(make_claim(), make_ref(history=[paid("H-1001")]))
    assert outcomes(results) == [("DENY", "DUP-01", "R102")]
    assert "H-1001" in results[0].detail


def test_duplicate_different_dos_is_not_duplicate():
    results = check_duplicate(make_claim(), make_ref(history=[paid("H-1002", dos=date(2026, 7, 22))]))
    assert results[0].outcome == "PASS"
    assert "H-1002" in results[0].detail


def test_duplicate_replacement_claim_is_not_duplicate():
    results = check_duplicate(make_claim(freq_code="7"), make_ref(history=[paid()]))
    assert results[0].outcome == "PASS"


def test_duplicate_ignores_unpaid_history():
    results = check_duplicate(make_claim(), make_ref(history=[paid(status="Denied")]))
    assert results[0].outcome == "PASS"


def test_duplicate_other_provider_is_not_duplicate():
    results = check_duplicate(make_claim(), make_ref(history=[paid(billing_provider_id="P-2")]))
    assert results[0].outcome == "PASS"


# ------------------------------------------------------------------ check 4


def surgery_claim():
    return make_claim(lines=[make_line(cpt="29881", charge="4800.00")], total_billed=Decimal("4800.00"))


def test_prior_auth_not_required_passes():
    assert check_prior_auth(make_claim(), make_ref())[0].outcome == "PASS"


def test_prior_auth_missing_fires_pa01():
    results = check_prior_auth(surgery_claim(), make_ref())
    assert outcomes(results) == [("NEEDS_HUMAN", "PA-01", "R401")]


def test_prior_auth_approved_and_in_date_passes():
    results = check_prior_auth(surgery_claim(), make_ref(prior_auths=[approved_pa()]))
    assert results[0].outcome == "PASS"
    assert "PA-1" in results[0].detail


def test_prior_auth_for_other_cpt_does_not_count():
    results = check_prior_auth(surgery_claim(), make_ref(prior_auths=[approved_pa("PA-MRI", cpt="73721")]))
    assert results[0].reason_code == "R401"
    assert "PA-MRI covers CPT 73721, not 29881" in results[0].detail


def test_prior_auth_out_of_date_range_does_not_count():
    pa = approved_pa(valid_from=date(2026, 11, 1), valid_to=date(2026, 12, 1))
    assert check_prior_auth(surgery_claim(), make_ref(prior_auths=[pa]))[0].reason_code == "R401"


def test_prior_auth_pending_does_not_count():
    pa = approved_pa(status="Pending - clinical information requested", valid_from=None, valid_to=None)
    results = check_prior_auth(surgery_claim(), make_ref(prior_auths=[pa]))
    assert results[0].reason_code == "R401"
    assert "Pending" in results[0].detail


def test_prior_auth_missing_benefit_rule_is_r203():
    claim = make_claim(lines=[make_line(cpt="12345")])
    assert outcomes(check_prior_auth(claim, make_ref())) == [("NEEDS_HUMAN", "PA-01", "R203")]


# ------------------------------------------------------------------ check 5


def test_network_column_name_follows_brief_hint():
    assert network_column("PLN-GLD-PPO") == "GLD_PPO"


def test_out_of_network_non_emergency_is_net01():
    ref = make_ref(providers={"P-1": make_provider(network={"SLV_PPO": "N"})})
    assert outcomes(check_network(make_claim(), ref)) == [("NEEDS_HUMAN", "NET-01", "R801")]


def test_out_of_network_emergency_is_emr01():
    ref = make_ref(providers={"P-1": make_provider(network={"SLV_PPO": "N"})})
    results = check_network(make_claim(emergency=True), ref)
    assert outcomes(results) == [("NEEDS_HUMAN", "EMR-01", "R801")]
    assert "balance billed" in results[0].detail


def test_unknown_provider_is_r203():
    assert check_network(make_claim(provider_id="P-404"), make_ref())[0].reason_code == "R203"


# ------------------------------------------------------------------ check 6


@pytest.mark.parametrize("total, outcome", [("10000.00", "PASS"), ("10000.01", "NEEDS_HUMAN"), ("140.00", "PASS")])
def test_amount_threshold(total, outcome):
    results = check_amount(make_claim(total_billed=Decimal(total)), make_ref())
    assert results[0].outcome == outcome
    if outcome != "PASS":
        assert (results[0].rule_id, results[0].reason_code) == ("AMT-01", "R901")


def test_amount_missing_total_is_not_evaluated():
    assert check_amount(make_claim(total_billed=None), make_ref())[0].outcome == "NOT_EVALUATED"


# ------------------------------------------------------------------ purity


def test_checks_do_not_mutate_inputs():
    claim, ref = make_claim(), make_ref(history=[paid()])
    before = (replace(claim), len(ref.history), dict(ref.members))
    for check in ALL_CHECKS:
        check(claim, ref)
    assert (claim, len(ref.history), ref.members) == before


# ------------------------------------------------------------------ spot checks on real files


@pytest.fixture(scope="module")
def real_ref(workbook_path: Path):
    return load_reference(workbook_path)


def fired(claims_dir: Path, real_ref, claim_id: str):
    path = claims_dir / f"{claim_id}.txt"
    claim = extract_claim(path.name, path.read_bytes())
    return [(r.rule_id, r.reason_code) for check in ALL_CHECKS for r in check(claim, real_ref) if r.fired]


@pytest.mark.parametrize("claim_id, expected", [
    ("CLM-2026-0001", []),
    ("CLM-2026-0002", [("DUP-01", "R102")]),
    ("CLM-2026-0003", [("PA-01", "R401"), ("AMT-01", "R901")]),
    ("CLM-2026-0004", [("ELIG-01", "R101")]),
    ("CLM-2026-0005", [("EMR-01", "R801")]),
    ("CLM-2026-0008", [("PA-01", "R401")]),
    ("CLM-2026-0009", [("VAL-01", "R201"), ("VAL-02", "R202")]),
])
def test_real_claims_fire_expected_rules(claims_dir: Path, real_ref, claim_id, expected):
    assert fired(claims_dir, real_ref, claim_id) == expected
