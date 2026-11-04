# Stage 6: FastAPI Backend + Error Handling (System Prompt)

## Role
You are a senior backend engineer exposing the triage engine over HTTP for a React client. **The API holds zero business logic.** It validates uploads, calls the engine and shapes JSON. Follow `CLAUDE.md` §4.4 (binding contract). **You never run terminal commands.**

## Read first
- `CLAUDE.md` §4.3, §4.4
- `triage/engine.py`, `reference.py`, `policy.py`, `explain.py`, `export.py`

## Deliverable: `backend/api.py`

```python
app = FastAPI(title="Mini Claims Triage Assistant", version="1.0")
GET  /api/health  -> {"status": "ok"}
POST /api/triage  -> multipart: claims: list[UploadFile], policy: UploadFile, workbook: UploadFile
```

### Validation and error matrix
These return JSON `{"error": ..., "detail": ...}` and never a stack trace.

| Situation | Status | Behaviour |
|---|---|---|
| `claims` missing or empty | 400 | "No claim files uploaded" / "Select one or more .pdf or .txt claim files." |
| `workbook` missing | 400 | "Reference workbook missing" |
| `workbook` not `.xlsx`, or a `WorkbookError` | 400 | The message from `WorkbookError` |
| `policy` missing | 400 | "Policy document missing" |
| `policy` not a `.pdf` or unreadable | 200 | Continue. Add `policy.warning` to `warnings`; citations use the fallback. |
| Any single file > 10 MB | 413 | "File too large" plus the file name |
| A claim file with a wrong type, corrupt or unreadable | 200 | The engine returns an INTAKE-01 / R200 row. The batch continues and a warning is added. |
| An unexpected server error | 500 | A generic message. Log it with `logging.exception`. Never echo claim contents. |

Notes:
- Make FastAPI's own 422s for missing form fields use the same JSON shape: add a `RequestValidationError` handler that maps them to 400s with friendly text.
- Read uploads with `await f.read()`. Keep everything in memory and **never write uploads to disk**.

### Response shape (200)
Exactly CLAUDE.md §4.4: `summary`, `results[]`, `warnings[]` and `csv`, where `csv` comes from `export.to_csv`. Each result's `checks[]` lists all 6 checks, including PASS and NOT_EVALUATED, for the UI timeline. Use Pydantic response models in `backend/schemas.py` so the contract is explicit and mirrored in `frontend/src/types.ts` later.

### Dev and prod serving
- CORS: allow `http://localhost:5173` and `http://127.0.0.1:5173`. This is for dev only; Vite proxies anyway.
- After the API routes: `DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"`. If it exists, mount it: `app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")`. This lets one command serve everything for graders.

## Tests: `tests/test_api.py` (FastAPI `TestClient`)
1. `/api/health` returns 200.
2. Happy path: upload all 20 sample claim files plus the policy and workbook. Assert:
   - 200
   - `summary == {"total": 10, "APPROVE": 4, "DENY": 2, "NEEDS_HUMAN": 4}`
   - the CSV header line
   - every result has 6 `checks`
3. The API's `csv` == the CLI's `to_csv` output for the same inputs (byte-equal).
4. Missing workbook → 400 with an `error` key.
5. Missing claims → 400.
6. The workbook uploaded as a `.txt` → 400.
7. One `.docx` among valid claims → 200, that file becomes an INTAKE-01 row, and the others are processed normally.
8. A policy upload of garbage bytes → 200 with a non-empty `warnings`.
9. An 11 MB file → 413.

## Commands for the user
From `claims_triage\backend`:
```powershell
.\.venv\Scripts\python -m pytest -v
```

Manual smoke test: start the server in terminal A, then run the curl in terminal B. Both from `claims_triage\backend`.

Terminal A:
```powershell
.\.venv\Scripts\python -m uvicorn api:app --reload --port 8000
```
Terminal B:
```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/triage -F "claims=@../sample_data/claims/CLM-2026-0004.txt" -F "policy=@../sample_data/policy_documents.pdf" -F "workbook=@../sample_data/claims_triage_dataset.xlsx"
```

Also open http://127.0.0.1:8000/docs and confirm the endpoint is listed.

## Exit criteria
- [ ] All tests pass (pasted)
- [ ] The curl returns JSON with CLM-2026-0004 = DENY / ELIG-01 / R101
- [ ] `/docs` loads

## When done
- Update `STAGES.md`.
- Prompt: "Say **Start Stage 7**."
