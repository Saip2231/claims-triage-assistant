# Mini Claims Triage Assistant: Working Plan

> **Updated 2026-11-04:** this plan has been superseded on two points.
> - **UI:** React + FastAPI, not Streamlit.
> - **Explanations:** template-only, with **no LLM anywhere**. Ignore the "LLM mode" in §9.
>
> The binding rules now live in `CLAUDE.md`. The stage-by-stage work lives in `STAGES.md` and `prompts/`.

> Built from a full read of `Problem Statement.pdf`, `policy_documents.pdf`, all 10 claims (TXT + PDF), and every sheet of `claims_triage_dataset.xlsx`.
> All data is synthetic.

---

## 1. What we're building (one paragraph)

This is a **Streamlit** web app. The user uploads claim files (PDF or TXT, several at once), the policy PDF and the reference workbook. For each claim, the app:

1. **extracts** the fields from the file itself, never from the `Claims` or `Claim_Lines` sheets;
2. runs **6 deterministic checks** as plain Python functions;
3. **combines** the results with the required priority order;
4. writes a **plain-language explanation** that cites the matching section of the *uploaded* policy.

Results appear in a table and download as `decisions.csv`. Nothing should crash the app: a bad file becomes a `NEEDS_HUMAN` row.

---

## 2. Scoring map: where the points come from

| Area | Pts | How this plan earns it |
|---|---|---|
| Decisions match expectations | 35 | Implement the 6 checks exactly as specified, including policy details (premium-paid-through, frequency code). Verify against the expected-results table in §6. |
| Extraction for PDF **and** TXT | 15 | One shared parser. Both formats are normalised to `label → value` first. The TXT and PDF versions of every claim must give identical fields (enforced by a test). |
| UI: uploads, table, CSV, errors | 15 | Three uploaders, a Run button, a results table, a download button, plus a defined error-handling matrix (§5.4). |
| Clear structure | 15 | One module per concern. Each check is a separate pure function that returns a `RuleResult`. |
| Explanations cite policy | 10 | Policy sections are parsed from the uploaded PDF at runtime. Each reason code maps to a section, and the explanation quotes the section number and title. |
| Tests and runnability | 5 | Around 12 pytest tests, `requirements.txt`, one-line run commands. |
| Honest limitations | 5 | The README lists what the 6 checks miss on these exact claims (§7). |

---

## 3. Key facts pulled from the documents

### 3.1 The 6 required checks

