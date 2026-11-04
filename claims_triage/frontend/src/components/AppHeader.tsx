import { ExternalLink, ShieldCheck, Stethoscope } from "lucide-react";

export function AppHeader() {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand__mark" aria-hidden="true">
          <Stethoscope size={20} />
        </span>
        <div>
          <h1 className="brand__title">Claims Triage Assistant</h1>
          <p className="brand__sub">Six rule checks · policy-cited explanations · CSV export</p>
        </div>
      </div>
      <div className="header-meta">
        <span className="pill" title="Decisions and explanations come only from rules and the reference data.">
          <ShieldCheck size={14} aria-hidden="true" />
          Deterministic rules · No AI
        </span>
        <a className="link" href="/docs" target="_blank" rel="noreferrer">
          API docs <ExternalLink size={13} aria-hidden="true" />
        </a>
      </div>
    </header>
  );
}
