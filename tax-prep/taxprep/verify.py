"""Mechanical verification suite (blind-orchestrator safe).

Every function in this module returns PII-free dicts: doc_ids, counts,
booleans, and check names -- never field values, payer/employer names,
EINs, dollar amounts, addresses, or raw text. Values are handled
internally (parsed, compared) but never echoed into results.

The workstation agent orchestrates through these checks; all
content-level validation is the human's job in the localhost review
UI. A FAILED check means "needs human eyes", not "wrong".
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from . import transcript

# Forms eligible for transcript reconciliation, mapped to their headline
# box on the document side...
_PRIMARY_BOX: dict[str, str] = {
    "W-2": "1",
    "1099-INT": "1",
    "1099-DIV": "1a",
    "1099-NEC": "1",
    "1099-R": "1",
    "1099-MISC": "1",
    "1099-B": "1d_proceeds",
}
# ...and the corresponding box key inside a transcript payer block.
_TRANSCRIPT_BOX: dict[str, str] = {
    "1": "1",
    "1a": "1a",
    "1d_proceeds": "1d",
}

_AMOUNT_TOLERANCE = Decimal("0.01")
_DATE_RE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")


def _to_decimal(v: Any) -> Decimal | None:
    """Best-effort money -> Decimal. None when unparseable (never raises)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    if isinstance(v, str):
        s = v.strip().replace("$", "").replace(",", "")
        if not s:
            return None
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
        return -d if neg else d
    return None


def _field_value(doc, code: str) -> Any:
    f = (doc.fields or {}).get(code)
    return f.get("value") if isinstance(f, dict) else None


