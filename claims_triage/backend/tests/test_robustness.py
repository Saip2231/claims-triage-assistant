"""Stage 8: messy inputs must give a row or a clean error, never an escaped exception.

Edited claim variants are built in memory from the sample text. sample_data is never modified.
"""

import re
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from api import app
from triage.engine import triage_files
from triage.explain import TemplateExplainer
from triage.policy import parse_policy
from triage.reference import WorkbookError, load_reference

client = TestClient(app)


@pytest.fixture(scope="module")
def ref(workbook_path: Path):
    return load_reference(workbook_path)


@pytest.fixture(scope="module")
def explainer(ref, policy_path: Path):
    return TemplateExplainer(parse_policy(policy_path.read_bytes()), ref)


def txt(claims_dir: Path, claim_id: str) -> str:
    return (claims_dir / f"{claim_id}.txt").read_text(encoding="utf-8")


def one(files, ref, explainer):
    rows, warnings = triage_files(files, ref, explainer)
    assert len(rows) == 1, [r.claim_id for r in rows]
    return rows[0], warnings


def checks_by_no(row):
    return {r.check_no: r for r in row.results}


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ unreadable files


@pytest.mark.parametrize("name, data", [
    ("empty.txt", b""),
    ("empty.pdf", b""),
    ("blank-page.pdf", None),  # a valid PDF with no text, e.g. an image-only scan
    ("notes.docx", b"PK\x03\x04 not a claim"),
    ("no-extension", b"Claim ID : CLM-X"),
])
def test_unreadable_files_become_intake_rows(ref, explainer, name, data):
    row, warnings = one([(name, blank_pdf() if data is None else data)], ref, explainer)
    assert (row.decision, row.rules_fired, row.reason_codes) == ("NEEDS_HUMAN", ["INTAKE-01"], ["R200"])
    assert row.claim_id == name
    assert "Section 3.1" in row.explanation
    assert warnings


# ------------------------------------------------------------------ missing or malformed fields


def test_missing_member_id_is_val01_and_dependent_checks_are_skipped(claims_dir, ref, explainer):
    text = re.sub(r"Member ID\s*:.*\n", "", txt(claims_dir, "CLM-2026-0001"))
    row, _ = one([("CLM-2026-0001.txt", text.encode())], ref, explainer)
    assert row.decision == "NEEDS_HUMAN"
    assert row.rules_fired == ["VAL-01"]
    assert "member ID" in row.explanation
    checks = checks_by_no(row)
    assert [checks[n].outcome for n in (2, 3, 4, 5)] == ["NOT_EVALUATED"] * 4
    assert checks[6].outcome == "PASS"


def test_non_iso_date_is_treated_as_missing_not_guessed(claims_dir, ref, explainer):
    text = re.sub(r"(Date of service\s*:\s*)2026-10-14", r"\g<1>10/14/2026", txt(claims_dir, "CLM-2026-0001"))
    row, _ = one([("CLM-2026-0001.txt", text.encode())], ref, explainer)
    assert row.rules_fired == ["VAL-01"]
    assert "date of service" in row.explanation
    assert row.extracted["dos"] is None


def test_blank_diagnosis_is_val02(claims_dir, ref, explainer):
    text = txt(claims_dir, "CLM-2026-0001").replace(": J06.9", ": (blank)")
    row, _ = one([("CLM-2026-0001.txt", text.encode())], ref, explainer)
    assert row.reason_codes == ["R202"]


def test_unknown_member_needs_a_human_once(claims_dir, ref, explainer):
    text = txt(claims_dir, "CLM-2026-0001").replace("MBR-100007", "MBR-999999")
    row, _ = one([("CLM-2026-0001.txt", text.encode())], ref, explainer)
    assert (row.decision, row.rules_fired, row.reason_codes) == ("NEEDS_HUMAN", ["ELIG-01"], ["R203"])


def test_unknown_provider_needs_a_human(claims_dir, ref, explainer):
    text = txt(claims_dir, "CLM-2026-0001").replace("P-002", "P-404")
    row, _ = one([("CLM-2026-0001.txt", text.encode())], ref, explainer)
    assert row.decision == "NEEDS_HUMAN"
    assert "R203" in row.reason_codes


