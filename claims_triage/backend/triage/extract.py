"""Turns an uploaded claim file (PDF or TXT) into a Claim.

Both formats share one core. Each layout is first normalised into a
{canonical_field: raw_value} dict:
  * TXT puts "Label : value" on one line;
  * PDF (via pypdf) puts the LABEL on one line and its value on the next.
Service lines are parsed with one regex over whitespace-collapsed text, which
works for both layouts.

Hard rules (CLAUDE.md §1):
  * Only the claim body is parsed, which ends at TOTAL CHARGE. Attachments
    never fill a field (e.g. CLM-2026-0009's OCR note must not supply the
    blank rendering NPI).
  * Nothing is guessed or corrected: a blank, unrecognised or malformed
    value becomes None.
  * Birth year and sex are deliberately never extracted (Policy §3.8).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader

from .models import Claim, ServiceLine, SourceFormat


class ExtractionError(ValueError):
    """The file cannot be read as a claim at all. The message is user-facing."""


SUPPORTED_SUFFIXES: dict[str, SourceFormat] = {".pdf": "pdf", ".txt": "txt"}

# Normalised label -> canonical field. Both the TXT and the PDF spelling of each label are listed.
ALIASES: dict[str, str] = {
    "claim id": "claim_id",
    "date received": "received_date",
    "claim frequency code": "freq_code",
    "member id": "member_id",
    "provider id": "provider_id",
    "billing npi": "billing_npi",
    "rendering provider npi": "rendering_npi",
    "place of service": "place_of_service",
    "date of service": "dos",
    "a primary diagnosis": "primary_dx",
    "a primary diagnosis icd 10 cm": "primary_dx",
    "b secondary diagnosis": "secondary_dx",
    "prior auth number": "prior_auth_number",
    "prior authorization number": "prior_auth_number",
    "emergency indicator": "emergency",
    "attachments submitted": "attachments",
}

# Labels we recognise but deliberately do not keep. Listing them stops a PDF
# label from being mistaken for another label's value.
IGNORED_LABELS: frozenset[str] = frozenset({
    "submission format", "relationship to insured", "patient relationship to insured",
    "birth year", "sex", "provider name", "specialty",
})

BLANK_MARKERS: frozenset[str] = frozenset({
    "", "(blank)", "[ blank ]", "[blank]", "blank", "none", "none provided", "n/a",
})

_COLON_LINE = re.compile(r"^\s*([A-Za-z][\w .()/-]*?)\s*:\s*(.*?)\s*$")
_TOTAL = re.compile(r"TOTAL CHARGE\s+([\d,]+\.\d{2})")
_ATTACHMENT_START = re.compile(r"(?im)^\s*(\[ATTACHMENT\b|Attachment \d+ of)")
_LINES_HEADER = re.compile(r"Charge \(USD\)")
_SERVICE_LINE = re.compile(
    r"(\d+) (\d{4}-\d{2}-\d{2}) (\d{2}) (\d{5}) (?:([A-Z0-9]{2}) )?([A-D]) (\d+) ([\d,]+\.\d{2})"
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --------------------------------------------------------------------------- reading


def read_text(filename: str, data: bytes) -> tuple[str, SourceFormat]:
    """Return the file's full text and its format. Raises ExtractionError if unreadable."""
    suffix = PurePath(filename).suffix.lower()
    fmt = SUPPORTED_SUFFIXES.get(suffix)
    if fmt is None:
        shown = suffix or "(no extension)"
        raise ExtractionError(f"Unsupported file type '{shown}' for {filename} – upload PDF or TXT claim files.")

    if fmt == "txt":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    else:
        try:
            reader = PdfReader(BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # pypdf raises many types for corrupt files
            raise ExtractionError(f"Could not read {filename}: the PDF is corrupt or unreadable.") from exc

    if not text.strip():
        raise ExtractionError(f"Could not read text from {filename} (empty, or an image-only PDF).")
    return text, fmt


# --------------------------------------------------------------------------- value normalisers


def normalise_label(label: str) -> str:
    """'A. PRIMARY DIAGNOSIS (ICD-10-CM)' -> 'a primary diagnosis icd 10 cm'."""
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def clean_value(value: str | None) -> str | None:
    """Strip a raw value. Blank markers such as '(blank)' or 'None provided' become None."""
    if value is None:
        return None
    value = value.strip()
    return None if value.lower() in BLANK_MARKERS else value


def parse_iso_date(value: str | None) -> date | None:
    """Accept YYYY-MM-DD only. Any other format is treated as missing, never guessed."""
    value = clean_value(value)
    if value is None or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_money(value: str | None) -> Decimal | None:
    value = clean_value(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _first_token(value: str | None) -> str | None:
    value = clean_value(value)
    return value.split()[0] if value else None


def _pos_code(value: str | None) -> str | None:
    value = clean_value(value)
    match = re.match(r"(\d{2})\b", value) if value else None
    return match.group(1) if match else None


def _yes_no(value: str | None) -> bool | None:
    value = clean_value(value)
    if value is None:
        return None
    return {"Y": True, "N": False}.get(value.upper())


def _attachments(value: str | None) -> list[str]:
    value = clean_value(value)
    if value is None:
        return []
    return [part.strip() for part in re.split(r"[,;]", value) if clean_value(part)]


# --------------------------------------------------------------------------- body parsing


def claim_body(text: str) -> str:
    """Return the claim body, which ends at the TOTAL CHARGE amount, so attachments are never parsed."""
    total = _TOTAL.search(text)
    if total:
        return text[: total.end()]
    attachment = _ATTACHMENT_START.search(text)
    return text[: attachment.start()] if attachment else text


def header_fields(body: str) -> dict[str, str]:
    """Collect raw header values from both layouts. The first occurrence of a field wins."""
    fields: dict[str, str] = {}
    lines = [line.strip() for line in body.splitlines()]

    # TXT style: "Label : value" on one line.
    for line in lines:
        match = _COLON_LINE.match(line)
        if match:
            canonical = ALIASES.get(normalise_label(match.group(1)))
            if canonical:
                fields.setdefault(canonical, match.group(2))

    # PDF style: the LABEL on its own line, the value on the next non-empty line.
    i = 0
    while i < len(lines):
        key = normalise_label(lines[i])
        if key in ALIASES or key in IGNORED_LABELS:
            j = i + 1
            while j < len(lines) and not lines[j]:
                j += 1
            if key in ALIASES and j < len(lines):
                fields.setdefault(ALIASES[key], lines[j])
            i = j + 1  # skip the value so it is never read as a label
            continue
        i += 1
    return fields


def service_lines(body: str) -> list[ServiceLine]:
    """Parse the service-line table between 'Charge (USD)' and 'TOTAL CHARGE'."""
    header = _LINES_HEADER.search(body)
    if not header:
        return []
    table = body[header.end():]
    total = table.find("TOTAL CHARGE")
    if total != -1:
        table = table[:total]
    flat = " ".join(table.split())
    return [
        ServiceLine(
            line_no=int(m.group(1)),
            dos=parse_iso_date(m.group(2)),
            pos=m.group(3),
            cpt=m.group(4),
            modifier=m.group(5),
            dx_pointer=m.group(6),
            units=int(m.group(7)),
            charge=parse_money(m.group(8)),
        )
        for m in _SERVICE_LINE.finditer(flat)
    ]


# --------------------------------------------------------------------------- public API


def parse_claim_text(text: str, source_file: str, source_format: SourceFormat) -> Claim:
    """Build a Claim from already-extracted text. Missing fields stay None."""
    body = claim_body(text)
    raw = header_fields(body)
    total = _TOTAL.search(body)
    return Claim(
        claim_id=clean_value(raw.get("claim_id")),
        source_file=source_file,
        source_format=source_format,
        received_date=parse_iso_date(raw.get("received_date")),
        freq_code=_first_token(raw.get("freq_code")),
        member_id=clean_value(raw.get("member_id")),
        provider_id=clean_value(raw.get("provider_id")),
        billing_npi=clean_value(raw.get("billing_npi")),
        rendering_npi=clean_value(raw.get("rendering_npi")),
        place_of_service=_pos_code(raw.get("place_of_service")),
        dos=parse_iso_date(raw.get("dos")),
        primary_dx=clean_value(raw.get("primary_dx")),
        secondary_dx=clean_value(raw.get("secondary_dx")),
        prior_auth_number=clean_value(raw.get("prior_auth_number")),
        emergency=_yes_no(raw.get("emergency")),
        attachments=_attachments(raw.get("attachments")),
        lines=service_lines(body),
        total_billed=parse_money(total.group(1)) if total else None,
    )


def extract_claim(filename: str, data: bytes) -> Claim:
    """Read an uploaded PDF/TXT claim file into a Claim.

    Raises ExtractionError only when the file can't be read at all
    (unsupported type, corrupt, or empty). A readable file with missing
    fields returns a Claim whose missing fields are None.
    """
    text, fmt = read_text(filename, data)
    return parse_claim_text(text, source_file=PurePath(filename).name, source_format=fmt)


def claim_fingerprint(claim: Claim) -> dict:
    """Every extracted field except the source file and format, in JSON-friendly form.

    Used to prove PDF/TXT parity, to dedupe the same claim uploaded twice,
    and as the 'extracted' block shown in the UI.
    """

    def plain(value):
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

    return {
        "claim_id": claim.claim_id,
        "received_date": plain(claim.received_date),
        "freq_code": claim.freq_code,
        "member_id": claim.member_id,
        "provider_id": claim.provider_id,
        "billing_npi": claim.billing_npi,
        "rendering_npi": claim.rendering_npi,
        "place_of_service": claim.place_of_service,
        "dos": plain(claim.dos),
        "primary_dx": claim.primary_dx,
        "secondary_dx": claim.secondary_dx,
        "prior_auth_number": claim.prior_auth_number,
        "emergency": claim.emergency,
        "attachments": list(claim.attachments),
        "lines": [
            {
                "line_no": line.line_no, "dos": plain(line.dos), "pos": line.pos, "cpt": line.cpt,
                "modifier": line.modifier, "dx_pointer": line.dx_pointer, "units": line.units,
                "charge": plain(line.charge),
            }
            for line in claim.lines
        ],
        "total_billed": plain(claim.total_billed),
    }
