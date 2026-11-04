import { Component, type ErrorInfo, type ReactNode } from "react";
import { CircleAlert, Download, Info, RefreshCw, TriangleAlert, X } from "lucide-react";
import type { ApiError } from "../api";

/** Red banner for API, network and validation errors. */
export function ErrorBanner({ error, onDismiss }: { error: ApiError; onDismiss: () => void }) {
  return (
    <div className="banner banner--error" role="alert">
      <CircleAlert size={20} aria-hidden="true" />
      <div className="banner__body">
        <p className="banner__title">{error.error}</p>
        <p className="banner__detail">{error.detail}</p>
      </div>
      <button type="button" className="icon-btn" aria-label="Dismiss error" onClick={onDismiss}>
        <X size={16} />
      </button>
    </div>
  );
}

/** Shown when the inputs changed after a run, so the table may be out of date. */
export function StaleBanner({ onRerun, disabled }: { onRerun: () => void; disabled: boolean }) {
  return (
    <div className="banner banner--info" role="status">
      <Info size={20} aria-hidden="true" />
      <div className="banner__body">
        <p className="banner__title">Inputs changed since the last run</p>
        <p className="banner__detail">These results reflect the previous uploads.</p>
      </div>
      <button type="button" className="btn btn--secondary" onClick={onRerun} disabled={disabled}>
        <RefreshCw size={15} aria-hidden="true" /> Re-run
      </button>
    </div>
  );
}

export function WarningsPanel({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <details className="warnings">
      <summary>
        <TriangleAlert size={16} aria-hidden="true" />
        {warnings.length} warning{warnings.length > 1 ? "s" : ""} from this run
      </summary>
      <ul>
        {warnings.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </details>
  );
}

/** Downloads the server-generated CSV exactly as returned, so it matches the CLI output byte for byte. */
export function DownloadButton({ csv }: { csv: string }) {
  function download() {
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "decisions.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
  return (
    <button type="button" className="btn btn--secondary" onClick={download}>
      <Download size={16} aria-hidden="true" /> Download decisions.csv
    </button>
  );
}

interface BoundaryState {
  error: Error | null;
}

/** Last line of defence: a render error shows a recovery card instead of a white screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="panel crash" role="alert">
        <h1 className="results__title">Something went wrong in the page</h1>
        <p className="muted">Your files were not changed. Reload the page to start again.</p>
        <p className="mono muted">{this.state.error.message}</p>
        <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
          <RefreshCw size={15} aria-hidden="true" /> Reload
        </button>
      </div>
    );
  }
}
