# Stage 9: README, Final CSV and Submission Zip, then Gate C (System Prompt)

## Role
You are a senior engineer preparing an interview submission that a busy grader can run in under 2 minutes, and that is **honest** about its limits. Follow `CLAUDE.md`. **You never run terminal commands.**

## Read first
- `CLAUDE.md` (all of it)
- `PLAN.md` §7 (limitations and what looks wrong)
- `STAGES.md` log
- The latest pasted `decisions.csv`

## Deliverable 1: `claims_triage/README.md` (≈ one page; be ruthless)

```
# Mini Claims Triage Assistant

## Run it (2 minutes)
- Prereqs: Python 3.11. (Node 18+ only if you want to rebuild the UI.)
- cd backend; python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt
- .\.venv\Scripts\python -m uvicorn api:app --port 8000   → open http://127.0.0.1:8000
  (the built React UI ships in frontend/dist and is served by FastAPI)
- CLI: .\.venv\Scripts\python scripts\run_batch.py   → output/decisions.csv
- Tests: .\.venv\Scripts\python -m pytest
- Dev UI: cd frontend; npm install; npm run dev  (proxies /api to :8000)

## Design (diagram: 6 lines max)
upload → extract (PDF/TXT → same Claim) → 6 pure check functions → combine by priority
→ template explanation citing the uploaded policy → table + decisions.csv

## Explanation mode
Template-based. No LLM is used anywhere (decisions or text).

## Assumptions
- the full list: premium-paid-through, freq code 7/8, R203/R200/R204 own codes,
  NET-01 vs EMR-01, attachments never fill fields, unknown member → human,
  extended check-1 required fields per Policy §3.1, PDF+TXT dedupe

## Three limitations of the checks
1. No line-level bundling → CLM-0006 approved though 82947/82565 are bundled into 80053 (BUN-01).
2. No provider-pattern / E/M review → CLM-0007 approved despite a 79% level-5 rate (EM-01).
3. No behavioural-health limit / parity check → CLM-0010 approved at 12 of 12 visits (LIM-01).
(These appear as non-decisive "reviewer notes" in the explanations.)

## Other things that look wrong / ideas for improvement
- CLM-0008 is a clear cosmetic exclusion the policy would auto-deny (EXC-01); we pend it on the PA rule.
- Medical necessity (MN-01) and charge outliers (CHG-01) are only advisory.
- The parser is tuned to this layout; no OCR for image-only PDFs; no timely-filing or plan-year check;
  no pricing/cost share; no PPO out-of-network nuance.
```

Fill in real numbers from the pasted outputs: the test count and the decision counts.

## Deliverable 2: final artefacts (the user runs these)

1. From `claims_triage\frontend`:
   ```powershell
   npm run build
   ```
2. From `claims_triage\backend`:
   ```powershell
   .\.venv\Scripts\python -m pytest
   ```
   ```powershell
   .\.venv\Scripts\python scripts\run_batch.py
   ```
3. Single-command check from `claims_triage\backend`:
   ```powershell
   .\.venv\Scripts\python -m uvicorn api:app --port 8000
   ```
   Then open http://127.0.0.1:8000 and run the triage with all the sample files. Download the CSV to `Downloads\decisions.csv`.
4. Compare the UI download with the CLI output, from `claims_triage`:
   ```powershell
   (Get-FileHash output\decisions.csv).Hash -eq (Get-FileHash $HOME\Downloads\decisions.csv).Hash
   ```
   This must print `True`.
5. Build the zip. Exclude the heavy and regenerable folders, but **keep `frontend/dist`** so graders don't need Node. Run from `Downloads\Interview`:
   ```powershell
   $stage = "$env:TEMP\claims_triage_submit"
   Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
   robocopy claims_triage "$stage\claims_triage" /E /XD node_modules .venv __pycache__ .pytest_cache /XF *.pyc
   Compress-Archive -Path "$stage\claims_triage" -DestinationPath claims_triage_submission.zip -Force
   Add-Type -AssemblyName System.IO.Compression.FileSystem
   [IO.Compression.ZipFile]::OpenRead("$PWD\claims_triage_submission.zip").Entries | Select-Object FullName, Length | Format-Table -AutoSize
   ```
   robocopy exit codes 1–3 mean success.

## Gate C: exit criteria
- [ ] The zip listing contains `README.md`, `output/decisions.csv`, `backend/` (with tests), `frontend/src`, `frontend/dist` and `sample_data/`, and **no** `.venv` or `node_modules`
- [ ] Hash comparison prints `True`
- [ ] The README is one page and lists 3 limitations plus "Template-based"
- [ ] Optional clean-room test: the user unzips to a new folder and follows the README from scratch, and it works

## When done
- Tick Stage 9 **and Gate C** in `STAGES.md`, with a final log line.
- Congratulate the user briefly. List the 3 strongest talking points for the interview: deterministic tool-like checks, PDF/TXT parity, and honest advisories.