| # | Check | Data used | Fail → | Code | `rules_fired` ID |
|---|---|---|---|---|---|
| 1 | Rendering NPI present **and** diagnosis code exists in `ICD10_Codes` | claim + `ICD10_Codes` | NEEDS_HUMAN | R201 (missing) / R202 (invalid dx) | `VAL-01` / `VAL-02` |
| 2 | Member active on DOS: `effective_date ≤ DOS ≤ termination_date` (if any) **and** `premium_paid_through ≥ DOS` (Policy §2.1) | `Members` | DENY | R101 | `ELIG-01` |
| 3 | Not a duplicate: a **Paid** history row with the same member + billing provider + DOS + CPT, **and** claim frequency code = 1 (Policy §3.3) | `Claims_History` | DENY | R102 | `DUP-01` |
| 4 | If `Benefit_Rules.prior_auth_required = Y` for (member's plan, CPT), then an **Approved** PA must exist for the same member + CPT with `valid_from ≤ DOS ≤ valid_to` | `Benefit_Rules`, `Prior_Auth_Log` | NEEDS_HUMAN | R401 | `PA-01` |
| 5 | Provider is in-network: column `in_network_` + plan ID with `PLN-` removed and `-` changed to `_` | `Providers` | NEEDS_HUMAN | R801 | `EMR-01` if emergency = Y, else `NET-01` |
| 6 | Total billed ≤ $10,000 | claim | NEEDS_HUMAN | R901 | `AMT-01` |

**Combining (strict priority):**

1. Check 1 failed → **NEEDS_HUMAN**
2. Otherwise, any DENY → **DENY**
3. Otherwise, any NEEDS_HUMAN → **NEEDS_HUMAN**
4. Otherwise → **APPROVE**

Always run all checks and list every rule that fired, even when check 1 decides the outcome.

### 3.2 Reason code → policy section, used for citations

| Code | Cite | Plus |
|---|---|---|
| R201 / R202 | §3.1 Required Fields | "Do not infer or fix codes. Pend and return to provider." |
| R101 | §2.1 Eligibility | §2.8 Appeals (180-day appeal right on every denial) |
| R102 | §3.3 Duplicates | §2.8 Appeals; cite the original history claim ID and its paid date |
| R401 | §2.5 Prior Authorization | "pended (not denied)" |
| R801 | §2.3 Network (+ §2.4 Emergency Services if the emergency flag is Y) | no balance billing |
| R901 | §3.6 Decision Authority and Thresholds | senior reviewer sign-off |
| APPROVE | §3.2 Recommended Validation Order | "all checks passed" |

### 3.3 Claim file formats: what the parser must handle

| | TXT | PDF (via `pypdf`, already installed) |
|---|---|---|
| Header fields | `Label            : value` on one line | `LABEL` on one line, value on the **next** line |
| Blank values | `(blank)`, `None`, `None provided` | `[ BLANK ]`, `None`, `None provided` |
| Service lines | fixed-width table row | one token per line between `Charge (USD)` and `TOTAL CHARGE` |
| Money | `18,500.00` (commas) | same |
| Attachments | after `[ATTACHMENT …]` | page 2 |

**Approach:**

1. Normalise both formats into a `{canonical_field: value}` dict using a label-alias table (for example `"Rendering provider NPI"` and `"RENDERING PROVIDER NPI"` both map to `rendering_npi`).
2. Parse service lines with **one regex** over whitespace-collapsed text:
   `(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2})\s+(\d{5})\s+(?:([A-Z0-9]{2})\s+)?([A-D])\s+(\d+)\s+([\d,]+\.\d{2})`
3. Only parse the claim body, which ends at `TOTAL CHARGE`. The attachment text must never fill in a field: CLM-0009's OCR attachment must not "fix" the blank NPI.
4. Never guess. Any blank or unrecognised value becomes `None`, which counts as missing.

---

## 4. Architecture

```
claims_triage/
├── app.py                  # Streamlit UI only (no business logic)
├── triage/
│   ├── models.py           # dataclasses: Claim, ServiceLine, RuleResult, Decision
│   ├── extract.py          # read_txt(), read_pdf(), parse_claim_text() → Claim
│   ├── reference.py        # load_workbook() → ReferenceData; validates sheets/columns
│   ├── checks.py           # check_required_fields, check_eligibility, check_duplicate,
│   │                       # check_prior_auth, check_network, check_amount
│   ├── engine.py           # run_all_checks(), combine(), triage_one(), triage_batch()
│   ├── policy.py           # parse policy PDF → {"2.1": ("Eligibility", text), …}
│   └── explain.py          # TemplateExplainer (default) + optional LLMExplainer
├── scripts/
│   └── run_batch.py        # CLI: produce output/decisions.csv without the UI
├── tests/
│   ├── fixtures/           # copies of the 10 claims + workbook + policy
│   ├── test_extract.py
│   ├── test_checks.py
│   ├── test_decisions.py
│   └── test_robustness.py
├── output/decisions.csv
├── requirements.txt        # streamlit, pandas, openpyxl, pypdf, pytest (+ anthropic, optional)
└── README.md
```

**Flow:**

```
upload files ─► extract.py ─► Claim ─► checks.py (×6) ─► [RuleResult…] ─► engine.combine()
                                          ▲                                    │
                         reference.py ────┘                                    ▼
                         policy.py ───────────────────────────────► explain.py ─► row
```

**Contracts:**

- Each check is `def check_x(claim: Claim, ref: ReferenceData) -> RuleResult`.
- `RuleResult` has the fields `check_no, rule_id, passed, outcome ('PASS'|'DENY'|'NEEDS_HUMAN'), reason_code, detail, evidence`.
- Checks are pure functions: no I/O and no LLM. They are trivially unit-testable.

---

## 5. Build steps

### Day 1: extraction and checks (aim: correct decisions for all 10 claims)

| Step | Task | Done when |
|---|---|---|
| 1.1 | Set up the project skeleton, `requirements.txt` and the dataclasses | `pytest` runs (with 0 tests) |
| 1.2 | `reference.py`: load sheets with `dtype=str` for IDs and codes (keeps `'09'` and `'I10'` intact), parse dates, check that the required sheets and columns exist | Clear error for a missing sheet |
| 1.3 | `extract.py`: TXT parser | All 10 TXT files parse correctly |
| 1.4 | `extract.py`: PDF parser that reuses the same normaliser | **TXT and PDF give identical `Claim` objects for all 10** |
| 1.5 | `checks.py`: the 6 functions | Unit test per check, pass and fail |
| 1.6 | `engine.py`: combine logic + `scripts/run_batch.py` | Output matches §6 for all 10 |

### Day 2: UI, explanations, tests, docs

| Step | Task | Done when |
|---|---|---|
| 2.1 | `policy.py`: split the uploaded policy into sections with the regex `^(\d\.\d+)\s+(.+)$` | Returns §2.1–§3.8 with text |
| 2.2 | `explain.py`: template explainer (default). Optional Claude explainer behind an env var. It receives **only** claim ID, member ID, rule results and policy text, and falls back to the template on any error. | Every row cites a section |
| 2.3 | `app.py`: UI (see 5.3) | Manual run works end to end |
| 2.4 | Error handling (see 5.4) | Every row in the error matrix is tested by hand |
| 2.5 | Tests (see §8) | All green |
| 2.6 | README (one page) and final `decisions.csv` | Zip-ready |

### 5.3 UI layout (Streamlit)

```
┌─ Mini Claims Triage Assistant ─────────────────────────────────────┐
│ Sidebar: Explanation mode ○ Template ○ LLM (only if API key set)    │
│                                                                    │
│ 1. Claims        [ drag & drop, multiple, .pdf/.txt ]              │
│ 2. Policy PDF    [ single .pdf ]                                   │
│ 3. Workbook      [ single .xlsx ]                                  │
│                                                                    │
│ [ ▶ Run triage ]   (disabled until all 3 are uploaded)             │
│                                                                    │
│ Summary: ✅ 4 APPROVE  ⛔ 2 DENY  👤 4 NEEDS_HUMAN                    │
│ ┌ claim_id │ decision │ rules_fired │ reason_codes │ explanation ┐ │
│ │ …colour-coded decision column…                                │ │
│ └───────────────────────────────────────────────────────────────┘ │
│ ▸ Per-claim detail expander: extracted fields + each check result  │
│ [ ⬇ Download decisions.csv ]                                       │
└────────────────────────────────────────────────────────────────────┘
```

Keep results in `st.session_state` so the download button doesn't trigger a rerun that wipes the table.

### 5.4 Error-handling matrix

| Situation | Behaviour |
|---|---|
| A required upload is missing | Run button disabled, with a clear `st.warning` naming what's missing |
| Wrong file type in the claims uploader (e.g. `.docx`) | Skip it with a warning and add a `NEEDS_HUMAN` row (`claim_id` = file name, explanation "unsupported file type") |
| PDF or TXT unreadable or corrupt, or no text extracted | `NEEDS_HUMAN` row: "file could not be read" |
| Claim ID not found in the file | `NEEDS_HUMAN` row keyed by file name |
| Required field missing (member, DOS, CPT, amount…) | That check fails as missing; never guess |
| Member, provider or plan not in the workbook | The check can't verify it → `NEEDS_HUMAN` with a clear detail (an unknown ID is not proof of ineligibility) |
| Workbook missing a sheet or column, or not an xlsx | `st.error` naming the sheet or column, and the run does not start |
| Policy PDF unreadable or no sections found | Run anyway. Explanations still give the section numbers, with a warning that the text couldn't be quoted. |
| Same claim uploaded as both PDF and TXT | Deduplicate by `claim_id`. If the fields differ → `NEEDS_HUMAN` ("conflicting documents", §3.6). |
| Exception inside any one claim | `try/except` per claim, so one bad claim never stops the batch |

---

## 6. Expected results for the 10 claims (hand-verified against the workbook)

| Claim | Member (plan) | Key facts | Fired | **Decision** |
|---|---|---|---|---|
| 0001 | 100007 (SLV-PPO) | Active; P-002 in-network; J06.9 valid; 99213 needs no PA; history H-1002 is a **different DOS** | — | **APPROVE** |
| 0002 | 100019 (GLD-PPO) | **H-1001**: same member, P-003, 2026-10-08, 99214, Paid on 10-13; frequency code 1 | DUP-01 / R102 | **DENY** |
| 0003 | 100034 (SLV-PPO) | 29881 needs PA. PA-07731 is *Pending* (a retro request). PA-06955 covers 73721, **not** 29881. Billed $18,500. | PA-01 / R401, AMT-01 / R901 | **NEEDS_HUMAN** |
| 0004 | 100042 (BRZ-HMO) | Terminated **2026-09-28**; DOS **2026-09-30** | ELIG-01 / R101 | **DENY** |
| 0005 | 100056 (GLD-PPO) | P-009 is `N` for every plan; emergency = Y; $3,550 | EMR-01 / R801 | **NEEDS_HUMAN** |
| 0006 | 100063 (PLT-EPO) | Everything passes; H-1005/1006 are DOS 07-15, not dups | — | **APPROVE** |
| 0007 | 100071 (SLV-PPO) | Everything passes; 99215 needs no PA | — | **APPROVE** |
| 0008 | 100078 (GLD-PPO) | 30400 needs PA (`Conditional`, PA = Y); no PA on file. Z41.1 *is* a valid ICD code. $9,800 ≤ $10k. | PA-01 / R401 | **NEEDS_HUMAN** |
| 0009 | 100085 (SLV-PPO) | Rendering NPI blank; **J06.99 is not in `ICD10_Codes`** (J06.9 is: don't auto-correct) | VAL-01 / R201, VAL-02 / R202 | **NEEDS_HUMAN** |
| 0010 | 100093 (BRZ-HMO) | Active; P-010 in BRZ network; 90837 needs no PA; H-1008 is a different DOS | — | **APPROVE** |

**Totals:** 4 APPROVE · 2 DENY · 4 NEEDS_HUMAN

These become the regression test (`test_decisions.py` asserts all 10).

---

## 7. "Review your results and note anything that looks wrong" (README limitations)

The fuller policy pack has rules **beyond the 6 required checks**. On these exact claims they would change the outcome. I'll keep the decisions as the spec requires, but mention each one as an advisory note in the explanation and in the README. That's honest, and it shows I read the policy.

| Claim | 6-check result | What the full policy says | Rule |
|---|---|---|---|
| **0006** | APPROVE | 82947 and 82565 are bundled into 80053, same provider and DOS → those 2 lines should be denied; pay the rest | BUN-01 / R301 (§3.4) |
| **0007** | APPROVE | P-007's level-5 rate is 0.79 vs a peer median of 0.08 (≥ 40% and ≥ 3×). The note shows 12 minutes and straightforward decision making → route to Payment Integrity. | EM-01 / R701 (§3.5, CP-EM-004) |
| **0010** | APPROVE | Bronze limit is 12 psychotherapy visits; the member has used 12 → Clinical/Compliance parity review, **not** auto-deny | LIM-01 / R601 (§2.7, CP-BH-002) |
| **0008** | NEEDS_HUMAN | Z41.1 plus a note saying "aesthetic, no functional impairment" is a clear cosmetic exclusion, ≤ $10k → policy allows **auto-DENY** | EXC-01 / R501 (§2.6, CP-COSM-001) |
| **0003** | NEEDS_HUMAN | M25.561 (pain only) doesn't support 29881 → also needs clinical review | MN-01 / R402 (CP-ORTHO-029) |
| **0005** | NEEDS_HUMAN | Billed 99285 at $2,850 vs $520 allowed (> 3×) → charge-outlier flag | CHG-01 / R902 |
| **0009** | NEEDS_HUMAN | OCR confidence 0.62 on the dx code also supports a human look | §3.6 confidence < 0.75 |

**Pick three for the README's "limitations of my checks":**

1. No line-level bundling (0006).
2. No provider-pattern or E/M review (0007).
3. No benefit limits or parity (0010).

Then list the others under "ideas for improvement".

**Other honest limits to mention:**

- The parser is tuned to this one layout. A different CMS-1500 rendering would need new aliases.
- No OCR for image-only PDFs.
- Plan-year and timely-filing checks are not applied.
- The network check doesn't apply the PPO out-of-network coverage nuance.

> **Stretch (only if time allows):** a sidebar toggle, **"Apply extended policy rules"**, that adds BUN-01, EM-01, LIM-01, EXC-01, MN-01 and CHG-01. It's **off by default**, so the submitted CSV follows the spec exactly.

---

## 8. Tests (the minimum asked is 4; plan ≈ 12)

| File | Test |
|---|---|
| `test_extract.py` | TXT extraction for CLM-0003 gives the expected member, provider, DOS, dx, CPT 29881 with modifier RT, and $18,500 |
| | PDF extraction for CLM-0005 gives 3 lines and a $3,550 total |
| | Parity: TXT == PDF for all 10 claims (parametrised) |
| | CLM-0009: blank rendering NPI → `None` (not taken from the attachment) |
| `test_checks.py` | One pass case and one fail case per check (6 checks), using small in-memory reference data |
| `test_decisions.py` | **APPROVE** (0001), **DENY** (0004), **NEEDS_HUMAN** (0009), and the full 10-claim table from §6 |
| | Priority: check 1 failing plus an eligibility DENY → NEEDS_HUMAN |
| `test_robustness.py` | A garbage `.txt` or empty PDF → a NEEDS_HUMAN row, no exception |
| | A missing workbook sheet → a clear error |

---

## 9. Explanation layer

**Template mode (default; guaranteed to work offline):**

```
CLM-2026-0004 (member MBR-100042): DENIED. The member's coverage was not in force on the
date of service 2026-09-30 – coverage ended 2026-09-28. Policy Section 2.1 Eligibility:
"…the termination date (if any) is on or after the DOS…". Reason R101. You may appeal
within 180 days (Section 2.8 Appeals).
```

**LLM mode (optional):**

- Uses Claude (`claude-sonnet-5-5`), enabled only when `ANTHROPIC_API_KEY` is set.
- The prompt receives only:
  - `claim_id`
  - `member_id`
  - the list of `{rule_id, reason_code, outcome, detail}`
  - the text of the relevant policy sections
- No birth year, sex or names.
- The LLM never changes the decision. It only rewrites the explanation. If the output doesn't mention the section number, fall back to the template.
- The README states which mode produced the submitted CSV (recommended: template, for reproducibility).

---

## 10. README outline (one page)

1. **Run:** `pip install -r requirements.txt` → `streamlit run app.py` · CLI: `python scripts/run_batch.py --claims … --workbook … --policy …` · tests: `pytest`
2. **Design:** the flow diagram from §4, and the fact that checks are pure functions and the LLM is explanation-only
3. **Assumptions:**
   - premium-paid-through is part of eligibility
   - frequency code 7 or 8 is never a duplicate
   - an unknown member or provider → NEEDS_HUMAN
   - the network rule ID is EMR-01 when emergency = Y, else NET-01
   - extraction reads only the claim body, never the attachments
4. **Three limitations, plus ideas for improvement** (§7)
5. **Explanation mode used:** template, or LLM

---

## 11. Submission checklist

- [ ] `decisions.csv` has exactly these columns: `claim_id, decision, rules_fired, reason_codes, explanation`
- [ ] Multi-value cells are joined with `;` (e.g. `PA-01;AMT-01` / `R401;R901`)
- [ ] The CSV was regenerated from the **UI** and from the CLI, and both are identical
- [ ] `pytest` is all green
- [ ] No real personal data anywhere; prompts and logs reference only member IDs
- [ ] Zip contents: code + `decisions.csv` + `README.md` + `tests/` (exclude `.venv` and `__pycache__`)
