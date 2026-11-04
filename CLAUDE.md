# CLAUDE.md: Mini Claims Triage Assistant

These are the house rules for every Claude session in this folder. Read them fully before doing anything.
Companion files:

- `PLAN.md`: the what and why
- `FLOWCHART.md`: the data flow
- `STAGES.md`: the progress tracker
- `prompts/stage-XX-*.md`: one system prompt per stage

---

## 0. Rule #1: Claude never runs anything in the terminal

- **Never** execute shell commands: no Bash, no PowerShell, no `run_in_terminal`. This includes "harmless" ones like `ls`, `pip list`, `pytest`, `npm install` and `git status`.
- When something needs to run, give the user the **exact command** in its own fenced code block. The user is on **Windows + PowerShell**, so commands must work in PowerShell, and the block must say which folder to run it from.
- Then **stop and wait**. The user runs it and pastes the output back. Read the pasted output carefully before continuing.
- **Never claim** that tests pass, a server starts or a file was generated unless the user has pasted output that proves it.
- Use only the file tools (Read / Write / Edit / Glob / Grep) to inspect and change files.

## 1. Product rules (from the brief: non-negotiable)

1. **No LLM anywhere in the product.** Decisions, duplicates, eligibility and explanations are all deterministic code plus workbook data. Explanations are **template-based** and cite the uploaded policy. No `anthropic` or `openai` packages and no API keys.
2. **Claim data comes only from the uploaded claim files** (PDF or TXT). **Never** read the `Claims` or `Claim_Lines` sheets of the workbook. The workbook is reference data only.
3. **Never guess or auto-correct.** A blank, unreadable or invalid field becomes `None` and counts as missing. `J06.99` stays `J06.99`; it never becomes `J06.9`.
4. **Attachments never fill in claim fields.** Extraction reads the claim body only, which ends at `TOTAL CHARGE`.
5. **One bad file must not stop the batch.** It becomes a `NEEDS_HUMAN` row explaining why.
6. **Synthetic data only.** Never add real personal or health data. Logs and explanations reference members **only by member ID**: no birth year, sex, names or ages (Policy §3.8).
7. The input folder `Interview/` (the provided files) is **read-only**. Never edit it.

## 2. Working rules

- Work **one stage at a time**, following `prompts/stage-XX-*.md`. Don't start the next stage until the user says so.
- When the user says **"Start Stage N"**:
  1. read `STAGES.md` and `prompts/stage-NN-*.md`;
  2. confirm the earlier stages are ticked;
  3. follow that prompt.
- A stage is **done** only when every exit criterion is proven by output the user pasted. Then tick it in `STAGES.md` and add a line to the progress log there.
- If a test fails, diagnose it from the pasted output, fix the code, and give the re-run command.
- Keep changes inside `claims_triage/`. Don't create files outside it except updates to `STAGES.md`.
- **No new dependencies** beyond §5 without asking the user first.
- **Git (the user runs it):**
  - The repo root is `Downloads/Interview`, pushed to a **private** GitHub repo.
  - At the end of each stage, once its exit criteria are proven, give the user the `git add` / `git commit` / `git push` commands with a ready-made message: `Stage N: <summary>`, then a blank line, then bullet points.
  - Never commit `Interview/` (the original handouts), `.venv`, `node_modules` or the zip; `.gitignore` excludes them.
  - Never force-push or rewrite history.
- Be honest. If something looks wrong in the data or the results, say so. The brief rewards that.

## 3. Project layout (target)

```
Downloads/Interview/
├── CLAUDE.md  PLAN.md  FLOWCHART.md  STAGES.md
├── prompts/                     # stage system prompts
├── Interview/                   # PROVIDED INPUTS (read-only)
│   ├── Claims/CLM-2026-00NN.pdf|.txt
│   ├── claims_triage_dataset.xlsx
│   ├── policy_documents.pdf
│   └── Problem Statement.pdf
└── claims_triage/               # THE SUBMISSION (this gets zipped)
    ├── README.md
    ├── sample_data/             # copies of the inputs (claims/, workbook, policy)
    ├── output/decisions.csv
    ├── backend/
    │   ├── requirements.txt
    │   ├── pytest.ini
    │   ├── api.py               # FastAPI app (HTTP only, no business logic)
    │   ├── scripts/run_batch.py # CLI → decisions.csv
    │   ├── triage/
    │   │   ├── __init__.py
    │   │   ├── models.py        # dataclasses (contracts below)
    │   │   ├── reference.py     # workbook → ReferenceData
    │   │   ├── extract.py       # PDF/TXT → Claim
    │   │   ├── checks.py        # the 6 checks (pure functions)
    │   │   ├── engine.py        # run checks, combine, triage_batch
    │   │   ├── policy.py        # policy PDF → sections
    │   │   ├── advisories.py    # non-decisive extra policy flags
    │   │   ├── explain.py       # template explanations
    │   │   └── export.py        # rows → CSV text
    │   └── tests/
    └── frontend/                # Vite + React + TypeScript
```

