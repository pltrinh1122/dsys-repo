"""R23 stream A: positional two-column transcript capture tests.

Synthetic transcript PDFs (reportlab, digital text -- no OCR involved)
cover dot leaders, text values, negative money, multi-page documents and
section headers / label-only rows. All fixtures are synthetic; no PII.
Deterministic: no wall-clock, no randomness.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep import ingest, twocol

W, H = letter
MONEY_RE = re.compile(r"^-?\$?[\d,]+(\.\d{1,2})?$")


# -- synthetic fixture builders ------------------------------------------


def _wb(text, x0, x1, top=100.0, bottom=112.0):
    """One synthetic word box (pdfplumber word-dict shape)."""
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom}


def _draw_label_value(c, y, label, value, dots=False):
    c.drawString(72, y, label)
    if dots:
        c.drawString(300, y, "..........")
    if value is not None:
        c.drawRightString(W - 72, y, value)
    return y - 14


def _synthetic_transcript_pdf(path: Path) -> Path:
    """Two-page synthetic transcript PDF (digital text)."""
    c = canvas.Canvas(str(path), pagesize=letter)
    y = H - 72
    c.drawCentredString(W / 2, y, "TAX RETURN TRANSCRIPT")
    y -= 20
    y = _draw_label_value(c, y, "Tax Year", "2024")
    y = _draw_label_value(c, y, "LINE ITEMS", None)
    y = _draw_label_value(c, y, "Adjusted Gross Income", "87,654", dots=True)
    y = _draw_label_value(c, y, "Filing Status", "Head of Household")
    y = _draw_label_value(c, y, "Capital Loss Carryover", "-1,234", dots=True)
    y = _draw_label_value(c, y, "Taxable Income", "62,100.00", dots=True)
    y = _draw_label_value(c, y, "Total Tax", None)  # label-only, no value
    c.showPage()
    y = H - 72
    c.drawCentredString(W / 2, y, "TAX RETURN TRANSCRIPT (CONTINUED)")
    y -= 20
    y = _draw_label_value(c, y, "Refund Issued", "3,456.78", dots=True)
    y = _draw_label_value(c, y, "Account Balance", "0.00")
    c.showPage()
    c.save()
    return path


# -- unit: normalize_label / is_dot_leader -------------------------------


def test_normalize_label_strips_collapses_uppercases():
    assert twocol.normalize_label("  Adjusted   Gross\nIncome ") == \
        "ADJUSTED GROSS INCOME"
    assert twocol.normalize_label("Tax\tYear") == "TAX YEAR"
    assert twocol.normalize_label("") == ""
    assert twocol.normalize_label("   ") == ""


def test_is_dot_leader():
    assert twocol.is_dot_leader(".....")
    assert twocol.is_dot_leader("...")
    assert twocol.is_dot_leader("  ..........  ")
    assert not twocol.is_dot_leader("87,654")
    assert not twocol.is_dot_leader("....5")
    assert not twocol.is_dot_leader("")


# -- unit: group_into_lines ----------------------------------------------


def test_group_into_lines_y_tolerance():
    words = [
        _wb("Value", 500.0, 540.0, top=100.0),
        _wb("Label", 72.0, 120.0, top=100.0),
        _wb("Next", 72.0, 110.0, top=114.0),
    ]
    lines = twocol.group_into_lines(words)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["Label", "Value"]
    assert [w["text"] for w in lines[1]] == ["Next"]


def test_group_into_lines_boundary_is_one_line():
    # |top delta| exactly at the 2.5pt tolerance still groups together.
    lines = twocol.group_into_lines([
        _wb("a", 72.0, 80.0, top=100.0),
        _wb("b", 500.0, 510.0, top=102.5),
    ])
    assert len(lines) == 1
    lines = twocol.group_into_lines([
        _wb("a", 72.0, 80.0, top=100.0),
        _wb("b", 500.0, 510.0, top=102.6),
    ])
    assert len(lines) == 2


# -- unit: split_line gap logic -------------------------------------------

PAGE = 612.0  # letter width


def test_split_line_basic():
    words = [_wb("Adjusted", 72, 120), _wb("Gross", 125, 160),
             _wb("Income", 165, 210), _wb("87,654", 500, 540)]
    label, value = twocol.split_line(words, PAGE)
    assert [w["text"] for w in label] == ["Adjusted", "Gross", "Income"]
    assert [w["text"] for w in value] == ["87,654"]


def test_split_line_gap_exactly_at_threshold_splits():
    # gap of exactly 14.0pt meets the >= 14 boundary (inclusive);
    # value x0 (215) is past 35% of the width (214.2).
    words = [_wb("Label", 72, 201), _wb("1,000", 215, 540)]
    assert twocol.split_line(words, PAGE) is not None


def test_split_line_gap_just_under_threshold_does_not_split():
    words = [_wb("Label", 72, 200), _wb("1,000", 213.99, 540)]
    assert twocol.split_line(words, PAGE) is None


def test_split_line_value_starting_at_or_before_35pct_does_not_split():
    # value x0 must be PAST 35% of the page width (214.2pt on letter).
    words = [_wb("Label", 72, 100), _wb("1,000", 214.2, 540)]
    assert twocol.split_line(words, PAGE) is None
    words = [_wb("Label", 72, 100), _wb("1,000", 214.3, 540)]
    assert twocol.split_line(words, PAGE) is not None


def test_split_line_right_end_at_or_before_55pct_does_not_split():
    # line x1 must be PAST 55% of the page width (336.6pt on letter).
    words = [_wb("Label", 72, 100), _wb("1,000", 250, 336.6)]
    assert twocol.split_line(words, PAGE) is None
    words = [_wb("Label", 72, 100), _wb("1,000", 250, 336.61)]
    assert twocol.split_line(words, PAGE) is not None


def test_split_line_tie_splits_at_leftmost_gap():
    words = [_wb("A", 72, 100), _wb("B", 220, 248), _wb("C", 368, 560)]
    label, value = twocol.split_line(words, PAGE)
    # both gaps are 120pt; the deterministic choice is the leftmost.
    assert [w["text"] for w in label] == ["A"]
    assert [w["text"] for w in value] == ["B", "C"]


def test_split_line_single_word_is_label_only():
    assert twocol.split_line([_wb("HEADER", 72, 150)], PAGE) is None


def test_split_line_largest_gap_wins_not_first():
    # the intra-label gap is small; the label/value gap dominates.
    words = [_wb("Total", 72, 100), _wb("Tax", 104, 130),
             _wb("12,340.00", 500, 560)]
    label, value = twocol.split_line(words, PAGE)
    assert [w["text"] for w in label] == ["Total", "Tax"]
    assert [w["text"] for w in value] == ["12,340.00"]


# -- unit: capture_page_pairs (dot leaders, label-only) --------------------


def test_capture_page_pairs_drops_dot_leaders_and_splits():
    words = [_wb("Adjusted", 72, 120), _wb("Gross", 125, 165),
             _wb("Income", 170, 215), _wb("..........", 300, 328),
             _wb("87,654", 500, 540)]
    rows = twocol.capture_page_pairs(words, PAGE, 792.0, 1)
    assert rows == [("Adjusted Gross Income", "87,654",
                     [72.0, 680.0, 540.0, 692.0], 1)]


def test_capture_page_pairs_dot_leader_only_line_skipped():
    rows = twocol.capture_page_pairs([_wb(".....", 300, 330)], PAGE, 792.0, 1)
    assert rows == []


def test_capture_page_pairs_bbox_origin_is_bottom_left():
    # word box origin top-left (top=100, bottom=112) must flip to
    # bottom-left against the page height.
    words = [_wb("Label", 72, 120, top=100.0, bottom=112.0),
             _wb("1,000", 500, 540, top=100.0, bottom=112.0)]
    (label, value, bbox, page), = twocol.capture_page_pairs(words, PAGE,
                                                            792.0, 3)
    assert (label, value, page) == ("Label", "1,000", 3)
    assert bbox == [72.0, 680.0, 540.0, 692.0]


# -- integration: capture_pairs over a synthetic digital PDF ---------------


@pytest.fixture()
def transcript_pdf(tmp_path):
    return _synthetic_transcript_pdf(tmp_path / "synthetic_transcript.pdf")


def test_capture_pairs_splits_money_dot_leaders_and_text(transcript_pdf):
    rows = twocol.capture_pairs(transcript_pdf)
    by_label = {r[0]: r for r in rows}
    assert by_label["Adjusted Gross Income"][1] == "87,654"
    assert by_label["Filing Status"][1] == "Head of Household"
    assert by_label["Tax Year"][1] == "2024"
    assert by_label["Taxable Income"][1] == "62,100.00"
    assert by_label["Refund Issued"][1] == "3,456.78"
    assert by_label["Account Balance"][1] == "0.00"


def test_capture_pairs_negative_money_stays_one_value(transcript_pdf):
    rows = twocol.capture_pairs(transcript_pdf)
    by_label = {r[0]: r for r in rows}
    assert by_label["Capital Loss Carryover"][1] == "-1,234"


def test_capture_pairs_label_only_rows(transcript_pdf):
    rows = twocol.capture_pairs(transcript_pdf)
    by_label = {r[0]: r for r in rows}
    assert by_label["LINE ITEMS"][1] == ""
    assert by_label["Total Tax"][1] == ""
    assert by_label["TAX RETURN TRANSCRIPT"][1] == ""


def test_capture_pairs_zero_unsplit_money_values(transcript_pdf):
    # An unsplit money value would strand its amount in a label-only row.
    rows = twocol.capture_pairs(transcript_pdf)
    for label, value, _bbox, _page in rows:
        if value == "":
            for token in label.split():
                assert not MONEY_RE.match(token), \
                    f"unsplit money value stranded in label-only row: {label!r}"


def test_capture_pairs_page_numbers_and_bbox(transcript_pdf):
    rows = twocol.capture_pairs(transcript_pdf)
    by_label = {r[0]: r for r in rows}
    assert by_label["Adjusted Gross Income"][3] == 1
    assert by_label["Refund Issued"][3] == 2
    pages = sorted({r[3] for r in rows})
    assert pages == [1, 2]
    for _label, _value, bbox, _page in rows:
        x0, y0, x1, y1 = bbox
        assert 0 <= x0 < x1 <= W
        assert 0 <= y0 < y1 <= H


# -- integration: _fields_from_transcript with the source PDF --------------


def _field_provenance_ok(entry, page):
    prov = entry["provenance"]
    assert prov["page"] == page
    assert prov["bbox_source"] == "pdfplumber"
    x0, y0, x1, y1 = prov["bbox_pdf"]
    assert len(prov["bbox_pdf"]) == 4
    assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H


def test_fields_from_transcript_pair_fields_shape(transcript_pdf):
    text = ("TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
            "Adjusted Gross Income: $85,420.00\n")
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", text, 2024, pdf_path=str(transcript_pdf))
    entry = fields["ADJUSTED GROSS INCOME"]
    assert entry["value"] == "87,654"
    assert entry["confidence"] == "medium"
    assert entry["raw_text"] == "Adjusted Gross Income 87,654"
    _field_provenance_ok(entry, page=1)


def test_fields_from_transcript_pair_fields_multipage(transcript_pdf):
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 2024,
        pdf_path=str(transcript_pdf))
    assert fields["REFUND ISSUED"]["value"] == "3,456.78"
    _field_provenance_ok(fields["REFUND ISSUED"], page=2)
    assert fields["FILING STATUS"]["value"] == "Head of Household"
    assert fields["CAPITAL LOSS CARRYOVER"]["value"] == "-1,234"


def test_fields_from_transcript_legacy_fields_kept(transcript_pdf):
    # The legacy parser's canonical keys + transactions survive alongside
    # the pair fields.
    text = ("TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
            "Adjusted Gross Income: $85,420.00\n"
            "150 Tax return filed 20241205 04-15-2025 $1,234.56\n")
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", text, 2024, pdf_path=str(transcript_pdf))
    assert fields["agi"]["value"] == "85420.00"
    assert fields["tc_150"]["value"] == "1234.56"
    assert fields["ADJUSTED GROSS INCOME"]["value"] == "87,654"


def test_fields_from_transcript_collision_rule(monkeypatch, tmp_path):
    # A normalized pair label already set by the legacy parser is never
    # overwritten: the pair lands at pair:<label> (then pair:<label>_2).
    monkeypatch.setattr(
        ingest.transcript, "parse_return_transcript",
        lambda text, tax_year=None: {
            "lines": {"ADJUSTED GROSS INCOME": "85420.00"},
            "line_raw_text": {"ADJUSTED GROSS INCOME":
                              "Adjusted Gross Income: $85,420.00"},
            "line_confidence": {"ADJUSTED GROSS INCOME": "high"},
            "line_spans": {"ADJUSTED GROSS INCOME": (0, 34)},
            "transactions": [], "unparsed_lines": [], "unparsed_spans": [],
        })
    monkeypatch.setattr(
        twocol, "capture_pairs",
        lambda _pdf: [("Adjusted Gross Income", "87,654",
                       [72.0, 680.0, 540.0, 692.0], 1),
                      ("Adjusted Gross Income", "87,654",
                       [72.0, 660.0, 540.0, 672.0], 2),
                      ("Filing Status", "Single",
                       [72.0, 640.0, 540.0, 652.0], 1)])
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 2024,
        pdf_path=str(tmp_path / "x.pdf"))
    assert fields["ADJUSTED GROSS INCOME"]["value"] == "85420.00"
    assert fields["pair:ADJUSTED GROSS INCOME"]["value"] == "87,654"
    assert fields["pair:ADJUSTED GROSS INCOME"]["confidence"] == "medium"
    assert fields["pair:ADJUSTED GROSS INCOME_2"]["value"] == "87,654"
    _field_provenance_ok(fields["pair:ADJUSTED GROSS INCOME"], page=1)
    _field_provenance_ok(fields["pair:ADJUSTED GROSS INCOME_2"], page=2)
    # Non-colliding pair keeps the bare normalized key.
    assert fields["FILING STATUS"]["value"] == "Single"


def test_fields_from_transcript_no_pdf_path_no_pair_fields():
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\nTax Year: 2024\n", 2024)
    assert not any(k.startswith("pair:") for k in fields)
    assert "ADJUSTED GROSS INCOME" not in fields


def test_fields_from_transcript_bad_pdf_path_never_fails_legacy(tmp_path):
    missing = tmp_path / "missing.pdf"
    fields, status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT",
        "TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
        "Adjusted Gross Income: $85,420.00\n",
        2024, pdf_path=str(missing))
    assert fields["agi"]["value"] == "85420.00"
    assert status == "transcribed"


def test_extract_for_type_threads_pdf_path(transcript_pdf):
    fields, _status = ingest._extract_for_type(
        "RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 2024,
        pdf_path=str(transcript_pdf))
    assert fields["ADJUSTED GROSS INCOME"]["value"] == "87,654"
    # box forms ignore pdf_path (no pair capture, no crash)
    fields, status = ingest._extract_for_type(
        "W-2", "Form W-2\n", 2024, pdf_path=str(transcript_pdf))
    assert status == "needs_review"


def test_pair_provenance_survives_attach_provenance(transcript_pdf):
    # The R15 attach step must not clobber the pair's pdfplumber bbox.
    fields, _status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", "TAX RETURN TRANSCRIPT\n", 2024,
        pdf_path=str(transcript_pdf))
    out = ingest._attach_provenance(
        fields, [(1, 0, len("TAX RETURN TRANSCRIPT\n"))],
        "RETURN_TRANSCRIPT", None, ["TAX RETURN TRANSCRIPT\n"])
    entry = out["ADJUSTED GROSS INCOME"]
    assert entry["provenance"]["bbox_source"] == "pdfplumber"
    assert entry["provenance"]["page"] == 1
    assert len(entry["provenance"]["bbox_pdf"]) == 4


def test_capture_pairs_missing_pdf_raises():
    with pytest.raises(FileNotFoundError):
        twocol.capture_pairs("/tmp/does-not-exist-twocol.pdf")
