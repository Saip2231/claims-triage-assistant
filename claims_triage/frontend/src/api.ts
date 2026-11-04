import type { ApiErrorBody, TriageResponse } from "./types";

const TIMEOUT_MS = 120_000;

/** Every failure the UI can show: HTTP errors, network failures and timeouts. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly error: string,
    public readonly detail: string,
  ) {
    super(`${error}: ${detail}`);
    this.name = "ApiError";
  }
}

export interface TriageInputs {
  claims: File[];
  policy: File;
  workbook: File;
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === "object" && value !== null && "error" in value && "detail" in value;
}

/** POST the three inputs to /api/triage. Always throws ApiError on failure. */
export async function triage(inputs: TriageInputs): Promise<TriageResponse> {
  const form = new FormData();
  inputs.claims.forEach((file) => form.append("claims", file, file.name));
  form.append("policy", inputs.policy, inputs.policy.name);
  form.append("workbook", inputs.workbook, inputs.workbook.name);

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch("/api/triage", { method: "POST", body: form, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "The triage took too long", "No answer after 2 minutes. Try fewer files or try again.");
    }
    throw new ApiError(
      0,
      "Can't reach the triage server",
      "Is it running on port 8000? Start it from claims_triage\\backend with: .\\.venv\\Scripts\\python -m uvicorn api:app --port 8000",
    );
  } finally {
    window.clearTimeout(timer);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // A non-JSON body (e.g. a proxy error page) is handled below.
  }

  if (!response.ok) {
    if (isErrorBody(body)) throw new ApiError(response.status, body.error, body.detail);
    // Our server always answers 5xx with a JSON {error, detail}. A bare 5xx comes from the dev
    // proxy when the backend is down.
    if (response.status >= 500) {
      throw new ApiError(
        response.status,
        "Can't reach the triage server",
        "Is it running on port 8000? Start it from claims_triage\\backend with: .\\.venv\\Scripts\\python -m uvicorn api:app --port 8000",
      );
    }
    throw new ApiError(response.status, `Request failed (${response.status})`, "Please try again.");
  }
  return body as TriageResponse;
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(0, "Something went wrong", err instanceof Error ? err.message : String(err));
}
