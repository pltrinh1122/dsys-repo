"""Mechanical verification tests -- all fixtures synthetic, outputs PII-free."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from taxprep.ingest import ingest_file
from taxprep.models import Document
from taxprep.store import DocumentStore
from taxprep import verify as V


def _field(value, confidence="high", raw=""):
    return {"value": value, "confidence": confidence, "raw_text": raw}


def _doc(doc_id, year, form, fields, status="transcribed"):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form,
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields,
        status=status,
    )


def _lot(proceeds=None, basis=None, term=None,
         d_acq="01/15/2024", d_sold="06/20/2024", wash_1g=None,
         fed_withheld_4=None, accrued_market_discount_1f=None):
    return {
        "description": None,
        "date_acquired": d_acq,
        "date_sold": d_sold,
        "proceeds_1d": proceeds,
        "basis_1e": basis,
        "wash_1g": wash_1g,
        "accrued_market_discount_1f": accrued_market_discount_1f,
        "fed_withheld_4": fed_withheld_4,
        "term": term,
        "covered": None,
    }


def _b1099(doc_id, year, proceeds, basis, term, status="validated",
           d_acq="01/15/2024", d_sold="06/20/2024", lots=None,
           summary_totals=None):
    if lots is None:
        lots = [_lot(proceeds, basis, term, d_acq, d_sold)]
    fields = {
        "lots": _field(lots),
        "broker": _field("Synthetic Broker"),
    }
    if summary_totals is not None:
        fields["summary_totals"] = _field(summary_totals)
    return _doc(doc_id, year, "1099-B", fields, status=status)


def _store_with(tmp_path, docs):
    store = DocumentStore(tmp_path / "data")
    for d in docs:
        store.upsert(d)
    return store


def _pii_free(obj):
    """Recursive blind-orchestrator assertion: no value/raw_text keys,
    no $<digit> money patterns in strings."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key leaked: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        import re
        assert not re.search(r"\$\d", obj), f"money pattern leaked: {obj[:60]!r}"


# -- verify_completeness ---------------------------------------------

def test_completeness_all_pass(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w1", 2024, "W-2", {}, "validated"),
        _doc("b1", 2023, "1099-B", {}, "transcribed"),
    ])
    r = V.verify_completeness(store)
    assert r == {"passed": True, "n_docs": 2,
                 "unknown_form_ids": [], "missing_year_ids": []}
    _pii_free(r)


def test_completeness_flags_unknown_form_and_missing_year(tmp_path):
    store = _store_with(tmp_path, [
        _doc("u1", 2024, "UNKNOWN", {}),
        _doc("y1", None, "W-2", {}),
        _doc("ok", 2024, "W-2", {}),
    ])
    r = V.verify_completeness(store)
    assert r["passed"] is False
    assert r["unknown_form_ids"] == ["u1"]
    assert r["missing_year_ids"] == ["y1"]
    assert r["n_docs"] == 3
    _pii_free(r)


# -- verify_validation_gate ------------------------------------------

def test_validation_gate(tmp_path):
    store = _store_with(tmp_path, [
        _doc("a", 2024, "W-2", {}, "validated"),
        _doc("b", 2024, "W-2", {}, "transcribed"),
        _doc("c", 2023, "W-2", {}, "needs_review"),
    ])
    r = V.verify_validation_gate(store)
    assert r["passed"] is False
    assert r["n_validated"] == 1 and r["n_total"] == 3
    assert r["unvalidated_ids"] == ["b", "c"]
    r24 = V.verify_validation_gate(store, 2024)
    assert r24["unvalidated_ids"] == ["b"] and r24["n_total"] == 2
    _pii_free(r)


# -- verify_lot_integrity --------------------------------------------

def test_lot_integrity_all_pass(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short"),
        _b1099("b2", 2024, "2,500.00", "$1,000.00", "long"),
    ])
    r = V.verify_lot_integrity(store, 2024)
    assert r["passed"] is True
    assert r["n_lots"] == 2
    assert r["n_checks"] == 12 and r["n_failed"] == 0
    assert r["failed_ids"] == []
    _pii_free(r)


