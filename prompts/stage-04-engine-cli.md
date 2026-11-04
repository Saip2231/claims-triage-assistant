# Stage 4: Engine, CSV Export and CLI, then Gate A (System Prompt)

## Role
You are a senior Python engineer wiring the checks into a robust batch engine and a CLI that produces `decisions.csv`. Follow `CLAUDE.md`. **You never run terminal commands.** This stage ends at **Gate A**: all 10 decisions must match CLAUDE.md §6. That area is worth 35 points.

## Read first
- `CLAUDE.md` §4.2 (combine plus the intake codes), §4.3 (CSV), §6 (golden table)
- `triage/models.py`, `triage/extract.py`, `triage/checks.py`

## Deliverables

### `triage/engine.py`
```python
def run_checks(claim, ref) -> list[RuleResult]          # runs ALL_CHECKS in order, concatenates
def combine(results: list[RuleResult]) -> Decision      # strict priority, CLAUDE.md §4.2
def triage_claim(claim, ref, explainer=None) -> TriageResult
def triage_files(files: list[tuple[str, bytes]], ref, explainer=None) -> tuple[list[TriageResult], list[str]]
```

**`combine` priority:**
1. Any check-1 result fired → `NEEDS_HUMAN`
2. Else any `DENY` → `DENY`
3. Else any `NEEDS_HUMAN` → `NEEDS_HUMAN`
4. Else → `APPROVE`

`NOT_EVALUATED` never fires.

**`triage_files`:**
1. Extract each file inside its own `try/except`:
   - `ExtractionError` → an **intake row**: NEEDS_HUMAN, `INTAKE-01`, `R200`, `claim_id` = file name, explanation = the error message, plus a warning string.
   - `claim.claim_id is None` → the same intake row, with "No claim ID found in <file>".
   - Any other exception while triaging one claim → an intake row too. Log the traceback with `logging.exception`, using the claim ID only.
2. **Dedupe** by `claim_id`. The same ID can come from several files (e.g. the PDF and TXT of one claim).
   - Equal `claim_fingerprint` → keep one and record both names in `source_files`.
   - Different fingerprints → NEEDS_HUMAN, `INTAKE-02`, `R204`, with an explanation listing the differing fields.
3. Return the results **sorted by claim_id**, plus the list of warnings.

**Explanation in this stage:** if `explainer` is None, use a placeholder: `"; ".join(detail for fired results)`, or "All checks passed." Stage 5 plugs in the real template explainer through the `explainer(claim, results, decision) -> tuple[str, list[str]]` callable, which returns the explanation and the advisories.

`extracted` is `claim_fingerprint(claim)` minus nothing sensitive. Claims don't carry names, but **drop `birth year` and `sex` if they ever appear**.

### `triage/export.py`
`to_csv(results: list[TriageResult]) -> str`:
- Uses the `csv` module with `lineterminator="\n"`.
- Writes the header `claim_id,decision,rules_fired,reason_codes,explanation`.
- Joins lists with `;`.

### `scripts/run_batch.py`
argparse options:
- `--claims-dir`, default `../sample_data/claims`
- `--workbook`, default `../sample_data/claims_triage_dataset.xlsx`
- `--policy`, default `../sample_data/policy_documents.pdf`; optional until Stage 5
- `--out`, default `../output/decisions.csv`

It reads every `.pdf`/`.txt` file in the folder, runs `triage_files`, writes the CSV, and prints a summary table: claim_id | decision | rules_fired. Then it prints the counts. It exits 0 even when some claims are NEEDS_HUMAN, and exits 2 with a clean message on a `WorkbookError`.

> Both the PDF and the TXT of each claim live in the same folder, so the batch also exercises dedupe. The result must still be **10 rows**.

## Tests
- `tests/test_engine.py`:
  1. Priority: a VAL-01 plus an ELIG-01 DENY → NEEDS_HUMAN.
  2. DENY + NEEDS_HUMAN → DENY.
  3. All PASS/NOT_EVALUATED → APPROVE.
  4. An unreadable file → an intake row, and the batch continues.
  5. The same claim as PDF + TXT → one row with two source files.
  6. Two TXT files with the same claim ID but different totals → INTAKE-02 / R204.
- `tests/test_golden.py`: parametrised over CLAUDE.md §6. Run the whole `sample_data/claims` folder and assert decision, rules_fired and reason_codes for every claim. Also assert exactly 10 rows. **One test per decision type is required by the brief**, so name the tests clearly: `test_approve_example_0001`, `test_deny_example_0004`, `test_needs_human_example_0009`, and the full table.
- `tests/test_export.py`: the header order, the `;` joining, and quoting of commas in explanations.

## Commands for the user
From `claims_triage\backend`:
```powershell
.\.venv\Scripts\python -m pytest -v
```
```powershell
.\.venv\Scripts\python scripts\run_batch.py
```
```powershell
Get-Content ..\output\decisions.csv
```

## Gate A: exit criteria
- [ ] The full test suite passes
- [ ] The `run_batch.py` summary shows **4 APPROVE · 2 DENY · 4 NEEDS_HUMAN**, matching CLAUDE.md §6 row by row
- [ ] `output/decisions.csv` has 10 rows plus a header

If any claim disagrees with the golden table:
1. Show the user the check-by-check results for that claim.
2. Explain the discrepancy, citing the data.
3. Propose a fix. Never silently change the golden table.

## When done
- Tick Stage 4 **and Gate A** in `STAGES.md`, with a log line.
- Prompt: "Say **Start Stage 5**."
