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

import itertools
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from . import transcript
from . import gaps as _gaps

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

    V1: a document WITH summary totals but zero comparable keys is
    NOT EVALUATED -- a vacuous check is not a PASS. Such documents
    land in ``not_evaluated_ids`` and fail the check (needs_human):
    ``"passed"`` is False when ``failed_ids`` OR ``not_evaluated_ids``
    is non-empty, and ``"evaluated"`` is True only when at least one
    comparison ran. verify_all consumes ``"passed"``, so a vacuous
    reconciliation fails the whole run -- never a quiet pass.
    """
    docs = store.list(year=year, form="1099-B")
    passed_ids: list[str] = []
    failed_ids: list[str] = []
    not_evaluated_ids: list[str] = []
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
        compared_here = 0
        for cat in ("short", "long"):
            tcat = totals.get(cat) or {}
            for key in ("proceeds_1d", "basis_1e"):
                tv = _to_decimal(tcat.get(key))
                if tv is None:
                    continue  # summary kind absent: nothing to compare
                compared_here += 1
                n_compared += 1
                lv = _sum_lot_money(lots, cat, key)
                if lv is None or abs(lv - tv) > _AMOUNT_TOLERANCE:
                    ok = False
        if compared_here == 0:
            # Statement shows totals but nothing was comparable: the
            # check did not evaluate this document. Vacuous is not PASS.
            not_evaluated_ids.append(d.doc_id)
        else:
            (passed_ids if ok else failed_ids).append(d.doc_id)
    evaluated = n_compared > 0
    return {
        "passed": not failed_ids and not not_evaluated_ids,
        "evaluated": evaluated,
        "n_compared": n_compared,
        "passed_ids": sorted(passed_ids),
        "failed_ids": sorted(failed_ids),
        "not_evaluated_ids": sorted(not_evaluated_ids),
        "skipped_ids": sorted(skipped_ids),
    }


def _doc_payer_identity(doc) -> tuple[str | None, str | None]:
    """(ein_digits, normalized_name) for a W-2/1099 doc. Either may be None."""
    ein = _norm_ein(_field_value(doc, "employer_ein"))
    name = _norm_name(_field_value(doc, "employer_name"))
    if name is None:
        name = _norm_name(_field_value(doc, "broker"))
    return ein, name


def _transcript_payers(store, year: int) -> tuple[list[dict], list[dict]]:
    """Re-parse WAGE_INCOME_TRANSCRIPT OCR text for a year into payer dicts.

    The stored field codes embed payer names, so re-parsing the OCR text
    is cleaner than reconstructing payers from field keys. Returns
    (payers, skipped): skipped transcripts are reported explicitly with
    a reason_code (G1) -- a transcript that exists but is unusable is
    never silently dropped. Header/notice lines are structural (see
    gaps.is_transcript_header_line) and do not count as unparsed.
    """
    payers = []
    skipped = []
    for d in store.list(year=year, form="WAGE_INCOME_TRANSCRIPT"):
        parsed, reason = _gaps.parse_transcript_doc(d, store)
        if reason is not None:
            skipped.append({"doc_id": d.doc_id, "reason_code": reason})
            continue
        for p in parsed.get("payers", []):
            payers.append({
                "ein": _norm_ein(p.get("payer_ein")),
                "name": _norm_name(p.get("payer")),
                "form_type": (p.get("form_type") or "UNKNOWN").upper(),
                "boxes": p.get("boxes") or {},
            })
    return payers, skipped


def verify_transcript_reconciliation(store, year: int) -> dict:
    """Engine-side reconciliation of validated docs vs the IRS wage & income
    transcript for a year.

    Pairs each validated W-2/1099 doc with a transcript payer block --
    EIN digits first, then normalized payer name, then an unambiguous 1:1
    form_type pairing -- and compares headline amounts with 1-cent
    tolerance. Returns counts and doc_ids only: never names or amounts.
    Docs with status != validated are skipped, not failed.

    G1: transcripts that exist for the year but could not be used are
    reported in "skipped_transcripts" with a reason_code, and the check
    FAILS (needs_human) -- it never passes vacuously over a missing or
    unusable transcript.
    """
    docs = [
        d for d in store.list(year=year)
        if d.form_type in _PRIMARY_BOX and d.status == "validated"
    ]
    payers, skipped = _transcript_payers(store, year)

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
    passed = passed and not skipped
    return {
        "passed": passed,
        "n_matched_payers": n_matched,
        "mismatched_ids": sorted(mismatched_ids),
        "n_transcript_only_payers": n_txn_only,
        "n_docs_only_payers": len(docs_only),
        "docs_only_ids": docs_only,
        # G1: transcripts that exist for the year but were unusable.
        "n_skipped_transcripts": len(skipped),
        "skipped_transcripts": sorted(skipped, key=lambda s: s["doc_id"]),
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


# -- R18: extraction-yield verification --------------------------------
#
# verify_completeness only flags UNKNOWN form_type or missing tax_year;
# a misclassified doc or a known type with zero extracted fields passes
# it. These five checks close that gap. All outputs are metadata-only
# (counts, ratios, doc_ids, reason codes) -- never field values.
#
# Thresholds (documented; mechanical, not learned):
#   _ZERO_YIELD_MIN_CHARS  = 200  -- OCR text longer than this with zero
#       extracted fields means extraction produced nothing.
#   _PARSE_COVERAGE_MIN    = 0.8  -- per transcript doc, fraction of
#       content lines (non-blank, non-header) the parser consumed.
#   _EXPECTED_COVERAGE_MIN = 0.75 -- per doc, fraction of the form's
#       expected keys present in fields / parsed structure.
# Docs in BLOCKED / ORPHANED / MULTI_FORM are excluded: extraction is
# not complete by design there (other workstreams own those states).

_ZERO_YIELD_MIN_CHARS = 200
_PARSE_COVERAGE_MIN = 0.8
_EXPECTED_COVERAGE_MIN = 0.75

_EXTRACTABLE_STATUSES = ("transcribed", "validated", "needs_review",
                         # R13: error-route docs keep the extractability
                         # they had as needs_review.
                         "errored")

_TRANSCRIPT_FORMS = {"WAGE_INCOME_TRANSCRIPT", "RETURN_TRANSCRIPT",
                     "ACCOUNT_TRANSCRIPT", "RECORD_OF_ACCOUNT"}

# Expected keys per form type for expected_coverage.
_W2_BOXES = ["1", "2", "3", "4", "5", "6"]
_1099_PRIMARY_BOXES = {
    "1099-INT": ["1"],
    "1099-DIV": ["1a"],
    "1099-NEC": ["1"],
    "1099-R": ["1"],
    "1099-MISC": ["1"],
}
_RETURN_CORE_LINES = ["agi", "taxable_income", "total_tax",
                      "withholding", "refund", "amount_owed"]

# Filename tokens -> form_type hint for type_hint_mismatch. No R11
# Operator-source-label mechanism exists in the tree (searched), so
# filename hints are the only hint source today.
_HINT_TOKENS = {
    "w2": "W-2",
    "1099b": "1099-B",
    "1099int": "1099-INT",
    "1099div": "1099-DIV",
    "1099nec": "1099-NEC",
    "1099r": "1099-R",
    "1099misc": "1099-MISC",
    "1040x": "1040-X",
    "1040": "1040",
    "1098": "1098",
    "scheduled": "SCHEDULE_D",
}
_HINT_NGRAMS = {
    ("wage", "income"): "WAGE_INCOME_TRANSCRIPT",
    ("return", "transcript"): "RETURN_TRANSCRIPT",
    ("account", "transcript"): "ACCOUNT_TRANSCRIPT",
    ("record", "of", "account"): "RECORD_OF_ACCOUNT",
    ("schedule", "d"): "SCHEDULE_D",
}


# -- Source-evidence blind check (R19/R19a) -------------------------------

_PAYER_CODE_RE = re.compile(r"^payer\d+$")


def _scrub_evidence_code(code: str) -> str:
    """Redact payer names embedded in transcript field codes.

    Mirrors mcp_server._scrub_code (kept local: verify.py must not import
    the MCP layer). Blind-safe output never carries taxpayer names.
    """
    parts = str(code).split(".")
    if len(parts) >= 3 and _PAYER_CODE_RE.fullmatch(parts[0]):
        return f"{parts[0]}.[payer].{parts[-1]}"
    return str(code)


def verify_evidence(store, year: int) -> dict:
    """R19/R19a: per-doc source-evidence coverage as blind metadata.

    Counts, per document: extracted fields without a derivable snapshot
    (no/invalid geometry, or a recorded box outside the page bounds),
    computed fields without lineage, and boxes outside page bounds.
    Page bounds come from the bronze PDF's vector page size -- no
    rendering, no PII, and no renderer required.

    Arming rule (mirrors the R17 precedent): the check reports
    ``applicable=False`` and stays green until at least one field in the
    year carries recorded geometry -- per-field geometry is the sibling
    R15-P4 contract and has not landed yet, so a field without geometry
    cannot have a snapshot and must not fail the suite for it. Once
    geometry exists anywhere in the year, every extracted field without
    a snapshot and every computed field without lineage fails.

    Blind-safe: doc_ids, scrubbed box codes, counts, booleans -- never
    values, raw_text, or image data.
    """
    from . import evidence as _evidence

    docs = [d for d in store.list(year=year)]
    per_doc: dict[str, dict] = {}
    n_without_snapshot = 0
    n_without_lineage = 0
    n_out_of_bounds = 0
    n_bounds_unknown = 0
    out_of_bounds: list[dict] = []
    any_geometry = False

    for d in docs:
        fields = {c: f for c, f in (d.fields or {}).items()
                  if isinstance(f, dict) and not c.startswith("__")}
        if not fields:
            continue
        bronze_path = _evidence.bronze_path_for_doc(store, d)
        stat = {"n_fields": len(fields), "n_with_geometry": 0,
                "n_without_snapshot": 0, "n_computed_without_lineage": 0,
                "n_out_of_bounds": 0, "n_bounds_unknown": 0}
        for code, f in fields.items():
            ev = _evidence.field_evidence(f)
            g = ev["geometry"]
            if g is not None:
                any_geometry = True
                stat["n_with_geometry"] += 1
            if _evidence.is_computed(f):
                if ev["state"] == _evidence.STATE_NO_EVIDENCE:
                    stat["n_computed_without_lineage"] += 1
                    n_without_lineage += 1
                continue
            if g is None:
                stat["n_without_snapshot"] += 1
                n_without_snapshot += 1
                continue
            if bronze_path is None:
                stat["n_bounds_unknown"] += 1
                n_bounds_unknown += 1
                continue
            size = _evidence.page_size_pt(
                bronze_path, _evidence.bronze_page_for(d, g["page"]))
            verdict = _evidence.bbox_within_bounds(g["bbox_pdf"], size)
            if verdict is None:
                stat["n_bounds_unknown"] += 1
                n_bounds_unknown += 1
            elif verdict is False:
                stat["n_out_of_bounds"] += 1
                n_out_of_bounds += 1
                stat["n_without_snapshot"] += 1
                n_without_snapshot += 1
                out_of_bounds.append(
                    {"doc_id": d.doc_id,
                     "field": _scrub_evidence_code(code)})
        per_doc[d.doc_id] = stat

    applicable = any_geometry
    passed = (not applicable
              or (n_without_snapshot == 0 and n_without_lineage == 0
                  and n_out_of_bounds == 0))
    return {
        "passed": passed,
        "applicable": applicable,
        "reason": None if applicable else "no_recorded_geometry",
        "n_docs": len(per_doc),
        "n_extracted_fields_without_snapshot": n_without_snapshot,
        "n_computed_fields_without_lineage": n_without_lineage,
        "n_bbox_out_of_bounds": n_out_of_bounds,
        "n_bbox_bounds_unknown": n_bounds_unknown,
        "out_of_bounds": out_of_bounds,
        "docs": per_doc,
    }


def verify_zero_yield(store, year: int) -> dict:
    """Docs with substantial OCR text but zero extracted fields.

    OCR text longer than _ZERO_YIELD_MIN_CHARS with an empty fields
    dict means the extraction pipeline produced nothing -- FAIL.
    Blind-safe: doc_ids and counts only.
    """
    failed_ids: list[str] = []
    n_checked = 0
    for d in store.list(year=year):
        if d.status not in _EXTRACTABLE_STATUSES:
            continue
        try:
            text = store.load_ocr(d.doc_id)
        except (FileNotFoundError, OSError):
            continue
        n_checked += 1
        if len(text) > _ZERO_YIELD_MIN_CHARS and not (d.fields or {}):
            failed_ids.append(d.doc_id)
    return {
        "passed": not failed_ids,
        "n_checked": n_checked,
        "n_failed": len(failed_ids),
        "failed_ids": sorted(failed_ids),
        "min_text_chars": _ZERO_YIELD_MIN_CHARS,
    }


def _content_line_count(text: str) -> int:
    """Non-blank, non-header lines: the transcript's real content."""
    n = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if _gaps.is_transcript_header_line(raw):
            continue
        n += 1
    return n


