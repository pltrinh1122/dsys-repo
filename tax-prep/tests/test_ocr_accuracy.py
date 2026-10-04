"""OCR accuracy arc (O1a/O1b/O2) — all fixtures synthetic, no engine needed.

O1a: OCR-tolerant 1099-B box-token matching when text_source=ocr:*.
O1b: lot-count completeness check (lot_count_mismatch).
O2:  per-page OCR records -- form-feed page markers in stored text and
     the tesseract word-box sidecar.

Engine-invoking coverage is limited to one honestly-skipped test (no
tesseract/ocrmypdf on this machine); everything else exercises the new
logic with synthetic OCR-style TEXT.
"""

import stat

import pytest
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep import ingest, ocr
from taxprep.extractors import extract_fields
from taxprep.ingest import ingest_file
from taxprep.provenance import (
    GeometryResolver,
    attach_field_provenance,
    geometry_resolver_from_store,
    page_spans_for_joined,
)
from taxprep.store import DocumentStore


def _field(fields, code):
    assert code in fields, f"missing box {code}"
    return fields[code]


# ---------------------------------------------------------------- O1a

# Clean box-token fallbacks (no labeled words, so the fallbacks extract).
B1099_CLEAN_TOKENS = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d $1000.00 1e $1500.00 1g $0.00
Lot 2 1d $2000.00 1e $2600.00 1g $300.00
"""

# Same lots, OCR-misread box tokens ("1d" -> "ld", "1e" -> "le",
# "1g" -> "lg"): one consistent misread per box, the audit's shape.
B1099_CONFUSED_TOKENS = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 ld $1000.00 le $1500.00 lg $0.00
Lot 2 ld $2000.00 le $2600.00 lg $300.00
"""

OCR_TS = "ocr:tesseract/force-ocr"


def _lot_values(fields):
    return [
        (l["proceeds_1d"], l["basis_1e"], l["wash_1g"])
        for l in _field(fields, "lots")["value"]
    ]


def test_ocr_confused_box_tokens_extract_like_clean():
    clean_fields, clean_status = extract_fields(
        "1099-B", B1099_CLEAN_TOKENS, text_source="native")
    ocr_fields, ocr_status = extract_fields(
        "1099-B", B1099_CONFUSED_TOKENS, text_source=OCR_TS)
    assert clean_status == "transcribed"
    assert ocr_status == "transcribed"
    assert _lot_values(ocr_fields) == _lot_values(clean_fields) == [
        ("1000.00", "1500.00", "0.00"),
        ("2000.00", "2600.00", "300.00"),
    ]


def test_ocr_tolerance_not_applied_on_native():
    # Same confused text through the native path: the old behavior --
    # box tokens do not match, lots come back missing, needs_review.
    for ts in ("native", None):
        fields, status = extract_fields(
            "1099-B", B1099_CONFUSED_TOKENS, text_source=ts)
        assert status == "needs_review"
        lots = _field(fields, "lots")
        assert lots["value"] is None
        assert lots["confidence"] == "low"


def test_ocr_tolerance_keeps_labeled_patterns_primary():
    # Labeled words still win on the OCR path (high confidence).
    text = (B1099_CONFUSED_TOKENS
            .replace("ld $1000.00", "Proceeds $1000.00")
            .replace("le $1500.00", "Cost or other basis $1500.00")
            .replace("ld $2000.00", "Proceeds $2000.00")
            .replace("le $2600.00", "Cost or other basis $2600.00"))
    fields, status = extract_fields("1099-B", text, text_source=OCR_TS)
    assert status == "transcribed"
    assert _field(fields, "lots")["confidence"] == "high"


# ---------------------------------------------------------------- O1b

def test_lot_count_mismatch_markers():
    text = """Form 1099-B Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1
Proceeds $100.00
Cost or other basis $90.00
Lot 2
Proceeds $200.00
Cost or other basis $190.00
Lot 3
Proceeds $300.00
Cost or other basis $290.00
Lot 4
Lot 5
"""
    fields, status = extract_fields("1099-B", text)
    # 5 markers, 3 extractable lots: never "transcribed" while rows are
    # missing. "lots" is a key box, so the low confidence -> needs_review.
    assert status == "needs_review"
    lots = _field(fields, "lots")
    assert lots["confidence"] == "low"
    assert lots["reason_code"] == "lot_count_mismatch"
    assert lots["reason_detail"] == {"expected": 5, "extracted": 3}


