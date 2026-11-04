# Mini Claims Triage Assistant: Flowcharts

> **Status: DRAFT FOR REVIEW.** The stage-by-stage plan, the system prompts and `CLAUDE.md` come after you approve this.
> Diagrams are Mermaid. They render in GitHub, VS Code (Markdown Preview Mermaid extension) or https://mermaid.live.

**Decisions locked in:**

- **React** frontend, with a **Python (FastAPI)** backend for the checks. Python is preferred by the brief.
- **Zero LLM** anywhere. Decisions come from code plus workbook data. Explanations are **template-based** and cite the uploaded policy.
- **You run every command.** Claude writes the files and the commands; you run them and paste the output back.

---

## 1. System architecture

```mermaid
flowchart LR
    U(["👤 User"]) --> FE

    subgraph FE["React frontend · Vite + TypeScript"]
        direction TB
        UP["Upload panel<br/>claims · policy · workbook"]
        RUN["Run Triage button"]
        TBL["Results table<br/>+ per-claim detail drawer"]
        DL["Download decisions.csv"]
        UP --> RUN --> TBL --> DL
    end

    FE -- "POST /api/triage<br/>multipart form" --> API

    subgraph BE["Python backend · FastAPI"]
        direction TB
        API["api.py<br/>validate uploads"]
        EXT["extract.py<br/>PDF/TXT → Claim"]
        REF["reference.py<br/>xlsx → ReferenceData"]
        POL["policy.py<br/>PDF → sections"]
        CHK["checks.py<br/>6 pure functions"]
        ENG["engine.py<br/>combine → decision"]
        EXP["explain.py<br/>templates, no LLM"]
        CSV["export.py<br/>rows → CSV text"]
        API --> EXT & REF & POL
        EXT --> CHK
        REF --> CHK
        CHK --> ENG --> EXP
        POL --> EXP
        EXP --> CSV
    end

    API -- "JSON: rows + summary<br/>+ warnings + csv" --> FE
    CLI["scripts/run_batch.py<br/>same engine, no UI"] -.-> EXT
```

**Run modes:**

- **Dev:** two terminals, `uvicorn` on port 8000 and `vite` on port 5173 with a proxy to `/api`.
- **Submission:** `npm run build`, then FastAPI serves the built React app. A grader needs **one command** to run it.

---

## 2. End-to-end data flow (one run)

```mermaid
flowchart TD
    A["User drops files"] --> B{"All 3 inputs present?<br/>claims ≥1 · policy PDF · workbook xlsx"}
    B -- No --> B1["Run button disabled<br/>banner names what is missing"]
    B -- Yes --> C["POST /api/triage"]

    C --> D["Load workbook<br/>check required sheets + columns"]
    D -- "bad / missing sheet" --> D1["❌ HTTP 400 with clear message<br/>run does not start"]
    D -- ok --> E["Parse policy PDF<br/>split into sections §1 … §6"]
    E -- "unreadable" --> E1["⚠ warning: cite section numbers<br/>without quoting text"]
    E --> F
    E1 --> F

    F["For EACH claim file"] --> G["Extract → Claim object"]
    G -- "wrong type / unreadable /<br/>no claim ID" --> G1["NEEDS_HUMAN row<br/>reason = file problem"]
    G -- ok --> H["Run all 6 checks<br/>collect every RuleResult"]
    H --> I["Combine by priority → decision"]
    I --> J["Build explanation<br/>template + policy section text"]
    J --> K["Result row"]
    G1 --> K

    K --> L{"More claims?"}
    L -- yes --> F
    L -- no --> M["Dedupe same claim_id<br/>uploaded as PDF and TXT"]
    M --> N["Response JSON<br/>rows · summary counts · warnings · csv"]
    N --> O["React renders table + summary chips"]
    O --> P["Download decisions.csv"]
```

> Each claim runs inside its own `try/except`. One bad claim never stops the batch.

---

## 3. Claim extraction (PDF and TXT → one `Claim`)