def _norm_ein(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    digits = re.sub(r"\D", "", s)
    return digits or None


def _norm_name(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    norm = re.sub(r"[^a-z0-9]", "", s.lower())
    return norm or None


# -- checks ------------------------------------------------------------


def verify_completeness(store) -> dict:
    """Every document has a known form_type and a non-null tax_year."""
    docs = store.list()
    unknown_form_ids = [d.doc_id for d in docs if d.form_type == "UNKNOWN"]
    missing_year_ids = [d.doc_id for d in docs if d.tax_year is None]
    passed = not unknown_form_ids and not missing_year_ids
    return {
        "passed": passed,
        "n_docs": len(docs),
        "unknown_form_ids": sorted(unknown_form_ids),
        "missing_year_ids": sorted(missing_year_ids),
    }


def verify_validation_gate(store, year: int | None = None) -> dict:
    """All documents (optionally filtered to a year) are validated."""
    docs = store.list(year=year) if year is not None else store.list()
    unvalidated_ids = sorted(d.doc_id for d in docs if d.status != "validated")
    n_total = len(docs)
    return {
        "passed": not unvalidated_ids,
        "n_validated": n_total - len(unvalidated_ids),
        "n_total": n_total,
        "unvalidated_ids": unvalidated_ids,
    }


_LOT_CHECKS = (
    "proceeds_present",
    "basis_present",
    "proceeds_nonnegative",
    "basis_nonnegative",
    "term_valid",
    "dates_parseable",
)


def _lot_check_results(doc) -> dict[str, bool]:
    """Per-check booleans for one 1099-B document. No values escape."""
    proceeds = _field_value(doc, "1d_proceeds")
    basis = _field_value(doc, "1e_basis")
    term = _field_value(doc, "term")
    d_acq = _field_value(doc, "date_acquired")
    d_sold = _field_value(doc, "date_sold")

    def present(v):
        return v is not None and (not isinstance(v, str) or v.strip() != "")

    p_dec = _to_decimal(proceeds)
    b_dec = _to_decimal(basis)

    def date_ok(v):
        if not present(v):
            return True  # absent dates are not a failure; presence is optional
        return bool(_DATE_RE.match(str(v).strip()))

    return {
        "proceeds_present": present(proceeds),
        "basis_present": present(basis),
        "proceeds_nonnegative": p_dec is not None and p_dec >= 0,
        "basis_nonnegative": b_dec is not None and b_dec >= 0,
        "term_valid": term in ("short", "long"),
        "dates_parseable": date_ok(d_acq) and date_ok(d_sold),
    }


def verify_lot_integrity(store, year: int) -> dict:
    """Structural checks on 1099-B lots for a year.

    Checks per document: proceeds/basis present and non-negative, term in
    {short, long}, dates parseable when present. Reports counts and the
    doc_ids that failed >= 1 check -- never the offending values.
    """
    docs = store.list(year=year, form="1099-B")
    failed_ids: list[str] = []
    failed_by_check: dict[str, int] = {c: 0 for c in _LOT_CHECKS}
    for d in docs:
        results = _lot_check_results(d)
        bad = [c for c, ok in results.items() if not ok]
        if bad:
            failed_ids.append(d.doc_id)
            for c in bad:
                failed_by_check[c] += 1
    return {
        "passed": not failed_ids,
        "n_checks": len(docs) * len(_LOT_CHECKS),
        "n_failed": sum(failed_by_check.values()),
        "failed_ids": sorted(failed_ids),
        "failed_by_check": failed_by_check,
    }


def _doc_payer_identity(doc) -> tuple[str | None, str | None]:
    """(ein_digits, normalized_name) for a W-2/1099 doc. Either may be None."""
    ein = _norm_ein(_field_value(doc, "employer_ein"))
    name = _norm_name(_field_value(doc, "employer_name"))
    if name is None:
        name = _norm_name(_field_value(doc, "broker"))
    return ein, name


def _transcript_payers(store, year: int) -> list[dict]:
    """Re-parse WAGE_INCOME_TRANSCRIPT OCR text for a year into payer dicts.

    The stored field codes embed payer names, so re-parsing the OCR text
    is cleaner than reconstructing payers from field keys. Only fully
    parsed transcripts (no unparsed lines at ingest) are used.
    """
    payers = []
    for d in store.list(year=year, form="WAGE_INCOME_TRANSCRIPT"):
        if d.status not in ("transcribed", "validated"):
            continue
        try:
            text = store.load_ocr(d.doc_id)
        except (FileNotFoundError, OSError):
            continue
        parsed = transcript.parse_wage_income_transcript(text, tax_year=year)
        if parsed.get("unparsed_lines"):
            continue
        for p in parsed.get("payers", []):
            payers.append({
                "ein": _norm_ein(p.get("payer_ein")),
                "name": _norm_name(p.get("payer")),
                "form_type": (p.get("form_type") or "UNKNOWN").upper(),
                "boxes": p.get("boxes") or {},
            })
    return payers


def verify_transcript_reconciliation(store, year: int) -> dict:
    """Engine-side reconciliation of validated docs vs the IRS wage & income
    transcript for a year.

    Pairs each validated W-2/1099 doc with a transcript payer block --
    EIN digits first, then normalized payer name, then an unambiguous 1:1
    form_type pairing -- and compares headline amounts with 1-cent
    tolerance. Returns counts and doc_ids only: never names or amounts.
    Docs with status != validated are skipped, not failed.
    """
    docs = [
        d for d in store.list(year=year)
        if d.form_type in _PRIMARY_BOX and d.status == "validated"
    ]
    payers = _transcript_payers(store, year)

    # pass 1: EIN digits
    by_ein: dict[str, list[int]] = {}
    for i, p in enumerate(payers):
        if p["ein"]:
            by_ein.setdefault(p["ein"], []).append(i)
    paired_doc: dict[str, int] = {}  # doc_id -> payer index
    used_payers: set[int] = set()
    remaining_docs = []
    for d in docs:
        ein, _name = _doc_payer_identity(d)
        idxs = [i for i in by_ein.get(ein, []) if i not in used_payers] if ein else []
        if idxs:
            paired_doc[d.doc_id] = idxs[0]
            used_payers.add(idxs[0])
        else:
            remaining_docs.append(d)

    # pass 2: normalized name
    by_name: dict[str, list[int]] = {}
    for i, p in enumerate(payers):
        if i not in used_payers and p["name"]:
            by_name.setdefault(p["name"], []).append(i)
    still_remaining = []
    for d in remaining_docs:
        _ein, name = _doc_payer_identity(d)
        idxs = by_name.get(name, []) if name else []
        if idxs:
            paired_doc[d.doc_id] = idxs[0]
            used_payers.add(idxs[0])
        else:
            still_remaining.append(d)

    # pass 3: unambiguous 1:1 on form_type among the leftovers
    rem_payers = [i for i in range(len(payers))
                  if i not in used_payers and payers[i]["form_type"] != "UNKNOWN"]
    by_form_p: dict[str, list[int]] = {}
    for i in rem_payers:
        by_form_p.setdefault(payers[i]["form_type"], []).append(i)
    by_form_d: dict[str, list] = {}
    for d in still_remaining:
        by_form_d.setdefault(d.form_type, []).append(d)
    final_remaining = []
    for d in still_remaining:
        cands = by_form_p.get(d.form_type, [])
        if len(cands) == 1 and len(by_form_d[d.form_type]) == 1:
            paired_doc[d.doc_id] = cands[0]
            used_payers.add(cands[0])
        else:
            final_remaining.append(d)

    # compare headline amounts on each pair
    doc_by_id = {d.doc_id: d for d in docs}
    mismatched_ids: list[str] = []
    n_matched = 0
    for doc_id, pi in paired_doc.items():
        d = doc_by_id[doc_id]
        p = payers[pi]
        n_matched += 1
        doc_amt = _to_decimal(_field_value(d, _PRIMARY_BOX[d.form_type]))
        txn_key = _TRANSCRIPT_BOX[_PRIMARY_BOX[d.form_type]]
        txn_amt = _to_decimal(p["boxes"].get(txn_key))
        if doc_amt is None or txn_amt is None:
            mismatched_ids.append(doc_id)  # cannot confirm -- needs eyes
        elif abs(doc_amt - txn_amt) > _AMOUNT_TOLERANCE:
            mismatched_ids.append(doc_id)

    paired_doc_ids = set(paired_doc)
    docs_only = sorted(d.doc_id for d in docs if d.doc_id not in paired_doc_ids)
    n_txn_only = sum(1 for i in range(len(payers)) if i not in used_payers)

    passed = not mismatched_ids and n_txn_only == 0 and not docs_only
    return {
        "passed": passed,
        "n_matched_payers": n_matched,
        "mismatched_ids": sorted(mismatched_ids),
        "n_transcript_only_payers": n_txn_only,
        "n_docs_only_payers": len(docs_only),
        "docs_only_ids": docs_only,
    }


def verify_carryforward_ready(store, year: int) -> dict:
    """Wrap carryforward.from_store's loud refusal as a check.

    Returns {passed, reason}: reason is "ready" or the refusal message
    (doc_ids and counts only -- from_store never puts PII in it).
    """
    from .carryforward import from_store

    try:
        from_store(store, year)
    except (ValueError, TypeError) as e:
        return {"passed": False, "reason": str(e)}
    return {"passed": True, "reason": "ready"}


def verify_all(store, year: int | None = None) -> dict:
    """Run every check. With year=None, per-year checks run for each year
    present in the store (keyed "name:year"); completeness is global."""
    checks: dict[str, dict] = {"completeness": verify_completeness(store)}
    if year is not None:
        years = [year]
        keyed = False
    else:
        years = sorted({d.tax_year for d in store.list()
                        if d.tax_year is not None})
        keyed = True
    for y in years:
        sub = {
            "validation_gate": verify_validation_gate(store, y),
            "lot_integrity": verify_lot_integrity(store, y),
            "transcript_reconciliation": verify_transcript_reconciliation(store, y),
            "carryforward_ready": verify_carryforward_ready(store, y),
        }
        if keyed:
            for name, result in sub.items():
                checks[f"{name}:{y}"] = result
        else:
            checks.update(sub)
    passed = all(c.get("passed", False) for c in checks.values())
    return {"passed": passed, "checks": checks}
