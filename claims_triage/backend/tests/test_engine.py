"""Stage 4: decision priority and batch robustness."""

from pathlib import Path

import pytest

from triage import engine
from triage.engine import combine, triage_files
from triage.models import RuleResult
from triage.reference import load_reference


def rr(check_no: int, outcome: str, rule_id: str | None = None, code: str | None = None) -> RuleResult:
    return RuleResult(check_no, f"check {check_no}", outcome, rule_id, code, "detail")


# ------------------------------------------------------------------ combine


def test_check1_failure_beats_a_deny():
    results = [rr(1, "NEEDS_HUMAN", "VAL-01", "R201"), rr(2, "DENY", "ELIG-01", "R101")]
    assert combine(results) == "NEEDS_HUMAN"


def test_deny_beats_needs_human():
    results = [rr(1, "PASS"), rr(3, "DENY", "DUP-01", "R102"), rr(6, "NEEDS_HUMAN", "AMT-01", "R901")]
    assert combine(results) == "DENY"


def test_needs_human_without_deny():
    assert combine([rr(1, "PASS"), rr(4, "NEEDS_HUMAN", "PA-01", "R401")]) == "NEEDS_HUMAN"


def test_all_pass_or_not_evaluated_approves():
    assert combine([rr(1, "PASS"), rr(2, "PASS"), rr(5, "NOT_EVALUATED")]) == "APPROVE"


# ------------------------------------------------------------------ batch robustness


@pytest.fixture(scope="module")
def ref(workbook_path: Path):
    return load_reference(workbook_path)


def read(claims_dir: Path, name: str) -> tuple[str, bytes]:
    return name, (claims_dir / name).read_bytes()


def test_unreadable_file_becomes_row_and_batch_continues(claims_dir, ref):
    rows, warnings = triage_files([("broken.pdf", b"junk"), read(claims_dir, "CLM-2026-0001.txt")], ref)
    by_id = {r.claim_id: r for r in rows}
    assert by_id["broken.pdf"].decision == "NEEDS_HUMAN"
    assert (by_id["broken.pdf"].rules_fired, by_id["broken.pdf"].reason_codes) == (["INTAKE-01"], ["R200"])
    assert by_id["CLM-2026-0001"].decision == "APPROVE"
    assert len(warnings) == 1


def test_unsupported_type_becomes_row(ref):
    rows, _ = triage_files([("notes.docx", b"hello")], ref)
    assert rows[0].reason_codes == ["R200"]
    assert "Unsupported file type" in rows[0].explanation


def test_file_without_claim_id_becomes_row(ref):
    rows, _ = triage_files([("random.txt", b"just some text")], ref)
    assert rows[0].claim_id == "random.txt"
    assert "No claim ID" in rows[0].explanation


def test_pdf_and_txt_of_same_claim_are_one_row(claims_dir, ref):
    rows, warnings = triage_files(
        [read(claims_dir, "CLM-2026-0004.pdf"), read(claims_dir, "CLM-2026-0004.txt")], ref)
    assert len(rows) == 1 and warnings == []
    assert rows[0].source_files == ["CLM-2026-0004.pdf", "CLM-2026-0004.txt"]
    assert rows[0].decision == "DENY"


def test_conflicting_copies_need_a_human(claims_dir, ref):
    name, data = read(claims_dir, "CLM-2026-0001.txt")
    edited = data.replace(b"140.00", b"999.00")
    rows, warnings = triage_files([(name, data), ("CLM-2026-0001-copy.txt", edited)], ref)
    assert len(rows) == 1
    row = rows[0]
    assert (row.decision, row.rules_fired, row.reason_codes) == ("NEEDS_HUMAN", ["INTAKE-02"], ["R204"])
    assert "total_billed" in row.explanation
    assert warnings


def test_unexpected_error_in_a_check_does_not_stop_the_batch(claims_dir, ref, monkeypatch):
    def boom(claim, ref):
        raise RuntimeError("simulated bug")

    monkeypatch.setattr(engine, "ALL_CHECKS", (boom,))
    rows, warnings = triage_files([read(claims_dir, "CLM-2026-0001.txt")], ref)
    assert rows[0].decision == "NEEDS_HUMAN"
    assert rows[0].reason_codes == ["R200"]
    assert warnings


def test_rows_are_sorted_by_claim_id(claims_dir, ref):
    rows, _ = triage_files([read(claims_dir, "CLM-2026-0010.txt"), read(claims_dir, "CLM-2026-0002.txt")], ref)
    assert [r.claim_id for r in rows] == ["CLM-2026-0002", "CLM-2026-0010"]
