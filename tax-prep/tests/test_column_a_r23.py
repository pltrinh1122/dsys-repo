"""Tests for taxprep.column_a R23 stream D.

The column-A builder reads canonical keys from either R23 source
(machine pair capture or Operator CSV) with PENDING_VALIDATION distinct
from MISSING (CA1). All fixtures synthetic; synthetic store/docs only.
Blind-orchestrator contract holds: no PII, no values leave the store.
Deterministic: no wall-clock assertions.
"""

from __future__ import annotations

import hashlib

import pytest

from taxprep import column_a, duplicates
from taxprep.models import Document
from taxprep.operator_csv import ingest_operator_csv
from taxprep.store import DocumentStore


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "data")


def _pair(value, label="Adjusted gross income", page=1):
    """Stream-A machine pair field shape (bare normalized key)."""
    return {
        "value": value,
        "confidence": "medium",
        "raw_text": f"{label} {value}".strip(),
        "provenance": {
            "page": page,
            "bbox_pdf": [10.0, 20.0, 500.0, 32.0],
            "bbox_source": "pdfplumber",
        },
    }


def _op(value, printed="Adjusted gross income", page=1):
    """Stream-B operator-CSV field shape (on its own OPERATOR_CSV doc)."""
    return {
        "value": value,
        "confidence": "medium",
        "raw_text": f"{printed}: {value}",
        "text_source": "operator-csv",
        "page": page,
        "printed_label": printed,
    }


def _ingest_validated_csv(store, pdf_doc_id, csv_text, filename):
    """Ingest an Operator CSV and mark the CSV doc validated.

    Returns the CSV doc_id. The PDF doc must already exist (its stem
    must match the CSV filename's stem).
    """
    res = ingest_operator_csv(store, pdf_doc_id, csv_text, filename)
    assert "doc_id" in res, res
    csv_doc = store.get(res["doc_id"])
    csv_doc.status = "validated"
    store.upsert(csv_doc)
    return res["doc_id"]


def _tfield(value):
    return {"value": value, "confidence": "high",
            "raw_text": f"legacy {value}"}


def _doc(doc_id, year, form, fields=None, status="validated", stem=None):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form,
        source_path=f"/synthetic/{stem or doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields or {},
        status=status,
    )


def _by_line(result):
    return {e["line"]: e for e in result["lines"]}


def _machine_operator_cid(label):
    return hashlib.sha256(
        f"corroboration:{label}:machine,operator_csv".encode("utf-8")
    ).hexdigest()[:32]


# -- R23 source resolution ------------------------------------------------


def test_pair_sourced_line_present_with_provenance(store):
    store.upsert(_doc("rt23p", 2023, "RETURN_TRANSCRIPT", {
        "ADJUSTED GROSS INCOME": _pair("45000.00"),
    }))
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "45000.00"          # Decimal-safe string
    assert l1["source"] == "return_transcript_pairs"
    assert l1["source_doc_id"] == "rt23p"
    assert l1["conflict_id"] is None
    prov = l1["provenance"]
    assert prov["confidence"] == "medium"
    assert prov["raw_text"] == "Adjusted gross income 45000.00"
    assert prov["geometry"]["bbox_source"] == "pdfplumber"
    assert prov["geometry"]["page"] == 1
    assert prov["evidence_ref"] == {
        "doc_id": "rt23p", "field": "ADJUSTED GROSS INCOME"}


def test_pair_collision_form_resolves(store):
    # Stream-A collision form: the bare key was taken by a legacy field,
    # so the pair landed at pair:<label>.
    store.upsert(_doc("rt23c", 2023, "RETURN_TRANSCRIPT", {
        "pair:ADJUSTED GROSS INCOME": _pair("45100.00"),
    }))
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "45100.00"
    assert l1["source"] == "return_transcript_pairs"
    assert l1["provenance"]["evidence_ref"] == {
        "doc_id": "rt23c", "field": "pair:ADJUSTED GROSS INCOME"}