def test_replacement_claim_is_not_denied_as_duplicate(claims_dir, ref, explainer):
    text = re.sub(r"(Claim frequency code\s*:\s*)1", r"\g<1>7", txt(claims_dir, "CLM-2026-0002"))
    row, _ = one([("CLM-2026-0002.txt", text.encode())], ref, explainer)
    assert "DUP-01" not in row.rules_fired
    assert row.decision == "APPROVE"


# ------------------------------------------------------------------ encodings and duplicates


@pytest.mark.parametrize("variant", ["crlf", "bom", "latin1", "upper-ext"])
def test_text_variants_still_parse(claims_dir, ref, explainer, variant):
    text = txt(claims_dir, "CLM-2026-0004")
    name = "CLM-2026-0004.txt"
    if variant == "crlf":
        data = text.replace("\n", "\r\n").encode()
    elif variant == "bom":
        data = text.encode("utf-8-sig")
    elif variant == "latin1":
        data = text.replace("(synthetic)", "(synthétique)").encode("latin-1")
    else:
        data, name = text.encode(), "CLM-2026-0004.TXT"
    row, _ = one([(name, data)], ref, explainer)
    assert (row.claim_id, row.decision, row.reason_codes) == ("CLM-2026-0004", "DENY", ["R101"])


def test_same_file_uploaded_twice_is_one_row(claims_dir, ref, explainer):
    data = (claims_dir / "CLM-2026-0004.txt").read_bytes()
    row, warnings = one([("CLM-2026-0004.txt", data), ("CLM-2026-0004 (1).txt", data)], ref, explainer)
    assert row.decision == "DENY" and warnings == []
    assert len(row.source_files) == 2


def test_conflicting_copies_are_flagged_with_r204(claims_dir, ref, explainer):
    original = (claims_dir / "CLM-2026-0001.txt").read_bytes()
    edited = original.replace(b"140.00", b"999.00")
    row, _ = one([("CLM-2026-0001.txt", original), ("CLM-2026-0001-copy.txt", edited)], ref, explainer)
    assert (row.rules_fired, row.reason_codes) == (["INTAKE-02"], ["R204"])
    assert "Section 3.6" in row.explanation


def test_bad_file_does_not_affect_good_ones(claims_dir, ref, explainer):
    files = [(p.name, p.read_bytes()) for p in sorted(claims_dir.iterdir())] + [("broken.pdf", b"%PDF-1.4 junk")]
    rows, _ = triage_files(files, ref, explainer)
    assert len(rows) == 11
    assert sum(r.decision == "APPROVE" for r in rows) == 4


# ------------------------------------------------------------------ workbook problems


def test_workbook_missing_providers_sheet(workbook_path: Path, tmp_path: Path, claims_dir, policy_path):
    wb = openpyxl.load_workbook(workbook_path)
    del wb["Providers"]
    broken = tmp_path / "no_providers.xlsx"
    wb.save(broken)

    with pytest.raises(WorkbookError, match="Providers"):
        load_reference(broken)

    files = [
        ("claims", ("CLM-2026-0001.txt", (claims_dir / "CLM-2026-0001.txt").read_bytes(), "text/plain")),
        ("policy", ("policy_documents.pdf", policy_path.read_bytes(), "application/pdf")),
        ("workbook", ("claims_triage_dataset.xlsx", broken.read_bytes(), "application/octet-stream")),
    ]
    response = client.post("/api/triage", files=files)
    assert response.status_code == 400
    assert "Providers" in response.json()["detail"]


def test_workbook_missing_column(workbook_path: Path, tmp_path: Path):
    wb = openpyxl.load_workbook(workbook_path)
    ws = wb["Members"]
    for cell in ws[1]:
        if cell.value == "termination_date":
            cell.value = "term_dt"
    broken = tmp_path / "renamed_col.xlsx"
    wb.save(broken)
    with pytest.raises(WorkbookError, match="termination_date"):
        load_reference(broken)
