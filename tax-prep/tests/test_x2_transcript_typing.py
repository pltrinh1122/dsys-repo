"""X2: document-level transcript typing + the X2 guard.

All fixtures synthetic. Pins the workstation's four probes (header
boilerplate + title line + body with embedded section headings) against
the fixed behavior:

  P1 "Form 1040 Tax Return Transcript" -> exactly 1 RETURN_TRANSCRIPT doc
  P2 "Form 1040 Account Transcript"    -> exactly 1 ACCOUNT_TRANSCRIPT doc
                                          (>=1 TC transaction)
  P3 "Form 1040 Record of Account"    -> exactly 1 RECORD_OF_ACCOUNT doc
  P4 Wage & Income transcript          -> exactly 1 WAGE_INCOME_TRANSCRIPT doc

Regression pinned: the whole-line transcript anchors missed a prefixed
title ("Form 1040 Tax Return Transcript"), the file fell through to the
R1 per-section split, and the embedded "Form W-2" / "Schedule D"
headings spawned PHANTOM box-form child documents (an L3 double-count
risk). The type is now decided at DOCUMENT level first -- from the
first three pages' title lines carrying a transcript title anywhere in
the line (X2b: the scan used to cover page 1 only, so a cover page
pushed the title off the detector and crashed ingest on the X2 guard)
-- and a transcript-typed document is never split.

G-2 canary details baked in: the title sits on page-1 line 3 sharing
its line with exactly 2 extra words, and the in-text "Form W-2" /
"Schedule D" headings are what the old splitter cut on.
"""

import hashlib

import pytest

from taxprep import ingest
from taxprep.extractors import FormSection, detect_transcript_type
from taxprep.ingest import BOX_FORMS, ingest_file
from taxprep.store import DocumentStore
from taxprep.transcript import (parse_account_transcript,
                                parse_record_of_account,
                                parse_return_transcript,
                                parse_wage_income_transcript)

# -- fixtures ---------------------------------------------------------------

# Two header-boilerplate lines; the title sits on page-1 line 3 sharing
# its line with exactly 2 extra words ("For", "TY2025").
_BOILERPLATE = (
    "DEPARTMENT OF THE TREASURY - INTERNAL REVENUE SERVICE\n"
    "TRANSCRIPT FULFILLMENT CENTER - DO NOT DISCARD\n"
)

PROBE_RETURN_TITLE = _BOILERPLATE + """\
Form 1040 Tax Return Transcript For TY2025
Tax Year: 2025
Form 1040
Adjusted Gross Income: $85,420.00
Total Tax: $12,340.00
Form W-2
Box 1 Wages: $50,000.00
Schedule D
Short-Term Capital Gain or (Loss): ($1,000.00)
150 Tax return filed 04-15-2026 $12,340.00
"""

PROBE_ACCOUNT_TITLE = _BOILERPLATE + """\
Form 1040 Account Transcript For TY2025
Tax Year: 2025
Account Balance: $1,234.56
Form W-2
Box 1 Wages: $10,000.00
Schedule D
150 Tax return filed 20251205 04-15-2026 $1,234.56
846 Refund issued 20253207 10-05-2026 $384.56
"""

PROBE_ROA_TITLE = _BOILERPLATE + """\
Form 1040 Record of Account For TY2025
Tax Year: 2025
TAX RETURN TRANSCRIPT
Adjusted Gross Income: $85,420.00
Form W-2
Schedule D
TAX ACCOUNT TRANSCRIPT
Account Balance: $0.00
150 Tax return filed 20251205 04-15-2026 $0.00
"""

PROBE_WAGE_INCOME_TITLE = _BOILERPLATE + """\
Wage and Income Transcript For TY2025
Tax Year: 2025
Payer: SYNTHETIC WIDGETS 11-2223333
Form W-2
Box 1 Wages: $85,000.00
Payer: SYNTHETIC SAVINGS
Form 1099-INT
Box 1 Interest: $420.50
Schedule D
"""


