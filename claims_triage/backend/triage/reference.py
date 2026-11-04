"""Loads the reference workbook into plain, typed structures (ReferenceData).

The brief requires that claim details come only from the uploaded claim
files, so this loader opens ONLY the reference sheets listed below. The
`Claims` and `Claim_Lines` sheets are never read, even if present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from openpyxl import load_workbook

log = logging.getLogger(__name__)


class WorkbookError(ValueError):
    """The reference workbook cannot be used. The message is user-facing."""


# Sheet -> columns that must exist. Checks 1-6 depend on these.
REQUIRED_SHEETS: dict[str, tuple[str, ...]] = {
    "Members": ("member_id", "plan_id", "effective_date", "termination_date", "premium_paid_through"),
    "Providers": (
        "provider_id", "npi",
        "in_network_BRZ_HMO", "in_network_SLV_PPO", "in_network_GLD_PPO", "in_network_PLT_EPO",
    ),
    "Claims_History": (
        "history_claim_id", "member_id", "billing_provider_id", "date_of_service",
        "cpt_code", "status", "paid_date",
    ),
    "Prior_Auth_Log": ("pa_number", "member_id", "cpt_code", "status", "valid_from", "valid_to"),
    "Benefit_Rules": ("plan_id", "cpt_code", "coverage_status", "prior_auth_required"),
    "ICD10_Codes": ("icd10_code",),
    "Plans": ("plan_id", "plan_name", "network_type"),
}

# Only used for non-decisive advisories (Stage 5). If missing, we warn and carry on.
OPTIONAL_SHEETS: dict[str, tuple[str, ...]] = {
    "CPT_Codes": ("cpt_code", "in_network_allowed_amount_usd"),
    "Medical_Necessity_Map": ("cpt_code", "supporting_dx_codes"),
    "Benefit_Usage": ("member_id", "used_ytd", "annual_limit"),
}

NETWORK_PREFIX = "in_network_"


# --------------------------------------------------------------------------- records


@dataclass(frozen=True)
class Member:
    member_id: str
    plan_id: str | None
    effective_date: date | None
    termination_date: date | None
    premium_paid_through: date | None
    status: str | None = None
    termination_reason: str | None = None


@dataclass(frozen=True)
class Provider:
    provider_id: str
    npi: str | None
    network: Mapping[str, str]  # e.g. {"GLD_PPO": "Y"}
    specialty: str | None = None
    provider_type: str | None = None
    level5_pct: float | None = None
    peer_median_level5_pct: float | None = None


@dataclass(frozen=True)
class HistoryClaim:
    history_claim_id: str
    member_id: str | None
    billing_provider_id: str | None
    dos: date | None
    cpt_code: str | None
    status: str | None
    paid_date: date | None


@dataclass(frozen=True)
class PriorAuth:
    pa_number: str
    member_id: str | None
    cpt_code: str | None
    status: str | None
    valid_from: date | None
    valid_to: date | None
    request_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True)
class BenefitRule:
    plan_id: str
    cpt_code: str
    coverage_status: str | None
    prior_auth_required: str | None  # "Y" / "N"
    annual_limit: str | None = None  # a number as text, "Unlimited", or None
    notes: str | None = None


@dataclass(frozen=True)
class Plan:
    plan_id: str
    plan_name: str | None
    network_type: str | None
    psychotherapy_limit: str | None = None


@dataclass
class ReferenceData:
    """Everything the checks and advisories need, keyed for fast lookup."""

    members: dict[str, Member] = field(default_factory=dict)
    providers: dict[str, Provider] = field(default_factory=dict)
    history: list[HistoryClaim] = field(default_factory=list)
    prior_auths: list[PriorAuth] = field(default_factory=list)
    benefit_rules: dict[tuple[str, str], BenefitRule] = field(default_factory=dict)
    icd10: frozenset[str] = frozenset()
    plans: dict[str, Plan] = field(default_factory=dict)
    cpt_allowed: dict[str, Decimal] = field(default_factory=dict)
    med_necessity: dict[str, str] = field(default_factory=dict)
    benefit_usage: dict[str, tuple[int, int | None]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- value helpers


def _text(value: Any) -> str | None:
    """Cell -> stripped str, or None if blank. Whole floats lose their '.0'."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _upper(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _float(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


# --------------------------------------------------------------------------- sheet reading


def _open_workbook(source: str | Path | bytes | BinaryIO):
    stream: Any = BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    try:
        return load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for bad files
        raise WorkbookError(
            "The reference workbook could not be opened. "
            "Upload the .xlsx file (claims_triage_dataset.xlsx)."
        ) from exc


