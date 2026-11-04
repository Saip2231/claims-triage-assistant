"""Stage 6: the HTTP API and its error matrix (CLAUDE.md §4.4)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app
from triage.engine import triage_files
from triage.explain import TemplateExplainer
from triage.export import to_csv
from triage.policy import parse_policy
from triage.reference import load_reference

client = TestClient(app)


def claim_parts(claims_dir: Path, names: list[str] | None = None):
    paths = sorted(claims_dir.iterdir()) if names is None else [claims_dir / n for n in names]
    return [("claims", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths]


def part(field: str, path: Path, name: str | None = None, data: bytes | None = None):
    return (field, (name or path.name, path.read_bytes() if data is None else data, "application/octet-stream"))


@pytest.fixture(scope="module")
def full_upload(claims_dir: Path, policy_path: Path, workbook_path: Path):
    return claim_parts(claims_dir) + [part("policy", policy_path), part("workbook", workbook_path)]


@pytest.fixture(scope="module")
def happy(full_upload):
    response = client.post("/api/triage", files=full_upload)
    assert response.status_code == 200, response.text
    return response.json()


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


# ------------------------------------------------------------------ happy path


def test_happy_path_summary_and_rows(happy):
    assert happy["summary"] == {"total": 10, "APPROVE": 4, "DENY": 2, "NEEDS_HUMAN": 4}
    assert len(happy["results"]) == 10
    assert happy["warnings"] == []


def test_every_result_lists_all_six_checks(happy):
    for result in happy["results"]:
        # A check may return more than one result (CLM-2026-0009 fires both VAL-01 and VAL-02),
        # so assert that every check ran, in order, rather than exactly six entries.
        numbers = [c["check_no"] for c in result["checks"]]
        assert numbers == sorted(numbers) and set(numbers) == {1, 2, 3, 4, 5, 6}, result["claim_id"]
        assert result["explanation"].startswith(result["claim_id"])
        assert sorted(result["source_files"]) == [f"{result['claim_id']}.pdf", f"{result['claim_id']}.txt"]


def test_result_fields_for_a_denial(happy):
    row = next(r for r in happy["results"] if r["claim_id"] == "CLM-2026-0004")
    assert (row["decision"], row["rules_fired"], row["reason_codes"]) == ("DENY", ["ELIG-01"], ["R101"])
    assert row["extracted"]["member_id"] == "MBR-100042"
    assert "birth_year" not in row["extracted"] and "sex" not in row["extracted"]


def test_api_csv_matches_cli_csv(happy, claims_dir, policy_path, workbook_path):
    ref = load_reference(workbook_path)
    files = [(p.name, p.read_bytes()) for p in sorted(claims_dir.iterdir())]
    rows, _ = triage_files(files, ref, TemplateExplainer(parse_policy(policy_path.read_bytes()), ref))
    assert happy["csv"] == to_csv(rows)
    assert happy["csv"].startswith("claim_id,decision,rules_fired,reason_codes,explanation\n")


# ------------------------------------------------------------------ error matrix


def test_missing_claims_is_400(policy_path, workbook_path):
    r = client.post("/api/triage", files=[part("policy", policy_path), part("workbook", workbook_path)])
    assert r.status_code == 400
    assert r.json()["error"] == "No claim files uploaded"


def test_missing_workbook_is_400(claims_dir, policy_path):
    r = client.post("/api/triage", files=claim_parts(claims_dir, ["CLM-2026-0001.txt"]) + [part("policy", policy_path)])
    assert r.status_code == 400
    assert set(r.json()) == {"error", "detail"}
    assert "workbook" in r.json()["error"].lower()


def test_missing_policy_is_400(claims_dir, workbook_path):
    r = client.post("/api/triage", files=claim_parts(claims_dir, ["CLM-2026-0001.txt"]) + [part("workbook", workbook_path)])
    assert r.status_code == 400
    assert "Policy" in r.json()["error"]


def test_workbook_with_wrong_extension_is_400(claims_dir, policy_path, workbook_path):
    files = claim_parts(claims_dir, ["CLM-2026-0001.txt"]) + [
        part("policy", policy_path), part("workbook", workbook_path, name="dataset.txt")]
    r = client.post("/api/triage", files=files)
    assert r.status_code == 400
    assert ".xlsx" in r.json()["error"]


def test_corrupt_workbook_is_400_with_loader_message(claims_dir, policy_path, workbook_path):
    files = claim_parts(claims_dir, ["CLM-2026-0001.txt"]) + [
        part("policy", policy_path), part("workbook", workbook_path, data=b"not really excel")]
    r = client.post("/api/triage", files=files)
    assert r.status_code == 400
    assert "could not be opened" in r.json()["detail"]


def test_wrong_claim_type_becomes_a_row_not_an_error(claims_dir, policy_path, workbook_path):
    files = claim_parts(claims_dir, ["CLM-2026-0004.txt"]) + [
        ("claims", ("notes.docx", b"meeting notes", "application/octet-stream")),
        part("policy", policy_path), part("workbook", workbook_path)]
    r = client.post("/api/triage", files=files)
    assert r.status_code == 200
    rows = {row["claim_id"]: row for row in r.json()["results"]}
    assert rows["notes.docx"]["reason_codes"] == ["R200"]
    assert rows["notes.docx"]["decision"] == "NEEDS_HUMAN"
    assert rows["CLM-2026-0004"]["decision"] == "DENY"
    assert r.json()["warnings"]


def test_garbage_policy_still_triages_with_warning(claims_dir, policy_path, workbook_path):
    files = claim_parts(claims_dir, ["CLM-2026-0004.txt"]) + [
        part("policy", policy_path, data=b"garbage"), part("workbook", workbook_path)]
    r = client.post("/api/triage", files=files)
    assert r.status_code == 200
    assert r.json()["warnings"]
    assert "Section 2.1 Eligibility" in r.json()["results"][0]["explanation"]


def test_file_over_10mb_is_413(policy_path, workbook_path):
    big = b"x" * (10 * 1024 * 1024 + 1)
    files = [("claims", ("huge.txt", big, "text/plain")), part("policy", policy_path), part("workbook", workbook_path)]
    r = client.post("/api/triage", files=files)
    assert r.status_code == 413
    assert "huge.txt" in r.json()["detail"]