def test_lot_integrity_failures_are_structural_only(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("missing-basis", 2024, "1000.00", None, "short"),
        _b1099("neg-proceeds", 2024, "-5.00", 10.00, "short"),
        _b1099("bad-term", 2024, "100.00", "50.00", "medium"),
        _b1099("bad-date", 2024, "100.00", "50.00", "long",
               d_acq="not-a-date"),
    ])
    r = V.verify_lot_integrity(store, 2024)
    assert r["passed"] is False
    assert r["failed_ids"] == ["bad-date", "bad-term",
                               "missing-basis", "neg-proceeds"]
    assert r["failed_by_check"]["basis_present"] == 1
    assert r["failed_by_check"]["proceeds_nonnegative"] == 1
    assert r["failed_by_check"]["term_valid"] == 1
    assert r["failed_by_check"]["dates_parseable"] == 1
    # no values leak: only counts and ids
    _pii_free(r)
    assert set(r) == {"passed", "n_lots", "n_checks", "n_failed",
                      "failed_ids", "failed_by_check"}


def test_lot_integrity_multi_lot_counts_per_lot(tmp_path):
    # one failing lot fails the doc; n_checks counts every lot
    store = _store_with(tmp_path, [
        _b1099("m1", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
            _lot("2000.00", None, "short"),  # missing basis
        ]),
    ])
    r = V.verify_lot_integrity(store, 2024)
    assert r["passed"] is False
    assert r["n_lots"] == 2
    assert r["n_checks"] == 12
    assert r["failed_ids"] == ["m1"]
    assert r["failed_by_check"]["basis_present"] == 1
    _pii_free(r)


# -- verify_summary_reconciliation -----------------------------------

def test_summary_reconciliation_pass(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
            _lot("2500.00", "3000.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": "3500.00",
                                     "basis_1e": "4500.00"}}),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["passed"] is True
    assert r["passed_ids"] == ["b1"]
    assert r["failed_ids"] == [] and r["skipped_ids"] == []
    assert r["n_compared"] == 2
    _pii_free(r)


def test_summary_reconciliation_tolerance_boundary(tmp_path):
    # exactly 1 cent of drift passes; more than 1 cent fails
    store = _store_with(tmp_path, [
        _b1099("edge", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": "1000.01",
                                     "basis_1e": "1500.00"}}),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["passed"] is True and r["passed_ids"] == ["edge"]


def test_summary_reconciliation_fail(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
            _lot("2500.00", "3000.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": "3500.00",
                                     "basis_1e": "4499.97"}}),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["passed"] is False
    assert r["failed_ids"] == ["b1"]
    assert r["passed_ids"] == [] and r["skipped_ids"] == []
    _pii_free(r)


def test_summary_reconciliation_skip_when_no_totals(tmp_path):
    # no summary totals on the statement: skipped, never failed
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short"),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["passed"] is True
    assert r["evaluated"] is False
    assert r["not_evaluated_ids"] == []
    assert r["skipped_ids"] == ["b1"]
    assert r["failed_ids"] == [] and r["passed_ids"] == []
    _pii_free(r)


def test_summary_reconciliation_not_evaluated_when_no_comparable_keys(tmp_path):
    # V1: the statement shows totals but zero keys are comparable --
    # a vacuous check is not a PASS: the doc is not evaluated and the
    # check fails (needs_human)
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": None,
                                     "basis_1e": None}}),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["n_compared"] == 0
    assert r["evaluated"] is False
    assert r["not_evaluated_ids"] == ["b1"]
    assert r["passed"] is False
    assert r["failed_ids"] == [] and r["passed_ids"] == []
    assert r["skipped_ids"] == []
    _pii_free(r)


def test_summary_reconciliation_mixed_evaluated_and_not_evaluated(tmp_path):
    # one doc evaluates and passes, one is vacuous: overall not PASS
    store = _store_with(tmp_path, [
        _b1099("ok", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": "1000.00",
                                     "basis_1e": "1500.00"}}),
        _b1099("vac", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": None}}),
    ])
    r = V.verify_summary_reconciliation(store, 2024)
    assert r["n_compared"] == 2
    assert r["evaluated"] is True
    assert r["passed_ids"] == ["ok"]
    assert r["not_evaluated_ids"] == ["vac"]
    assert r["passed"] is False  # vacuous drags the check down
    _pii_free(r)


