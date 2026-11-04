import { CircleCheck, CircleX, Files, UserRound } from "lucide-react";
import type { Decision, Summary } from "../types";

export type Filter = Decision | "ALL";

interface Props {
  summary: Summary;
  filter: Filter;
  onFilter: (filter: Filter) => void;
}

const CARDS: { key: Filter; label: string; Icon: typeof Files }[] = [
  { key: "ALL", label: "Total claims", Icon: Files },
  { key: "APPROVE", label: "Approve", Icon: CircleCheck },
  { key: "DENY", label: "Deny", Icon: CircleX },
  { key: "NEEDS_HUMAN", label: "Needs human", Icon: UserRound },
];

/** Four counters that double as decision filters. */
export function SummaryStrip({ summary, filter, onFilter }: Props) {
  return (
    <div className="summary" role="group" aria-label="Filter by decision">
      {CARDS.map(({ key, label, Icon }) => {
        const value = key === "ALL" ? summary.total : summary[key];
        const active = filter === key;
        return (
          <button
            key={key}
            type="button"
            className={`stat stat--${key}`}
            aria-pressed={active}
            onClick={() => onFilter(active && key !== "ALL" ? "ALL" : key)}
          >
            <span className="stat__label">
              <Icon size={14} aria-hidden="true" />
              {label}
            </span>
            <span className="stat__value">{value}</span>
          </button>
        );
      })}
    </div>
  );
}