def verify_parse_coverage(store, year: int) -> dict:
    """Per transcript doc: parsed content lines / all content lines.

    Header/notice lines are structural (G1) and excluded from both
    sides of the ratio. A doc below _PARSE_COVERAGE_MIN FAILs; docs
    that cannot be assessed (wrong status, no OCR, parser unavailable)
    are listed and also fail -- needs_human, never a quiet pass.
    """
    docs_out: list[dict] = []
    low_ids: list[str] = []
    unassessable: list[dict] = []
    for d in sorted(store.list(year=year), key=lambda d: d.doc_id):
        if d.form_type not in _TRANSCRIPT_FORMS:
            continue
        if d.status not in _EXTRACTABLE_STATUSES:
            unassessable.append(
                {"doc_id": d.doc_id, "reason_code": "wrong_status"})
            continue
        try:
            text = store.load_ocr(d.doc_id)
        except (FileNotFoundError, OSError):
            unassessable.append(
                {"doc_id": d.doc_id, "reason_code": "ocr_unavailable"})
            continue
        parser = _gaps.parser_for(d.form_type)
        if parser is None:
            unassessable.append(
                {"doc_id": d.doc_id, "reason_code": "parser_unavailable"})
            continue
        parsed = parser(text, tax_year=d.tax_year)
        n_content = _content_line_count(text)
        n_unparsed = len(_gaps.effective_unparsed_lines(parsed))
        coverage = ((n_content - n_unparsed) / n_content
                    if n_content else 0.0)
        docs_out.append({"doc_id": d.doc_id, "form_type": d.form_type,
                         "coverage": coverage, "n_content_lines": n_content})
        if coverage < _PARSE_COVERAGE_MIN:
            low_ids.append(d.doc_id)
    return {
        "passed": not low_ids and not unassessable,
        "threshold": _PARSE_COVERAGE_MIN,
        "n_transcripts": len(docs_out) + len(unassessable),
        "docs": docs_out,
        "low_ids": sorted(low_ids),
        "unassessable": sorted(unassessable, key=lambda e: e["doc_id"]),
    }


