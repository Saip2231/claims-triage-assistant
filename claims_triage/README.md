# Mini Claims Triage Assistant

Upload claim files (PDF or TXT), the policy PDF and the reference workbook. Each claim gets an
**APPROVE / DENY / NEEDS_HUMAN** decision, the rules that fired, and a plain-language explanation that
cites the policy. Results show in a table and download as `decisions.csv`.
**No LLM is used anywhere:** decisions and explanations are deterministic code plus the workbook data.

## Run it (≈2 minutes, Python 3.11 only)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.\.venv\Scripts\python -m uvicorn api:app --port 8000          # then open http://127.0.0.1:8000
```

- The built React UI ships in `frontend/dist` and is served by FastAPI. The API docs are at `/docs`.
- **CLI:** `.\.venv\Scripts\python scripts\run_batch.py` writes `output/decisions.csv` from `sample_data/`.
- **Tests:** `.\.venv\Scripts\python -m pytest` (203 tests).
- **UI dev mode (needs Node 18+):** `cd frontend; npm install; npm run dev`, then open http://localhost:5173. It proxies `/api` to :8000.

## Design

```
upload → extract (PDF/TXT → one Claim) → 6 check functions → combine by priority → template explanation → table + CSV
```

- **`extract.py`:** a single parser for both formats. TXT has `Label : value` on one line; the PDF (via pypdf) has the label and value on separate lines. Both map through one alias table. Only the claim body, up to `TOTAL CHARGE`, is parsed, so attachments never fill a field. Blank or malformed values become missing; nothing is guessed or corrected. PDF and TXT give identical fields for all 10 claims, and a test enforces this.
- **`checks.py`:** six pure functions, `check(claim, ref) -> [RuleResult]`, with no I/O. Each passing check still returns a readable detail, so the UI can show a full check list.
- **`engine.py`:** runs **all** checks, then combines them:
  1. check 1 fired → NEEDS_HUMAN;
  2. otherwise any DENY → DENY;
  3. otherwise any NEEDS_HUMAN → NEEDS_HUMAN;
  4. otherwise → APPROVE.

  Each file is isolated, so one bad file becomes a NEEDS_HUMAN row and the batch continues. The PDF and TXT of the same claim merge into one row.
- **`explain.py` and `policy.py`:** the **uploaded** policy PDF is split into numbered sections. Each reason code maps to a section, and the explanation quotes it, e.g. *Section 2.1 Eligibility – "…termination date…"*. Denials add the 180-day appeal right (§2.8). Only the claim ID, member ID, codes, dates and amounts are used: never birth year or sex (§3.8).
- **`api.py` (FastAPI):** HTTP only, with `{error, detail}` messages for bad uploads. **`frontend/`:** React + TypeScript with hand-written CSS. The CLI and the UI download use the same `to_csv()`, so their CSVs are byte-identical (tested).

**Explanation mode: template-based** (no LLM, no API key).

**Result for the 10 claims:**

| Decision | Claims |
|---|---|
| APPROVE (4) | 0001, 0006, 0007, 0010 |
| DENY (2) | 0002 (R102 duplicate of H-1001), 0004 (R101 coverage ended 2026-09-28) |
| NEEDS_HUMAN (4) | 0003 (R401 + R901), 0005 (R801 out-of-network ER), 0008 (R401), 0009 (R201 + R202) |

## Assumptions

- **Eligibility** also requires `premium_paid_through ≥ DOS` (§2.1). Coverage on the termination date itself counts.
- **Duplicates** match a **Paid** history row with the same member + billing provider + DOS + any line's CPT, and only when the frequency code is 1. Codes 7 and 8 are never duplicates (§3.3).
- **Check 1** covers all §3.1 required fields (member, provider, rendering NPI, DOS, lines with CPT and charge, total), not only the NPI and diagnosis.
- **Network rule ID** is `EMR-01` when the claim's emergency flag is Y, otherwise `NET-01`. Both use reason R801.
- **Our own codes:**
  - `R203`: member, provider or benefit rule not found in the workbook → human review, never a denial.
  - `R200` / `INTAKE-01`: the file couldn't be read.
  - `R204` / `INTAKE-02`: the same claim was uploaded twice with different contents.
- **Dates** must be `YYYY-MM-DD`; any other format is treated as missing. The workbook's `Claims` and `Claim_Lines` sheets are never read.

## Three limitations of the checks

1. **No line-level bundling.** CLM-0006 is approved although 82947 and 82565 are bundled into 80053 (§3.4, BUN-01).
2. **No provider-pattern / E/M review.** CLM-0007 is approved although P-007 bills level 5 on 79% of visits vs a peer median of 8%, for a 12-minute straightforward visit (§3.5, EM-01).
3. **No benefit-limit check.** CLM-0010 is approved at psychotherapy visit 12 of 12, which needs a parity review (§2.7, LIM-01).

These, plus MN-01, EXC-01 and CHG-01, are computed deterministically and shown as **"Reviewer notes (do not change this decision)"** in the explanation and UI. They are deliberately non-decisive, so the decisions follow the brief's six checks exactly.

## Other things that look wrong, and ideas

- **CLM-0008** is a clear cosmetic exclusion (Z41.1; the note says aesthetic only). The policy allows an auto-**DENY** (EXC-01), but the six checks pend it as R401.
- **CLM-0003** has a pain-only diagnosis (M25.561) for meniscectomy, so it also needs a clinical review (MN-01).
- **CLM-0009**'s OCR confidence (0.62 on the diagnosis) isn't used, because attachments are ignored by design.
- **Not implemented:** timely filing (180 days), plan-year bounds, PPO out-of-network cost share, pricing, HMO referrals, and OCR for image-only PDFs.
- **The parser is tuned to this claim layout.** A new layout needs new aliases.
- **Next steps:** make the advisories optional decision rules behind a flag, add line-level decisions (PARTIAL_PAY), and add an audit log per §3.7.

`output/extracted_claims.csv` (from `scripts/dump_extracted.py`) lists every extracted field for manual checking.