def _ingest_text(text: str, tmp_path, name: str = "probe.txt"):
    incoming = tmp_path / "incoming"
    incoming.mkdir(exist_ok=True)
    src = incoming / name
    src.write_text(text)
    store = DocumentStore(tmp_path / "data")
    return ingest_file(src, store), store


def _no_box_form_docs(docs):
    # the guard's contract at the document level: no transcript source
    # may yield a box-form document
    assert all(d.form_type not in BOX_FORMS for d in docs)


# -- document-level detection ------------------------------------------------

def test_detector_prefixed_title_with_extra_words():
    pages = [("line one\nline two\n"
              "Form 1040 Tax Return Transcript For TY2025\n"
              "body\n")]
    assert detect_transcript_type(pages) == "RETURN_TRANSCRIPT"


def test_detector_most_specific_title_wins_in_line():
    # "Record of Account Transcript" contains "Account Transcript" --
    # the most specific title wins, never ACCOUNT_TRANSCRIPT.
    assert detect_transcript_type(
        ["Record of Account Transcript"]) == "RECORD_OF_ACCOUNT"
    assert detect_transcript_type(
        ["Form 1040 Account Transcript"]) == "ACCOUNT_TRANSCRIPT"


def test_detector_first_matching_line_wins():
    pages = ["Tax Return Transcript\nbody\nRecord of Account\n"]
    assert detect_transcript_type(pages) == "RETURN_TRANSCRIPT"


def test_detector_no_title():
    assert detect_transcript_type(["Cover sheet\nno transcript here\n"]) \
        is None
    assert detect_transcript_type([]) is None
    assert detect_transcript_type([""]) is None


def test_detector_wage_income():
    assert detect_transcript_type(
        ["Wage and Income Transcript For TY2025"]) == \
        "WAGE_INCOME_TRANSCRIPT"


# -- the four probes ----------------------------------------------------------

def test_probe_return_transcript_prefixed_title(tmp_path):
    docs, _store = _ingest_text(PROBE_RETURN_TITLE, tmp_path,
                                "return-2025.txt")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.form_type == "RETURN_TRANSCRIPT"
    _no_box_form_docs(docs)
    # the transcript parser ran over the whole text: the embedded
    # "Schedule D" section line is a transcript field, not a child doc
    assert doc.fields["agi"]["value"] == "85420.00"
    assert doc.fields["total_tax"]["value"] == "12340.00"
    assert doc.fields["short_term_gain_loss"]["value"] == "-1000.00"
    assert doc.fields["tc_150"]["value"] == "12340.00"
    # D2: Decimal-safe strings end to end, never floats
    for key in ("agi", "total_tax", "short_term_gain_loss", "tc_150"):
        assert isinstance(doc.fields[key]["value"], str), key


def test_probe_account_transcript_prefixed_title(tmp_path):
    docs, _store = _ingest_text(PROBE_ACCOUNT_TITLE, tmp_path,
                                "account-2025.txt")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.form_type == "ACCOUNT_TRANSCRIPT"
    _no_box_form_docs(docs)
    assert doc.fields["account_balance"]["value"] == "1234.56"
    tc_keys = [k for k in doc.fields if k.startswith("tc_")]
    assert len(tc_keys) >= 1  # G-2: >=1 TC transaction
    assert doc.fields["tc_150"]["value"] == "1234.56"


def test_probe_record_of_account_prefixed_title(tmp_path):
    docs, _store = _ingest_text(PROBE_ROA_TITLE, tmp_path, "roa-2025.txt")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.form_type == "RECORD_OF_ACCOUNT"
    _no_box_form_docs(docs)
    # both sections merged by the record-of-account parser
    assert doc.fields["agi"]["value"] == "85420.00"
    assert doc.fields["account_balance"]["value"] == "0.00"