```mermaid
flowchart TD
    IN["Uploaded file"] --> T{"Extension?"}
    T -- ".txt" --> TX["Decode UTF-8<br/>fallback latin-1"]
    T -- ".pdf" --> PX["pypdf: extract text<br/>from every page"]
    T -- other --> BAD["Unsupported type<br/>→ NEEDS_HUMAN row"]

    TX --> CUT["Keep claim body only<br/>stop at 'TOTAL CHARGE'<br/>attachments are ignored"]
    PX --> EMPTY{"Any text?"}
    EMPTY -- no --> BAD2["Image-only or corrupt PDF<br/>→ NEEDS_HUMAN row"]
    EMPTY -- yes --> CUT

    CUT --> NORM["Normalise to label → value<br/>TXT: 'Label : value' on one line<br/>PDF: LABEL line, then value line"]
    NORM --> ALIAS["Alias table → canonical fields<br/>claim_id · freq_code · member_id<br/>provider_id · rendering_npi · dos<br/>primary_dx · secondary_dx · emergency"]
    CUT --> LINES["Service-line regex<br/>line · DOS · POS · CPT · mod? ·<br/>dx ptr · units · charge"]
    CUT --> TOT["TOTAL CHARGE → total_billed"]

    ALIAS --> BL["Blank markers → None<br/>'(blank)' · '[ BLANK ]' ·<br/>'None' · 'None provided'"]
    BL --> CL(["Claim object<br/>missing fields = None<br/>NEVER guessed"])
    LINES --> CL
    TOT --> CL
```

**Guarantees:**

- The TXT and PDF versions of each claim must produce **identical** `Claim` objects. A test enforces this for all 10.
- Attachment text never fills a field. Claim 0009's OCR note cannot hide its blank NPI.

---

## 4. The 6 checks and the decision logic

```mermaid
flowchart TD
    CL(["Claim + ReferenceData"]) --> C1 & C2 & C3 & C4 & C5 & C6

    C1["① Required fields<br/>rendering NPI present?<br/>dx in ICD10_Codes?"]
    C2["② Eligibility<br/>effective ≤ DOS ≤ termination<br/>premium_paid_through ≥ DOS"]
    C3["③ Duplicate<br/>Paid history with same member +<br/>provider + DOS + CPT, freq code = 1"]
    C4["④ Prior auth<br/>Benefit_Rules PA = Y for plan+CPT?<br/>→ Approved PA covering DOS?"]
    C5["⑤ Network<br/>Providers.in_network_GLD_PPO etc.<br/>= 'Y'?"]
    C6["⑥ Amount<br/>total billed ≤ $10,000?"]

    C1 -- fail --> R1["VAL-01 R201 / VAL-02 R202<br/>NEEDS_HUMAN"]
    C2 -- fail --> R2["ELIG-01 R101<br/>DENY"]
    C3 -- fail --> R3["DUP-01 R102<br/>DENY"]
    C4 -- fail --> R4["PA-01 R401<br/>NEEDS_HUMAN"]
    C5 -- fail --> R5["EMR-01 or NET-01 R801<br/>NEEDS_HUMAN"]
    C6 -- fail --> R6["AMT-01 R901<br/>NEEDS_HUMAN"]

    R1 & R2 & R3 & R4 & R5 & R6 --> ALL["List of ALL rules fired"]
    C1 & C2 & C3 & C4 & C5 & C6 -- pass --> ALL

    ALL --> P1{"Check ① failed?"}
    P1 -- yes --> NH1(["NEEDS_HUMAN"])
    P1 -- no --> P2{"Any DENY?"}
    P2 -- yes --> DN(["DENY"])
    P2 -- no --> P3{"Any NEEDS_HUMAN?"}
    P3 -- yes --> NH2(["NEEDS_HUMAN"])
    P3 -- no --> AP(["APPROVE"])

    style AP fill:#d1fae5,stroke:#059669
    style DN fill:#fee2e2,stroke:#dc2626
    style NH1 fill:#fef3c7,stroke:#d97706
    style NH2 fill:#fef3c7,stroke:#d97706
```

**Rules for missing data:**

- A field a check needs is missing → that check returns NEEDS_HUMAN with "cannot verify". It never passes or denies by default.
- The member or provider is not in the workbook → NEEDS_HUMAN, not DENY.

---

## 5. Explanation builder (deterministic, no LLM)

