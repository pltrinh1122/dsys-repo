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


def _b1099(doc_id, year, proceeds, basis, term, status="validated",
           d_acq="01/15/2024", d_sold="06/20/2024"):
    return _doc(
        doc_id, year, "1099-B",
        {
            "1d_proceeds": _field(proceeds),
            "1e_basis": _field(basis),
            "term": _field(term),
            "broker": _field("Synthetic Broker"),
            "date_acquired": _field(d_acq),
            "date_sold": _field(d_sold),
        },
        status=status,
    )


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
    assert set(r) == {"passed", "n_checks", "n_failed", "failed_ids",
                      "failed_by_check"}


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
                                "transcript_reconciliation",
                                "carryforward_ready"}
    assert r["checks"]["validation_gate"]["passed"] is True
    assert r["passed"] is False  # reconciliation: no transcript doc
    _pii_free(r)

    r2 = V.verify_all(store)  # all years present
    assert "validation_gate:2024" in r2["checks"]
    assert "validation_gate:2023" in r2["checks"]
    assert r2["checks"]["validation_gate:2023"]["passed"] is False
    _pii_free(r2)
    json.dumps(r2)  # fully JSON-serializable