## 4. Contracts (every stage must respect these)

### 4.1 Models (`triage/models.py`)

```python
Outcome = Literal["PASS", "DENY", "NEEDS_HUMAN", "NOT_EVALUATED"]
Decision = Literal["APPROVE", "DENY", "NEEDS_HUMAN"]

@dataclass(frozen=True)
class ServiceLine:
    line_no: int; dos: date | None; pos: str | None; cpt: str | None
    modifier: str | None; dx_pointer: str | None; units: int | None; charge: Decimal | None

@dataclass
class Claim:
    claim_id: str | None; source_file: str; source_format: Literal["pdf", "txt"]
    received_date: date | None; freq_code: str | None
    member_id: str | None; provider_id: str | None
    billing_npi: str | None; rendering_npi: str | None
    place_of_service: str | None; dos: date | None
    primary_dx: str | None; secondary_dx: str | None
    prior_auth_number: str | None; emergency: bool | None
    attachments: list[str]; lines: list[ServiceLine]; total_billed: Decimal | None

@dataclass(frozen=True)
class RuleResult:
    check_no: int            # 1..6
    check_name: str          # "Required fields", "Eligibility", "Duplicate", "Prior authorization", "Network", "Amount"
    outcome: Outcome
    rule_id: str | None      # e.g. "VAL-01"; None when PASS
    reason_code: str | None  # e.g. "R201"; None when PASS
    detail: str              # plain-language fact, e.g. "Coverage ended 2026-09-28; DOS 2026-09-30"
    evidence: tuple[str, ...] = ()   # e.g. ("Members.termination_date",)
    # property fired -> outcome in ("DENY", "NEEDS_HUMAN")

@dataclass
class TriageResult:
    claim_id: str; decision: Decision; results: list[RuleResult]
    explanation: str; advisories: list[str]; source_files: list[str]; extracted: dict
    # properties: rules_fired -> list[str], reason_codes -> list[str] (fired only, check order, de-duplicated)
```

- Money is `Decimal`, dates are `datetime.date`, and codes and IDs are `str`.
- Each check is `def check_x(claim: Claim, ref: ReferenceData) -> list[RuleResult]`. It is pure: no I/O, no globals.

### 4.2 The 6 checks

| # | Check | Fails → | rule_id | reason |
|---|---|---|---|---|
| 1 | Required fields (Policy §3.1): member ID, provider ID, **rendering NPI**, DOS, ≥1 service line with CPT + charge, total billed → missing gives VAL-01. **Every** dx code (primary + secondary if present) must be in `ICD10_Codes` → otherwise VAL-02. Can return both. | NEEDS_HUMAN | VAL-01 / VAL-02 | R201 / R202 |
| 2 | Eligibility: `effective_date ≤ DOS`, `termination_date` blank or `≥ DOS`, `premium_paid_through ≥ DOS` | DENY | ELIG-01 | R101 |
| 3 | Duplicate: a `Claims_History` row with status **Paid** and the same member + billing provider + DOS + CPT (any line), **and** claim freq code = `1` | DENY | DUP-01 | R102 |
| 4 | Prior auth: for each line, if `Benefit_Rules[(plan, cpt)].prior_auth_required == "Y"`, an **Approved** PA must exist with the same member + CPT and `valid_from ≤ DOS ≤ valid_to` | NEEDS_HUMAN | PA-01 | R401 |
| 5 | Network: `Providers[provider]["in_network_" + plan.removeprefix("PLN-").replace("-", "_")] == "Y"` | NEEDS_HUMAN | EMR-01 if emergency, else NET-01 | R801 |
| 6 | Amount: `total_billed ≤ 10000` | NEEDS_HUMAN | AMT-01 | R901 |

**Can't-evaluate rules:**

- A field a check needs is missing (and check 1 already flags it) → `NOT_EVALUATED` (not fired).
- The member, provider or benefit rule is not found in the workbook → `NEEDS_HUMAN`, rule = the check's rule_id, reason **R203** "Reference record not found". This is a documented assumption. Report it once per root cause: an unknown member makes checks 4 and 5 `NOT_EVALUATED`, since the plan is unknown.

**Intake-level codes (our own, documented in the README):**