def test_verify_all_fails_on_vacuous_reconciliation(tmp_path):
    # the not-evaluated case wires into verify_all as a FAIL signal
    store = _store_with(tmp_path, [
        _b1099("vac", 2024, None, None, None, lots=[
            _lot("1000.00", "1500.00", "short"),
        ], summary_totals={"short": {"proceeds_1d": None}},
         status="validated"),
    ])
    r = V.verify_all(store, 2024)
    assert r["checks"]["summary_reconciliation"]["passed"] is False
    assert r["checks"]["summary_reconciliation"]["not_evaluated_ids"] == ["vac"]
    assert r["passed"] is False
    _pii_free(r)


# -- verify_transcript_reconciliation --------------------------------

WAGE_INCOME = """WAGE AND INCOME TRANSCRIPT Tax Year 2024
Payer: ACME CORPORATION 12-3456789
Form W-2
Box 1 Wages: $85,000.00
Box 2 Withheld: $12,340.00
Payer: EXAMPLE BANK
Form 1099-INT
Box 1 Interest: $420.50
"""


def _store_with_transcript(tmp_path, transcript_text, docs):
    store = DocumentStore(tmp_path / "data")
    tpath = Path(tmp_path) / "wage_income_2024.txt"
    tpath.write_text(transcript_text)
    ingest_file(tpath, store)
    for d in docs:
        store.upsert(d)
    return store


def _w2(doc_id, wages, ein="12-3456789", name="ACME CORPORATION",
        status="validated"):
    return _doc(doc_id, 2024, "W-2",
                {"1": _field(wages),
                 "employer_ein": _field(ein),
                 "employer_name": _field(name)},
                status=status)


def _i1099(doc_id, form, box, amount, status="validated"):
    return _doc(doc_id, 2024, form, {box: _field(amount)}, status=status)


def test_reconciliation_match(tmp_path):
    store = _store_with_transcript(tmp_path, WAGE_INCOME, [
        _w2("w2-a", 85000.00),
        _i1099("i-a", "1099-INT", "1", 420.50),
    ])
    r = V.verify_transcript_reconciliation(store, 2024)
    assert r["passed"] is True
    assert r["n_matched_payers"] == 2
    assert r["mismatched_ids"] == []
    assert r["n_transcript_only_payers"] == 0
    assert r["n_docs_only_payers"] == 0
    _pii_free(r)


def test_reconciliation_mismatch(tmp_path):
    store = _store_with_transcript(tmp_path, WAGE_INCOME, [
        _w2("w2-a", 85000.00),
        _i1099("i-a", "1099-INT", "1", 999.99),  # transcript says 420.50
    ])
    r = V.verify_transcript_reconciliation(store, 2024)
    assert r["passed"] is False
    assert r["mismatched_ids"] == ["i-a"]
    assert r["n_matched_payers"] == 2
    _pii_free(r)


def test_reconciliation_transcript_only_payer(tmp_path):
    extra = WAGE_INCOME + ("Payer: OTHER BANK\nForm 1099-DIV\n"
                           "Box 1a Ordinary: $10.00\n")
    store = _store_with_transcript(tmp_path, extra, [
        _w2("w2-a", 85000.00),
        _i1099("i-a", "1099-INT", "1", 420.50),
    ])
    r = V.verify_transcript_reconciliation(store, 2024)
    assert r["passed"] is False
    assert r["n_transcript_only_payers"] == 1
    assert r["n_matched_payers"] == 2
    _pii_free(r)