def _expected_keys_for_transcript(doc, store) -> tuple[tuple | None,
                                                   str | None]:
    """Expected vs present keys for a transcript doc from its parse.

    Returns ((expected, present), None) on success, or (None,
    reason_code) when the doc cannot be parsed (caller records it as
    unassessable).
    """
    parsed, reason = _gaps.parse_transcript_doc(doc, store)
    if parsed is None:
        return None, reason
    ft = doc.form_type
    if ft == "WAGE_INCOME_TRANSCRIPT":
        return ((["payer_present"],
                 ["payer_present"] if parsed.get("payers") else []), None)
    if ft == "RETURN_TRANSCRIPT":
        lines = parsed.get("lines") or {}
        return (_RETURN_CORE_LINES,
                [k for k in _RETURN_CORE_LINES if k in lines]), None
    if ft == "ACCOUNT_TRANSCRIPT":
        return ((["transaction_present"], ["transaction_present"]
                 if parsed.get("transactions") else []), None)
    if ft == "RECORD_OF_ACCOUNT":
        return ((["return_section", "account_section"],
                 [k for k in ("return_section", "account_section")
                  if parsed.get(k)]), None)
    return None, "no_expectation"


def verify_expected_coverage(store, year: int) -> dict:
    """Per form type, the fraction of expected keys present.

    W-2 boxes 1-6; 1099 primary box per type (1099-B: non-empty lot
    table); return-transcript core lines (agi, taxable_income,
    total_tax, withholding, refund, amount_owed); >=1 payer per
    wage & income transcript; >=1 transaction per account transcript.
    Below _EXPECTED_COVERAGE_MIN -> FAIL. Reports ratios, never values.
    """
    low: list[dict] = []
    unassessable: list[dict] = []
    n_assessed = 0
    n_not_applicable = 0
    for d in sorted(store.list(year=year), key=lambda d: d.doc_id):
        if d.status not in _EXTRACTABLE_STATUSES:
            continue
        ft = d.form_type
        if ft in _TRANSCRIPT_FORMS:
            expected_present, reason = _expected_keys_for_transcript(d, store)
            if expected_present is None:
                unassessable.append(
                    {"doc_id": d.doc_id, "reason_code": reason})
                continue
            expected, present = expected_present
        elif ft == "W-2":
            expected = _W2_BOXES
            present = [b for b in expected if b in (d.fields or {})]
        elif ft in _1099_PRIMARY_BOXES:
            expected = _1099_PRIMARY_BOXES[ft]
            present = [b for b in expected if b in (d.fields or {})]
        elif ft == "1099-B":
            expected = ["lots_present"]
            present = ["lots_present"] if _doc_lots(d) else []
        else:
            n_not_applicable += 1
            continue
        n_assessed += 1
        coverage = len(present) / len(expected)
        if coverage < _EXPECTED_COVERAGE_MIN:
            low.append({"doc_id": d.doc_id, "form_type": ft,
                        "coverage": coverage,
                        "n_expected": len(expected),
                        "n_present": len(present)})
    return {
        "passed": not low and not unassessable,
        "threshold": _EXPECTED_COVERAGE_MIN,
        "n_assessed": n_assessed,
        "n_not_applicable": n_not_applicable,
        "low": low,
        "unassessable": sorted(unassessable, key=lambda e: e["doc_id"]),
    }


