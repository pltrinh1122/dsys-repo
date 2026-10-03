"""Tests for relevance triage + gap analysis. All fixtures synthetic."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from taxprep import gaps as G
from taxprep import relevance as R
from taxprep import verify as V
from taxprep.models import Document
from taxprep.store import DocumentStore

SCOPE = [2023, 2024, 2025, 2026]


def _doc(doc_id, year, form, status="transcribed"):
    return Document(doc_id=doc_id, tax_year=year, form_type=form,
                    source_path=f"{doc_id}.pdf", ocr_text_ref=f"ocr/{doc_id}.txt",
                    fields={}, status=status)


@pytest.fixture()
def store(tmp_path):
    s = DocumentStore(tmp_path / "data")
    return s


def _with_ocr(store, doc, text):
    store.save_ocr(doc.doc_id, text)
    store.upsert(doc)
    return doc


# -- verdict rules -------------------------------------------------------


def test_in_scope_is_relevant(store):
    _with_ocr(store, _doc("w1", 2024, "W-2"), "w2 text one")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["w1"] == {"verdict": "relevant", "reasons": ["in_scope"]}


def test_year_out_of_scope_is_irrelevant(store):
    _with_ocr(store, _doc("w-old", 2021, "W-2"), "old w2")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["w-old"]["verdict"] == "irrelevant"
    assert v["w-old"]["reasons"] == ["year_out_of_scope"]


def test_duplicate_ocr_is_irrelevant_keep_first(store):
    _with_ocr(store, _doc("b-scan", 2024, "1099-B"), "same scan text")
    _with_ocr(store, _doc("a-scan", 2024, "1099-B"), "same scan text")
    v = R.assess_relevance(store, SCOPE, persist=False)
    # lexicographically first doc_id is kept
    assert v["a-scan"]["verdict"] == "relevant"
    assert v["b-scan"]["verdict"] == "irrelevant"
    assert v["b-scan"]["reasons"] == ["duplicate_of:a-scan"]


def test_missing_ocr_is_never_duplicate(store):
    # no OCR saved for either -> cannot prove duplication -> relevant
    store.upsert(_doc("x1", 2024, "W-2"))
    store.upsert(_doc("x2", 2024, "W-2"))
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["x1"]["verdict"] == "relevant"
    assert v["x2"]["verdict"] == "relevant"


def test_unknown_form_needs_human_never_dropped(store):
    _with_ocr(store, _doc("myst", 2024, "UNKNOWN"), "mystery text")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["myst"]["verdict"] == "needs_human"
    assert v["myst"]["reasons"] == ["unclassified"]


def test_null_year_in_scope_is_relevant(store):
    _with_ocr(store, _doc("ny", None, "W-2"), "no year text")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["ny"]["verdict"] == "relevant"  # completeness check flags it separately


def test_persist_and_roundtrip(store):
    _with_ocr(store, _doc("w1", 2024, "W-2"), "text a")
    _with_ocr(store, _doc("w0", 2021, "W-2"), "text b")
    R.assess_relevance(store, SCOPE, persist=True)
    reloaded = DocumentStore(store.data_dir)
    assert reloaded.get("w1").relevance == "relevant"
    assert reloaded.get("w0").relevance == "irrelevant"


def test_summarize_shape(store):
    _with_ocr(store, _doc("w1", 2024, "W-2"), "text a")
    _with_ocr(store, _doc("u1", 2024, "UNKNOWN"), "text b")
    s = R.summarize(R.assess_relevance(store, SCOPE, persist=False))
    assert s["n_docs"] == 2
    assert s["counts"] == {"relevant": 1, "irrelevant": 0, "needs_human": 1}
    assert s["relevant_ids"] == ["w1"]
    assert s["needs_human"][0]["doc_id"] == "u1"
    json.dumps(s)


# -- verify_no_silent_drops ----------------------------------------------


def test_no_silent_drops_fails_when_unassessed(store):
    store.upsert(_doc("w1", 2024, "W-2"))
    r = V.verify_no_silent_drops(store)
    assert r["passed"] is False
    assert r["unassessed_ids"] == ["w1"]
    assert r["n_unassessed"] == 1


def test_no_silent_drops_passes_after_triage(store):
    _with_ocr(store, _doc("w1", 2024, "W-2"), "text a")
    _with_ocr(store, _doc("u1", 2024, "UNKNOWN"), "text b")
    R.assess_relevance(store, SCOPE, persist=True)
    r = V.verify_no_silent_drops(store)
    assert r["passed"] is True
    assert r["unassessed_ids"] == []


def test_no_silent_drops_wired_into_verify_all(store):
    store.upsert(_doc("w1", 2024, "W-2"))
    r = V.verify_all(store, 2024)
    assert "no_silent_drops" in r["checks"]
    assert r["checks"]["no_silent_drops"]["passed"] is False


# -- gaps -----------------------------------------------------------------

WAGE_CLEAN = """WAGE AND INCOME TRANSCRIPT Tax Year 2024
Payer: ACME CORPORATION 12-3456789
Form W-2
Box 1 Wages: $85,000.00
Payer: EXAMPLE BANK 98-7654321
Form 1099-INT
Box 1 Interest: $420.50
"""

RETURN_WITH_SCHED_D = """TAX RETURN TRANSCRIPT
Tax Year: 2024
Filing Status: Single
Adjusted Gross Income: $85,420.00
Schedule D Capital Gains and Losses attached.
"""


def _wage_doc(store, doc_id, year, text, status="transcribed"):
    d = _doc(doc_id, year, "WAGE_INCOME_TRANSCRIPT", status=status)
    return _with_ocr(store, d, text)


def test_gaps_missing_form_detected(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN)
    _with_ocr(store, _doc("w1", 2024, "W-2"), "w2 text")  # 1099-INT missing
    out = G.analyze_gaps(store, SCOPE, year=2024)
    g = out["2024"]
    assert g["expected_forms"] == ["1099-INT", "W-2"]
    assert g["missing_forms"] == ["1099-INT"]
    assert g["n_transcript_payers"] == 2
    assert g["n_document_payers"] == 1
    assert g["has_transcript"] is True
    json.dumps(out)


def test_gaps_all_present(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN)
    _with_ocr(store, _doc("w1", 2024, "W-2"), "w2 text")
    _with_ocr(store, _doc("i1", 2024, "1099-INT"), "int text")
    out = G.analyze_gaps(store, SCOPE, year=2024)
    assert out["2024"]["missing_forms"] == []


def test_gaps_no_transcript_no_false_allclear(store):
    _with_ocr(store, _doc("w1", 2024, "W-2"), "w2 text")
    out = G.analyze_gaps(store, SCOPE, year=2024)
    g = out["2024"]
    assert g["expected_forms"] == []
    assert g["missing_forms"] == []
    assert g["has_transcript"] is False


def test_gaps_schedule_d_expects_1099b(store):
    d = _doc("r1", 2024, "RETURN_TRANSCRIPT")
    _with_ocr(store, d, RETURN_WITH_SCHED_D)
    out = G.analyze_gaps(store, SCOPE, year=2024)
    g = out["2024"]
    assert "1099-B" in g["expected_forms"]
    assert "1099-B" in g["missing_forms"]
    assert g["schedules_seen"] == ["D"]


def test_gaps_report_file_has_payer_detail_but_shape_does_not(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN)
    out = G.analyze_gaps(store, SCOPE, year=2024)
    report = Path(out["report_path"])
    assert report.exists() and report.parent.name == "reports"
    text = report.read_text(encoding="utf-8")
    assert "ACME CORPORATION" in text  # names live in the file only
    assert "MISSING" in text
    # the returned shape carries no names
    shape_text = json.dumps(out)
    assert "ACME CORPORATION" not in shape_text
    assert "EXAMPLE BANK" not in shape_text
    # and no dollar amounts cross the boundary either
    assert not re.search(r"\$\d", shape_text)


def test_gaps_unparsed_transcript_ignored(store):
    # stray line -> unparsed_lines non-empty -> transcript not trusted
    _wage_doc(store, "t1", 2024, WAGE_CLEAN + "random stray line here\n")
    out = G.analyze_gaps(store, SCOPE, year=2024)
    assert out["2024"]["has_transcript"] is False
    assert out["2024"]["expected_forms"] == []


def test_gaps_multi_year_keys(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN)
    out = G.analyze_gaps(store, SCOPE)
    assert set(out) == {"2023", "2024", "2025", "2026", "report_path"}
    assert out["2023"]["has_transcript"] is False
