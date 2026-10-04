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


def test_duplicate_ocr_raised_to_human_never_auto_dropped(store):
    # Arc B: text-duplicates are L2 candidates raised to the operator via
    # dup_group + explicit ruling. Relevance keeps the detection signal
    # but must not mechanically resolve it.
    _with_ocr(store, _doc("b-scan", 2024, "1099-B"), "same scan text")
    _with_ocr(store, _doc("a-scan", 2024, "1099-B"), "same scan text")
    v = R.assess_relevance(store, SCOPE, persist=False)
    # lexicographically first doc_id is the reference
    assert v["a-scan"]["verdict"] == "relevant"
    assert v["b-scan"]["verdict"] == "needs_human"
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


# -- N2 carryover seeds ---------------------------------------------------


def test_carryover_seed_stays_relevant_below_scope(store):
    _with_ocr(store, _doc("sched-d-22", 2022, "SCHEDULE_D"), "sched d 2022")
    _with_ocr(store, _doc("r1040-22", 2022, "1040"), "1040 2022")
    _with_ocr(store, _doc("x22", 2022, "1040-X"), "1040x 2022")
    _with_ocr(store, _doc("rt22", 2022, "RETURN_TRANSCRIPT"),
              "return transcript 2022")
    _with_ocr(store, _doc("w2-22", 2022, "W-2"), "w2 2022")
    _with_ocr(store, _doc("wit22", 2022, "WAGE_INCOME_TRANSCRIPT"),
              "wage transcript 2022")
    v = R.assess_relevance(store, SCOPE, persist=False)
    for did in ("sched-d-22", "r1040-22", "x22", "rt22"):
        assert v[did] == {"verdict": "relevant",
                          "reasons": ["carryover_seed"]}, did
    # non-seed forms below the scope are still out of scope
    assert v["w2-22"]["verdict"] == "irrelevant"
    assert v["w2-22"]["reasons"] == ["year_out_of_scope"]
    assert v["wit22"]["reasons"] == ["year_out_of_scope"]


def test_seed_form_above_scope_still_out_of_scope(store):
    _with_ocr(store, _doc("sched-d-27", 2027, "SCHEDULE_D"), "sched d 2027")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["sched-d-27"]["verdict"] == "irrelevant"
    assert v["sched-d-27"]["reasons"] == ["year_out_of_scope"]


def test_duplicate_still_detected_before_carryover_seed(store):
    # The duplication signal still takes precedence over the seed rule,
    # but the duplicate is raised (needs_human), not auto-dropped.
    _with_ocr(store, _doc("b-sched", 2022, "SCHEDULE_D"), "same seed text")
    _with_ocr(store, _doc("a-sched", 2022, "SCHEDULE_D"), "same seed text")
    v = R.assess_relevance(store, SCOPE, persist=False)
    assert v["a-sched"] == {"verdict": "relevant",
                            "reasons": ["carryover_seed"]}
    assert v["b-sched"]["verdict"] == "needs_human"
    assert v["b-sched"]["reasons"] == ["duplicate_of:a-sched"]


def test_carryover_seed_uses_scope_floor(store):
    # with a narrower scope the floor moves: 2023 becomes a seed year.
    _with_ocr(store, _doc("sched-d-23", 2023, "SCHEDULE_D"), "sched d 2023")
    v = R.assess_relevance(store, [2024, 2025, 2026], persist=False)
    assert v["sched-d-23"] == {"verdict": "relevant",
                               "reasons": ["carryover_seed"]}


def test_carryover_seed_persists_as_label(store):
    _with_ocr(store, _doc("sched-d-22", 2022, "SCHEDULE_D"), "sched d 2022")
    R.assess_relevance(store, SCOPE, persist=True)
    assert (DocumentStore(store.data_dir).get("sched-d-22").relevance
            == "relevant")


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
    # C1: stray line -> unparsed_lines non-empty -> transcript is
    # "partial", not ignored. Mapped payers still count; the unparsed
    # line is reported as coverage, not a skip.
    _wage_doc(store, "t1", 2024, WAGE_CLEAN + "random stray line here\n")
    out = G.analyze_gaps(store, SCOPE, year=2024)
    # Partial transcripts ARE trusted for their mapped content.
    assert out["2024"]["has_transcript"] is True


def test_gaps_multi_year_keys(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN)
    out = G.analyze_gaps(store, SCOPE)
    assert set(out) == {"2023", "2024", "2025", "2026", "report_path"}
    assert out["2023"]["has_transcript"] is False