def test_pair_source_label_follows_form_type(store):
    store.upsert(_doc("roa23p", 2023, "RECORD_OF_ACCOUNT", {
        "TOTAL TAX": _pair("2345.00", label="Total Tax"),
    }))
    l11 = _by_line(column_a.build_column_a(store, 2023))["L11"]
    assert l11["status"] == "present"
    assert l11["value"] == "2345.00"
    assert l11["source"] == "record_of_account_pairs"
    assert l11["source_doc_id"] == "roa23p"


def test_operator_csv_sourced_line_present(store):
    store.upsert(_doc("rt23o", 2023, "RETURN_TRANSCRIPT", {},
                      stem="rt23o"))
    csv_id = _ingest_validated_csv(
        store, "rt23o",
        "label,value\n@page 1\nAdjusted gross income,46000.00\n",
        "rt23o.csv")
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "46000.00"
    assert l1["source"] == "operator_csv"
    assert l1["source_doc_id"] == csv_id
    assert l1["conflict_id"] is None
    prov = l1["provenance"]
    assert prov["confidence"] == "medium"
    assert prov["evidence_ref"] == {
        "doc_id": csv_id, "field": "ADJUSTED GROSS INCOME"}


def test_machine_operator_agreement_one_entry(store):
    store.upsert(_doc("rt23a", 2023, "RETURN_TRANSCRIPT", {
        "ADJUSTED GROSS INCOME": _pair("45000.00"),
    }, stem="rt23a"))
    _ingest_validated_csv(
        store, "rt23a",
        "label,value\nAdjusted gross income,45000.00\n",
        "rt23a.csv")
    result = column_a.build_column_a(store, 2023)
    l1 = _by_line(result)["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "45000.00"
    assert l1["source"] == "operator_csv"
    assert l1["conflict_id"] is None
    assert duplicates.open_conflicts(store) == {}
    machine_seen = [s for s in l1["also_seen"]
                    if s["source"] == "return_transcript_pairs"]
    assert len(machine_seen) == 1
    assert machine_seen[0]["value"] == "45000.00"
    assert machine_seen[0]["agrees"] is True


def test_machine_operator_disagreement_operator_wins(store):
    # The ingest-raised corroboration conflict is surfaced on the entry;
    # the builder raises nothing itself (read-model).
    store.upsert(_doc("rt23d", 2023, "RETURN_TRANSCRIPT", {
        "ADJUSTED GROSS INCOME": _pair("45000.00"),
    }, stem="rt23d"))
    res = ingest_operator_csv(
        store, "rt23d",
        "label,value\n@page 1\nAdjusted gross income,46000.00\n",
        "rt23d.csv")
    assert res["n_conflicts"] == 1
    # validate the CSV doc so its value is usable
    csv_doc = store.get(res["doc_id"])
    csv_doc.status = "validated"
    store.upsert(csv_doc)
    expected_cid = _machine_operator_cid("ADJUSTED GROSS INCOME")

    result = column_a.build_column_a(store, 2023)
    l1 = _by_line(result)["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "46000.00"      # Operator's final adjustment wins
    assert l1["source"] == "operator_csv"
    assert l1["source_doc_id"] == res["doc_id"]
    assert l1["conflict_id"] == expected_cid
    assert result["conflicts_raised"] == []   # no new raise by the builder
    assert duplicates.open_conflicts(store) == {"corroboration": 1}
    machine_seen = [s for s in l1["also_seen"]
                    if s["source"] == "return_transcript_pairs"]
    assert len(machine_seen) == 1
    assert machine_seen[0]["value"] == "45000.00"
    assert machine_seen[0]["agrees"] is False


def test_operator_beats_legacy_transcript_value(store):
    # Operator CSV wins over the legacy transcript parse for the line;
    # the legacy value is surfaced (not silently resolved) in also_seen.
    store.upsert(_doc("rt23m", 2023, "RETURN_TRANSCRIPT", {
        "agi": _tfield("44000.00"),
    }, stem="rt23m"))
    csv_id = _ingest_validated_csv(
        store, "rt23m",
        "label,value\nAdjusted gross income,46000.00\n",
        "rt23m.csv")
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "46000.00"
    assert l1["source"] == "operator_csv"
    assert l1["source_doc_id"] == csv_id
    legacy_seen = [s for s in l1["also_seen"]
                   if s["source"] == "return_transcript"]
    assert len(legacy_seen) == 1
    assert legacy_seen[0]["value"] == "44000.00"
    assert legacy_seen[0]["agrees"] is False


# -- CA1: PENDING_VALIDATION distinct from MISSING ---------------------------


def test_pending_validation_vs_missing(store):
    store.upsert(_doc("rt23v", 2023, "RETURN_TRANSCRIPT", {
        "ADJUSTED GROSS INCOME": _pair("45000.00"),
    }))
    store.upsert(_doc("rt23u", 2023, "RETURN_TRANSCRIPT", {
        "FEDERAL INCOME TAX WITHHELD": _pair(
            "5000.00", label="Federal income tax withheld"),
    }, status="transcribed"))
    by_line = _by_line(column_a.build_column_a(store, 2023))

    l12 = by_line["L12"]
    assert l12["status"] == "PENDING_VALIDATION"
    assert l12["value"] is None
    assert l12["source"] is None
    assert l12["provenance"] is None
    assert l12["source_doc_id"] == "rt23u"
    assert l12["pending_doc_ids"] == ["rt23u"]

    # Validated present line is unaffected.
    assert by_line["L1"]["status"] == "present"

    # A line with no keys and no candidates stays MISSING-first-class.
    l6 = by_line["L6"]
    assert l6["status"] == "MISSING"
    assert l6["value"] is None and l6["source"] is None
    assert "pending_doc_ids" not in l6


def test_pending_lists_all_candidate_docs_in_order(store):
    store.upsert(_doc("rt23b", 2023, "RETURN_TRANSCRIPT", {
        "FEDERAL INCOME TAX WITHHELD": _pair(
            "5000.00", label="Federal income tax withheld"),
    }, status="needs_review"))
    store.upsert(_doc("rt23a", 2023, "RETURN_TRANSCRIPT", {
        "WITHHOLDING": _pair("5100.00", label="Withholding"),
    }, status="transcribed"))
    l12 = _by_line(column_a.build_column_a(store, 2023))["L12"]
    assert l12["status"] == "PENDING_VALIDATION"
    assert l12["pending_doc_ids"] == ["rt23a", "rt23b"]
    assert l12["source_doc_id"] == "rt23a"


def test_pending_from_operator_csv_on_unvalidated_doc(store):
    # Operator decision: CSV-derived fields need review-UI validation
    # before gold. An unvalidated CSV doc makes the line
    # PENDING_VALIDATION (not present), with the CSV doc as the
    # pending candidate.
    store.upsert(_doc("rt23u", 2023, "RETURN_TRANSCRIPT", {},
                      stem="rt23u"))
    res = ingest_operator_csv(
        store, "rt23u",
        "label,value\nAdjusted gross income,45000.00\n",
        "rt23u.csv")
    assert res["n_conflicts"] == 0  # no machine value to disagree with
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "PENDING_VALIDATION"
    assert l1["pending_doc_ids"] == [res["doc_id"]]
    assert l1["source_doc_id"] == res["doc_id"]


def test_pending_from_unvalidated_csv_on_validated_transcript(store):
    # Validated transcript, unvalidated CSV: the machine value is absent,
    # the operator value is pending -- the line is PENDING_VALIDATION
    # pointing at the CSV doc.
    store.upsert(_doc("rt23v", 2023, "RETURN_TRANSCRIPT", {},
                      stem="rt23v"))
    res = ingest_operator_csv(
        store, "rt23v",
        "label,value\nAdjusted gross income,45000.00\n",
        "rt23v.csv")
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "PENDING_VALIDATION"
    assert l1["pending_doc_ids"] == [res["doc_id"]]


def test_pending_ignores_excluded_and_other_years(store):
    store.upsert(_doc("rt23x", 2023, "RETURN_TRANSCRIPT", {
        "FEDERAL INCOME TAX WITHHELD": _pair(
            "5000.00", label="Federal income tax withheld"),
    }, status="excluded"))
    store.upsert(_doc("rt24u", 2024, "RETURN_TRANSCRIPT", {
        "FEDERAL INCOME TAX WITHHELD": _pair(
            "5000.00", label="Federal income tax withheld"),
    }, status="transcribed"))
    l12 = _by_line(column_a.build_column_a(store, 2023))["L12"]
    assert l12["status"] == "MISSING"


def test_unvalidated_legacy_key_stays_missing(store):
    # CA1 pending is scoped to R23 machine/operator capture keys; legacy
    # parser keys on unvalidated docs keep MISSING-first-class behavior.
    store.upsert(_doc("rt23u", 2023, "RETURN_TRANSCRIPT",
                      {"agi": _tfield("100.00")}, status="transcribed"))
    l1 = _by_line(column_a.build_column_a(store, 2023))["L1"]
    assert l1["status"] == "MISSING"


def test_coverage_counts_include_n_pending_validation(store):
    store.upsert(_doc("rt23v", 2023, "RETURN_TRANSCRIPT", {
        "ADJUSTED GROSS INCOME": _pair("45000.00"),
    }))
    store.upsert(_doc("rt23u", 2023, "RETURN_TRANSCRIPT", {
        "FEDERAL INCOME TAX WITHHELD": _pair(
            "5000.00", label="Federal income tax withheld"),
    }, status="transcribed"))
    cov = column_a.build_column_a(store, 2023)["coverage"]
    assert cov["n_present"] == 1
    assert cov["n_pending_validation"] == 1
    assert cov["n_missing"] == cov["n_lines"] - 2
    assert cov["n_conflict"] == 0
    assert cov["n_source_docs"] == 1   # validated docs only


# -- legacy behavior unchanged -------------------------------------------------


def test_legacy_lookup_behavior_unchanged(store):
    store.upsert(_doc("rt23l", 2023, "RETURN_TRANSCRIPT", {
        "agi": _tfield("12345.67"),
        "withholding": _tfield("2000.00"),
    }))
    result = column_a.build_column_a(store, 2023)
    by_line = _by_line(result)

    l1 = by_line["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "12345.67"
    assert l1["source"] == "return_transcript"
    assert l1["source_doc_id"] == "rt23l"
    assert l1["provenance"]["confidence"] == "high"
    assert l1["provenance"]["evidence_ref"] == {
        "doc_id": "rt23l", "field": "agi"}

    l12 = by_line["L12"]
    assert l12["status"] == "present" and l12["value"] == "2000.00"

    for code in ("L2", "L6", "L7", "L10", "L13", "L14", "L15", "L16"):
        e = by_line[code]
        assert e["status"] == "MISSING", code
        assert e["value"] is None and e["source"] is None
        assert e["provenance"] is None
        assert "pending_doc_ids" not in e

    cov = result["coverage"]
    assert cov["n_present"] == 2
    assert cov["n_missing"] == cov["n_lines"] - 2
    assert cov["n_conflict"] == 0
    assert cov["n_pending_validation"] == 0


def test_legacy_2025_corroboration_still_conflicts(store):
    store.upsert(_doc("rt25", 2025, "RETURN_TRANSCRIPT",
                      {"agi": _tfield("51000.00")}))
    store.upsert(_doc("o25", 2025, "1040", {"agi": _tfield("50000.00")}))
    result = column_a.build_column_a(store, 2025)
    l1 = _by_line(result)["L1"]
    assert l1["status"] == "CONFLICT"
    assert l1["value"] is None
    assert l1["conflict_id"]
    assert len(result["conflicts_raised"]) == 1
    assert duplicates.open_conflicts(store) == {"corroboration": 1}