| Situation | rules_fired | reason_codes | decision |
|---|---|---|---|
| File can't be read, has an unsupported type, or has no claim ID | `INTAKE-01` | `R200` "Claim file could not be processed" | NEEDS_HUMAN |
| Same claim ID uploaded twice with **different** extracted fields | `INTAKE-02` | `R204` "Conflicting claim documents" (Policy §3.6) | NEEDS_HUMAN |
| An unexpected exception while triaging one claim | `INTAKE-01` | `R200` | NEEDS_HUMAN |

A row whose claim ID is unknown uses the **file name** as `claim_id`.

**Combine (strict priority), always after running ALL checks:**

1. Check 1 fired → `NEEDS_HUMAN`
2. Otherwise, any `DENY` → `DENY`
3. Otherwise, any `NEEDS_HUMAN` → `NEEDS_HUMAN`
4. Otherwise → `APPROVE`

### 4.3 CSV (`decisions.csv`)

- Columns, in exactly this order: `claim_id,decision,rules_fired,reason_codes,explanation`
- Multi-values joined with `;` (e.g. `PA-01;AMT-01`). Empty string when none.
- UTF-8, `\n` line endings, standard CSV quoting. Rows sorted by `claim_id`.
- Both the API and the CLI use the **same** `export.to_csv()` function.

### 4.4 API

- `GET /api/health` → `{"status": "ok"}`
- `POST /api/triage` takes a multipart form with three fields:
  - `claims`: 1..n files, `.pdf` or `.txt`
  - `policy`: 1 `.pdf`
  - `workbook`: 1 `.xlsx`
- Success (200) returns:
  ```json
  { "summary": {"total": 10, "APPROVE": 4, "DENY": 2, "NEEDS_HUMAN": 4},
    "results": [{ "claim_id", "decision", "rules_fired": [], "reason_codes": [], "explanation",
                  "advisories": [], "source_files": [], "extracted": {},
                  "checks": [{ "check_no", "check_name", "outcome", "rule_id", "reason_code", "detail" }] }],
    "warnings": ["..."], "csv": "<decisions.csv text>" }
  ```
- Input errors (400/413/422) return `{"error": "<short title>", "detail": "<what to do>"}`. Use these for a missing upload, a bad workbook, or a file over 10 MB.
- When `frontend/dist` exists, FastAPI also serves it at `/`, so one command runs everything.

### 4.5 Reason code → policy citation

| Code | Section | Code | Section |
|---|---|---|---|
| R201 / R202 / R203 | 3.1 Required Fields | R401 | 2.5 Prior Authorization |
| R101 | 2.1 Eligibility (+ 2.8 Appeals) | R801 | 2.3 Network (+ 2.4 Emergency Services if ER) |
| R102 | 3.3 Duplicates (+ 2.8 Appeals) | R901 | 3.6 Decision Authority and Thresholds |
| APPROVE | 3.2 Recommended Validation Order | | |

## 5. Allowed dependencies

- **Backend (Python 3.11):** `fastapi`, `uvicorn[standard]`, `python-multipart`, `pypdf`, `openpyxl`, `pandas`, `pytest`, `httpx` (for FastAPI's TestClient)
- **Frontend:** `react`, `react-dom`, `vite`, `typescript`, `@vitejs/plugin-react`, `lucide-react` (icons), `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`. Hand-written CSS with design tokens; **no** UI component library and no Streamlit.

## 6. Golden results (the 10 provided claims): the regression target

| Claim | Decision | rules_fired | reason_codes |
|---|---|---|---|
| CLM-2026-0001 | APPROVE | | |
| CLM-2026-0002 | DENY | DUP-01 | R102 |
| CLM-2026-0003 | NEEDS_HUMAN | PA-01;AMT-01 | R401;R901 |
| CLM-2026-0004 | DENY | ELIG-01 | R101 |
| CLM-2026-0005 | NEEDS_HUMAN | EMR-01 | R801 |
| CLM-2026-0006 | APPROVE | | |
| CLM-2026-0007 | APPROVE | | |
| CLM-2026-0008 | NEEDS_HUMAN | PA-01 | R401 |
| CLM-2026-0009 | NEEDS_HUMAN | VAL-01;VAL-02 | R201;R202 |
| CLM-2026-0010 | APPROVE | | |

If the code disagrees with this table, investigate before changing either one, and tell the user what you found.

## 7. Code style

- Python: type hints everywhere, small functions, docstrings on public functions. No `print` in library code; use `logging`, which logs member IDs only. f-strings.
- TypeScript: `strict` mode, function components and hooks, and API types mirrored in `src/types.ts`.
- Comments explain *why*, not *what*.