def test_probe_wage_income_transcript(tmp_path):
    docs, _store = _ingest_text(PROBE_WAGE_INCOME_TITLE, tmp_path,
                                "wage-income-2025.txt")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.form_type == "WAGE_INCOME_TRANSCRIPT"
    _no_box_form_docs(docs)
    # payer blocks parsed by the wage & income parser, not split out
    assert doc.fields["payer1.name"]["value"] == "SYNTHETIC WIDGETS"
    assert doc.fields["payer2.name"]["value"] == "SYNTHETIC SAVINGS"


def test_no_probe_yields_box_form_documents(tmp_path):
    # all four probes through one store: zero box-form documents total
    store = DocumentStore(tmp_path / "data")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    for name, text in (("p1.txt", PROBE_RETURN_TITLE),
                       ("p2.txt", PROBE_ACCOUNT_TITLE),
                       ("p3.txt", PROBE_ROA_TITLE),
                       ("p4.txt", PROBE_WAGE_INCOME_TITLE)):
        (incoming / name).write_text(text)
    for name in ("p1.txt", "p2.txt", "p3.txt", "p4.txt"):
        ingest_file(incoming / name, store)
    docs = store.list()
    assert len(docs) == 4
    assert sorted(d.form_type for d in docs) == [
        "ACCOUNT_TRANSCRIPT",
        "RECORD_OF_ACCOUNT",
        "RETURN_TRANSCRIPT",
        "WAGE_INCOME_TRANSCRIPT",
    ]
    assert not any(d.form_type in BOX_FORMS for d in docs)


# -- per-source yield >= baseline ----------------------------------------------

def _baseline_values(parse_fn, text):
    """Values the transcript parser yields on the whole text directly."""
    parsed = parse_fn(text)
    out = dict(parsed.get("lines", {}))
    for t in parsed.get("transactions", []):
        out[f"tc_{t['code']}"] = t["amount"]
    for section in ("return_section", "account_section"):
        sec = parsed.get(section)
        if sec:
            out.update(_baseline_values(
                lambda _t, _s=sec: _s, ""))
    return out


def test_return_probe_yield_matches_direct_parse(tmp_path):
    # the X2 document path must yield every field the parser finds on
    # the same text -- never fewer than the (correct) baseline
    docs, _store = _ingest_text(PROBE_RETURN_TITLE, tmp_path)
    doc = docs[0]
    baseline = _baseline_values(parse_return_transcript, PROBE_RETURN_TITLE)
    for key, value in baseline.items():
        assert doc.fields[key]["value"] == value, key


def test_account_probe_yield_matches_direct_parse(tmp_path):
    docs, _store = _ingest_text(PROBE_ACCOUNT_TITLE, tmp_path)
    doc = docs[0]
    baseline = _baseline_values(parse_account_transcript, PROBE_ACCOUNT_TITLE)
    for key, value in baseline.items():
        assert doc.fields[key]["value"] == value, key


def test_roa_probe_yield_matches_direct_parse(tmp_path):
    docs, _store = _ingest_text(PROBE_ROA_TITLE, tmp_path)
    doc = docs[0]
    baseline = _baseline_values(parse_record_of_account, PROBE_ROA_TITLE)
    for key, value in baseline.items():
        assert doc.fields[key]["value"] == value, key


def test_wage_income_probe_yield_matches_direct_parse(tmp_path):
    docs, _store = _ingest_text(PROBE_WAGE_INCOME_TITLE, tmp_path)
    doc = docs[0]
    parsed = parse_wage_income_transcript(PROBE_WAGE_INCOME_TITLE)
    for i, payer in enumerate(parsed["payers"], start=1):
        assert doc.fields[f"payer{i}.name"]["value"] == payer["payer"]


# -- multi-page transcript: never split -----------------------------------------