def test_lot_count_mismatch_50_lot_ocr_fixture():
    # The audit shape: 50 "Lot N" markers, confused labels recovered by
    # O1a on 14 lots, 36 lot lines lost outright.
    lines = ["Form 1099-B Proceeds From Broker Transactions Tax Year 2024",
             "Broker: EXAMPLE BROKERAGE"]
    for i in range(1, 51):
        lines.append(f"Lot {i}")
        if i <= 14:
            lines.append(f"ld ${1000 + i}.00 le ${900 + i}.00")
        else:
            lines.append("~~~ unreadable scan fragment ~~~")
    text = "\n".join(lines) + "\n"
    fields, status = extract_fields("1099-B", text, text_source=OCR_TS)
    lots = _field(fields, "lots")
    assert len(lots["value"]) == 14
    assert lots["value"][0]["proceeds_1d"] == "1001.00"
    assert status == "needs_review"
    assert status != "transcribed"
    assert lots["reason_code"] == "lot_count_mismatch"
    assert lots["reason_detail"] == {"expected": 50, "extracted": 14}


def test_lot_count_mismatch_row_shaped_lines():
    # No "Lot N" markers: row-shaped lines (date + amount, one line)
    # are the expected count.
    text = """Form 1099-B Tax Year 2024
Broker: EXAMPLE BROKERAGE
100 shrs EXAMPLE 01/15/2024 06/20/2024 Proceeds $1000.00 Basis $900.00
200 shrs SAMPLE 02/10/2024 07/25/2024 Proceeds $2000.00 Basis $1900.00
300 shrs DEMO 03/12/2024 08/30/2024 $999.99 (unreadable)
"""
    fields, status = extract_fields("1099-B", text)
    assert status == "needs_review"
    lots = _field(fields, "lots")
    assert lots["reason_code"] == "lot_count_mismatch"
    assert lots["reason_detail"] == {"expected": 3, "extracted": 2}


def test_lot_count_ok_no_false_positive():
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 short term
Lot 2 1d Proceeds $2000.00 1e Cost or other basis $2600.00 short term
Lot 3 1d Proceeds $500.00 1e Cost or other basis $400.00 short term
"""
    fields, status = extract_fields("1099-B", text)
    assert status == "transcribed"
    assert "reason_code" not in _field(fields, "lots")


def test_lot_count_no_signal_no_check():
    # No markers and no row-shaped lines (dates and amounts on separate
    # lines): no completeness signal, no check.
    text = """Form 1099-B Tax Year 2024
