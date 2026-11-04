# STAGES.md: Progress Tracker

**Legend:** ⬜ not started · 🟨 in progress · ✅ done (proven by pasted output) · 🚧 gate

## How to run a stage

1. Open a Claude session in `Downloads/Interview`. `CLAUDE.md` loads automatically.
2. Type **`Start Stage N`**. Claude reads `prompts/stage-NN-*.md` and follows it.
   - Or paste the stage prompt in yourself.
3. Claude writes the files and gives you commands. **You** run them and paste the output back.
4. When every exit criterion is proven, Claude ticks the stage here and logs it below.

---

| # | Stage | Prompt | Key output | Status |
|---|---|---|---|---|
| 0 | Setup and environment | [stage-00](prompts/stage-00-setup.md) | folders, venv, deps, sample_data, Node check | ✅ |
| 1 | Models + reference loader | [stage-01](prompts/stage-01-models-reference.md) | `models.py`, `reference.py` + tests | ✅ |
| 2 | Claim extraction (PDF + TXT) | [stage-02](prompts/stage-02-extraction.md) | `extract.py` + parity test 10/10 | ✅ |
| 3 | The 6 checks | [stage-03](prompts/stage-03-checks.md) | `checks.py` + pass/fail test per check | ✅ |
| 4 | Engine + CLI → decisions.csv | [stage-04](prompts/stage-04-engine-cli.md) | `engine.py`, `export.py`, `run_batch.py` | ✅ |
| 🚧 | **Gate A:** all 10 decisions match the golden table | | | ✅ |
| 5 | Policy parser + explanations + advisories | [stage-05](prompts/stage-05-policy-explanations.md) | `policy.py`, `explain.py`, `advisories.py` | ⬜ |
| 6 | FastAPI backend + error handling | [stage-06](prompts/stage-06-api.md) | `api.py` + API tests | ⬜ |
| 7 | React UI | [stage-07](prompts/stage-07-react-ui.md) | `frontend/` working against the API | ⬜ |
| 🚧 | **Gate B:** full flow works in your browser | | | ⬜ |
| 8 | Tests + hardening | [stage-08](prompts/stage-08-tests-hardening.md) | robustness + end-to-end tests, all green | ⬜ |
| 9 | README + final CSV + zip | [stage-09-submission](prompts/stage-09-submission.md) | `README.md`, `output/decisions.csv`, zip | ⬜ |
| 🚧 | **Gate C:** submission zip verified | | | ⬜ |

---

## Detailed checklist

### Stage 0: Setup
- [x] `node -v` ≥ 18 and `npm -v` confirmed
- [x] `claims_triage/` skeleton created
- [x] `sample_data/` copied (10 PDF + 10 TXT, workbook, policy)
- [x] `.venv` created, `requirements.txt` installed
- [x] `pytest` runs (0 tests collected is fine)

### Stage 1: Models + reference loader
- [x] Dataclasses match the CLAUDE.md §4.1 contract
- [x] `load_reference()` loads all needed sheets, with a clear error on a missing sheet or column
- [x] Tests green (members, providers, ICD set, benefit rules, PA log, history)

### Stage 2: Extraction
- [x] TXT parser
- [x] PDF parser
- [x] Parity: TXT == PDF for all 10 claims
- [x] CLM-0009 rendering NPI is `None`; CLM-0005 has 3 lines; CLM-0003 total is 18500.00
- [x] Manual cross-check of `output/extracted_claims.csv` by the user

### Stage 3: Checks
- [x] The 6 check functions are pure
- [x] Pass + fail test for each check, plus the R203 and NOT_EVALUATED paths

### Stage 4: Engine + CLI
- [x] `combine()` priority test
- [x] `run_batch.py` writes `output/decisions.csv`
- [x] Golden test: 10/10 match → **Gate A**

### Stage 5: Policy + explanations
- [ ] Policy sections parsed (2.1 … 3.8), with a fallback if parsing fails
- [ ] Every explanation cites "Section X.Y Title"
- [ ] Advisories match the golden advisory table

### Stage 6: API
- [ ] `/api/health` and `/api/triage`
- [ ] Error matrix covered by TestClient tests
- [ ] Serves `frontend/dist` when present

### Stage 7: React UI
- [ ] Three upload zones with type validation
- [ ] Run button, loading state, summary strip
- [ ] Results table: filter, search, colour-coded decisions
- [ ] Claim detail drawer: extracted fields, 6-check timeline, explanation, advisories
- [ ] Download `decisions.csv`
- [ ] Error banners: no white screens → **Gate B**

### Stage 8: Hardening
- [ ] Bad, empty and garbage files → NEEDS_HUMAN rows
- [ ] Same claim uploaded as PDF + TXT → deduped (conflict → NEEDS_HUMAN)
- [ ] Full suite green, ≥ 12 tests

### Stage 9: Submission
- [ ] README (one page): run, design, assumptions, 3 limitations, explanation mode = template
- [ ] Final `output/decisions.csv` from the CLI == the UI download
- [ ] Zip built and contents checked → **Gate C**

---

## Progress log

| Date | Stage | Note |
|---|---|---|
| 2026-11-04 | — | Plan, flowchart, CLAUDE.md and stage prompts written |
| 2026-11-04 | 0 | ✅ Python 3.11.4, Node v24.15.0, npm 11.12.1; deps ok; pytest runs; sample_data has 22 files |
| 2026-11-04 | 1 | ✅ models.py + reference.py; test_reference.py 13/13 passed (pytest 9.2.0) |
| 2026-11-04 | git | First commit pushed to github.com/Saip2231/claims-triage-assistant (private), branch `main` |
| 2026-11-04 | 2 | ✅ extract.py; test_extract.py 34/34 passed (incl. PDF/TXT parity 10/10). Added scripts/dump_extracted.py for a manual check |
| 2026-11-04 | 2 | User cross-checked extracted_claims.csv: correct. Stage 2 committed and pushed |
| 2026-11-04 | 3 | ✅ checks.py (6 pure checks) + factories; test_checks.py 40/40; full suite 87/87 |
| 2026-11-04 | 4 | ✅ engine.py, export.py, run_batch.py; 117/117 tests. **Gate A passed:** 10 claims from 20 files, 4 APPROVE / 2 DENY / 4 NEEDS_HUMAN, every row matches the golden table |