def _filename_hint(source_path: str | None) -> str | None:
    """A form_type hint from the source filename, or None.

    Token-exact (single tokens and 2-3 token n-grams) against the hint
    tables. Ambiguous (several distinct hints) or hint-less filenames
    yield None -- a hint is only raised when it is unambiguous.
    """
    if not source_path:
        return None
    tokens = re.sub(r"[^a-z0-9]+", " ", Path(source_path).stem.lower()).split()
    hints: set[str] = set()
    for t in tokens:
        if t in _HINT_TOKENS:
            hints.add(_HINT_TOKENS[t])
    for i in range(len(tokens)):
        for n in (2, 3):
            gram = tuple(tokens[i:i + n])
            if gram in _HINT_NGRAMS:
                hints.add(_HINT_NGRAMS[gram])
    return next(iter(hints)) if len(hints) == 1 else None


def verify_type_hint_mismatch(store, year: int) -> dict:
    """An unambiguous source-filename hint differing from form_type.

    Raised as needs_human (mismatched entries); NEVER auto-reclassifies
    -- the Operator disposes classification. doc_ids and form labels
    only, never filenames' content.
    """
    mismatched: list[dict] = []
    n_checked = 0
    n_no_hint = 0
    for d in sorted(store.list(year=year), key=lambda d: d.doc_id):
        if d.status not in _EXTRACTABLE_STATUSES:
            continue
        if d.form_type == "UNKNOWN":
            continue  # completeness already flags these
        n_checked += 1
        hint = _filename_hint(d.source_path)
        if hint is None:
            n_no_hint += 1
            continue
        if hint != d.form_type:
            mismatched.append({"doc_id": d.doc_id, "hint": hint,
                               "form_type": d.form_type})
    return {
        "passed": not mismatched,
        "n_checked": n_checked,
        "n_no_hint": n_no_hint,
        "mismatched": mismatched,
    }


