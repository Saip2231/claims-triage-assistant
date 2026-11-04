"""FastAPI app: HTTP only, with no business logic (CLAUDE.md §4.4).

It validates the three uploads, calls the triage engine and shapes JSON.
Uploads are kept in memory and never written to disk.

Run (from claims_triage/backend):
    .\\.venv\\Scripts\\python -m uvicorn api:app --reload --port 8000
When frontend/dist exists (after `npm run build`), the React UI is served at /.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path, PurePath

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from schemas import ErrorOut, ResultOut, SummaryOut, TriageResponse
from triage.engine import triage_files
from triage.explain import TemplateExplainer
from triage.export import to_csv
from triage.policy import parse_policy
from triage.reference import WorkbookError, load_reference

log = logging.getLogger("claims_triage.api")

MAX_FILE_BYTES = 10 * 1024 * 1024
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

app = FastAPI(
    title="Mini Claims Triage Assistant",
    version="1.0",
    description="Deterministic claims triage: six rule checks, template explanations, no LLM.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server only
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- errors


class ApiError(Exception):
    """An input problem the user can fix. Becomes {"error", "detail"} JSON."""

    def __init__(self, status: int, error: str, detail: str):
        self.status, self.error, self.detail = status, error, detail


def _error(status: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorOut(error=error, detail=detail).model_dump())


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return _error(exc.status, exc.error, exc.detail)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted({str(e.get("loc", ["", "?"])[-1]) for e in exc.errors()})
    return _error(400, "Invalid upload",
                  f"Check these form fields: {', '.join(fields)}. Send claims, policy and workbook as files.")


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unexpected server error")  # never echo claim contents back
    return _error(500, "Unexpected server error", "Something went wrong on the server. Please try again.")


# --------------------------------------------------------------------------- helpers


def _suffix(upload: UploadFile) -> str:
    return PurePath(upload.filename or "").suffix.lower()


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(413, "File too large", f"{upload.filename} is larger than 10 MB. Upload a smaller file.")
    return data


def _present(upload: UploadFile | None) -> bool:
    # Browsers send an empty part with no filename when nothing was chosen.
    return upload is not None and bool(upload.filename)


# --------------------------------------------------------------------------- routes


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/triage",
    response_model=TriageResponse,
    responses={400: {"model": ErrorOut}, 413: {"model": ErrorOut}, 500: {"model": ErrorOut}},
)
async def triage(
    claims: list[UploadFile] = File(default=[], description="One or more claim files (.pdf or .txt)"),
    policy: UploadFile | None = File(default=None, description="The policy document (.pdf)"),
    workbook: UploadFile | None = File(default=None, description="The reference workbook (.xlsx)"),
) -> TriageResponse:
    claim_uploads = [c for c in claims if _present(c)]
    if not claim_uploads:
        raise ApiError(400, "No claim files uploaded", "Select one or more .pdf or .txt claim files.")
    if not _present(workbook):
        raise ApiError(400, "Reference workbook missing", "Upload claims_triage_dataset.xlsx.")
    if _suffix(workbook) != ".xlsx":
        raise ApiError(400, "Reference workbook must be an .xlsx file",
                       f"'{workbook.filename}' is not an Excel workbook. Upload claims_triage_dataset.xlsx.")
    if not _present(policy):
        raise ApiError(400, "Policy document missing", "Upload policy_documents.pdf.")

    # Read everything up front so size limits apply before any processing.
    files = [(c.filename or "unnamed", await _read(c)) for c in claim_uploads]
    workbook_bytes = await _read(workbook)
    policy_bytes = await _read(policy)

    try:
        ref = await run_in_threadpool(load_reference, workbook_bytes)
    except WorkbookError as exc:
        raise ApiError(400, "Reference workbook problem", str(exc)) from exc

    warnings: list[str] = []
    if _suffix(policy) != ".pdf":
        warnings.append(f"'{policy.filename}' is not a PDF; explanations cite section numbers without quotes.")
        policy_index = parse_policy(None)
    else:
        policy_index = await run_in_threadpool(parse_policy, policy_bytes)
        if policy_index.warning:
            warnings.append(policy_index.warning)

    results, triage_warnings = await run_in_threadpool(
        triage_files, files, ref, TemplateExplainer(policy_index, ref)
    )
    warnings = triage_warnings + warnings + ref.warnings

    counts = Counter(r.decision for r in results)
    log.info("Triaged %d claims from %d files", len(results), len(files))
    return TriageResponse(
        summary=SummaryOut(total=len(results), APPROVE=counts["APPROVE"], DENY=counts["DENY"],
                           NEEDS_HUMAN=counts["NEEDS_HUMAN"]),
        results=[ResultOut.from_result(r) for r in results],
        warnings=warnings,
        csv=to_csv(results),
    )


# Serve the built React app last, so /api/* and /docs always win.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
else:
    # No UI built yet (before `npm run build`): send visitors to the API docs instead of a bare 404.
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs")