def test_reconciliation_docs_only_payer(tmp_path):
    store = _store_with_transcript(tmp_path, WAGE_INCOME, [
        _w2("w2-a", 85000.00),
        _i1099("i-a", "1099-INT", "1", 420.50),
        _i1099("n-a", "1099-NEC", "1", 5000.00),  # no transcript block
    ])
    r = V.verify_transcript_reconciliation(store, 2024)
    assert r["passed"] is False
    assert r["n_docs_only_payers"] == 1
    assert r["docs_only_ids"] == ["n-a"]
    _pii_free(r)


def test_reconciliation_skips_unvalidated(tmp_path):
    store = _store_with_transcript(tmp_path, WAGE_INCOME, [
        _w2("w2-a", 85000.00),
        _i1099("i-a", "1099-INT", "1", 420.50, status="transcribed"),
    ])
    r = V.verify_transcript_reconciliation(store, 2024)
    # unvalidated 1099-INT skipped: its transcript payer is transcript-only
    assert r["n_matched_payers"] == 1
    assert r["n_transcript_only_payers"] == 1
    assert r["passed"] is False  # asymmetry still surfaces
    _pii_free(r)


def test_reconciliation_no_transcript(tmp_path):
    store = _store_with(tmp_path, [_w2("w2-a", 85000.00)])
    r = V.verify_transcript_reconciliation(store, 2024)
    assert r["passed"] is False
    assert r["n_matched_payers"] == 0
    assert r["n_docs_only_payers"] == 1
    _pii_free(r)


# -- verify_carryforward_ready ---------------------------------------

def test_carryforward_ready_refusal_as_check(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short", status="transcribed"),
    ])
    r = V.verify_carryforward_ready(store, 2024)
    assert r["passed"] is False
    assert "not yet validated" in r["reason"]
    _pii_free(r)


def test_carryforward_ready_ok(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short", status="validated"),
    ])
    r = V.verify_carryforward_ready(store, 2024)
    assert r == {"passed": True, "reason": "ready"}
    _pii_free(r)


# -- R3 guard blockers surface through carryforward_ready ---------------

def test_carryforward_ready_reports_guard_blockers(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short", status="validated"),
        _doc("u1", 2024, "UNKNOWN", {}, "validated"),
    ])
    r = V.verify_carryforward_ready(store, 2024)
    assert r["passed"] is False
    assert "u1(unknown_form)" in r["reason"]
    _pii_free(r)


def test_carryforward_ready_reports_missing_year_and_zero_lots(tmp_path):
    store = _store_with(tmp_path, [
        _doc("ny1", None, "W-2", {}, "validated"),
        _doc("z1", 2024, "1099-B", {}, "validated"),
    ])
    r = V.verify_carryforward_ready(store, 2024)
    assert r["passed"] is False
    assert "ny1(missing_year)" in r["reason"]
    assert "z1(zero_lots)" in r["reason"]
    _pii_free(r)


def test_carryforward_ready_exclusion_clears_blocker(tmp_path):
    from taxprep import exclusions as X
    store = _store_with(tmp_path, [
        _doc("u1", 2024, "UNKNOWN", {}, "validated"),
    ])
    r = V.verify_carryforward_ready(store, 2024)
    assert r["passed"] is False
    X.record_exclusion(store.data_dir, "u1", "operator: superseded by re-scan")
    r2 = V.verify_carryforward_ready(store, 2024)
    assert r2 == {"passed": True, "reason": "ready"}
    _pii_free(r2)


def test_verify_all_carryforward_ready_carries_blockers(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "1000.00", "1500.00", "short", status="validated"),
        _doc("u1", 2023, "UNKNOWN", {}, "validated"),  # other year: still blocks
    ])
    r = V.verify_all(store)
    assert r["passed"] is False
    cr = r["checks"]["carryforward_ready:2024"]
    assert cr["passed"] is False
    assert "u1(unknown_form)" in cr["reason"]
    _pii_free(r)


# -- verify_all --------------------------------------------------------