def _content_prefix(text: str, n: int = 400) -> str:
    """Whitespace-collapsed leading chars: the duplicate-candidate
    fingerprint. 400 chars is a documented heuristic -- long enough to
    cover a form header + first data rows, short enough to ignore
    page-level noise."""
    return re.sub(r"\s+", " ", text).strip()[:n]


def verify_cross_doc(store, year: int) -> dict:
    """Same form + payer + year appearing twice with overlapping content.

    Pairs docs sharing (form_type, tax_year, EIN-or-normalized-name);
    a pair whose OCR texts share the 400-char content prefix is a
    duplicate candidate -- needs_human, never merged mechanically.
    """
    groups: dict[tuple, list] = {}
    for d in store.list(year=year):
        if d.status not in _EXTRACTABLE_STATUSES:
            continue
        if d.form_type in _TRANSCRIPT_FORMS:
            continue
        ein, name = _doc_payer_identity(d)
        identity = ein or name
        if identity is None:
            continue
        groups.setdefault((d.form_type, d.tax_year, identity), []).append(d)
    candidates: list[dict] = []
    n_pairs = 0
    for _key, ds in sorted(groups.items(),
                           key=lambda kv: [d.doc_id for d in kv[1]]):
        ds = sorted(ds, key=lambda d: d.doc_id)
        texts: dict[str, str | None] = {}
        for d in ds:
            try:
                texts[d.doc_id] = store.load_ocr(d.doc_id)
            except (FileNotFoundError, OSError):
                texts[d.doc_id] = None
        for a, b in itertools.combinations(ds, 2):
            ta, tb = texts[a.doc_id], texts[b.doc_id]
            if ta is None or tb is None:
                continue
            n_pairs += 1
            pa, pb = _content_prefix(ta), _content_prefix(tb)
            if pa and pa == pb:
                candidates.append({"doc_ids": [a.doc_id, b.doc_id]})
    return {
        "passed": not candidates,
        "n_pairs_checked": n_pairs,
        "candidates": candidates,
    }


