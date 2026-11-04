"""Stage 1: the reference workbook loader."""

from datetime import date
from pathlib import Path

import openpyxl
import pytest

from triage.models import RuleResult, TriageResult
from triage.reference import ReferenceData, WorkbookError, load_reference


@pytest.fixture(scope="module")
def ref(workbook_path: Path) -> ReferenceData:
    return load_reference(workbook_path)


def _copy_without(workbook_path: Path, tmp_path: Path, *sheets: str) -> Path:
    wb = openpyxl.load_workbook(workbook_path)
    for name in sheets:
        del wb[name]
    out = tmp_path / "modified.xlsx"
    wb.save(out)
    return out


# ------------------------------------------------------------------ real workbook


def test_members_loaded(ref: ReferenceData):
    assert len(ref.members) == 100
    m = ref.members["MBR-100042"]
    assert m.plan_id == "PLN-BRZ-HMO"
    assert m.termination_date == date(2026, 9, 28)
    assert m.premium_paid_through == date(2026, 9, 28)
    assert ref.members["MBR-100007"].termination_date is None


def test_provider_network_flags(ref: ReferenceData):
    assert len(ref.providers) == 15
    assert ref.providers["P-009"].network["GLD_PPO"] == "N"
    assert ref.providers["P-002"].network["SLV_PPO"] == "Y"
    assert ref.providers["P-002"].npi == "9000000002"
    assert ref.providers["P-007"].level5_pct == pytest.approx(0.79)


def test_icd10_codes_are_exact_text(ref: ReferenceData):
    assert "J06.9" in ref.icd10
    assert "J06.99" not in ref.icd10  # never auto-corrected
    assert "I10" in ref.icd10


def test_benefit_rules_prior_auth_flags(ref: ReferenceData):
    assert ref.benefit_rules[("PLN-SLV-PPO", "29881")].prior_auth_required == "Y"
    assert ref.benefit_rules[("PLN-SLV-PPO", "99213")].prior_auth_required == "N"
    assert ref.benefit_rules[("PLN-GLD-PPO", "30400")].prior_auth_required == "Y"


def test_prior_auth_log(ref: ReferenceData):
    assert len(ref.prior_auths) == 6
    pa = next(p for p in ref.prior_auths if p.pa_number == "PA-2026-06955")
    assert pa.cpt_code == "73721"
    assert pa.status == "Approved"
    pending = next(p for p in ref.prior_auths if p.pa_number == "PA-2026-07731")
    assert pending.valid_from is None and pending.valid_to is None


def test_claims_history(ref: ReferenceData):
    assert len(ref.history) == 20
    assert all(h.status == "Paid" for h in ref.history)
    h1001 = next(h for h in ref.history if h.history_claim_id == "H-1001")
    assert (h1001.member_id, h1001.billing_provider_id, h1001.dos, h1001.cpt_code) == (
        "MBR-100019", "P-003", date(2026, 10, 8), "99214",
    )


def test_optional_sheets_loaded(ref: ReferenceData):
    assert ref.cpt_allowed["99285"] == 520
    assert "M23.221" in ref.med_necessity["29881"]
    assert ref.benefit_usage["MBR-100093"] == (12, 12)
    assert ref.warnings == []


# ------------------------------------------------------------------ failure modes


def test_missing_required_sheet_names_the_sheet(workbook_path: Path, tmp_path: Path):
    broken = _copy_without(workbook_path, tmp_path, "Members")
    with pytest.raises(WorkbookError, match="Members"):
        load_reference(broken)


def test_missing_optional_sheet_only_warns(workbook_path: Path, tmp_path: Path):
    partial = _copy_without(workbook_path, tmp_path, "CPT_Codes")
    ref = load_reference(partial)
    assert ref.cpt_allowed == {}
    assert any("CPT_Codes" in w for w in ref.warnings)


def test_garbage_bytes_raise_workbook_error():
    with pytest.raises(WorkbookError, match="could not be opened"):
        load_reference(b"this is definitely not an xlsx file")


def test_claims_sheets_are_never_needed(workbook_path: Path, tmp_path: Path):
    # Claim data must come from the uploaded files, so the loader must work without these sheets.
    without_claims = _copy_without(workbook_path, tmp_path, "Claims", "Claim_Lines")
    assert len(load_reference(without_claims).members) == 100


def test_loads_from_bytes(workbook_path: Path):
    assert len(load_reference(workbook_path.read_bytes()).providers) == 15


# ------------------------------------------------------------------ model contract


def test_triage_result_properties_follow_check_order():
    results = [
        RuleResult(6, "Amount", "NEEDS_HUMAN", "AMT-01", "R901", "over limit"),
        RuleResult(4, "Prior authorization", "NEEDS_HUMAN", "PA-01", "R401", "no PA"),
        RuleResult(2, "Eligibility", "PASS", detail="active"),
        RuleResult(5, "Network", "NOT_EVALUATED", detail="plan unknown"),
    ]
    tr = TriageResult(claim_id="CLM-X", decision="NEEDS_HUMAN", results=results)
    assert tr.rules_fired == ["PA-01", "AMT-01"]
    assert tr.reason_codes == ["R401", "R901"]
    assert not results[3].fired