def test_verify_all_year_scoping(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w1", 2024, "W-2", {"1": _field(1)}, "validated"),
        _doc("w2", 2023, "W-2", {"1": _field(1)}, "transcribed"),
    ])
    r = V.verify_all(store, 2024)
    assert set(r["checks"]) == {"completeness", "no_silent_drops",
                                "validation_gate", "lot_integrity",
                                "summary_reconciliation",
                                "transcript_reconciliation",
                                "carryforward_ready",
                                "extraction_yield",
                                "roa_corroboration",
                                "source_integrity"}  # R15
    assert r["checks"]["extraction_yield"]["checks"]["zero_yield"]["passed"] is True
    assert r["checks"]["roa_corroboration"]["applicable"] is True  # R17 landed
    _pii_free(r["checks"]["extraction_yield"])
    _pii_free(r["checks"]["roa_corroboration"])
    assert r["checks"]["validation_gate"]["passed"] is True
    assert r["passed"] is False  # reconciliation: no transcript doc
    _pii_free(r)

    r2 = V.verify_all(store)  # all years present
    assert "validation_gate:2024" in r2["checks"]
    assert "validation_gate:2023" in r2["checks"]
    assert r2["checks"]["validation_gate:2023"]["passed"] is False
    _pii_free(r2)
    json.dumps(r2)  # fully JSON-serializable

# -- R18: extraction-yield verification (all fixtures synthetic) -------

from taxprep import transcript as _T


def _ocr(store, doc, text):
    store.save_ocr(doc.doc_id, text)
    store.upsert(doc)
    return doc


def test_zero_yield_fails_on_text_without_fields(tmp_path):
    store = _store_with(tmp_path, [])
    d = _doc("z1", 2024, "W-2", {}, "transcribed")
    _ocr(store, d, "synthetic form filler line\n" * 50)  # > 200 chars
    r = V.verify_zero_yield(store, 2024)
    assert r["passed"] is False
    assert r["failed_ids"] == ["z1"]
    assert r["min_text_chars"] == 200
    _pii_free(r)


def test_zero_yield_passes(tmp_path):
    store = _store_with(tmp_path, [])
    ok = _doc("ok", 2024, "W-2", {"1": _field(1)}, "transcribed")
    _ocr(store, ok, "synthetic form filler line\n" * 50)
    short = _doc("short", 2024, "W-2", {}, "transcribed")
    _ocr(store, short, "tiny")  # below the char threshold: not a failure
    r = V.verify_zero_yield(store, 2024)
    assert r["passed"] is True
    assert r["failed_ids"] == [] and r["n_checked"] == 2
    _pii_free(r)


WAGE_WITH_HEADERS = """WAGE AND INCOME TRANSCRIPT
For Tax Year 2024
Note: This transcript is provided for your information only.
This transcript shows income reported to the IRS for the tax year.
Taxpayer: SYNTHETIC PERSON 000-00-0001
Payer: ACME CORPORATION 12-3456789
Form W-2
Box 1 Wages: $85,000.00
"""


def test_parse_coverage_headers_do_not_count(tmp_path):
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("t1", 2024, "WAGE_INCOME_TRANSCRIPT", {},
                     "needs_review"), WAGE_WITH_HEADERS)
    r = V.verify_parse_coverage(store, 2024)
    assert r["passed"] is True
    assert len(r["docs"]) == 1
    assert r["docs"][0]["coverage"] == 1.0
    assert r["low_ids"] == [] and r["unassessable"] == []
    _pii_free(r)


def test_parse_coverage_fails_on_genuine_unparsed(tmp_path):
    store = _store_with(tmp_path, [])
    text = WAGE_WITH_HEADERS + "Some unrecognized content line @@@\n"
    _ocr(store, _doc("t1", 2024, "WAGE_INCOME_TRANSCRIPT", {},
                     "transcribed"), text)
    r = V.verify_parse_coverage(store, 2024)
    assert r["passed"] is False
    assert r["low_ids"] == ["t1"]
    assert r["docs"][0]["coverage"] == 0.75  # 3 of 4 content lines parsed
    assert r["threshold"] == 0.8
    _pii_free(r)