def verify_extraction_yield(store, year: int) -> dict:
    """R18: the five extraction-yield checks as one verify_all entry.

    zero_yield / parse_coverage / expected_coverage FAIL on low yield;
    type_hint_mismatch and cross_doc surface needs_human candidates.
    Every sub-check follows the check-result shape (a "passed" key plus
    PII-free detail).
    """
    checks = {
        "zero_yield": verify_zero_yield(store, year),
        "parse_coverage": verify_parse_coverage(store, year),
        "expected_coverage": verify_expected_coverage(store, year),
        "type_hint_mismatch": verify_type_hint_mismatch(store, year),
        "cross_doc": verify_cross_doc(store, year),
        # R19/R19a: source-evidence coverage (blind metadata only).
        "evidence": verify_evidence(store, year),
    }
    return {
        "passed": all(c["passed"] for c in checks.values()),
        "checks": checks,
    }


# -- Record-of-Account corroboration (R17-adjacent) ---------------------

def _canon_amount(v) -> str | None:
    """Canonical amount string for set comparison. None when not money."""
    d = _to_decimal(v)
    return None if d is None else format(d.normalize(), "f")


def _txn_signature(t: dict) -> tuple:
    return (t.get("code"), t.get("date"), _canon_amount(t.get("amount")))


def _roa_section_conflicts(section: str, roa_section: dict,
                           standalone: dict) -> list[dict]:
    """Compare one ROA section against its standalone transcript parse.

    Returns PII-free conflict entries {"section", "key", "conflict"}:
    "value_mismatch" (both sides have the key, values differ),
    "roa_only" / "standalone_only". Values are compared internally
    (Decimal for money) but never echoed -- keys and kinds only.
    Transactions are compared as multisets of (code, date, amount).
    """
    conflicts: list[dict] = []
    roa_lines = roa_section.get("lines") or {}
    st_lines = standalone.get("lines") or {}
    for key in sorted(set(roa_lines) | set(st_lines)):
        if key not in roa_lines:
            conflicts.append({"section": section, "key": key,
                              "conflict": "standalone_only"})
        elif key not in st_lines:
            conflicts.append({"section": section, "key": key,
                              "conflict": "roa_only"})
        else:
            rv, sv = roa_lines[key], st_lines[key]
            rd, sd = _to_decimal(rv), _to_decimal(sv)
            same = (rd == sd) if (rd is not None and sd is not None) \
                else (rv == sv)
            if not same:
                conflicts.append({"section": section, "key": key,
                                  "conflict": "value_mismatch"})
    roa_txns = Counter(_txn_signature(t)
                       for t in (roa_section.get("transactions") or []))
    st_txns = Counter(_txn_signature(t)
                      for t in (standalone.get("transactions") or []))
    for sig in sorted(set(roa_txns) | set(st_txns), key=repr):
        code = sig[0] if sig[0] is not None else "?"
        for _ in range(roa_txns[sig] - st_txns[sig]):
            conflicts.append({"section": section, "key": f"tc_{code}",
                              "conflict": "roa_only"})
        for _ in range(st_txns[sig] - roa_txns[sig]):
            conflicts.append({"section": section, "key": f"tc_{code}",
                              "conflict": "standalone_only"})
    return conflicts