```mermaid
flowchart LR
    RR["Fired rules<br/>e.g. ELIG-01 / R101"] --> MAP["Reason code → policy section<br/>R101→§2.1 · R102→§3.3 · R201/R202→§3.1<br/>R401→§2.5 · R801→§2.3 (+§2.4 if ER)<br/>R901→§3.6 · APPROVE→§3.2"]
    POL["Parsed policy sections<br/>from the UPLOADED PDF"] --> Q["Pick the key sentence<br/>of the cited section"]
    MAP --> Q
    TPL["Template per reason code<br/>filled with claim facts:<br/>dates, CPT, PA number, amounts"] --> OUT
    Q --> OUT["Explanation =<br/>outcome + plain reason(s) +<br/>'Policy Section X.Y Title: …' +<br/>next step / appeal right on DENY (§2.8)"]
    ADV["Advisory notes, not decisive<br/>BUN-01 · EM-01 · LIM-01 · EXC-01"] -.-> OUT
```

> The explanation uses only the claim ID, member ID, rule results and policy text. No birth year, sex or other personal fields (Policy §3.8).

---

## 6. Expected outcome for the 10 claims

```mermaid
flowchart LR
    subgraph APPROVE
        A1["0001"] ~~~ A6["0006 ⚑ bundling"] ~~~ A7["0007 ⚑ E/M pattern"] ~~~ A10["0010 ⚑ BH limit"]
    end
    subgraph DENY
        D2["0002 · R102 duplicate"] ~~~ D4["0004 · R101 terminated"]
    end
    subgraph NEEDS_HUMAN
        N3["0003 · R401 + R901"] ~~~ N5["0005 · R801 OON ER"] ~~~ N8["0008 · R401 ⚑ cosmetic"] ~~~ N9["0009 · R201 + R202"]
    end
    style APPROVE fill:#ecfdf5,stroke:#059669
    style DENY fill:#fef2f2,stroke:#dc2626
    style NEEDS_HUMAN fill:#fffbeb,stroke:#d97706
```

⚑ = an advisory note from the full policy. It is mentioned in the explanation and README, but it does not change the 6-check decision.

---

## 7. Build stages and how we work together

```mermaid
flowchart TD
    S0["Stage 0 · Setup<br/>folders, CLAUDE.md, requirements,<br/>package.json"] --> S1
    S1["Stage 1 · Models + reference loader<br/>dataclasses, workbook → ReferenceData"] --> S2
    S2["Stage 2 · Claim extraction<br/>TXT + PDF parsers, parity test"] --> S3
    S3["Stage 3 · The 6 checks<br/>pure functions + unit tests"] --> S4
    S4["Stage 4 · Engine + CLI<br/>combine, run_batch.py → decisions.csv<br/>✅ matches expected 10/10"] --> S5
    S5["Stage 5 · Policy parser + explanations<br/>section split, templates"] --> S6
    S6["Stage 6 · FastAPI backend<br/>/api/triage, error matrix"] --> S7
    S7["Stage 7 · React UI<br/>upload, table, drawer, CSV, error states"] --> S8
    S8["Stage 8 · Tests + hardening<br/>robustness, end-to-end"] --> S9
    S9["Stage 9 · README + final CSV + zip"]

    subgraph LOOP["Loop inside EVERY stage"]
        direction LR
        L1["Claude writes files<br/>+ gives exact commands"] --> L2["👤 You run them<br/>in your terminal"]
        L2 --> L3["👤 You paste the output back"]
        L3 --> L4{"Stage exit<br/>criteria met?"}
        L4 -- no --> L1
        L4 -- "yes + your OK" --> L5["Next stage"]
    end
```

**Stage gates:**

- **Gate A:** after Stage 4, all 10 decisions are correct. This is the 35-point area, so it is locked down before any UI work.
- **Gate B:** after Stage 7, the full UI flow works in your browser.
- **Gate C:** after Stage 9, the zip is ready.

---

### Review checklist for you

- [ ] React + FastAPI split, with FastAPI serving the built React app for submission. OK?
- [ ] Template-only explanations, no LLM anywhere. OK? The README will say "template-based".
- [ ] Advisory notes (bundling, E/M, BH limit, cosmetic) appear in the explanation but don't change decisions. OK?
- [ ] 10 stages with 3 gates. Merge or split any?
