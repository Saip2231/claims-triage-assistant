"""Turns triage results into decisions.csv text (CLAUDE.md §4.3).

The API and the CLI both call to_csv(), so the CSV you download from the UI is
byte-for-byte the same as the one the command line writes.
"""

from __future__ import annotations

import csv
from io import StringIO

from .models import TriageResult

CSV_COLUMNS = ("claim_id", "decision", "rules_fired", "reason_codes", "explanation")


def to_csv(results: list[TriageResult]) -> str:
    """Return the CSV text: fixed column order, ';'-joined lists, rows sorted by claim_id."""
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in sorted(results, key=lambda r: r.claim_id):
        writer.writerow([r.claim_id, r.decision, ";".join(r.rules_fired), ";".join(r.reason_codes), r.explanation])
    return buffer.getvalue()
