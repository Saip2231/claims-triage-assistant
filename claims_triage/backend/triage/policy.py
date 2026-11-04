"""Parses the UPLOADED policy PDF into numbered sections so explanations can cite it.

Citations come from what the user uploaded. If the PDF can't be read, or a
section can't be found, we fall back to the known section titles. The
explanation still cites "Section X.Y Title" but without a quote, and a
warning tells the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader

# The sections our explanations cite. Used for degraded mode and to judge whether parsing worked.
FALLBACK_TITLES: dict[str, str] = {
    "2.1": "Eligibility",
    "2.3": "Network",
    "2.4": "Emergency Services",
    "2.5": "Prior Authorization",
    "2.6": "Exclusions",
    "2.7": "Behavioral Health",
    "2.8": "Appeals",
    "3.1": "Required Fields",
    "3.2": "Recommended Validation Order",
    "3.3": "Duplicates",
    "3.4": "Bundling",
    "3.5": "E/M Level Review",
    "3.6": "Decision Authority and Thresholds",
}

_HEADING = re.compile(r"^(\d\.\d{1,2})\s+([A-Z][A-Za-z/&() -]{2,60}?)\s*$")
# Top-level headings ("3. Claims Adjudication Guidelines (Internal)") are dropped from section text.
_TOP_LEVEL = re.compile(r"^\d\.\s+[A-Z][A-Za-z ()&/-]{3,60}$")
_NOISE = re.compile(r"SYNTHETIC DATA|^Page \d+$", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class PolicySection:
    number: str
    title: str
    text: str


@dataclass
class PolicyIndex:
    sections: dict[str, PolicySection] = field(default_factory=dict)
    parsed_ok: bool = False
    warning: str | None = None

    def title(self, number: str) -> str:
        section = self.sections.get(number)
        return section.title if section else FALLBACK_TITLES.get(number, "")

    def cite(self, number: str) -> str:
        """'Section 2.1 Eligibility'."""
        return f"Section {number} {self.title(number)}".strip()

    def quote(self, number: str, keyword: str, max_len: int = 240) -> str | None:
        """The sentence of a section that contains `keyword` (case-insensitive), or None.

        A long sentence (e.g. text flattened from a table) is cut to start at
        the keyword, so the quote shows the relevant part.
        """
        section = self.sections.get(number)
        if section is None or not keyword:
            return None
        for sentence in _SENTENCE_END.split(section.text):
            at = sentence.lower().find(keyword.lower())
            if at == -1:
                continue
            sentence = sentence.strip()
            if len(sentence) <= max_len:
                return sentence
            at = sentence.lower().find(keyword.lower())
            snippet = sentence[at: at + max_len].rstrip()
            prefix = "…" if at > 0 else ""
            suffix = "…" if at + max_len < len(sentence) else ""
            return f"{prefix}{snippet}{suffix}"
        return None


def _pdf_lines(data: bytes) -> list[str]:
    reader = PdfReader(BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return [line.strip() for line in text.splitlines() if line.strip() and not _NOISE.search(line)]


def parse_policy(data: bytes | None) -> PolicyIndex:
    """Split the policy PDF into sections keyed by number ('2.1', '3.3', ...).

    Never raises. On failure it returns an index with parsed_ok=False and a
    user-facing warning, and citations then use FALLBACK_TITLES.
    """
    if not data:
        return PolicyIndex(warning="No policy document was provided; explanations cite section numbers without quotes.")
    try:
        lines = _pdf_lines(data)
    except Exception:
        return PolicyIndex(warning="The policy document could not be read; explanations cite section numbers without quotes.")

    sections: dict[str, PolicySection] = {}
    current: tuple[str, str] | None = None
    body: list[str] = []

    def flush() -> None:
        if current and current[0] not in sections:
            sections[current[0]] = PolicySection(current[0], current[1], " ".join(" ".join(body).split()))

    for line in lines:
        heading = _HEADING.match(line)
        if heading:
            flush()
            current, body = (heading.group(1), heading.group(2).strip()), []
        elif current and not _TOP_LEVEL.match(line):
            body.append(line)
    flush()

    missing = [n for n in FALLBACK_TITLES if n not in sections]
    warning = None
    if not sections:
        warning = "No numbered sections were found in the policy document; explanations cite section numbers without quotes."
    elif missing:
        warning = f"Policy sections {', '.join(missing)} were not found in the uploaded policy; those citations have no quote."
    return PolicyIndex(sections=sections, parsed_ok=not missing, warning=warning)
