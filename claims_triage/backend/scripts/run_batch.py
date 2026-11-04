"""Triage a folder of claim files from the command line and write decisions.csv.

Usage (from claims_triage/backend):
    .\\.venv\\Scripts\\python scripts\\run_batch.py
    .\\.venv\\Scripts\\python scripts\\run_batch.py --claims-dir ..\\sample_data\\claims --out ..\\output\\decisions.csv

Every file in the folder is processed. The PDF and TXT copies of the same claim
are merged into one row. Exit codes: 0 = done (even if some claims need a
human), 2 = the workbook could not be used.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from triage.engine import triage_files  # noqa: E402
from triage.export import to_csv  # noqa: E402
from triage.reference import WorkbookError, load_reference  # noqa: E402

PROJECT = Path(__file__).resolve().parents[2]
SAMPLE = PROJECT / "sample_data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Triage claim files and write decisions.csv.")
    parser.add_argument("--claims-dir", type=Path, default=SAMPLE / "claims")
    parser.add_argument("--workbook", type=Path, default=SAMPLE / "claims_triage_dataset.xlsx")
    parser.add_argument("--policy", type=Path, default=SAMPLE / "policy_documents.pdf",
                        help="Policy PDF used to cite sections in explanations.")
    parser.add_argument("--out", type=Path, default=PROJECT / "output" / "decisions.csv")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()

    try:
        ref = load_reference(args.workbook)
    except (WorkbookError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if not args.claims_dir.is_dir():
        print(f"ERROR: claims folder not found: {args.claims_dir}")
        return 2
    files = [(p.name, p.read_bytes()) for p in sorted(args.claims_dir.iterdir()) if p.is_file()]

    results, warnings = triage_files(files, ref)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps the "\n" line endings exactly as to_csv produced them.
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        fh.write(to_csv(results))

    print(f"{'claim_id':<16} {'decision':<12} {'rules_fired':<16} reason_codes")
    print("-" * 64)
    for r in results:
        print(f"{r.claim_id:<16} {r.decision:<12} {';'.join(r.rules_fired):<16} {';'.join(r.reason_codes)}")
    counts = Counter(r.decision for r in results)
    print("-" * 64)
    print(f"{len(results)} claims from {len(files)} files: "
          f"{counts['APPROVE']} APPROVE | {counts['DENY']} DENY | {counts['NEEDS_HUMAN']} NEEDS_HUMAN")
    for w in warnings + ref.warnings:
        print(f"WARNING: {w}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
