"""Stage 8: end to end, the CLI and the API produce the same decisions.csv byte for byte."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from scripts import run_batch
from tests.test_golden import GOLDEN


def test_cli_and_api_csv_are_identical(monkeypatch, tmp_path: Path, claims_dir, workbook_path, policy_path, capsys):
    out = tmp_path / "decisions.csv"
    monkeypatch.setattr(sys, "argv", [
        "run_batch.py", "--claims-dir", str(claims_dir), "--workbook", str(workbook_path),
        "--policy", str(policy_path), "--out", str(out),
    ])
    assert run_batch.main() == 0
    printed = capsys.readouterr().out
    assert "10 claims from 20 files: 4 APPROVE | 2 DENY | 4 NEEDS_HUMAN" in printed
    cli_csv = out.read_bytes().decode("utf-8")

    files = [("claims", (p.name, p.read_bytes(), "application/octet-stream")) for p in sorted(claims_dir.iterdir())]
    files += [
        ("policy", (policy_path.name, policy_path.read_bytes(), "application/pdf")),
        ("workbook", (workbook_path.name, workbook_path.read_bytes(), "application/octet-stream")),
    ]
    response = TestClient(app).post("/api/triage", files=files)
    assert response.status_code == 200
    assert response.json()["csv"] == cli_csv

    lines = cli_csv.splitlines()
    assert lines[0] == "claim_id,decision,rules_fired,reason_codes,explanation"
    assert [line.split(",")[0] for line in lines[1:]] == sorted(GOLDEN)


def test_cli_reports_bad_workbook_cleanly(monkeypatch, tmp_path: Path, claims_dir, capsys):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not excel")
    monkeypatch.setattr(sys, "argv", ["run_batch.py", "--claims-dir", str(claims_dir), "--workbook", str(bad),
                                      "--out", str(tmp_path / "x.csv")])
    assert run_batch.main() == 2
    assert "could not be opened" in capsys.readouterr().out