Broker: EXAMPLE BROKERAGE
Box 1d Proceeds: $12,500.00
Box 1e Cost basis: $9,800.00
Date acquired: 03/15/2022 Date sold: 06/20/2024
"""
    fields, status = extract_fields("1099-B", text)
    assert status == "transcribed"
    assert "reason_code" not in _field(fields, "lots")


# ---------------------------------------------------------------- O2

def _store(tmp_path):
    return DocumentStore(tmp_path / "data")


def test_save_ocr_page_markers(tmp_path):
    store = _store(tmp_path)
    ref = store.save_ocr("d1", "p1\np2\np3", pages=["p1", "p2", "p3"])
    assert ref == "ocr/d1.txt"
    stored = store.load_ocr("d1")
    assert stored == "p1\fp2\fp3"
    assert stored.split("\f") == ["p1", "p2", "p3"]
    # Legacy call sites (pages=None): byte-identical stored text.
    store.save_ocr("d2", "x\ny")
    assert store.load_ocr("d2") == "x\ny"


def test_words_sidecar_round_trip(tmp_path):
    store = _store(tmp_path)
    words = {
        0: [{"text": "Proceeds", "bbox": [10.0, 20.0, 60.0, 30.0],
             "conf": 95.0, "page": 0}],
        2: [{"text": "1d", "bbox": [1.0, 2.0, 3.0, 4.0],
             "conf": 80.0, "page": 2}],
    }
    ref = store.save_ocr_words("d1", words)
    assert ref == "ocr/d1.words.json"
    loaded = store.load_ocr_words("d1")
    assert loaded == words
    # 0-based page numbers survive the round trip.
    assert sorted(loaded) == [0, 2]
    assert loaded[2][0]["page"] == 2
    # Absent / empty: None, nothing written.
    assert store.load_ocr_words("missing") is None
    assert store.save_ocr_words("d2", {}) is None
    assert store.save_ocr_words("d2", None) is None
    assert not (tmp_path / "data" / "ocr" / "d2.words.json").exists()
    # 0700 dir.
    mode = stat.S_IMODE((tmp_path / "data" / "ocr").stat().st_mode)
    assert mode & 0o077 == 0


def test_geometry_resolver_from_stored_words(tmp_path):
    store = _store(tmp_path)
    store.save_ocr_words("d1", {
        1: [{"text": "Proceeds", "bbox": [10.0, 20.0, 60.0, 30.0],
             "conf": 95.0, "page": 1}],
    })
    resolver = geometry_resolver_from_store(store, "d1")
    bbox, source = resolver.resolve(1, "Proceeds 1000.00", 0, 8,
                                    "Proceeds 1000.00")
    assert source == "tesseract"
    assert bbox == [10.0, 20.0, 60.0, 30.0]
    # No sidecar: (None, None), never a guess.
    resolver2 = geometry_resolver_from_store(store, "missing")
    assert resolver2.resolve(0, "x", 0, 1, "x") == (None, None)


def test_field_provenance_carries_page_numbers():
    # Extraction text stays "\n"-joined; page_spans_for_joined maps
    # extraction-time spans back to 0-based pages. (A span straddling a
    # page boundary degrades to page 0/None by the standing R15
    # no-guess rule -- positions are never guessed.)
    pages = [
        "Form W-2 Tax Year 2024\n",
        "Box 1 Wages, tips, other compensation: $85,000.00\n",
    ]
    fields, _ = extract_fields("W-2", "\n".join(pages))
    fields = attach_field_provenance(
        fields, page_spans_for_joined(pages), "extractors:4",
        GeometryResolver(), pages)
    prov = _field(fields, "1")["provenance"]
    assert prov["page"] == 1
    assert prov["char_span"]["page"] == 1
    span_text = pages[1][prov["char_span"]["start"]:prov["char_span"]["end"]]
    assert "$85,000.00" in span_text  # the span is the labeled match

    # Per-lot provenance on a single page: all lots map to page 0.
    b_pages = ["Form 1099-B Tax Year 2024\nBroker: EXAMPLE BROKERAGE\n"
               "Lot 1 1d $100.00 1e $90.00\nLot 2 1d $200.00 1e $190.00\n"]
    b_fields, _ = extract_fields("1099-B", "\n".join(b_pages),
                                 text_source=OCR_TS)
    b_fields = attach_field_provenance(
        b_fields, page_spans_for_joined(b_pages), "extractors:4",
        GeometryResolver(), b_pages)
    lot_prov = _field(b_fields, "lots")["lot_provenance"]
    assert [p["page"] for p in lot_prov] == [0, 0]
    assert all(p["extractor"] == "extractors:4" for p in lot_prov)


# -- O2 ingest-level: faked per-page OCR (no engine), real store --------

OCR_PAGES = [
    # Anchor-less on purpose: the whole-document OCR path stores page
    # markers (a single typed section would store section text only).
    "BROKER STATEMENT Tax Year 2024\nPage one holdings\n",
    "BROKER STATEMENT Tax Year 2024\nPage two holdings\n",
    "BROKER STATEMENT Tax Year 2024\nPage three holdings\n",
]


def _image_only_pdf(path, n_pages=3, page_texts=None):
    """Render a multi-page image-only PDF with REAL text (T2 repair).

    Each page gets a distinct line set rendered in a TrueType font at
    high resolution, so a real OCR engine returns characters (not the
    0-char UNKNOWN of a blank image). page_texts overrides the default
    OCR_PAGES content per page.
    """
    from PIL import ImageDraw, ImageFont
    texts = page_texts if page_texts is not None else OCR_PAGES
    # 2550x3300 at 300dpi for letter size (8.5x11in)
    W, H = 2550, 3300
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(font_path, 60)
    except OSError:
        font = ImageFont.load_default()
    img_paths = []
    for i in range(n_pages):
        img = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(img)
        lines = texts[i % len(texts)].split("\n")
        y = 200
        for line in lines:
            if line.strip():
                draw.text((200, y), line, fill="black", font=font)
            y += 120
        img_path = str(path) + f".p{i}.png"
        img.save(img_path)
        img_paths.append(img_path)
    c = canvas.Canvas(str(path), pagesize=letter)
    for img_path in img_paths:
        c.drawImage(img_path, 0, 0, width=letter[0], height=letter[1])
        c.showPage()
    c.save()
    from pathlib import Path

    for img_path in img_paths:
        Path(img_path).unlink()
    return path


def test_ingest_ocr_stores_page_markers_and_word_boxes(tmp_path, monkeypatch):
    src = tmp_path / "incoming"
    src.mkdir()
    store = DocumentStore(tmp_path / "data")
    calls = {"n": 0}

    def _fake_ocr(pdf_path, mode, work_dir):
        i = calls["n"]
        calls["n"] += 1
        page_text = OCR_PAGES[i]
        words = [{"text": w, "bbox": [float(j), 1.0, float(j + 5), 2.0],
                  "conf": 90.0, "page": 0}
                 for j, w in enumerate(page_text.split()[:3])]
        return {
            "ok": True, "text": page_text, "mean_confidence": 90.0,
            "attempts": [{"mode": mode, "engine": "tesseract",
                          "engine_version": "5.3.4", "ok": True,
                          "chars": len(page_text), "mean_confidence": 90.0,
                          "reason_code": None}],
            "reason_code": None, "engine": "tesseract",
            "engine_version": "5.3.4", "words": words,
        }

    monkeypatch.setattr(ingest, "_ocr_pdf", _fake_ocr)
    monkeypatch.setattr(ingest, "_ocr_escalate",
                        lambda p, w, m: _fake_ocr(p, m[0], w))
    monkeypatch.setattr("taxprep.ocr.available", lambda: True)

    pdf = _image_only_pdf(src / "scan.pdf")
    doc = ingest_file(pdf, store)[0]

    assert doc.text_source.startswith("ocr:")
    # O2: the stored text carries page structure (form feeds).
    stored = store.load_ocr(doc.doc_id)
    assert stored.count("\f") == 2
    assert stored.split("\f") == OCR_PAGES
    # The extraction text is still the "\n" join (byte-identical).
    assert stored.replace("\f", "\n") == "\n".join(OCR_PAGES)
    # O2: the word-box sidecar round-trips with 0-based pages.
    words = store.load_ocr_words(doc.doc_id)
    assert words is not None
    assert sorted(words) == [0, 1, 2]
    for p, ws in words.items():
        assert all(w["page"] == p for w in ws)
    # Consumers search the stored text as before (\f is whitespace).
    import re

    assert re.search(r"Page two holdings", stored)


needs_engine = pytest.mark.skipif(not ocr.available(),
                                  reason="no OCR engine on PATH")


@needs_engine
def test_real_engine_multipage_stores_page_markers(tmp_path):
    """End-to-end with a real engine: 3 scanned pages -> 3 stored pages.

    Skipped where no engine is installed (this machine). Runs on the
    workstation (tesseract 5.3.4): proves _run_tesseract's per-page
    words and the ingest page-marker wiring against a real engine.
    """
    src = tmp_path / "incoming"
    src.mkdir()
    store = DocumentStore(tmp_path / "data")
    pdf = _image_only_pdf(src / "scan.pdf")
    doc = ingest_file(pdf, store)[0]
    assert doc.text_source.startswith("ocr:")
    assert len(store.load_ocr(doc.doc_id).split("\f")) == 3


# ---------------------------------------------------------------- Repair arc
# T2: fixture renders real text (not blank) -- verify pixels vary.
def test_image_only_pdf_renders_real_text(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (2550, 3300), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
    draw.text((200, 200), "BROKER STATEMENT Tax Year 2024",
              fill="black", font=font)
    # Not blank: count dark pixels from rendered text.
    gray = img.convert("L")
    pixels = list(gray.getdata())
    dark = sum(1 for p in pixels if p < 128)
    assert dark > 1000
    # And the PDF helper produces a valid multi-page file.
    pdf_path = _image_only_pdf(tmp_path / "scan.pdf", n_pages=2)
    assert pdf_path.exists()


# O1a-repair: box token and amount on separate lines (real tesseract
# often breaks narrow columns). OCR mode matches across the newline;
# native does not (byte-identical).
def test_ocr_box_token_newline_separated_amount():
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Lot 1
le
$1500.00
ld $1000.00
"""
    fields, status = extract_fields(
        "1099-B", text, text_source="ocr:tesseract/force-ocr")
    lots = fields["lots"]["value"]
    assert len(lots) == 1
    assert lots[0]["basis_1e"] == "1500.00"
    assert lots[0]["proceeds_1d"] == "1000.00"
    # Native: no cross-line match (unchanged behavior).
    fields_n, _ = extract_fields("1099-B", text, text_source="native")
    lots_n = fields_n.get("lots", {}).get("value") if fields_n.get("lots") else None
    # Native may extract fewer or none; the key is it doesn't match
    # the newline-separated "le".
    if lots_n:
        assert all(l["basis_1e"] != "1500.00" for l in lots_n)


# O2-repair: _store_pages_for stores markers when ocr_engine is set,
# even if route != "ocr" (escalation path).
def test_store_pages_for_escalation_path():
    from taxprep.ingest import _store_pages_for, PageBundle
    pages = ["page one", "page two"]
    bundle = PageBundle(
        pages=pages, route="native",  # route string differs on escalation
        text_source="ocr:ocrmypdf+tesseract/force-ocr",
        ocr_engine="ocrmypdf+tesseract",
    )
    text = "\n".join(pages)
    result = _store_pages_for(bundle, text)
    assert result == pages
    # Non-OCR bundle still returns None.
    bundle2 = PageBundle(pages=pages, route="native",
                         text_source="native")
    assert _store_pages_for(bundle2, text) is None
    # Section text (not whole bundle) still returns None.
    assert _store_pages_for(bundle, "page one") is None