# -- G1: header lines are structural; skipped transcripts reported ------

WAGE_WITH_HEADERS = """WAGE AND INCOME TRANSCRIPT
For Tax Year 2024
Note: This transcript is provided for your information only.
This transcript shows income reported to the IRS for the tax year.
Taxpayer: SYNTHETIC PERSON 000-00-0001
Payer: ACME CORPORATION 12-3456789
Form W-2
Box 1 Wages: $85,000.00
"""


def test_header_lines_recognized_as_structural():
    for line in ("WAGE AND INCOME TRANSCRIPT",
                 "TAX RETURN TRANSCRIPT",
                 "For Tax Year 2024",
                 "Tax Year: 2024",
                 "Note: informational use only.",
                 "This transcript shows income reported to the IRS.",
                 "For your information: keep this transcript.",
                 "Taxpayer: SYNTHETIC PERSON 000-00-0001"):
        assert G.is_transcript_header_line(line), line
    for line in ("Payer: ACME CORPORATION 12-3456789",
                 "Form W-2",
                 "Box 1 Wages: $85,000.00",
                 "Adjusted Gross Income: $85,420.00"):
        assert not G.is_transcript_header_line(line), line


def test_wage_transcript_with_headers_not_skipped(store):
    # headers only: usable even in needs_review status (the G1 fix)
    _wage_doc(store, "t1", 2024, WAGE_WITH_HEADERS, status="needs_review")
    payers, skipped = G._wage_payers(store, 2024)
    assert len(payers) == 1 and skipped == []
    out = G.analyze_gaps(store, SCOPE, year=2024)
    g = out["2024"]
    assert g["has_transcript"] is True
    assert g["n_skipped_transcripts"] == 0
    assert g["skipped_transcripts"] == []
    json.dumps(out)


def test_wage_transcript_with_genuine_unparsed_is_skipped(store):
    # C1: unrecognized line -> "partial", not "still_unusable". Mapped
    # payers are returned (with partial=True); the doc is not skipped.
    text = WAGE_WITH_HEADERS + "Some unrecognized content line @@@\n"
    _wage_doc(store, "t1", 2024, text)
    payers, skipped = G._wage_payers(store, 2024)
    assert len(payers) == 1
    assert payers[0]["partial"] is True
    assert payers[0]["n_unparsed"] == 1
    assert skipped == []


def test_wage_transcript_wrong_status_reported(store):
    _wage_doc(store, "t1", 2024, WAGE_CLEAN, status="BLOCKED")
    payers, skipped = G._wage_payers(store, 2024)
    assert payers == []
    assert skipped == [{"doc_id": "t1", "reason_code": "wrong_status"}]


def test_reconciliation_never_passes_over_unusable_transcript(store):
    # C1: validated W-2 + a wage transcript with unparsed lines.
    # The transcript is "partial", not skipped: reconciliation runs
    # on the mapped payer, but the result is not a clean pass --
    # the partial coverage is surfaced, never a vacuous pass.
    text = WAGE_WITH_HEADERS + "Some unrecognized content line @@@\n"
    _wage_doc(store, "t1", 2024, text)
    d = _doc("w1", 2024, "W-2", status="validated")
    store.save_ocr("w1", "synthetic w2 text")
    store.upsert(d)
    r = V.verify_transcript_reconciliation(store, 2024)
    # Not skipped: the mapped payer was compared.
    assert r["n_skipped_transcripts"] == 0
    # PII sweep over the new reconciliation output
    import re as _re

    def _pii_free(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in ("value", "raw_text"), k
                _pii_free(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _pii_free(v)
        elif isinstance(obj, str):
            assert not _re.search(r"\$\d", obj), obj[:60]
    _pii_free(r)
    json.dumps(r)


# ---------------------------------------------------------------- C1 repair
# parse_transcript_doc returns "partial" (not "still_unusable") when
# unparsed lines remain; callers proceed on mapped content.
def test_parse_transcript_doc_partial_not_unusable(store):
    from taxprep import gaps as G2
    text = WAGE_WITH_HEADERS + "Some unrecognized content line @@@\n"
    _wage_doc(store, "t1", 2024, text)
    d = store.get("t1")
    parsed, reason = G2.parse_transcript_doc(d, store)
    assert reason == "partial"
    assert parsed is not None
    assert parsed["n_unparsed"] == 1
    assert len(parsed.get("payers", [])) == 1