def verify_roa_corroboration(store, year: int) -> dict:
    """Record-of-Account vs standalone transcripts for a year.

    When a RECORD_OF_ACCOUNT doc and same-year RETURN_TRANSCRIPT /
    ACCOUNT_TRANSCRIPT docs exist, the ROA's return_section and
    account_section are compared against the standalone parses. Every
    disagreement is raised as a needs_human conflict entry (standing
    conflicts rule: raised to the Operator, never mechanically
    resolved). Entries are metadata-only: doc_ids, section, key,
    conflict kind -- never values.

    The R17 workstream owns parse_account_transcript and
    parse_record_of_account in transcript.py. Until they exist this
    check reports applicable=False and stays green -- it arms itself
    the moment the parsers land (no reimplementation here).
    """
    parse_roa = getattr(transcript, "parse_record_of_account", None)
    parse_account = getattr(transcript, "parse_account_transcript", None)
    roa_docs = store.list(year=year, form="RECORD_OF_ACCOUNT")
    if parse_roa is None or parse_account is None:
        return {
            "passed": True,
            "applicable": False,
            "reason": "parsers_not_present",
            "n_roa": len(roa_docs),
            "n_conflicts": 0,
            "conflicts": [],
            "skipped": [],
        }
    conflicts: list[dict] = []
    skipped: list[dict] = []
    n_roa = 0
    for roa in sorted(roa_docs, key=lambda d: d.doc_id):
        n_roa += 1
        roa_parsed, roa_reason = _gaps.parse_transcript_doc(roa, store)
        if roa_reason is not None:
            skipped.append({"doc_id": roa.doc_id, "role": "roa",
                            "reason_code": roa_reason})
            continue
        pairs = [
            ("return", "RETURN_TRANSCRIPT",
             roa_parsed.get("return_section") or {}),
            ("account", "ACCOUNT_TRANSCRIPT",
             roa_parsed.get("account_section") or {}),
        ]
        for section, form, roa_section in pairs:
            standalone_docs = store.list(year=year, form=form)
            if not standalone_docs:
                skipped.append({"doc_id": roa.doc_id,
                                "role": f"standalone_{section}",
                                "reason_code": "no_standalone"})
                continue
            for st in sorted(standalone_docs, key=lambda d: d.doc_id):
                st_parsed, st_reason = _gaps.parse_transcript_doc(st, store)
                if st_reason is not None:
                    skipped.append({"doc_id": st.doc_id,
                                    "role": f"standalone_{section}",
                                    "reason_code": st_reason})
                    continue
                for c in _roa_section_conflicts(section, roa_section,
                                                st_parsed):
                    entry = {"roa_doc_id": roa.doc_id,
                             "standalone_doc_id": st.doc_id}
                    entry.update(c)
                    conflicts.append(entry)
    blocking = [s for s in skipped
                if s["reason_code"] != "no_standalone"]
    return {
        "passed": not conflicts and not blocking,
        "applicable": True,
        "n_roa": n_roa,
        "n_conflicts": len(conflicts),
        "conflicts": conflicts,
        "skipped": sorted(skipped, key=lambda s: (s["doc_id"],
                                                 s["role"])),
    }


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


