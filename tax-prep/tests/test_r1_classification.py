"""R1 classification regression tests — all fixtures synthetic.

Pins the four Workstation probes (quoted verbatim from the R1 build
request) against the fixed behavior:

  P1  1099-B title                   -> 1099-B   (title anchor, incl. full title)
  P2  title + recipient instructions -> 1099-B   (instruction section excluded;
                                                 "(Form 1040)" is a reference)
  P3  consolidated INT / DIV / B     -> split into 3 sections, never collapsed
                                                 to one form_type
  P4  W-2 + Notice to Employee       -> W-2      (notice excluded; the notice's
                                                 "Form 1040" mention is not
                                                 a title)
"""

from pathlib import Path

import pytest

from taxprep import extractors
from taxprep.extractors import classify_form, split_form_sections
from taxprep.ingest import ingest_dir, ingest_file, make_doc_id
from taxprep.models import Document
from taxprep.store import DocumentStore

# -- the four probes, verbatim ---------------------------------------------

PROBE_1099B = (
    "Form 1099-B Proceeds From Broker and Barter Exchange Transactions "
    "1d Proceeds 1e Cost or other basis"
)
PROBE_1099B_INSTRUCTIONS = PROBE_1099B + (
    " 1d Proceeds Instructions for Recipient: report on Form 8949 and/or "
    "Schedule D (Form 1040)"
)
PROBE_CONSOLIDATED = (
    "Form 1099-INT Interest Income 1 Interest income  "
    "Form 1099-DIV Dividends and Distributions 1a Total ordinary dividends  "
    "Form 1099-B Proceeds From Broker and Barter Exchange Transactions "
    "1d Proceeds"
)
PROBE_W2_NOTICE = (
    "Form W-2 Wage and Tax Statement 1 Wages, tips, other compensation "
    "Notice to Employee: see the Form 1040 instructions"
)


def _typed_sections(text):
    pages = text if isinstance(text, list) else [text]
    return [
        s for s in split_form_sections(pages)
        if not s.excluded and s.form_type
    ]


# -- probes -----------------------------------------------------------------

def test_probe1_1099b_title_anchor():
    # The full 1099-B title ("...Broker and Barter Exchange Transactions")
    # is a title anchor — the old "BROKER TRANSACTIONS" keyword never
    # matched it.
    assert classify_form(PROBE_1099B) == "1099-B"


def test_probe2_instruction_section_excluded():
    # Was SCHEDULE_D under whole-document substring matching.
    assert classify_form(PROBE_1099B_INSTRUCTIONS) == "1099-B"


def test_probe2_excluded_section_never_a_form():
    sections = split_form_sections([PROBE_1099B_INSTRUCTIONS])
    typed = [s for s in sections if not s.excluded and s.form_type]
    excluded = [s for s in sections if s.excluded]
    assert [s.form_type for s in typed] == ["1099-B"]
    assert len(excluded) == 1
    assert all(s.form_type is None for s in excluded)


def test_probe3_consolidated_splits_into_sections():
    sections = _typed_sections(PROBE_CONSOLIDATED)
    assert [s.form_type for s in sections] == ["1099-INT", "1099-DIV", "1099-B"]


def test_probe3_never_collapsed_to_one_form_type():
    # classify_form must not pick a single winner for multi-form input.
    assert classify_form(PROBE_CONSOLIDATED) == "UNKNOWN"
    assert classify_form(PROBE_CONSOLIDATED) not in (
        "1099-INT", "1099-DIV", "1099-B",
    )


def test_probe4_w2_notice_not_1040():
    # Was 1040 under whole-document substring matching ("FORM 1040"
    # pre-empted). The notice is excluded from scoring.
    assert classify_form(PROBE_W2_NOTICE) == "W-2"


# -- ingest: split / block ---------------------------------------------------