def test_expected_coverage_w2_boxes(tmp_path):
    store = _store_with(tmp_path, [])
    thin = _doc("thin", 2024, "W-2", {"1": _field(1)}, "transcribed")
    store.upsert(thin)
    r = V.verify_expected_coverage(store, 2024)
    assert r["passed"] is False
    assert len(r["low"]) == 1
    assert r["low"][0]["doc_id"] == "thin"
    assert r["low"][0]["coverage"] == pytest.approx(1 / 6)
    assert r["low"][0]["n_expected"] == 6 and r["low"][0]["n_present"] == 1
    _pii_free(r)

    full = _doc("full", 2024, "W-2",
                {b: _field(1) for b in ("1", "2", "3", "4", "5", "6")},
                "transcribed")
    store.upsert(full)
    r2 = V.verify_expected_coverage(store, 2024)
    assert r2["passed"] is False  # "thin" still low
    assert r2["n_assessed"] == 2
    assert [e["doc_id"] for e in r2["low"]] == ["thin"]
    _pii_free(r2)


def test_expected_coverage_return_transcript_core_lines(tmp_path):
    full_text = """TAX RETURN TRANSCRIPT
For Tax Year 2024
Adjusted Gross Income: $85,420.00
Taxable Income: $62,000.00
Total Tax: $9,800.00
Federal Income Tax Withheld: $11,200.00
Refund: $1,400.00
Amount Owed: $0.00
"""
    thin_text = """TAX RETURN TRANSCRIPT
For Tax Year 2024
Adjusted Gross Income: $85,420.00
"""
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("rt-full", 2024, "RETURN_TRANSCRIPT", {},
                     "transcribed"), full_text)
    _ocr(store, _doc("rt-thin", 2024, "RETURN_TRANSCRIPT", {},
                     "transcribed"), thin_text)
    r = V.verify_expected_coverage(store, 2024)
    assert r["passed"] is False
    assert [e["doc_id"] for e in r["low"]] == ["rt-thin"]
    thin = r["low"][0]
    assert thin["coverage"] == pytest.approx(1 / 6)
    assert thin["n_expected"] == 6 and thin["n_present"] == 1
    _pii_free(r)


def test_expected_coverage_wage_transcript_needs_payer(tmp_path):
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("t1", 2024, "WAGE_INCOME_TRANSCRIPT", {},
                     "transcribed"),
         "WAGE AND INCOME TRANSCRIPT\nFor Tax Year 2024\n")
    r = V.verify_expected_coverage(store, 2024)
    assert r["passed"] is False
    assert r["low"][0]["coverage"] == 0.0
    _pii_free(r)


def test_type_hint_mismatch_flags(tmp_path):
    store = _store_with(tmp_path, [])
    d = Document(doc_id="m1", tax_year=2024, form_type="1099-INT",
                  source_path="w2_acme_2024.pdf",
                  ocr_text_ref="ocr/m1.txt",
                  fields={"1": _field(1)}, status="transcribed")
    store.upsert(d)
    r = V.verify_type_hint_mismatch(store, 2024)
    assert r["passed"] is False
    assert r["mismatched"] == [{"doc_id": "m1", "hint": "W-2",
                               "form_type": "1099-INT"}]
    _pii_free(r)
    # never auto-reclassifies: the stored doc is untouched
    assert store.get("m1").form_type == "1099-INT"


def test_type_hint_mismatch_passes(tmp_path):
    store = _store_with(tmp_path, [])
    agree = Document(doc_id="a1", tax_year=2024, form_type="W-2",
                      source_path="w2_acme_2024.pdf",
                      ocr_text_ref="ocr/a1.txt",
                      fields={"1": _field(1)}, status="transcribed")
    nohint = Document(doc_id="n1", tax_year=2024, form_type="W-2",
                       source_path="scan_0042.pdf",
                       ocr_text_ref="ocr/n1.txt",
                       fields={"1": _field(1)}, status="transcribed")
    ambig = Document(doc_id="x1", tax_year=2024, form_type="W-2",
                      source_path="w2_1099int_combined.pdf",
                      ocr_text_ref="ocr/x1.txt",
                      fields={"1": _field(1)}, status="transcribed")
    for d in (agree, nohint, ambig):
        store.upsert(d)
    r = V.verify_type_hint_mismatch(store, 2024)
    assert r["passed"] is True
    assert r["mismatched"] == []
    assert r["n_no_hint"] == 2  # scan_0042 + the ambiguous filename
    _pii_free(r)


