"""Stage 5: policy parsing, template explanations and reviewer notes."""

import re
from pathlib import Path

import pytest

from tests.test_golden import GOLDEN
from triage.advisories import advisory_ids
from triage.engine import triage_files
from triage.explain import TemplateExplainer
from triage.policy import parse_policy
from triage.reference import load_reference

EXPECTED_SECTIONS = {
    "CLM-2026-0001": ["3.2"],
    "CLM-2026-0002": ["3.3", "2.8"],
    "CLM-2026-0003": ["2.5", "3.6"],
    "CLM-2026-0004": ["2.1", "2.8"],
    "CLM-2026-0005": ["2.3", "2.4"],
    "CLM-2026-0006": ["3.2"],
    "CLM-2026-0007": ["3.2"],
    "CLM-2026-0008": ["2.5"],
    "CLM-2026-0009": ["3.1"],
    "CLM-2026-0010": ["3.2"],
}

GOLDEN_ADVISORIES = {
    "CLM-2026-0001": set(),
    "CLM-2026-0002": set(),
    "CLM-2026-0003": {"MN-01", "CHG-01"},
    "CLM-2026-0004": set(),
    "CLM-2026-0005": {"CHG-01"},
    "CLM-2026-0006": {"BUN-01"},
    "CLM-2026-0007": {"EM-01"},
    "CLM-2026-0008": {"EXC-01", "MN-01"},
    "CLM-2026-0009": set(),
    "CLM-2026-0010": {"LIM-01"},
}

# Birth years of the 10 sample members: they must never appear in an explanation.
BIRTH_YEARS = ["1985", "1971", "1972", "1990", "1968", "1964", "1993", "1996", "1980", "1988"]


@pytest.fixture(scope="module")
def ref(workbook_path: Path):
    return load_reference(workbook_path)


@pytest.fixture(scope="module")
def policy(policy_path: Path):
    return parse_policy(policy_path.read_bytes())


def run(claims_dir: Path, ref, policy):
    files = [(p.name, p.read_bytes()) for p in sorted(claims_dir.iterdir()) if p.is_file()]
    rows, _ = triage_files(files, ref, explainer=TemplateExplainer(policy, ref))
    return {r.claim_id: r for r in rows}


@pytest.fixture(scope="module")
def rows(claims_dir: Path, ref, policy):
    return run(claims_dir, ref, policy)


# ------------------------------------------------------------------ policy parsing


def test_policy_sections_parsed(policy):
    assert policy.parsed_ok, policy.warning
    assert policy.sections["2.1"].title == "Eligibility"
    assert policy.sections["3.3"].title == "Duplicates"
    assert policy.cite("2.1") == "Section 2.1 Eligibility"
    for number in ("2.5", "3.6", "2.8", "3.1"):
        assert number in policy.sections


@pytest.mark.parametrize("section, keyword", [
    ("2.1", "termination date"),
    ("2.3", "out-of-network"),
    ("2.4", "require human review"),
    ("2.5", "pended"),
    ("3.1", "pend and return"),
    ("3.1", "infer"),
    ("3.3", "paid claim"),
    ("3.6", "Escalate to human"),
])
def test_every_cited_keyword_is_found_in_the_policy(policy, section, keyword):
    quote = policy.quote(section, keyword)
    assert quote and keyword.lower() in quote.lower()


def test_garbage_policy_falls_back_to_known_titles(claims_dir, ref):
    broken = parse_policy(b"not a pdf")
    assert not broken.parsed_ok and broken.warning
    rows = run(claims_dir, ref, broken)
    assert "Section 2.1 Eligibility" in rows["CLM-2026-0004"].explanation


def test_missing_policy_falls_back(ref):
    assert parse_policy(None).warning


# ------------------------------------------------------------------ explanations


@pytest.mark.parametrize("claim_id", sorted(EXPECTED_SECTIONS))
def test_explanation_cites_expected_sections(rows, claim_id):
    text = rows[claim_id].explanation
    assert text.startswith(claim_id)
    for number in EXPECTED_SECTIONS[claim_id]:
        assert f"Section {number} " in text, f"{claim_id} should cite Section {number}: {text}"


@pytest.mark.parametrize("claim_id", [c for c, (d, _, _) in GOLDEN.items() if d != "APPROVE"])
def test_non_approvals_quote_the_policy(rows, claim_id):
    assert re.search(r'Policy basis: Section \d\.\d+ [^"]+ – "', rows[claim_id].explanation)


def test_denials_mention_appeal_rights(rows):
    for claim_id in ("CLM-2026-0002", "CLM-2026-0004"):
        assert "appeal" in rows[claim_id].explanation and "180 days" in rows[claim_id].explanation


def test_explanations_never_contain_personal_details(rows):
    for row in rows.values():
        for year in BIRTH_YEARS:
            assert not re.search(rf"\b{year}\b", row.explanation), (row.claim_id, year)
        assert not re.search(r"\b(male|female|year-old)\b", row.explanation, re.IGNORECASE), row.claim_id


def test_intake_rows_are_explained_with_a_citation(ref, policy):
    rows, _ = triage_files([("notes.docx", b"x")], ref, explainer=TemplateExplainer(policy, ref))
    assert "Section 3.1" in rows[0].explanation
    assert "Unsupported file type" in rows[0].explanation


# ------------------------------------------------------------------ advisories


@pytest.mark.parametrize("claim_id", sorted(GOLDEN_ADVISORIES))
def test_golden_advisories(rows, claim_id):
    assert advisory_ids(rows[claim_id].advisories) == GOLDEN_ADVISORIES[claim_id]


@pytest.mark.parametrize("claim_id", sorted(GOLDEN))
def test_advisories_never_change_the_decision(rows, claim_id):
    row = rows[claim_id]
    assert (row.decision, row.rules_fired, row.reason_codes) == GOLDEN[claim_id]


def test_reviewer_notes_are_labelled_in_the_explanation(rows):
    text = rows["CLM-2026-0006"].explanation
    assert "Reviewer notes (do not change this decision): BUN-01" in text
    assert rows["CLM-2026-0006"].decision == "APPROVE"
