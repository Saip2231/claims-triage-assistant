// Builds a short Word write-up (about 3-4 pages, no code): output/Claims_Triage_Report.docx
//
// Usage (from claims_triage/tools/report):
//   npm install
//   node build_report.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  AlignmentType,
  BorderStyle,
  Document,
  HeadingLevel,
  LevelFormat,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";

const AUTHOR = "Sai Prashanth"; // change if needed
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT_FILE = path.resolve(HERE, "..", "..", "output", "Claims_Triage_Report.docx");

const FONT = "Calibri";
const PAGE = { width: 11906, height: 16838 }; // A4
const MARGIN = 1134; // 2 cm
const CONTENT_W = PAGE.width - 2 * MARGIN;

// ------------------------------------------------------------------ helpers

const t = (text, opts = {}) => new TextRun({ text, font: FONT, size: 22, ...opts });
const b = (text) => t(text, { bold: true });
const parts = (xs) => xs.map((x) => (typeof x === "string" ? t(x) : x));
const p = (...xs) => new Paragraph({ spacing: { after: 140 }, children: parts(xs) });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [t(text)] });
const bullet = (...xs) =>
  new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 }, children: parts(xs) });

/** A dashed box with a label, to paste a screenshot or diagram into. */
function placeholder(label) {
  const edge = { style: BorderStyle.DASHED, size: 8, color: "999999", space: 24 };
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 300, after: 300 },
    border: { top: edge, bottom: edge, left: edge, right: edge },
    children: [t(`[ ${label} ]`, { italics: true, color: "888888" })],
  });
}

function table(headers, rows, widths) {
  const cell = (text, width, header) =>
    new TableCell({
      width: { size: width, type: WidthType.DXA },
      margins: { top: 50, bottom: 50, left: 100, right: 100 },
      shading: header ? { type: ShadingType.CLEAR, fill: "E7E6E6", color: "auto" } : undefined,
      children: [new Paragraph({ children: [t(text, { size: 20, bold: header })] })],
    });
  return new Table({
    width: { size: widths.reduce((a, c) => a + c, 0), type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((v, i) => cell(v, widths[i], false)) })),
    ],
  });
}

// ------------------------------------------------------------------ content

const content = [
  new Paragraph({ spacing: { after: 60 }, children: [t("Mini Claims Triage Assistant", { size: 44, bold: true })] }),
  new Paragraph({ spacing: { after: 360 }, children: [t(`Take-home exercise write-up · ${AUTHOR}`, { color: "666666" })] }),

  h1("1. What I built"),
  p(
    "A small web app that goes through health insurance claims and decides, for each one, whether it can be approved, should be denied, or needs a person to look at it. You upload the claim files (PDF or TXT), the policy document and the reference workbook, press Run, and get a table of decisions with a short reason for each. The results can be downloaded as decisions.csv.",
  ),
  p(
    "Everything is decided by plain rules and the data in the workbook. I did not use an LLM anywhere, including the explanations, which are written from simple templates and quote the relevant section of the uploaded policy.",
  ),

  h1("2. How it works"),
  placeholder("Architecture diagram"),
  bullet(b("Read the claim. "), "The PDF and TXT files look different, so I wrote one reader for both and checked that they give exactly the same details for all 10 claims. If something is blank or unreadable, it stays missing. Nothing is guessed or corrected."),
  bullet(b("Run six checks. "), "Required details and a valid diagnosis code, member covered on the date of service, not a duplicate of a paid claim, prior authorization if needed, provider in-network, and a total of $10,000 or less."),
  bullet(b("Pick the decision. "), "If required details are missing it goes to a human. Otherwise a deny wins, then anything that needs a human, and if nothing came up it is approved."),
  bullet(b("Explain it. "), "Each reason points to the policy section it comes from, and denials mention the 180-day appeal right."),
  p("If a file is broken or the wrong type, it shows up as a 'needs human' row and the rest of the batch carries on. The backend is Python and the interface is React."),

  h1("3. The app"),
  placeholder("Screenshot: results screen after running all 10 claims"),
  placeholder("Screenshot: details of one claim (e.g. CLM-2026-0009)"),

  h1("4. Results"),
  table(
    ["Claim", "Decision", "Why"],
    [
      ["CLM-2026-0001", "Approve", "All checks passed"],
      ["CLM-2026-0002", "Deny", "Duplicate of a claim that was already paid"],
      ["CLM-2026-0003", "Needs human", "No approved prior authorization, and $18,500 is over the limit"],
      ["CLM-2026-0004", "Deny", "Coverage ended two days before the service date"],
      ["CLM-2026-0005", "Needs human", "Emergency room visit at an out-of-network hospital"],
      ["CLM-2026-0006", "Approve", "All checks passed"],
      ["CLM-2026-0007", "Approve", "All checks passed"],
      ["CLM-2026-0008", "Needs human", "Needs prior authorization and none is on file"],
      ["CLM-2026-0009", "Needs human", "Rendering NPI missing and the diagnosis code is not valid"],
      ["CLM-2026-0010", "Approve", "All checks passed"],
    ],
    [1900, 1500, CONTENT_W - 3400],
  ),
  p(""),
  p("In total: 4 approved, 2 denied and 4 sent to a human."),
  placeholder("Screenshot: decisions.csv"),

  h1("5. Testing"),
  p(
    "I tested reading both file formats, each check on its own, the decision order, the expected result for every claim, the explanations, and a lot of messy cases like empty files, wrong file types, missing details and a broken workbook. All tests pass.",
  ),
  placeholder("Screenshot: test results"),

  h1("6. Assumptions"),
  bullet("Coverage also needs the premium to be paid up to the service date, as the policy says."),
  bullet("A claim only counts as a duplicate if the earlier one was paid and the new one is an original, not a correction."),
  bullet("If a member or provider is not in the workbook, the claim goes to a human rather than being denied."),
  bullet("Dates must be in the YYYY-MM-DD format, anything else is treated as missing."),

  h1("7. Limitations and next steps"),
  p("I kept to the six checks the brief asked for, so a few claims get approved that the full policy would question:"),
  bullet(b("CLM-2026-0006: "), "two lab tests are already part of a panel on the same claim and should not be paid separately."),
  bullet(b("CLM-2026-0007: "), "the provider bills the highest visit level far more often than others, for a short simple visit."),
  bullet(b("CLM-2026-0010: "), "the member has already used all 12 therapy visits for the year."),
  p(
    "Rather than quietly change the required logic, the app flags these as reviewer notes on the claim. CLM-2026-0008 also looks clearly cosmetic, which the policy would allow to be denied outright. The file reader is built around this claim layout, so a very different form would need changes. With more time I would turn the reviewer notes into optional rules and decide claims line by line.",
  ),
];

// ------------------------------------------------------------------ write

const doc = new Document({
  creator: AUTHOR,
  title: "Mini Claims Triage Assistant",
  styles: {
    default: {
      document: { run: { font: FONT, size: 22 } },
      heading1: {
        run: { font: FONT, size: 28, bold: true },
        paragraph: { spacing: { before: 320, after: 120 }, keepNext: true },
      },
    },
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 540, hanging: 270 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: { page: { size: PAGE, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      children: content,
    },
  ],
});

fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
try {
  fs.writeFileSync(OUT_FILE, await Packer.toBuffer(doc));
  console.log(`Wrote ${OUT_FILE}`);
} catch (err) {
  if (err.code === "EBUSY" || err.code === "EPERM") {
    console.error("The document is open in Word. Close it and run again.");
    process.exit(3);
  }
  throw err;
}
