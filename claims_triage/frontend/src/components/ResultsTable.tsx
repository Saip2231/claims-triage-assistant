import { useState, type KeyboardEvent } from "react";
import { ArrowDownUp, NotebookPen, Search } from "lucide-react";
import { DECISION_LABEL, type ResultOut } from "../types";
import { DecisionStamp } from "./DecisionStamp";
import type { Filter } from "./SummaryStrip";

interface Props {
  rows: ResultOut[];
  totalRows: number;
  filter: Filter;
  query: string;
  onQuery: (q: string) => void;
  onSelect: (claimId: string) => void;
}

export const NOTES_MARKER = " Reviewer notes (do not change this decision): ";

/** The explanation without the reviewer-notes tail, which the table shows as a flag instead. */
export function mainExplanation(text: string): string {
  return text.split(NOTES_MARKER)[0];
}

function Codes({ values }: { values: string[] }) {
  if (values.length === 0) return <span className="code code--empty">—</span>;
  return (
    <span className="code-list">
      {values.map((v) => (
        <span key={v} className="code">
          {v}
        </span>
      ))}
    </span>
  );
}

export function ResultsTable({ rows, totalRows, filter, query, onQuery, onSelect }: Props) {
  const [ascending, setAscending] = useState(true);
  const sorted = [...rows].sort((a, b) =>
    ascending ? a.claim_id.localeCompare(b.claim_id) : b.claim_id.localeCompare(a.claim_id),
  );

  const onRowKey = (e: KeyboardEvent, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id);
    }
  };

  return (
    <div className="panel table-card">
      <div className="toolbar">
        <label className="search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Search results</span>
          <input
            type="search"
            placeholder="Search claim ID, code or text…"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
        </label>
        <span className="filter-note">
          Showing {rows.length} of {totalRows}
          {filter !== "ALL" && ` · ${DECISION_LABEL[filter]} only`}
        </span>
      </div>

      <div className="table-wrap">
        <table className="results-table">
          <thead>
            <tr>
              <th scope="col" aria-sort={ascending ? "ascending" : "descending"}>
                <button type="button" className="th-sort" onClick={() => setAscending(!ascending)}>
                  Claim ID <ArrowDownUp size={12} aria-hidden="true" />
                </button>
              </th>
              <th scope="col">Decision</th>
              <th scope="col">Rules fired</th>
              <th scope="col">Reason codes</th>
              <th scope="col">Explanation</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.claim_id}
                tabIndex={0}
                aria-label={`${r.claim_id}, ${DECISION_LABEL[r.decision]}. Open details`}
                onClick={() => onSelect(r.claim_id)}
                onKeyDown={(e) => onRowKey(e, r.claim_id)}
              >
                <td className="cell-id">{r.claim_id}</td>
                <td>
                  <DecisionStamp decision={r.decision} />
                </td>
                <td>
                  <Codes values={r.rules_fired} />
                </td>
                <td>
                  <Codes values={r.reason_codes} />
                </td>
                <td>
                  <span className="clamp">{mainExplanation(r.explanation)}</span>
                  {r.advisories.length > 0 && (
                    <span className="note-flag">
                      <NotebookPen size={12} aria-hidden="true" />
                      {r.advisories.length} reviewer note{r.advisories.length > 1 ? "s" : ""}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && <p className="table-empty">No claims match this filter or search.</p>}
      </div>
    </div>
  );
}
