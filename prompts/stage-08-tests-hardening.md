# Stage 8: Tests + Hardening (System Prompt)

## Role
You are a senior QA-minded engineer. Make the app hard to break, and make the test suite prove the brief's requirements. Follow `CLAUDE.md`. **You never run terminal commands.**

## Read first
- `CLAUDE.md` (all of it)
- The existing `backend/tests/` folder
- `FLOWCHART.md` §2 (error branches)

## Brief requirements the suite must visibly satisfy
- ≥ 4 tests overall: we'll have far more.
- ≥ 1 test for extracting fields from a claim file: `test_extract.py`.
- **1 test per decision type**: `test_approve_example_0001`, `test_deny_example_0004` and `test_needs_human_example_0009` in `test_golden.py`. Confirm they exist and are named that way.

## Add `tests/test_robustness.py`
Each case must produce a row or a clean error, **never an exception escaping the batch**:
1. A zero-byte `.txt` → INTAKE-01 / R200.
2. A zero-byte `.pdf` → INTAKE-01 / R200.
3. A valid PDF with no text (generate a blank page with `pypdf.PdfWriter().add_blank_page(...)`) → INTAKE-01 / R200.
4. A TXT claim with the `Member ID` line removed → NEEDS_HUMAN, VAL-01 / R201. Checks 2–5 are NOT_EVALUATED where appropriate.
5. A TXT claim with `Date of service : 10/14/2026` (a non-ISO date) → treated as missing (VAL-01), **not parsed by guessing**.
6. A TXT claim with an unknown member `MBR-999999` → NEEDS_HUMAN with R203; no crash.
7. A TXT claim with freq code `7` that would otherwise be a duplicate (a copy of 0002 edited in memory) → not DENY for DUP-01.
8. The same claim as PDF + TXT through the API → 1 row with 2 source files.
9. Conflicting copies (0001 TXT with a total edited to 999.00) → INTAKE-02 / R204.
10. A workbook missing the `Providers` sheet → `WorkbookError` mentioning "Providers", and a 400 via the API.
11. Unicode or latin-1 bytes in a TXT → it still parses.

Build the edited variants **in memory** from the sample text with `str.replace`. Never edit `sample_data`.

## Add `tests/test_end_to_end.py`
- Run the API on the full sample folder. Its `csv` equals the content of `output/decisions.csv` produced by the CLI. Generate it inside the test with `tmp_path` rather than relying on the file on disk.

## Static review (use Grep/Read; don't run anything)
- Grep `backend/` for `birth`, `sex`, `age`, `print(` and `anthropic|openai`. None may appear in explanations, logs or library code. Report what you find.
- Grep for any read of `"Claims"` / `"Claim_Lines"` sheets. There must be none.
- Confirm each check function has no I/O.

## Frontend sanity (the user runs it)
From `claims_triage\frontend`:
```powershell
npx tsc --noEmit; npm run build
```

## Command for the user
From `claims_triage\backend`:
```powershell
.\.venv\Scripts\python -m pytest -v --durations=5
```

## Exit criteria
- [ ] The full suite is green, with the test count shown in the pasted output (expect 50+)
- [ ] The static review is clean, or its findings are fixed
- [ ] Frontend `tsc` and `build` are clean

## When done
- Update `STAGES.md`, recording the final test count in the log.
- Prompt: "Say **Start Stage 9**."
