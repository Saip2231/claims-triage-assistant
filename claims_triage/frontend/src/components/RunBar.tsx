import { LoaderCircle, Play } from "lucide-react";

interface Props {
  missing: string[];
  running: boolean;
  onRun: () => void;
}

/** The Run button. Disabled until all three inputs are present, and says exactly what is missing. */
export function RunBar({ missing, running, onRun }: Props) {
  const ready = missing.length === 0;
  return (
    <div className="runbar">
      <button type="button" className="btn btn--primary btn--block" disabled={!ready || running} onClick={onRun}>
        {running ? <LoaderCircle size={17} className="spin" aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
        {running ? "Running triage…" : "Run triage"}
      </button>
      <p className="runbar__help" aria-live="polite">
        {running
          ? "Extracting claims and running the six checks…"
          : ready
            ? "All inputs ready."
            : `Still needed: ${missing.join(", ")}.`}
      </p>
    </div>
  );
}