def verify_source_integrity(store) -> dict:
    """R15/P2: every bronze object's recorded source still identifies it.

    For each bronze object with recorded alias paths (the ingest-time
    absolute paths): each alias must exist on disk AND its bytes must
    still hash to the bronze hash. A rename/move surfaces as
    "source_missing"; different bytes at the same path surface as
    "hash_mismatch" (P2's byte-swap probe). Output is doc_ids and reason
    codes only -- never paths (blind-orchestrator safe; local paths can
    leak usernames).

    Bronze objects with no aliases (tombstone/legacy rows) are reported
    in n_unchecked -- they cannot be integrity-checked, never silently
    passed.
    """
    failed: list[dict] = []
    unchecked = 0
    n_aliases = 0
    for sha in store.bronze_hashes():
        bronze = store.get_bronze(sha)
        aliases = (bronze or {}).get("aliases") or []
        doc_ids = sorted(
            d.doc_id for d in store.list()
            if getattr(d, "source_sha256", None) == sha)
        if not aliases or (bronze or {}).get("blocked_reason"):
            # Tombstone/legacy rows never captured source bytes: they
            # cannot be integrity-checked, never silently passed.
            unchecked += 1
            continue
        for alias in aliases:
            n_aliases += 1
            reason = _check_source_alias(sha, alias)
            if reason is not None:
                failed.append({"doc_ids": doc_ids,
                               "reason_code": reason})
                break  # one entry per bronze object
    return {
        "passed": not failed,
        "n_bronze": len(store.bronze_hashes()),
        "n_aliases": n_aliases,
        "n_unchecked": unchecked,
        "failed": failed,
    }


def _check_source_alias(sha: str, alias: str) -> str | None:
    """None when the alias path still identifies the bronze bytes, else a
    stable reason code ("source_missing" | "hash_mismatch")."""
    import hashlib

    path = Path(alias)
    try:
        if not path.is_file():
            return "source_missing"
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return "source_missing"
    return None if h.hexdigest() == sha else "hash_mismatch"


def verify_all(store, year: int | None = None) -> dict:
    """Run every check. With year=None, per-year checks run for each year
    present in the store (keyed "name:year"); completeness,
    no_silent_drops, and source_integrity are global."""
    checks: dict[str, dict] = {
        "completeness": verify_completeness(store),
        "no_silent_drops": verify_no_silent_drops(store),
        "source_integrity": verify_source_integrity(store),
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
            "extraction_yield": verify_extraction_yield(store, y),
            "roa_corroboration": verify_roa_corroboration(store, y),
        }
        if keyed:
            for name, result in sub.items():
                checks[f"{name}:{y}"] = result
        else:
            checks.update(sub)
    passed = all(c.get("passed", False) for c in checks.values())
    return {"passed": passed, "checks": checks}
