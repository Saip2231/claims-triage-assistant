import { useEffect, useRef, type KeyboardEvent } from "react";
import { CircleCheck, CircleX, Minus, TriangleAlert, X } from "lucide-react";
import type { CheckOut, Outcome, ResultOut } from "../types";
import { DecisionStamp } from "./DecisionStamp";
import { mainExplanation } from "./ResultsTable";

const OUTCOME_ICON = { PASS: CircleCheck, DENY: CircleX, NEEDS_HUMAN: TriangleAlert, NOT_EVALUATED: Minus } as const;
const OUTCOME_LABEL: Record<Outcome, string> = {
  PASS: "Passed",
  DENY: "Deny",
  NEEDS_HUMAN: "Needs human",
  NOT_EVALUATED: "Not evaluated",
};

const FIELD_LABELS: [string, string][] = [
  ["claim_id", "Claim ID"],
  ["received_date", "Received"],
  ["freq_code", "Frequency code"],
  ["member_id", "Member ID"],
  ["provider_id", "Billing provider"],
  ["billing_npi", "Billing NPI"],
  ["rendering_npi", "Rendering NPI"],
  ["place_of_service", "Place of service"],
  ["dos", "Date of service"],
  ["primary_dx", "Primary diagnosis"],
  ["secondary_dx", "Secondary diagnosis"],
  ["prior_auth_number", "Prior auth number"],
  ["emergency", "Emergency"],
  ["attachments", "Attachments"],
  ["total_billed", "Total billed"],
];

interface Line {
  line_no: number;
  dos: string | null;
  cpt: string | null;
  modifier: string | null;
  dx_pointer: string | null;
  units: number | null;
  charge: string | null;
}

function show(value: unknown) {
  if (value === null || value === undefined || value === "") return <span className="missing">missing</span>;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  return String(value);
}

function CheckItem({ check }: { check: CheckOut }) {
  const Icon = OUTCOME_ICON[check.outcome];
  return (
    <li>
      <span className={`tl-icon tl-icon--${check.outcome}`} aria-hidden="true">
        <Icon size={16} strokeWidth={2.4} />
      </span>
      <div>
        <div className="tl-head">
          <span className="tl-name">
            {check.check_no > 0 ? `${check.check_no}. ` : ""}
            {check.check_name}
          </span>
          <span className="tl-outcome">· {OUTCOME_LABEL[check.outcome]}</span>
          {check.rule_id && <span className="code">{check.rule_id}</span>}
          {check.reason_code && <span className="code">{check.reason_code}</span>}
        </div>
        <p className="tl-detail">{check.detail}</p>
      </div>
    </li>
  );
}

interface Props {
  result: ResultOut;
  onClose: () => void;
}

/** Side drawer with the full story of one claim. Esc closes it, and focus stays inside while it is open. */
export function ClaimDrawer({ result, onClose }: Props) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => previous?.focus();
  }, [result.claim_id]);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !panelRef.current) return;
    const focusable = panelRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const lines = (Array.isArray(result.extracted.lines) ? result.extracted.lines : []) as Line[];
  const hasFields = Object.keys(result.extracted).length > 0;

  return (
    <>
      <div className="overlay" onClick={onClose} aria-hidden="true" />
      <aside
        ref={panelRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onKeyDown={onKeyDown}
      >
        <div className="drawer__head">
          <div>
            <h2 className="drawer__id" id="drawer-title">
              {result.claim_id}
            </h2>
            <DecisionStamp decision={result.decision} large />
            <p className="drawer__files">Source: {result.source_files.join(" + ")}</p>
          </div>
          <button ref={closeRef} type="button" className="icon-btn" aria-label="Close details" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="drawer__body">
          <section>
            <h3>Check results</h3>
            <ol className="timeline">
              {result.checks.map((c, i) => (
                <CheckItem key={`${c.check_no}-${c.rule_id ?? "pass"}-${i}`} check={c} />
              ))}
            </ol>
          </section>

          <section>
            <h3>Explanation</h3>
            <p className="explanation">{mainExplanation(result.explanation)}</p>
          </section>

          {result.advisories.length > 0 && (
            <section className="notes" aria-label="Reviewer notes">
              <p className="notes__caption">Reviewer notes · do not change this decision</p>
              <ul>
                {result.advisories.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </section>
          )}

          {hasFields && (
            <section>
              <h3>Extracted from the claim file</h3>
              <dl className="fields">
                {FIELD_LABELS.map(([key, label]) => (
                  <div key={key} style={{ display: "contents" }}>
                    <dt>{label}</dt>
                    <dd>{show(result.extracted[key])}</dd>
                  </div>
                ))}
              </dl>
              {lines.length > 0 && (
                <table className="lines-table">
                  <thead>
                    <tr>
                      <th>Line</th>
                      <th>DOS</th>
                      <th>CPT</th>
                      <th>Mod</th>
                      <th>Dx</th>
                      <th className="num">Units</th>
                      <th className="num">Charge</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l) => (
                      <tr key={l.line_no}>
                        <td>{l.line_no}</td>
                        <td>{show(l.dos)}</td>
                        <td>{show(l.cpt)}</td>
                        <td>{l.modifier ?? "–"}</td>
                        <td>{show(l.dx_pointer)}</td>
                        <td className="num">{show(l.units)}</td>
                        <td className="num">{show(l.charge)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}
        </div>
      </aside>
    </>
  );
}
