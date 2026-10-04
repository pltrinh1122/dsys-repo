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
    # 1099-B headline = the lot table; the doc-side amount is the sum of
    # lot proceeds (the transcript's 1d is the payer's total proceeds).
    "1099-B": "lots",
}
# ...and the corresponding box key inside a transcript payer block.
_TRANSCRIPT_BOX: dict[str, str] = {
    "1": "1",
    "1a": "1a",
    "lots": "1d",
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


def _doc_lots(doc) -> list[dict]:
    """The 1099-B lot table as a list of per-lot dicts (possibly empty)."""
    lots = (doc.fields or {}).get("lots")
    v = lots.get("value") if isinstance(lots, dict) else None
    return [l for l in v if isinstance(l, dict)] if isinstance(v, list) else []


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
    """Per-check booleans for one 1099-B document, over ALL its lots.

    A document passes a check iff it has at least one lot and every lot
    passes that check. A document with no lots fails every check (the
    old "missing fields" behavior). No values escape.
    """
    results = {c: True for c in _LOT_CHECKS}
    lots = _doc_lots(doc)
    if not lots:
        return {c: False for c in _LOT_CHECKS}

    def present(v):
        return v is not None and (not isinstance(v, str) or v.strip() != "")

    def date_ok(v):
        if not present(v):
            return True  # absent dates are not a failure; presence is optional
        return bool(_DATE_RE.match(str(v).strip()))

    for lot in lots:
        proceeds = lot.get("proceeds_1d")
        basis = lot.get("basis_1e")
        term = lot.get("term")
        d_acq = lot.get("date_acquired")
        d_sold = lot.get("date_sold")
        p_dec = _to_decimal(proceeds)
        b_dec = _to_decimal(basis)
        lot_results = {
            "proceeds_present": present(proceeds),
            "basis_present": present(basis),
            "proceeds_nonnegative": p_dec is not None and p_dec >= 0,
            "basis_nonnegative": b_dec is not None and b_dec >= 0,
            "term_valid": term in ("short", "long"),
            "dates_parseable": date_ok(d_acq) and date_ok(d_sold),
        }
        for c, ok in lot_results.items():
            results[c] = results[c] and ok
    return results


def verify_lot_integrity(store, year: int) -> dict:
    """Structural checks on 1099-B lots for a year.

    Checks per lot: proceeds/basis present and non-negative, term in
    {short, long}, dates parseable when present. Reports counts and the
    doc_ids that failed >= 1 check -- never the offending values.
    """
    docs = store.list(year=year, form="1099-B")
    failed_ids: list[str] = []
    failed_by_check: dict[str, int] = {c: 0 for c in _LOT_CHECKS}
    n_lots = 0
    for d in docs:
        lots = _doc_lots(d)
        n_lots += len(lots) or 1  # a lot-less doc still runs one check row
        results = _lot_check_results(d)
        bad = [c for c, ok in results.items() if not ok]
        if bad:
            failed_ids.append(d.doc_id)
            for c in bad:
                failed_by_check[c] += 1
    return {
        "passed": not failed_ids,
        "n_lots": n_lots,
        "n_checks": n_lots * len(_LOT_CHECKS),
        "n_failed": sum(failed_by_check.values()),
        "failed_ids": sorted(failed_ids),
        "failed_by_check": failed_by_check,
    }


def _sum_lot_money(lots: list[dict], term: str,
                   key: str) -> Decimal | None:
    """Sum one money key over lots of a term. None when any lot's amount
    is missing or unparseable (cannot confirm -- never guessed)."""
    total = Decimal("0")
    for lot in lots:
        if lot.get("term") != term:
            continue
        d = _to_decimal(lot.get(key))
        if d is None:
            return None
        total += d
    return total


def verify_summary_reconciliation(store, year: int) -> dict:
    """Lot sums vs statement summary totals for 1099-B docs (F1).

    For each term category present in BOTH the lot table and the
    statement's summary_totals, compare summed lot proceeds/basis
    against the statement totals within 1 cent. Returns doc_ids only
    (blind-safe). A document whose statement shows no summary totals
    is SKIPPED -- never failed.
    """
    docs = store.list(year=year, form="1099-B")
    passed_ids: list[str] = []
    failed_ids: list[str] = []
    skipped_ids: list[str] = []
    n_compared = 0
    for d in docs:
        raw_totals = ((d.fields or {}).get("summary_totals") or {}).get("value")
        totals = {c: v for c, v in (raw_totals or {}).items()
                  if isinstance(v, dict) and v} \
            if isinstance(raw_totals, dict) else {}
        if not totals:
            skipped_ids.append(d.doc_id)
            continue
        lots = _doc_lots(d)
        ok = True
        for cat in ("short", "long"):
            tcat = totals.get(cat) or {}
            for key in ("proceeds_1d", "basis_1e"):
                tv = _to_decimal(tcat.get(key))
                if tv is None:
                    continue  # summary kind absent: nothing to compare
                n_compared += 1
                lv = _sum_lot_money(lots, cat, key)
                if lv is None or abs(lv - tv) > _AMOUNT_TOLERANCE:
                    ok = False
        (passed_ids if ok else failed_ids).append(d.doc_id)
    return {
        "passed": not failed_ids,
        "n_compared": n_compared,
        "passed_ids": sorted(passed_ids),
        "failed_ids": sorted(failed_ids),
        "skipped_ids": sorted(skipped_ids),
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
        doc_box = _PRIMARY_BOX[d.form_type]
        if doc_box == "lots":
            # 1099-B headline = sum of lot proceeds (the transcript's 1d
            # is the payer's total proceeds); None when any lot's
            # proceeds are missing/unparseable -- cannot confirm.
            doc_amt = _sum_lot_money(_doc_lots(d), "short", "proceeds_1d")
            doc_amt_lt = _sum_lot_money(_doc_lots(d), "long", "proceeds_1d")
            doc_amt = (None if doc_amt is None or doc_amt_lt is None
                       else doc_amt + doc_amt_lt)
        else:
            doc_amt = _to_decimal(_field_value(d, doc_box))
        txn_key = _TRANSCRIPT_BOX[doc_box]
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

    Returns {passed, reason}: reason is "ready" or the refusal message.
    The R3 guard's blockers surface as doc_id(reason_code) pairs in the
    message -- doc_ids and reason codes only, never values or names
    (blind-orchestrator safe).
    """
    from .carryforward import from_store

    try:
        from_store(store, year)
    except (ValueError, TypeError) as e:
        return {"passed": False, "reason": str(e)}
    return {"passed": True, "reason": "ready"}


def verify_no_silent_drops(store) -> dict:
    """Every ingested document carries an explicit relevance verdict.

    The relevance triage never deletes anything, so the mechanical
    counterpart is: no document may sit unassessed. A FAILED check
    means "run `taxprep relevance`", not "something is wrong".
    """
    docs = store.list()
    unassessed_ids = sorted(
        d.doc_id for d in docs
        if getattr(d, "relevance", "unassessed") == "unassessed")
    return {
        "passed": not unassessed_ids,
        "n_docs": len(docs),
        "n_unassessed": len(unassessed_ids),
        "unassessed_ids": unassessed_ids,
    }


def verify_all(store, year: int | None = None) -> dict:
    """Run every check. With year=None, per-year checks run for each year
    present in the store (keyed "name:year"); completeness and
    no_silent_drops are global."""
    checks: dict[str, dict] = {
        "completeness": verify_completeness(store),
        "no_silent_drops": verify_no_silent_drops(store),
    }
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
            "summary_reconciliation": verify_summary_reconciliation(store, y),
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
