"""Stage 2: claim extraction from PDF and TXT files."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from triage.extract import (
    ExtractionError,
    claim_fingerprint,
    clean_value,
    extract_claim,
    parse_iso_date,
)

CLAIM_IDS = [f"CLM-2026-{n:04d}" for n in range(1, 11)]


def load(claims_dir: Path, claim_id: str, fmt: str):
    path = claims_dir / f"{claim_id}.{fmt}"
    return extract_claim(path.name, path.read_bytes())


# ------------------------------------------------------------------ TXT


def test_txt_extracts_simple_claim_0001(claims_dir: Path):
    c = load(claims_dir, "CLM-2026-0001", "txt")
    assert c.source_format == "txt"
    assert c.claim_id == "CLM-2026-0001"
    assert c.received_date == date(2026, 10, 20)
    assert c.freq_code == "1"
    assert c.member_id == "MBR-100007"
    assert c.provider_id == "P-002"
    assert c.rendering_npi == "9000000002"
    assert c.place_of_service == "11"
    assert c.dos == date(2026, 10, 14)
    assert c.primary_dx == "J06.9"
    assert c.secondary_dx is None
    assert c.prior_auth_number is None
    assert c.emergency is False
    assert c.attachments == []
    assert [(l.cpt, l.charge) for l in c.lines] == [("99213", Decimal("140.00"))]
    assert c.total_billed == Decimal("140.00")


def test_txt_extracts_surgery_claim_0003(claims_dir: Path):
    c = load(claims_dir, "CLM-2026-0003", "txt")
    assert len(c.lines) == 1
    line = c.lines[0]
    assert (line.cpt, line.modifier, line.dx_pointer, line.units) == ("29881", "RT", "A", 1)
    assert line.charge == Decimal("18500.00")
    assert c.total_billed == Decimal("18500.00")
    assert c.attachments == ["DOC-C003-01"]
    assert c.prior_auth_number is None


# ------------------------------------------------------------------ PDF


def test_pdf_extracts_emergency_claim_0005(claims_dir: Path):
    c = load(claims_dir, "CLM-2026-0005", "pdf")
    assert c.source_format == "pdf"
    assert c.claim_id == "CLM-2026-0005"
    assert c.member_id == "MBR-100056"
    assert c.provider_id == "P-009"
    assert [l.cpt for l in c.lines] == ["99285", "93000", "71046"]
    assert c.total_billed == Decimal("3550.00")
    assert c.emergency is True
    assert c.place_of_service == "23"


def test_pdf_blank_npi_and_dx_are_not_fixed_0009(claims_dir: Path):
    c = load(claims_dir, "CLM-2026-0009", "pdf")
    assert c.rendering_npi is None  # the OCR attachment must not leak in
    assert c.primary_dx == "J06.99"  # kept exactly as written, never "corrected"
    assert c.billing_npi == "9000000008"


def test_multi_line_lab_claim_0006(claims_dir: Path):
    for fmt in ("txt", "pdf"):
        c = load(claims_dir, "CLM-2026-0006", fmt)
        assert [l.cpt for l in c.lines] == ["80053", "82947", "82565", "85025", "36415"]
        assert c.total_billed == Decimal("103.00")


def test_telehealth_modifier_0010(claims_dir: Path):
    c = load(claims_dir, "CLM-2026-0010", "pdf")
    assert c.place_of_service == "10"
    assert (c.lines[0].cpt, c.lines[0].modifier) == ("90837", "95")


# ------------------------------------------------------------------ parity


@pytest.mark.parametrize("claim_id", CLAIM_IDS)
def test_pdf_and_txt_give_identical_fields(claims_dir: Path, claim_id: str):
    txt = claim_fingerprint(load(claims_dir, claim_id, "txt"))
    pdf = claim_fingerprint(load(claims_dir, claim_id, "pdf"))
    assert txt == pdf
    assert txt["claim_id"] == claim_id
    assert txt["lines"], "every sample claim has at least one service line"


# ------------------------------------------------------------------ failure modes


def test_unsupported_extension_raises():
    with pytest.raises(ExtractionError, match="Unsupported file type"):
        extract_claim("notes.docx", b"anything")


def test_garbage_pdf_raises():
    with pytest.raises(ExtractionError):
        extract_claim("broken.pdf", b"not a pdf at all")


def test_empty_txt_raises():
    with pytest.raises(ExtractionError, match="empty"):
        extract_claim("empty.txt", b"   \n  ")


def test_txt_without_fields_returns_empty_claim():
    c = extract_claim("random.txt", b"hello world, nothing to see here")
    assert c.claim_id is None
    assert c.lines == []
    assert c.total_billed is None


def test_latin1_txt_still_parses(claims_dir: Path):
    data = (claims_dir / "CLM-2026-0001.txt").read_bytes().replace(b"(synthetic)", "(synth\xe9tic)".encode("latin-1"))
    assert extract_claim("CLM-2026-0001.txt", data).member_id == "MBR-100007"


# ------------------------------------------------------------------ normalisers


@pytest.mark.parametrize("raw", ["", "  ", "(blank)", "[ BLANK ]", "[blank]", "None", "None provided", "N/A"])
def test_blank_markers_become_none(raw: str):
    assert clean_value(raw) is None


def test_real_values_are_kept_verbatim():
    assert clean_value("  J06.99 ") == "J06.99"


@pytest.mark.parametrize("raw", ["10/16/2026", "2026-13-01", "Oct 16 2026", None])
def test_non_iso_dates_are_missing_not_guessed(raw):
    assert parse_iso_date(raw) is None
