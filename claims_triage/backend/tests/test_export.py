"""Stage 4: decisions.csv format (CLAUDE.md §4.3)."""

import csv
from io import StringIO

from triage.export import CSV_COLUMNS, to_csv
from triage.models import RuleResult, TriageResult


def row(claim_id, decision, fired, explanation):
    results = [RuleResult(n, f"check {n}", outcome, rule, code, "d") for n, outcome, rule, code in fired]
    return TriageResult(claim_id=claim_id, decision=decision, results=results, explanation=explanation)


def test_header_and_column_order():
    text = to_csv([])
    assert text == "claim_id,decision,rules_fired,reason_codes,explanation\n"
    assert CSV_COLUMNS == ("claim_id", "decision", "rules_fired", "reason_codes", "explanation")


def test_lists_are_joined_with_semicolons_and_rows_sorted():
    rows = [
        row("CLM-B", "APPROVE", [], "All checks passed."),
        row("CLM-A", "NEEDS_HUMAN",
            [(4, "NEEDS_HUMAN", "PA-01", "R401"), (6, "NEEDS_HUMAN", "AMT-01", "R901")], "Needs review."),
    ]
    parsed = list(csv.DictReader(StringIO(to_csv(rows))))
    assert [p["claim_id"] for p in parsed] == ["CLM-A", "CLM-B"]
    assert parsed[0]["rules_fired"] == "PA-01;AMT-01"
    assert parsed[0]["reason_codes"] == "R401;R901"
    assert parsed[1]["rules_fired"] == "" and parsed[1]["reason_codes"] == ""


def test_commas_quotes_and_newlines_in_explanations_round_trip():
    text = 'Denied, see "Section 2.1 Eligibility".\nYou may appeal.'
    parsed = list(csv.DictReader(StringIO(to_csv([row("CLM-A", "DENY", [], text)]))))
    assert parsed[0]["explanation"] == text


def test_unix_line_endings():
    assert "\r\n" not in to_csv([row("CLM-A", "APPROVE", [], "ok")])
