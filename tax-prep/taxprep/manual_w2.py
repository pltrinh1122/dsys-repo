"""Manual W-2 ingest (Operator-keyed; format spec doc/manual-w2-format.md v1).

The machine does not extract W-2s: the Operator types them into one CSV
per W-2 (one employer, one tax year) using the R23 Operator CSV v2
syntax. This module reuses :func:`taxprep.operator_csv.parse_operator_csv`
for the syntax (headings, boilerplate, source-error audit notes, the
backslash escape) and implements the W-2-specific label map, value
validation, and ingest path.

Unlike ingest_operator_csv, a manual W-2 has NO source PDF -- the CSV
itself is the Bronze source (exact bytes + content hash, R4), and the
resulting Document has form_type "W-2" so verify.py's _W2_BOXES coverage
and transcript reconciliation consume it unchanged.

Validation is fail-loud (ValueError), never silently coerced:
  - money: ^\\d+\\.\\d{2}$ (no $, no commas, no parens, never negative);
  - box 12: ^[A-Z]{1,2} \\d+\\.\\d{2}$;
  - EIN: ^\\d{2}-\\d{7}$;
  - checkbox (box 13): exactly "X";
  - tax_year: ^\\d{4}$, required, as are employer_name / employer_ein;
  - unknown label: ValueError, never silently dropped;
  - a blank-printed row (trailing ":") has no meaning here -- blank boxes
    must be omitted entirely, so it fails loud.

Synthetic fixtures only in tests. Fully local, deterministic.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation

from .models import Document
from .operator_csv import (
    AUDIT_NOTES_KEY,
    SUPERSEDED_BY_KEY,
    _dedup_key,
    parse_operator_csv,
)

__all__ = [
    "MANUAL_W2_VERSION",
    "TEXT_SOURCE_MANUAL_W2",
    "W2_LABEL_MAP",
    "MANUAL_W2_META_KEY",
    "ingest_manual_w2",
    "latest_manual_w2_doc",
]

# Manual W-2 record format version (doc/manual-w2-format.md).
MANUAL_W2_VERSION = "1.0"

# text_source vocabulary: names WHICH text was used -- here, the
# Operator's manually keyed CSV (cf. ingest.py TS_* / "broker-csv" /
# operator_csv's "operator-csv").
TEXT_SOURCE_MANUAL_W2 = "manual"

# Reserved meta key on the manual W-2 document (lowercase: cannot
# collide with numeric box keys or normalized label keys).
MANUAL_W2_META_KEY = "_manual_w2_meta"

# Normalized label (UPPERCASE, collapsed whitespace, per
# twocol.normalize_label) -> (field key, kind). Kinds: "tax_year",
# "employer_name", "employer_ein", "money", "box12", "checkbox",
# "box14" (free text, repeatable), "state", "state_money".
W2_LABEL_MAP = {
    "TAX_YEAR": ("tax_year", "tax_year"),
    "EMPLOYER_NAME": ("employer_name", "employer_name"),
    "EMPLOYER_EIN": ("employer_ein", "employer_ein"),
    "1 WAGES TIPS OTHER COMPENSATION": ("1", "money"),
    "2 FEDERAL INCOME TAX WITHHELD": ("2", "money"),
    "3 SOCIAL SECURITY WAGES": ("3", "money"),
    "4 SOCIAL SECURITY TAX WITHHELD": ("4", "money"),
    "5 MEDICARE WAGES AND TIPS": ("5", "money"),
    "6 MEDICARE TAX WITHHELD": ("6", "money"),
    "12A": ("12a", "box12"),
    "12B": ("12b", "box12"),
    "12C": ("12c", "box12"),
    "12D": ("12d", "box12"),
    "13 STATUTORY EMPLOYEE": ("13_statutory", "checkbox"),
    "13 RETIREMENT PLAN": ("13_retirement", "checkbox"),
    "13 THIRD-PARTY SICK PAY": ("13_sick", "checkbox"),
    "14": ("14", "box14"),
    "15 STATE": ("15_state", "state"),
    "16 STATE WAGES": ("16", "state_money"),
    "17 STATE INCOME TAX": ("17", "state_money"),
}

# Only these field keys may repeat (ordinal-suffixed via _dedup_key):
# box 14 items, and box 12 letters used more than once.
_REPEATABLE_KEYS = frozenset({"14", "12a", "12b", "12c", "12d"})

_MONEY_RE = re.compile(r"^\d+\.\d{2}$")
_BOX12_RE = re.compile(r"^[A-Z]{1,2} \d+\.\d{2}$")
_EIN_RE = re.compile(r"^\d{2}-\d{7}$")
_YEAR_RE = re.compile(r"^\d{4}$")


def _validate_value(field_key: str, kind: str, value: str,
                    csv_row: int) -> str:
    """Validate a value against its kind; return it unchanged (fail loud)."""
    where = f"CSV row {csv_row} ({field_key})"
    if kind in ("money", "state_money"):
        if not _MONEY_RE.match(value):
            raise ValueError(
                f"{where}: money must be ^\\d+\\.\\d{{2}}$ (no $, no "
                f"commas, no parentheses, never negative), got "
                f"{value!r}")
        try:
            Decimal(value)
        except InvalidOperation:
            raise ValueError(
                f"{where}: not a valid decimal: {value!r}") from None
        return value
    if kind == "box12":
        if not _BOX12_RE.match(value):
            raise ValueError(
                f"{where}: box 12 must be 'CODE AMOUNT' "
                f"(^[A-Z]{{1,2}} \\d+\\.\\d{{2}}$), got {value!r}")
        return value
    if kind == "checkbox":
        if value != "X":
            raise ValueError(
                f"{where}: box 13 checkbox must be exactly 'X' when "
                f"checked (omit the row when unchecked), got {value!r}")
        return value
    if kind == "employer_ein":
        if not _EIN_RE.match(value):
            raise ValueError(
                f"{where}: EIN must be NN-NNNNNNN, got {value!r}")
        return value
    if kind == "tax_year":
        if not _YEAR_RE.match(value):
            raise ValueError(
                f"{where}: tax_year must be YYYY, got {value!r}")
        return value
    # employer_name, box14, state: free text (non-empty; parse strips).
    return value


def _manual_w2_docs(store, tax_year: int, employer_ein: str) -> list:
    """All manual W-2 docs for one (tax_year, employer_ein), any
    supersede state."""
    out = []
    for d in store.list(year=tax_year, form="W-2"):
        if d.text_source != TEXT_SOURCE_MANUAL_W2:
            continue
        ein = (d.fields or {}).get("employer_ein", {})
        if isinstance(ein, dict) and ein.get("value") == employer_ein:
            out.append(d)
    return out


def latest_manual_w2_doc(store, tax_year: int, employer_ein: str):
    """The current (non-superseded) manual W-2 doc for a
    (tax_year, employer_ein). None when no manual W-2 was ingested.
    Deterministic tiebreak on doc_id; the ingest supersede logic
    maintains at most one non-superseded doc per (year, ein)."""
    cands = [d for d in _manual_w2_docs(store, tax_year, employer_ein)
             if not (d.fields or {}).get(SUPERSEDED_BY_KEY)]
    if not cands:
        return None
    return sorted(cands, key=lambda d: d.doc_id)[0]


def ingest_manual_w2(store, csv_text: str, filename: str) -> dict:
    """Ingest an Operator-keyed manual W-2 CSV (format v1).

    The CSV itself is the Bronze source: exact bytes, content-hash
    doc_id (first 16 hex, R4), idempotent. Fields carry the box keys
    verify.py and transcript reconciliation expect ("1".."6", "12",
    "14", "employer_ein", "employer_name"), confidence "medium",
    text_source "manual", and csv_row provenance. The document enters
    with status "needs_review" (review UI before Gold, like every
    other source).

    A re-edited CSV (new hash) for the same (tax_year, employer_ein)
    supersedes the earlier manual W-2; old bytes and audit notes stay.

    Returns {"doc_id", "tax_year", "employer_ein", "n_rows", "csv_hash",
    "superseded": [...]} or {"duplicate_import": True, "doc_id": ...}
    on hash-identical re-import. Raises ValueError (fail loud) on any
    spec violation.
    """
    # Bronze: the exact CSV bytes, content-addressed (idempotent).
    csv_bytes = csv_text.encode("utf-8")
    sha = hashlib.sha256(csv_bytes).hexdigest()
    store.store_bronze_bytes(sha, csv_bytes)
    w2_doc_id = sha[:16]  # R4: doc_id derives from the source bytes

    existing = store.get(w2_doc_id)
    if (existing is not None and existing.form_type == "W-2"
            and existing.text_source == TEXT_SOURCE_MANUAL_W2):
        # Same bytes re-ingested: no-op (supersede state untouched --
        # re-ingesting an old CSV never un-supersedes a newer one).
        return {"duplicate_import": True, "doc_id": w2_doc_id}

    parsed = parse_operator_csv(csv_text)

    fields: dict = {}
    key_counts: dict = {}
    seen_single: set = set()
    n_rows = 0
    tax_year_value: str | None = None
    ein_value: str | None = None
    for row in parsed["data_rows"]:
        if row["is_blank"]:
            # Blank boxes are omitted entirely in this format (the
            # trailing-":" blank convention belongs to transcripts).
            raise ValueError(
                f"CSV row {row['csv_row']}: blank-printed row "
                f"{row['printed_label']!r} has no meaning in a manual "
                f"W-2 -- omit the row (a blank box is not a field)")
        norm = row["normalized"]
        mapped = W2_LABEL_MAP.get(norm)
        if mapped is None:
            raise ValueError(
                f"CSV row {row['csv_row']}: unknown W-2 label "
                f"{row['printed_label']!r} (normalized {norm!r}) -- "
                f"unknown labels fail loud, never silently dropped")
        field_key, kind = mapped
        value = _validate_value(field_key, kind, row["value"],
                                row["csv_row"])
        if kind == "tax_year":
            tax_year_value = value
        elif kind == "employer_ein":
            ein_value = value
        if field_key in _REPEATABLE_KEYS:
            key = _dedup_key(key_counts, field_key)
        else:
            if field_key in seen_single:
                raise ValueError(
                    f"CSV row {row['csv_row']}: duplicate label for "
                    f"non-repeatable field {field_key!r} -- only box 14 "
                    f"and box 12 letters may repeat")
            seen_single.add(field_key)
            key = field_key
        fields[key] = {
            "value": value,
            "confidence": "medium",
            "text_source": TEXT_SOURCE_MANUAL_W2,
            "csv_row": row["csv_row"],
            "printed_label": row["printed_label"],
            "raw_text": f"{row['printed_label']}: {value}",
            "provenance": {"csv_row": row["csv_row"]},
        }
        n_rows += 1

    if tax_year_value is None:
        raise ValueError("manual W-2 is missing the required tax_year row")
    if "employer_name" not in seen_single:
        raise ValueError(
            "manual W-2 is missing the required employer_name row")
    if ein_value is None:
        raise ValueError(
            "manual W-2 is missing the required employer_ein row")
    tax_year = int(tax_year_value)

    if parsed["source_errors"]:
        fields[AUDIT_NOTES_KEY] = [
            {"kind": "source_error", "text": e["text"],
             "csv_row": e["csv_row"]}
            for e in parsed["source_errors"]
        ]
    fields[MANUAL_W2_META_KEY] = {
        "filename": filename,
        "csv_hash": sha,
        "manual_format_version": MANUAL_W2_VERSION,
        "n_data_rows": n_rows,
        "n_source_errors": len(parsed["source_errors"]),
    }

    w2_doc = Document(
        doc_id=w2_doc_id,
        tax_year=tax_year,
        form_type="W-2",
        source_path=filename,
        ocr_text_ref="",
        fields=fields,
        source_sha256=sha,
        parent_doc_id=None,
        text_source=TEXT_SOURCE_MANUAL_W2,
        # Like every other source: review UI before Gold.
        status="needs_review",
    )

    # Supersede: a re-edited CSV (new hash) supersedes the earlier
    # manual W-2(s) of the same (tax_year, employer_ein). The old docs
    # keep their bytes and audit notes; only the lookup skips them.
    superseded: list[str] = []
    for old in _manual_w2_docs(store, tax_year, ein_value):
        if old.doc_id == w2_doc_id:
            continue
        old_fields = dict(old.fields or {})
        if old_fields.get(SUPERSEDED_BY_KEY):
            continue
        old_fields[SUPERSEDED_BY_KEY] = w2_doc_id
        old.fields = old_fields
        store.upsert(old)
        superseded.append(old.doc_id)

    store.upsert(w2_doc)
    return {"doc_id": w2_doc_id, "tax_year": tax_year,
            "employer_ein": ein_value, "n_rows": n_rows, "csv_hash": sha,
            "superseded": superseded}
