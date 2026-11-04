import { useMemo, useReducer } from "react";
import { FileSpreadsheet, FileText, ScrollText } from "lucide-react";
import { ApiError, toApiError, triage } from "./api";
import { AppHeader } from "./components/AppHeader";
import { ClaimDrawer } from "./components/ClaimDrawer";
import { DownloadButton, ErrorBanner, StaleBanner, WarningsPanel } from "./components/Feedback";
import { ResultsTable } from "./components/ResultsTable";
import { RunBar } from "./components/RunBar";
import { SummaryStrip, type Filter } from "./components/SummaryStrip";
import { UploadZone } from "./components/UploadZone";
import type { TriageResponse } from "./types";

// ------------------------------------------------------------------ state

type Status = "idle" | "running" | "done" | "error";

interface State {
  claims: File[];
  policy: File | null;
  workbook: File | null;
  status: Status;
  response: TriageResponse | null;
  error: ApiError | null;
  stale: boolean;
  filter: Filter;
  query: string;
  selectedId: string | null;
}

type Action =
  | { type: "claims"; files: File[] }
  | { type: "policy"; file: File | null }
  | { type: "workbook"; file: File | null }
  | { type: "run" }
  | { type: "success"; response: TriageResponse }
  | { type: "failure"; error: ApiError }
  | { type: "dismissError" }
  | { type: "filter"; filter: Filter }
  | { type: "query"; query: string }
  | { type: "select"; id: string | null };

const initialState: State = {
  claims: [],
  policy: null,
  workbook: null,
  status: "idle",
  response: null,
  error: null,
  stale: false,
  filter: "ALL",
  query: "",
  selectedId: null,
};

function reducer(state: State, action: Action): State {
  // Changing an input after a run marks the shown results as stale.
  const touched = { stale: state.response !== null };
  switch (action.type) {
    case "claims":
      return { ...state, ...touched, claims: action.files };
    case "policy":
      return { ...state, ...touched, policy: action.file };
    case "workbook":
      return { ...state, ...touched, workbook: action.file };
    case "run":
      return { ...state, status: "running", error: null };
    case "success":
      return { ...state, status: "done", response: action.response, stale: false, filter: "ALL", query: "", selectedId: null };
    case "failure":
      return { ...state, status: "error", error: action.error };
    case "dismissError":
      return { ...state, error: null };
    case "filter":
      return { ...state, filter: action.filter };
    case "query":
      return { ...state, query: action.query };
    case "select":
      return { ...state, selectedId: action.id };
  }
}

function missingInputs(s: State): string[] {
  const missing: string[] = [];
  if (s.claims.length === 0) missing.push("claim files");
  if (!s.policy) missing.push("policy PDF");
  if (!s.workbook) missing.push("reference workbook");
  return missing;
}

// ------------------------------------------------------------------ view

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { response, status } = state;
  const running = status === "running";
  const missing = missingInputs(state);

  async function run() {
    if (!state.policy || !state.workbook || state.claims.length === 0 || running) return;
    dispatch({ type: "run" });
    try {
      const result = await triage({ claims: state.claims, policy: state.policy, workbook: state.workbook });
      dispatch({ type: "success", response: result });
    } catch (err) {
      dispatch({ type: "failure", error: toApiError(err) });
    }
  }

  const visible = useMemo(() => {
    if (!response) return [];
    const q = state.query.trim().toLowerCase();
    return response.results.filter((r) => {
      if (state.filter !== "ALL" && r.decision !== state.filter) return false;
      if (!q) return true;
      const haystack = [r.claim_id, r.decision, ...r.rules_fired, ...r.reason_codes, r.explanation].join(" ");
      return haystack.toLowerCase().includes(q);
    });
  }, [response, state.filter, state.query]);

  const selected = response?.results.find((r) => r.claim_id === state.selectedId) ?? null;
  const announcement = response
    ? `Triage complete: ${response.summary.total} claims, ${response.summary.APPROVE} approved, ` +
      `${response.summary.DENY} denied, ${response.summary.NEEDS_HUMAN} need a human.`
    : "";

  return (
    <>
      <AppHeader />
      <main className="layout">
        <aside className="panel inputs" aria-label="Inputs">
          <h2 className="section-title">Inputs</h2>
          <UploadZone
            label="Claim files"
            hint="PDF or TXT · select many at once"
            accept={[".pdf", ".txt"]}
            multiple
            files={state.claims}
            onChange={(files) => dispatch({ type: "claims", files })}
            icon={<FileText size={22} aria-hidden="true" />}
            disabled={running}
          />
          <UploadZone
            label="Policy document"
            hint="policy_documents.pdf"
            accept={[".pdf"]}
            files={state.policy ? [state.policy] : []}
            onChange={(files) => dispatch({ type: "policy", file: files[0] ?? null })}
            icon={<ScrollText size={22} aria-hidden="true" />}
            disabled={running}
          />
          <UploadZone
            label="Reference workbook"
            hint="claims_triage_dataset.xlsx"
            accept={[".xlsx"]}
            files={state.workbook ? [state.workbook] : []}
            onChange={(files) => dispatch({ type: "workbook", file: files[0] ?? null })}
            icon={<FileSpreadsheet size={22} aria-hidden="true" />}
            disabled={running}
          />
          <RunBar missing={missing} running={running} onRun={run} />
        </aside>

        <section className="results" aria-label="Results" aria-busy={running}>
          <div className="results__head">
            <h2 className="results__title">Results</h2>
            {response && <DownloadButton csv={response.csv} />}
          </div>

          {running && <div className="progress" role="progressbar" aria-label="Running triage" />}
          {state.error && <ErrorBanner error={state.error} onDismiss={() => dispatch({ type: "dismissError" })} />}
          {state.stale && !running && <StaleBanner onRerun={run} disabled={missing.length > 0} />}

          {response ? (
            <>
              <SummaryStrip
                summary={response.summary}
                filter={state.filter}
                onFilter={(filter) => dispatch({ type: "filter", filter })}
              />
              <WarningsPanel warnings={response.warnings} />
              <ResultsTable
                rows={visible}
                totalRows={response.results.length}
                filter={state.filter}
                query={state.query}
                onQuery={(query) => dispatch({ type: "query", query })}
                onSelect={(id) => dispatch({ type: "select", id })}
              />
            </>
          ) : (
            <div className="panel empty">
              <h3 className="empty__title">No results yet</h3>
              <p className="muted">Each claim gets a decision, the rules that fired and a plain-language reason.</p>
              <ol className="empty__steps">
                <li>
                  <span className="step-no">1</span> Add claim files
                </li>
                <li>
                  <span className="step-no">2</span> Add the policy and workbook
                </li>
                <li>
                  <span className="step-no">3</span> Run triage
                </li>
              </ol>
            </div>
          )}
        </section>
      </main>

      {selected && <ClaimDrawer result={selected} onClose={() => dispatch({ type: "select", id: null })} />}
      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>
    </>
  );
}