def test_ingest_splits_consolidated_file(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    src = incoming / "consolidated.txt"
    src.write_text(PROBE_CONSOLIDATED)
    store = DocumentStore(tmp_path / "data")

    docs = ingest_file(src, store)

    assert len(docs) == 3
    assert [d.form_type for d in docs] == ["1099-INT", "1099-DIV", "1099-B"]
    parent = make_doc_id(src.name, PROBE_CONSOLIDATED)
    assert all(d.parent_doc_id == parent for d in docs)
    assert all(d.page_range == "1" for d in docs)
    assert len({d.doc_id for d in docs}) == 3
    # every child round-trips through the store
    assert {d.doc_id for d in store.list()} == {d.doc_id for d in docs}


def test_ingest_dir_counts_split_children(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "consolidated.txt").write_text(PROBE_CONSOLIDATED)
    (incoming / "w2.txt").write_text(
        "Form W-2 Wage and Tax Statement\nTax Year 2024\n"
        "Box 1 Wages $10,000.00\n"
    )
    store = DocumentStore(tmp_path / "data")

    docs = ingest_dir(str(incoming), store)

    assert len(docs) == 4
    assert sorted(d.form_type for d in docs) == [
        "1099-B", "1099-DIV", "1099-INT", "W-2",
    ]


def test_ingest_blocks_bare_title_mentions(tmp_path):
    # Titles with no content cannot be split honestly: one MULTI_FORM
    # document, blocked — and never collapsed to a single form_type.
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    text = "Form 1099-INT Form 1099-DIV"
    src = incoming / "titles_only.txt"
    src.write_text(text)
    store = DocumentStore(tmp_path / "data")

    docs = ingest_file(src, store)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.status == "MULTI_FORM"
    assert doc.form_type == "UNKNOWN"
    assert doc.doc_id == make_doc_id(src.name, text)


def test_child_page_range_format(tmp_path):
    # page_range is "3" for a single page, "3-5" for a span.
    from taxprep.ingest import _child_document

    store = DocumentStore(tmp_path / "data")
    src = Path("broker_statement.txt")
    parent = make_doc_id(src.name, "x")

    single = extractors.FormSection("1099-INT", "Form 1099-INT\n1 Interest", 3, 3)
    span = extractors.FormSection("1099-DIV", "Form 1099-DIV\n1a Divs", 3, 5)
    d1 = _child_document(src, single, parent, "x", store)
    d2 = _child_document(src, span, parent, "x", store)
    assert d1.page_range == "3"
    assert d2.page_range == "3-5"
    assert d1.parent_doc_id == parent == d2.parent_doc_id


# -- transcripts: explicit types, no keyword fallthrough ---------------------

def test_account_transcript_not_1099_int():
    text = (
        "Internal Revenue Service\n"
        "Account Transcript\n"
        "Tax Year: 2024\n"
        "Interest charged: recorded\n"
    )
    assert classify_form(text) == "ACCOUNT_TRANSCRIPT"


def test_record_of_account_transcript():
    text = (
        "Record of Account Transcript\n"
        "Tax Year: 2024\n"
        "Return and account data follow\n"
    )
    assert classify_form(text) == "RECORD_OF_ACCOUNT"


def test_wage_income_transcript_inner_forms_suppressed(tmp_path):
    # Transcript pages mention other forms in their payer blocks; those are
    # content, not titles.
    text = (
        "WAGE AND INCOME TRANSCRIPT\n"
        "Tax Year: 2023\n"
        "Payer: SYNTHETIC WIDGETS 11-2223333\n"
        "Form W-2\n"
        "Box 1 Wages: $10,000.00\n"
        "Payer: SYNTHETIC SAVINGS\n"
        "Form 1099-INT\n"
        "Box 1 Interest: $11.11\n"
    )
    assert classify_form(text) == "WAGE_INCOME_TRANSCRIPT"

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    src = incoming / "wage_income_2023.txt"
    src.write_text(text)
    store = DocumentStore(tmp_path / "data")
    docs = ingest_file(src, store)
    assert len(docs) == 1
    assert docs[0].form_type == "WAGE_INCOME_TRANSCRIPT"


# -- instruction / notice / reference handling --------------------------------

def test_instruction_only_text_is_unknown():
    text = (
        "Instructions for Recipient\n"
        "Report interest on Schedule D (Form 1040).\n"
    )
    sections = split_form_sections([text])
    assert sections and all(s.excluded for s in sections)
    assert classify_form(text) == "UNKNOWN"


def test_parenthesized_form_1040_is_a_reference():
    # Old code returned 1040 via the "FORM 1040" substring.
    text = "Quarterly worksheet\n(see Form 1040 for details)\nno tax forms here"
    assert classify_form(text) == "UNKNOWN"


def test_1040_schedule_d_mention_is_not_a_section():
    # Bare "Schedule D" mid-sentence is a mention, not a title anchor.
    text = (
        "Form 1040 U.S. Individual Income Tax Return\n"
        "Tax Year 2024\n"
        "1 Total income. Attach Schedule D if you sold stock.\n"
    )
    sections = _typed_sections(text)
    assert [s.form_type for s in sections] == ["1040"]
    assert classify_form(text) == "1040"


def test_schedule_d_line_start_title():
    text = "SCHEDULE D\nCapital Gains and Losses\nPart I Short-Term\n"
    assert classify_form(text) == "SCHEDULE_D"


def test_mid_sentence_notice_mention_does_not_cut():
    # "see Notice to Employee for details" (no colon / line end) is not a
    # heading: the form page stays intact.
    text = (
        "Form W-2 Wage and Tax Statement\n"
        "Box 1 Wages $10,000.00 see Notice to Employee for details\n"
    )
    assert classify_form(text) == "W-2"
    sections = _typed_sections(text)
    assert len(sections) == 1


def test_continuation_page_attaches_to_form_section():
    pages = [
        "Form W-2 Wage and Tax Statement\nTax Year 2024\n",
        "Box 1 Wages: $10,000.00\nBox 2 Withheld: $1,000.00\n",
    ]
    sections = split_form_sections(pages)
    typed = [s for s in sections if not s.excluded and s.form_type]
    assert len(typed) == 1
    assert typed[0].form_type == "W-2"
    assert (typed[0].page_start, typed[0].page_end) == (1, 2)


def test_multipage_split_keeps_page_numbers():
    pages = [
        "Form 1099-INT Interest Income\n1 Interest income\nTax Year 2024\n",
        "Form 1099-DIV Dividends and Distributions\n1a Total ordinary dividends\n",
    ]
    sections = _typed_sections(pages)
    assert [(s.form_type, s.page_start, s.page_end) for s in sections] == [
        ("1099-INT", 1, 1),
        ("1099-DIV", 2, 2),
    ]


# -- models: R1 statuses and split fields -------------------------------------

def test_new_statuses_accepted():
    for status in ("MULTI_FORM", "BLOCKED", "ORPHANED"):
        d = Document(
            doc_id="d1",
            tax_year=2024,
            form_type="UNKNOWN",
            source_path="s",
            ocr_text_ref="r",
            status=status,
        )
        assert d.status == status


def test_bad_status_still_rejected():
    with pytest.raises(ValueError):
        Document(
            doc_id="d1",
            tax_year=2024,
            form_type="UNKNOWN",
            source_path="s",
            ocr_text_ref="r",
            status="NOPE",
        )


def test_page_range_parent_doc_id_defaults_and_roundtrip():
    d = Document(
        doc_id="d1",
        tax_year=2024,
        form_type="1099-INT",
        source_path="s",
        ocr_text_ref="r",
    )
    assert d.page_range is None
    assert d.parent_doc_id is None

    child = Document(
        doc_id="d2",
        tax_year=2024,
        form_type="1099-INT",
        source_path="s",
        ocr_text_ref="r",
        page_range="3-5",
        parent_doc_id="d1",
    )
    back = Document.from_dict(child.to_dict())
    assert back.page_range == "3-5"
    assert back.parent_doc_id == "d1"


def test_from_dict_backward_compatible():
    old = {
        "doc_id": "d1",
        "tax_year": 2024,
        "form_type": "W-2",
        "source_path": "s",
        "ocr_text_ref": "r",
        "fields": {},
        "status": "needs_review",
        "validated_at": None,
        "relevance": "unassessed",
    }
    d = Document.from_dict(old)
    assert d.page_range is None
    assert d.parent_doc_id is None


def test_new_form_types_accepted():
    for form_type in ("ACCOUNT_TRANSCRIPT", "RECORD_OF_ACCOUNT"):
        d = Document(
            doc_id="d1",
            tax_year=2024,
            form_type=form_type,
            source_path="s",
            ocr_text_ref="r",
        )
        assert d.form_type == form_type
