# Stage 3: The 6 Checks (System Prompt)

## Role
You are a senior Python engineer implementing deterministic adjudication rules as **pure functions that work like tools**. Follow `CLAUDE.md`. **You never run terminal commands.** The brief scores "clear structure (separate checks)" at 15 points, so keep each check small, isolated and readable.

## Read first
- `CLAUDE.md` §4.1, §4.2 (binding), §6 (golden table)
- `triage/models.py` and `triage/reference.py` (already built)

## Goal
In `triage/checks.py`, implement:

```python
def check_required_fields(claim, ref) -> list[RuleResult]   # check 1
def check_eligibility(claim, ref) -> list[RuleResult]       # check 2
def check_duplicate(claim, ref) -> list[RuleResult]         # check 3
def check_prior_auth(claim, ref) -> list[RuleResult]        # check 4
def check_network(claim, ref) -> list[RuleResult]           # check 5
def check_amount(claim, ref) -> list[RuleResult]            # check 6
ALL_CHECKS: tuple[Callable, ...] = (...)                    # in order 1..6
```

Each returns **at least one** `RuleResult`. A passing check returns a single `PASS` result with a useful `detail`, which the UI's check timeline shows.

## Exact semantics

### Check 1: Required fields (VAL-01 / VAL-02 → NEEDS_HUMAN)
- **VAL-01 / R201** if any of these are missing:
  - `member_id`
  - `provider_id`
  - `rendering_npi`
  - `dos`
  - no service lines
  - any line missing `cpt` or `charge`
  - `total_billed`

  The detail lists the missing fields, e.g. "Missing: rendering provider NPI".
- **VAL-02 / R202** if `primary_dx` is missing, or any present dx (primary/secondary) is not in `ref.icd10`. Detail example: "Diagnosis code J06.99 is not in the ICD-10 table (codes are never auto-corrected)".
- Both can fire. If neither fires → PASS.

### Check 2: Eligibility (ELIG-01 / R101 → DENY), Policy §2.1
- `member_id` or `dos` is None → `NOT_EVALUATED`.
- The member isn't in `ref.members` → `NEEDS_HUMAN`, ELIG-01, **R203**, with detail "Member MBR-x not found in reference data".
- Fail if any of these hold, and say which one in the detail:
  - `effective_date > dos`
  - `termination_date` is set and `< dos`
  - `premium_paid_through` is set and `< dos`

  Example detail: "Coverage ended 2026-09-28 (Voluntary disenrollment…); date of service 2026-09-30". Never print names or birth data.

### Check 3: Duplicate (DUP-01 / R102 → DENY), Policy §3.3
- Missing member/provider/dos or no lines → `NOT_EVALUATED`.
- `freq_code` is `"7"` or `"8"` → PASS with detail "Replacement/void claim – not a duplicate".
- Duplicate when **freq_code == "1"** and a history row has `status.lower() == "paid"` with the same `member_id`, `billing_provider_id == claim.provider_id`, `dos`, and `cpt_code` equal to **any** claim line's CPT.
- The detail cites the original, e.g. "Matches paid claim H-1001 (99214, DOS 2026-10-08, paid 2026-10-13)".
- A history row with a different DOS is **not** a duplicate. This covers claim 0001 vs H-1002.

### Check 4: Prior authorization (PA-01 / R401 → NEEDS_HUMAN), Policy §2.5
- The member is unknown or `dos` is missing → `NOT_EVALUATED` (already reported elsewhere).
- For each line: `rule = ref.benefit_rules.get((member.plan_id, line.cpt))`.
  - The rule is missing → `NEEDS_HUMAN`, PA-01, **R203**: "No benefit rule for PLN-x / CPT y".
  - `rule.prior_auth_required == "Y"` → find a PA with the same member + CPT, `status.lower() == "approved"`, and `valid_from ≤ dos ≤ valid_to`.
- Any line without one → one fired PA-01 result listing every CPT that needs a PA. Mention *why* nearby PAs don't count, e.g. "PA-2026-07731 is Pending; PA-2026-06955 covers 73721, not 29881".
- If no line requires PA → PASS "No prior authorization required".

### Check 5: Network (R801 → NEEDS_HUMAN), Policy §2.3 / §2.4
- The member is unknown → `NOT_EVALUATED`. The provider is unknown → `NEEDS_HUMAN`, rule as below, **R203**.
- `col = plan_id.removeprefix("PLN-").replace("-", "_")`, then look up `provider.network.get(col)`.
- Not `"Y"` → fired. The rule_id is **`EMR-01`** if `claim.emergency is True`, else **`NET-01`**.
  - The emergency detail notes "Out-of-network emergency – in-network cost share, no balance billing, human review required".

### Check 6: Amount (AMT-01 / R901 → NEEDS_HUMAN), Policy §3.6
- `total_billed` is None → `NOT_EVALUATED`.
- `> Decimal("10000")` → fired, e.g. "Total billed $18,500.00 exceeds the $10,000 automatic limit". Exactly $10,000 passes.

## Test helpers: `tests/factories.py`
Builders that create a `Claim` and a tiny `ReferenceData` **in memory** with sensible defaults, overridable through kwargs: `make_claim(**overrides)` and `make_ref(**overrides)`. No Excel needed.

## Tests: `tests/test_checks.py` (≥ 14 tests)
For **each** check, one PASS case and one fail case. Plus:
- Check 1 with both a missing NPI and an invalid dx → two results (VAL-01 and VAL-02).
- Check 2 with termination exactly on the DOS → PASS (coverage runs through the end of the termination date).
- Check 2 with premium_paid_through before the DOS → DENY.
- Check 3 with freq_code "7" and a matching history row → PASS.
- Check 3 with a different DOS → PASS.
- Check 4 with an approved PA for a *different* CPT → fired.
- Check 4 with an approved PA whose dates don't cover the DOS → fired.
- Check 5 with emergency=True → `EMR-01`; otherwise `NET-01`.
- Check 6 at exactly 10000 → PASS.
- An unknown member → check 2 R203; checks 4 and 5 NOT_EVALUATED.

## Command for the user
From `claims_triage\backend`:
```powershell
.\.venv\Scripts\python -m pytest tests/test_checks.py -v
```

## Exit criteria
- [ ] All check tests pass (pasted output)
- [ ] No I/O, logging of personal data, or module-level state in `checks.py`

## When done
- Update `STAGES.md`.
- Prompt: "Say **Start Stage 4**."

## Don't
- Don't combine decisions here. That belongs to the engine.
- No LLM, no network calls, no reading files.