def test_multipage_transcript_never_split(tmp_path):
    # title on page 1; embedded "Form W-2" / "Schedule D" headings on
    # later pages -- still exactly one transcript document
    page1 = (_BOILERPLATE
             + "Form 1040 Tax Return Transcript For TY2025\n"
             + "Tax Year: 2025\n")
    page2 = ("Adjusted Gross Income: $85,420.00\n"
             "Form W-2\n"
             "Box 1 Wages: $50,000.00\n")
    page3 = ("Schedule D\n"
             "Short-Term Capital Gain or (Loss): ($1,000.00)\n"
             "150 Tax return filed 04-15-2026 $12,340.00\n")
    store = DocumentStore(tmp_path / "data")
    bundle = ingest.PageBundle(pages=[page1, page2, page3], route="native",
                               text_source="native")
    text = "\n".join([page1, page2, page3])
    source_bytes = text.encode("utf-8")
    sha = hashlib.sha256(source_bytes).hexdigest()
    # the real flow registers the bronze before deriving (I7: the
    # silver_doc FK always holds)
    ingest._register_bronze(store, sha, source_bytes, "probe.txt",
                             encryption=None)
    docs = ingest._build_documents("probe.txt",
                                    ingest.source_doc_id(source_bytes),
                                    bundle, sha, store)
    assert len(docs) == 1
    assert docs[0].form_type == "RETURN_TRANSCRIPT"
    assert docs[0].fields["agi"]["value"] == "85420.00"


# -- the X2 guard -----------------------------------------------------------------