def _w2_pair(doc_id, ein, name, text, year=2024):
    return _doc(doc_id, year, "W-2",
                {"1": _field(1), "employer_ein": _field(ein),
                 "employer_name": _field(name)}, "transcribed"), text


def test_cross_doc_duplicate_candidate(tmp_path):
    store = _store_with(tmp_path, [])
    text = ("SYNTHETIC W-2 ACME CORPORATION 12-3456789 Box 1 wages\n" * 20)
    d1, t1 = _w2_pair("w2a", "12-3456789", "ACME CORPORATION", text)
    d2, t2 = _w2_pair("w2b", "12-3456789", "ACME CORPORATION", text)
    _ocr(store, d1, t1)
    _ocr(store, d2, t2)
    r = V.verify_cross_doc(store, 2024)
    assert r["passed"] is False
    assert r["candidates"] == [{"doc_ids": ["w2a", "w2b"]}]
    assert r["n_pairs_checked"] == 1
    _pii_free(r)


def test_cross_doc_no_candidate_when_content_differs(tmp_path):
    store = _store_with(tmp_path, [])
    d1, t1 = _w2_pair("w2a", "12-3456789", "ACME CORPORATION",
                      "FIRST SCAN synthetic w2 content\n" * 20)
    d2, t2 = _w2_pair("w2b", "12-3456789", "ACME CORPORATION",
                      "SECOND SCAN different synthetic w2 content\n" * 20)
    _ocr(store, d1, t1)
    _ocr(store, d2, t2)
    r = V.verify_cross_doc(store, 2024)
    assert r["passed"] is True
    assert r["candidates"] == []
    assert r["n_pairs_checked"] == 1
    _pii_free(r)


def test_extraction_yield_wires_into_verify_all(tmp_path):
    store = _store_with(tmp_path, [])
    d = _doc("z1", 2024, "W-2", {}, "transcribed")
    _ocr(store, d, "synthetic form filler line\n" * 50)
    r = V.verify_all(store, 2024)
    ey = r["checks"]["extraction_yield"]
    assert ey["passed"] is False
    assert ey["checks"]["zero_yield"]["failed_ids"] == ["z1"]
    for sub in ey["checks"].values():
        _pii_free(sub)
    _pii_free(ey)


# -- Record-of-Account corroboration (R17-adjacent) --------------------

def test_roa_corroboration_arms_when_parsers_present(tmp_path):
    # R17 landed: the parsers exist, so the check arms itself. No
    # standalone transcripts here, so both sections skip cleanly.
    from taxprep import transcript as T
    assert hasattr(T, "parse_record_of_account")
    assert hasattr(T, "parse_account_transcript")
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("roa1", 2024, "RECORD_OF_ACCOUNT", {},
                     "transcribed"), "synthetic roa text")
    r = V.verify_roa_corroboration(store, 2024)
    assert r["applicable"] is True
    assert r["passed"] is True
    assert r["n_roa"] == 1
    assert r["n_conflicts"] == 0
    assert all(s["reason_code"] == "no_standalone" for s in r["skipped"])
    _pii_free(r)


def test_roa_section_conflicts_comparator():
    # comparator only, on documented-shape dicts -- no parsers involved
    roa = {"lines": {"agi": 85420.0, "total_tax": 12340.0,
                     "withholding": 11200.0},
           "transactions": [{"code": "150", "date": "04/15/2025",
                             "amount": 12340.0}]}
    standalone = {"lines": {"agi": 85420.0, "total_tax": 12341.0},
                  "transactions": [{"code": "150", "date": "04/15/2025",
                                    "amount": 12340.0},
                                   {"code": "766", "date": "04/15/2025",
                                    "amount": 1400.0}]}
    c = V._roa_section_conflicts("return", roa, standalone)
    assert {"section": "return", "key": "total_tax",
            "conflict": "value_mismatch"} in c
    assert {"section": "return", "key": "withholding",
            "conflict": "roa_only"} in c
    assert {"section": "return", "key": "tc_766",
            "conflict": "standalone_only"} in c
    assert len(c) == 3  # agi agrees, tc_150 agrees: no entries
    # no values anywhere in the conflict entries
    for e in c:
        assert set(e) == {"section", "key", "conflict"}
    _pii_free(c)