def _read_sheet(wb, sheet: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    """Return the sheet's rows as dicts. Raises WorkbookError on a missing sheet or column."""
    if sheet not in wb.sheetnames:
        raise WorkbookError(f"The reference workbook is missing the '{sheet}' sheet.")
    rows = wb[sheet].iter_rows(values_only=True)
    header_row = next(rows, None) or ()
    header = [_text(h) or "" for h in header_row]
    missing = [c for c in columns if c not in header]
    if missing:
        raise WorkbookError(
            f"The '{sheet}' sheet is missing the column(s): {', '.join(missing)}."
        )
    records = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        records.append({name: row[i] if i < len(row) else None for i, name in enumerate(header) if name})
    return records


def _read_optional(wb, sheet: str, columns: tuple[str, ...], warnings: list[str]) -> list[dict[str, Any]]:
    try:
        return _read_sheet(wb, sheet, columns)
    except WorkbookError as exc:
        warnings.append(f"{exc} Related reviewer notes are skipped.")
        return []


# --------------------------------------------------------------------------- builders


def _members(rows) -> dict[str, Member]:
    out = {}
    for r in rows:
        member_id = _text(r.get("member_id"))
        if not member_id:
            continue
        out[member_id] = Member(
            member_id=member_id,
            plan_id=_text(r.get("plan_id")),
            effective_date=_date(r.get("effective_date")),
            termination_date=_date(r.get("termination_date")),
            premium_paid_through=_date(r.get("premium_paid_through")),
            status=_text(r.get("status")),
            termination_reason=_text(r.get("termination_reason")),
        )
    return out


def _providers(rows) -> dict[str, Provider]:
    out = {}
    for r in rows:
        provider_id = _text(r.get("provider_id"))
        if not provider_id:
            continue
        # Keep every in_network_* column generically, so a new plan needs no code change.
        network = {
            key[len(NETWORK_PREFIX):]: _upper(value) or ""
            for key, value in r.items()
            if key.startswith(NETWORK_PREFIX)
        }
        out[provider_id] = Provider(
            provider_id=provider_id,
            npi=_text(r.get("npi")),
            network=network,
            specialty=_text(r.get("specialty")),
            provider_type=_text(r.get("provider_type")),
            level5_pct=_float(r.get("level5_em_pct_last_90d")),
            peer_median_level5_pct=_float(r.get("peer_median_level5_em_pct")),
        )
    return out


def _history(rows) -> list[HistoryClaim]:
    return [
        HistoryClaim(
            history_claim_id=_text(r.get("history_claim_id")) or "",
            member_id=_text(r.get("member_id")),
            billing_provider_id=_text(r.get("billing_provider_id")),
            dos=_date(r.get("date_of_service")),
            cpt_code=_text(r.get("cpt_code")),
            status=_text(r.get("status")),
            paid_date=_date(r.get("paid_date")),
        )
        for r in rows
    ]


def _prior_auths(rows) -> list[PriorAuth]:
    return [
        PriorAuth(
            pa_number=_text(r.get("pa_number")) or "",
            member_id=_text(r.get("member_id")),
            cpt_code=_text(r.get("cpt_code")),
            status=_text(r.get("status")),
            valid_from=_date(r.get("valid_from")),
            valid_to=_date(r.get("valid_to")),
            request_date=_date(r.get("request_date")),
            notes=_text(r.get("notes")),
        )
        for r in rows
    ]


def _benefit_rules(rows) -> dict[tuple[str, str], BenefitRule]:
    out = {}
    for r in rows:
        plan_id, cpt = _text(r.get("plan_id")), _text(r.get("cpt_code"))
        if not plan_id or not cpt:
            continue
        out[(plan_id, cpt)] = BenefitRule(
            plan_id=plan_id,
            cpt_code=cpt,
            coverage_status=_text(r.get("coverage_status")),
            prior_auth_required=_upper(r.get("prior_auth_required")),
            annual_limit=_text(r.get("annual_limit")),
            notes=_text(r.get("notes")),
        )
    return out


def _plans(rows) -> dict[str, Plan]:
    out = {}
    for r in rows:
        plan_id = _text(r.get("plan_id"))
        if plan_id:
            out[plan_id] = Plan(
                plan_id=plan_id,
                plan_name=_text(r.get("plan_name")),
                network_type=_text(r.get("network_type")),
                psychotherapy_limit=_text(r.get("psychotherapy_visit_limit_per_year")),
            )
    return out


def _benefit_usage(rows) -> dict[str, tuple[int, int | None]]:
    out = {}
    for r in rows:
        member_id, used = _text(r.get("member_id")), _int(r.get("used_ytd"))
        if member_id and used is not None:
            out[member_id] = (used, _int(r.get("annual_limit")))  # "Unlimited" -> None
    return out


# --------------------------------------------------------------------------- public API


def load_reference(source: str | Path | bytes | BinaryIO) -> ReferenceData:
    """Load the reference workbook from a path, raw bytes or a binary stream.

    Raises WorkbookError with a user-facing message if the file is not a
    readable .xlsx, or a required sheet or column is missing.
    """
    wb = _open_workbook(source)
    try:
        sheets = {name: _read_sheet(wb, name, cols) for name, cols in REQUIRED_SHEETS.items()}
        warnings: list[str] = []
        optional = {name: _read_optional(wb, name, cols, warnings) for name, cols in OPTIONAL_SHEETS.items()}
    finally:
        wb.close()

    ref = ReferenceData(
        members=_members(sheets["Members"]),
        providers=_providers(sheets["Providers"]),
        history=_history(sheets["Claims_History"]),
        prior_auths=_prior_auths(sheets["Prior_Auth_Log"]),
        benefit_rules=_benefit_rules(sheets["Benefit_Rules"]),
        icd10=frozenset(c for c in (_text(r.get("icd10_code")) for r in sheets["ICD10_Codes"]) if c),
        plans=_plans(sheets["Plans"]),
        cpt_allowed={
            cpt: amount
            for r in optional["CPT_Codes"]
            if (cpt := _text(r.get("cpt_code"))) and (amount := _decimal(r.get("in_network_allowed_amount_usd"))) is not None
        },
        med_necessity={
            cpt: dx
            for r in optional["Medical_Necessity_Map"]
            if (cpt := _text(r.get("cpt_code"))) and (dx := _text(r.get("supporting_dx_codes")))
        },
        benefit_usage=_benefit_usage(optional["Benefit_Usage"]),
        warnings=warnings,
    )
    log.info(
        "Reference loaded: %d members, %d providers, %d history rows, %d PAs, %d benefit rules, %d ICD codes",
        len(ref.members), len(ref.providers), len(ref.history), len(ref.prior_auths),
        len(ref.benefit_rules), len(ref.icd10),
    )
    return ref
