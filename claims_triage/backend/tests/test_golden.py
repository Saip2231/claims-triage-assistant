"""Gate A: all 10 provided claims match the expected decisions (CLAUDE.md §6).

The brief asks for at least one test per decision type. Those are the three
named tests below. The parametrised test covers the full table.
"""

from pathlib import Path

import pytest

from triage.engine import triage_files
from triage.reference import load_reference

GOLDEN = {
    "CLM-2026-0001": ("APPROVE", [], []),
    "CLM-2026-0002": ("DENY", ["DUP-01"], ["R102"]),
    "CLM-2026-0003": ("NEEDS_HUMAN", ["PA-01", "AMT-01"], ["R401", "R901"]),
    "CLM-2026-0004": ("DENY", ["ELIG-01"], ["R101"]),
    "CLM-2026-0005": ("NEEDS_HUMAN", ["EMR-01"], ["R801"]),
    "CLM-2026-0006": ("APPROVE", [], []),
    "CLM-2026-0007": ("APPROVE", [], []),
    "CLM-2026-0008": ("NEEDS_HUMAN", ["PA-01"], ["R401"]),
    "CLM-2026-0009": ("NEEDS_HUMAN", ["VAL-01", "VAL-02"], ["R201", "R202"]),
    "CLM-2026-0010": ("APPROVE", [], []),
}


@pytest.fixture(scope="module")
def batch(claims_dir: Path, workbook_path: Path):
    files = [(p.name, p.read_bytes()) for p in sorted(claims_dir.iterdir()) if p.is_file()]
    results, warnings = triage_files(files, load_reference(workbook_path))
    return {r.claim_id: r for r in results}, warnings


def test_batch_has_exactly_ten_rows_and_no_warnings(batch):
    rows, warnings = batch
    assert sorted(rows) == sorted(GOLDEN)
    assert warnings == []


def test_pdf_and_txt_copies_are_merged(batch):
    rows, _ = batch
    for claim_id, row in rows.items():
        assert sorted(row.source_files) == [f"{claim_id}.pdf", f"{claim_id}.txt"]


def test_approve_example_0001(batch):
    assert batch[0]["CLM-2026-0001"].decision == "APPROVE"


def test_deny_example_0004(batch):
    row = batch[0]["CLM-2026-0004"]
    assert (row.decision, row.rules_fired, row.reason_codes) == ("DENY", ["ELIG-01"], ["R101"])


def test_needs_human_example_0009(batch):
    row = batch[0]["CLM-2026-0009"]
    assert row.decision == "NEEDS_HUMAN"
    assert row.reason_codes == ["R201", "R202"]


@pytest.mark.parametrize("claim_id", sorted(GOLDEN))
def test_golden_table(batch, claim_id):
    row = batch[0][claim_id]
    assert (row.decision, row.rules_fired, row.reason_codes) == GOLDEN[claim_id]
    assert len([r for r in row.results if r.check_no in range(1, 7)]) >= 6, "all six checks must run"