def test_roa_section_conflicts_all_agree(tmp_path):
    section = {"lines": {"agi": 85420.0},
               "transactions": [{"code": "150", "date": "04/15/2025",
                                 "amount": 12340.0}]}
    assert V._roa_section_conflicts("return", section, section) == []


@pytest.mark.skipif(not hasattr(_T, "parse_record_of_account"),
                    reason="R17 parsers not yet in tree")
def test_roa_corroboration_arms_when_parsers_land(tmp_path):
    # integration: the check activates once the R17 workstream adds the
    # parsers; no standalone transcripts -> informational skip only.
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("roa1", 2024, "RECORD_OF_ACCOUNT", {},
                     "transcribed"), "synthetic roa text")
    r = V.verify_roa_corroboration(store, 2024)
    assert r["applicable"] is True
    assert r["n_roa"] == 1
    _pii_free(r)


# X3: the ROA's account section must actually populate, or
# roa_corroboration compares nothing on the account side. Synthetic ROA
# with no clean account title (the X3 shape) plus a same-year standalone
# Account Transcript carrying a different balance: the disagreement must
# surface as a needs_human conflict, metadata-only.
_ROA_X3_CORRO = """\
RECORD OF ACCOUNT
Tax Year: 2024
TAX RETURN TRANSCRIPT
Adjusted Gross Income: $85,420.00
Account Balance: $0.00
Accrued Interest: $5.00 as of 09/22/2025
150 Tax return filed 20241205 04-15-2025 $12,340.00
846 Refund issued 20243207 10-05-2025 $0.00
"""

_STANDALONE_ACCT_X3 = """\
TAX ACCOUNT TRANSCRIPT
Tax Year: 2024
Account Balance: $100.00
Accrued Interest: $5.00 as of 09/22/2025
150 Tax return filed 20241205 04-15-2025 $12,340.00
846 Refund issued 20243207 10-05-2025 $0.00
"""


def test_x3_roa_corroboration_evaluates_account_side(tmp_path):
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("roa1", 2024, "RECORD_OF_ACCOUNT", {},
                     "transcribed"), _ROA_X3_CORRO)
    _ocr(store, _doc("acct1", 2024, "ACCOUNT_TRANSCRIPT", {},
                     "transcribed"), _STANDALONE_ACCT_X3)
    r = V.verify_roa_corroboration(store, 2024)
    assert r["applicable"] is True
    assert r["n_roa"] == 1
    # the account side is compared now (X3 populated it): the balance
    # disagreement is raised to the Operator, never auto-resolved
    assert r["n_conflicts"] >= 1
    assert r["passed"] is False
    acct_conflicts = [c for c in r["conflicts"] if c["section"] == "account"]
    assert acct_conflicts, r["conflicts"]
    assert any(c["key"] == "account_balance"
               and c["conflict"] == "value_mismatch"
               for c in acct_conflicts)
    _pii_free(r)


def test_x3_roa_corroboration_agreeing_account_side(tmp_path):
    # identical account content -> no conflicts, check passes
    store = _store_with(tmp_path, [])
    _ocr(store, _doc("roa1", 2024, "RECORD_OF_ACCOUNT", {},
                     "transcribed"), _ROA_X3_CORRO)
    _ocr(store, _doc("acct1", 2024, "ACCOUNT_TRANSCRIPT", {},
                     "transcribed"), _STANDALONE_ACCT_X3.replace(
                         "Account Balance: $100.00",
                         "Account Balance: $0.00"))
    r = V.verify_roa_corroboration(store, 2024)
    assert r["applicable"] is True
    assert r["n_conflicts"] == 0
    assert r["passed"] is True
    _pii_free(r)
