"""Write every field extracted from every claim file to a CSV for a manual cross-check.

There is one row per service line, and the claim header fields repeat on each
row. Missing fields are written as "(missing)" so a blank can't be mistaken
for an empty string. The pdf_txt_match column says whether the PDF and TXT
versions of the same claim extracted identically.

Usage (from claims_triage/backend):
    .\\.venv\\Scripts\\python scripts\\dump_extracted.py
    .\\.venv\\Scripts\\python scripts\\dump_extracted.py --claims-dir ..\\sample_data\\claims --out ..\\output\\extracted_claims.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from triage.extract import ExtractionError, claim_fingerprint, extract_claim  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS = BACKEND.parent / "sample_data" / "claims"
DEFAULT_OUT = BACKEND.parent / "output" / "extracted_claims.csv"

HEADER_FIELDS = [
    "claim_id", "received_date", "freq_code", "member_id", "provider_id", "billing_npi",
    "rendering_npi", "place_of_service", "dos", "primary_dx", "secondary_dx",
    "prior_auth_number", "emergency", "attachments", "total_billed",
]
LINE_FIELDS = ["line_no", "dos", "pos", "cpt", "modifier", "dx_pointer", "units", "charge"]
COLUMNS = (
    ["source_file", "format"] + HEADER_FIELDS + ["line_count"]
    + [f"line_{f}" for f in LINE_FIELDS] + ["pdf_txt_match", "error"]
)
MISSING = "(missing)"


def show(value) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, list):
        return ";".join(value) if value else "(none)"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--claims-dir", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    files = sorted(p for p in args.claims_dir.iterdir() if p.is_file())
    if not files:
        print(f"No files found in {args.claims_dir}")
        return 1

    fingerprints: dict[str, dict[str, dict]] = defaultdict(dict)
    extracted: list[tuple[Path, str, dict | None, str]] = []
    for path in files:
        fmt = path.suffix.lower().lstrip(".")
        try:
            fp = claim_fingerprint(extract_claim(path.name, path.read_bytes()))
            fingerprints[fp["claim_id"] or path.name][fmt] = fp
            extracted.append((path, fmt, fp, ""))
        except ExtractionError as exc:
            extracted.append((path, fmt, None, str(exc)))

    def parity(fp: dict) -> str:
        versions = fingerprints.get(fp["claim_id"] or "", {})
        if {"pdf", "txt"} <= versions.keys():
            return "YES" if versions["pdf"] == versions["txt"] else "NO"
        return "only one format"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    # utf-8-sig so Excel shows the file correctly when double-clicked
    with args.out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for path, fmt, fp, error in sorted(extracted, key=lambda e: ((e[2] or {}).get("claim_id") or e[0].name, e[1])):
            base = {"source_file": path.name, "format": fmt.upper(), "error": error}
            if fp is None:
                writer.writerow(base)
                rows += 1
                continue
            base.update({f: show(fp[f]) for f in HEADER_FIELDS})
            base["line_count"] = len(fp["lines"])
            base["pdf_txt_match"] = parity(fp)
            for line in fp["lines"] or [{}]:
                row = dict(base)
                row.update({f"line_{f}": show(line.get(f)) for f in LINE_FIELDS})
                writer.writerow(row)
                rows += 1

    print(f"Wrote {rows} rows from {len(files)} files to {args.out}")
    print(f"{'claim_id':<15} {'PDF==TXT':<16} lines  total")
    for claim_id, versions in sorted(fingerprints.items()):
        fp = next(iter(versions.values()))
        match = parity(fp)
        print(f"{claim_id:<15} {match:<16} {len(fp['lines']):<6} {show(fp['total_billed'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