def test_guard_rejects_transcript_box_mix():
    sections = [
        FormSection("RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 1, 1),
        FormSection("W-2", "Form W-2\nBox 1 Wages: $1.00\n", 1, 1),
    ]
    with pytest.raises(AssertionError, match="X2 guard"):
        ingest._check_no_transcript_box_mix(sections)


def test_guard_passes_transcript_only_and_box_only():
    ingest._check_no_transcript_box_mix([
        FormSection("RETURN_TRANSCRIPT", "t", 1, 1),
        FormSection("ACCOUNT_TRANSCRIPT", "t", 1, 1),
    ])
    ingest._check_no_transcript_box_mix([
        FormSection("W-2", "t", 1, 1),
        FormSection("1099-INT", "t", 1, 1),
    ])
    ingest._check_no_transcript_box_mix([])


def test_guard_fires_on_split_path_when_detector_misses(tmp_path):
    # title NOT on page 1 (detector misses), transcript anchor on page 2
    # and a "Form W-2" heading with box content on page 3: the R1 split
    # would mix a transcript child with a box-form child -- the guard
    # fails loudly instead of emitting the phantom W-2.
    store = DocumentStore(tmp_path / "data")
    bundle = ingest.PageBundle(
        pages=["Cover sheet\n",
               "TAX RETURN TRANSCRIPT\nAdjusted Gross Income: $1.00\n",
               "Form W-2\nBox 1 Wages: $10,000.00\n"],
        route="native", text_source="native")
    text = "\n".join(bundle.pages)
    source_bytes = text.encode("utf-8")
    with pytest.raises(AssertionError, match="X2 guard"):
        ingest._build_documents("mixed.txt",
                                ingest.source_doc_id(source_bytes),
                                bundle,
                                hashlib.sha256(source_bytes).hexdigest(),
                                store)


def test_guard_still_fires_when_split_mixes_transcript_and_box():
    # the guard's own contract, pinned directly: a split that mixes a
    # transcript child with a box-form child fails loudly, never
    # silently emits phantoms
    sections = [
        FormSection("RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 4, 4),
        FormSection("W-2", "Form W-2\nBox 1 Wages: $1.00\n", 5, 5),
    ]
    with pytest.raises(AssertionError, match="X2 guard"):
        ingest._check_no_transcript_box_mix(sections)


def test_embedded_headings_are_transcript_content_not_children(tmp_path):
    # the exact headings the old splitter cut on -- "Form 1040",
    # "Form W-2", "Schedule D" -- inside a transcript body
    text = ("TAX RETURN TRANSCRIPT\nTax Year: 2025\n"
            "Form 1040\n"
            "Form W-2\n"
            "Schedule D\n"
            "Adjusted Gross Income: $10.00\n")
    docs, _store = _ingest_text(text, tmp_path, "headings.txt")
    assert len(docs) == 1
    assert docs[0].form_type == "RETURN_TRANSCRIPT"
    assert docs[0].parent_doc_id is None  # not a split child


# -- X2b: multi-page transcripts never split (regression) -----------------------
#
# The workstation's gate audit confirmed X2b fixed: the X2 document-level
# transcript guard covers multi-page sources (105-page transcripts yield
# exactly 1 document, no phantoms). These tests pin that behavior.

def _build_docs_from_pages(pages, tmp_path, name):
    """_build_documents over an explicit page list (I7: bronze first)."""
    store = DocumentStore(tmp_path / "data")
    bundle = ingest.PageBundle(pages=pages, route="native",
                               text_source="native")
    text = "\n".join(pages)
    source_bytes = text.encode("utf-8")
    sha = hashlib.sha256(source_bytes).hexdigest()
    ingest._register_bronze(store, sha, source_bytes, name,
                            encryption=None)
    docs = ingest._build_documents(name, ingest.source_doc_id(source_bytes),
                                   bundle, sha, store)
    return docs


def _filler_page(n):
    # benign continuation body; embedded form/schedule headings that the
    # R1 split would cut on (the audit's literal 105-page scenario)
    return (f"Page {n} continuation\n"
            f"Account activity detail line {n}.\n"
            "Form 1099-B\n"
            "Proceeds: $1.00\n"
            "Schedule D\n"
            f"Detail row {n}.\n")


def _long_transcript(pages_total, title_page_idx, title_line,
                     body_first):
    pages = []
    for i in range(pages_total):
        if i == title_page_idx:
            pages.append(_BOILERPLATE + title_line + body_first)
        else:
            pages.append(_filler_page(i + 1))
    return pages


@pytest.mark.parametrize("title_line,form_type", [
    ("Form 1040 Tax Return Transcript For TY2025\n",
     "RETURN_TRANSCRIPT"),
    ("Wage and Income Transcript For TY2025\n",
     "WAGE_INCOME_TRANSCRIPT"),
    ("Form 1040 Record of Account For TY2025\n",
     "RECORD_OF_ACCOUNT"),
])
def test_105_page_transcripts_never_split(tmp_path, title_line, form_type):
    # the audit's acceptance: 105-page transcripts with embedded
    # "Form 1099-B" / "Schedule D" headings on every filler page yield
    # exactly 1 document each
    pages = _long_transcript(
        105, 0, title_line,
        "Tax Year: 2025\nAdjusted Gross Income: $85,420.00\n")
    docs = _build_docs_from_pages(pages, tmp_path, "long.txt")
    assert len(docs) == 1
    assert docs[0].form_type == form_type
    _no_box_form_docs(docs)




def test_title_on_page_four_is_not_detected():
    # the detector scans page-1 title lines only: a title past page 1
    # is invisible to it and falls through to the ordinary split path
    # by design (the X2 guard stays the loud backstop there)
    pages = ["Cover\n", "Cover\n", "Cover\n",
             "Form 1040 Tax Return Transcript For TY2025\nbody\n"]
    assert detect_transcript_type(pages) is None


def test_broker_boilerplate_on_page_five_not_mistyped(tmp_path):
    # "record of account" boilerplate deep in a long broker statement
    # must not type the document as a transcript
    pages = [
        "SYNTHETIC BROKERAGE MONTHLY STATEMENT\nAccount: 99-111\n",
        "Holdings summary\nPosition detail\n",
        "Activity detail\nDividend detail\n",
        "Fee schedule\nTax documents enclosed\n",
        ("You may request a record of account at any time by calling "
         "the number above.\nForm 1099-B\nProceeds: $2.00\n"),
    ]
    assert detect_transcript_type(pages) is None
    docs = _build_docs_from_pages(pages, tmp_path, "broker.txt")
    assert all(d.form_type != "RECORD_OF_ACCOUNT" for d in docs)
    assert all(d.form_type not in
               ("RETURN_TRANSCRIPT", "ACCOUNT_TRANSCRIPT",
                "WAGE_INCOME_TRANSCRIPT") for d in docs)



