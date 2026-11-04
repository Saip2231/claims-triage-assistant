import { CircleCheck, CircleX, UserRound } from "lucide-react";
import { DECISION_LABEL, type Decision } from "../types";

const ICONS = { APPROVE: CircleCheck, DENY: CircleX, NEEDS_HUMAN: UserRound } as const;

/** Decision badge styled as a rubber stamp. Always shows text plus an icon, never colour alone. */
export function DecisionStamp({ decision, large = false }: { decision: Decision; large?: boolean }) {
  const Icon = ICONS[decision];
  return (
    <span className={`stamp stamp--${decision}${large ? " stamp--lg" : ""}`}>
      <Icon size={large ? 15 : 13} strokeWidth={2.4} aria-hidden="true" />
      {DECISION_LABEL[decision]}
    </span>
  );
}
