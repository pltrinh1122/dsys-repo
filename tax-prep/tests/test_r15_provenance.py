"""R15 field provenance probes (P1..P6 falsifications, Arc C workstream W2).

Every probe is a falsification from the spec
(~/workspace/dsys-store/bus/tax-prep.ops/20261003T233654658312-msg_2eb38247ea4a.json):
extracted fields must carry clear provenance to the source document by
path and name. Synthetic fixtures only.
"""
import hashlib
import json
from pathlib import Path

import pytest

from taxprep import ingest, review, verify
from taxprep.models import Document
from taxprep.provenance import words_from_tsv
from taxprep.store import DocumentStore


# -- helpers -----------------------------------------------------------

def _iso(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    return {"src": src, "store": DocumentStore(tmp_path / "data")}


W2_TEXT = ("Form W-2 Wage and Tax Statement 2024\n"
           "Wages, tips, other compensation 85000.00\n"
           "Federal income tax withheld 12750.00\n")


def _native_w2_pdf(path: Path) -> None:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 720
    for line in W2_TEXT.splitlines():
        c.drawString(72, y, line)
        y -= 20
    c.save()


# -- P1: sidecar text_source names the .txt actually used ----------------

def test_p1_sidecar_text_source_names_txt(tmp_path):
    iso = _iso(tmp_path)
    pdf = iso["src"] / "placeholder.pdf"
    _native_w2_pdf(pdf)  # real PDF present, but the sidecar wins
    (iso["src"] / "placeholder.txt").write_text(W2_TEXT)
    report = ingest.ingest_dir(iso["src"], iso["store"])
    assert len(report.docs) == 1
    doc = report.docs[0]
    # P1: not "ocr:..." and not bare "native" -- the .txt is named
    assert doc.text_source == "sidecar:placeholder.txt"


def test_p1_sidecar_relative_to_ingest_root(tmp_path):
    iso = _iso(tmp_path)
    sub = iso["src"] / "sub"
    sub.mkdir()
    pdf = sub / "scan.pdf"
    _native_w2_pdf(pdf)
    (sub / "scan.txt").write_text(W2_TEXT)
    report = ingest.ingest_dir(iso["src"], iso["store"])
    assert report.docs[0].text_source == "sidecar:sub/scan.txt"


# -- P2: source_integrity detects rename and byte-swap ------------------

def test_source_integrity_detects_rename(tmp_path):
    iso = _iso(tmp_path)
    src = iso["src"] / "w2.txt"
    src.write_text(W2_TEXT)
    doc = ingest.ingest_file(src, iso["store"])[0]
    ok = verify.verify_source_integrity(iso["store"])
    assert ok["passed"] is True
    # rename the source: the recorded alias no longer exists
    moved = iso["src"] / "w2-renamed.txt"
    src.rename(moved)
    bad = verify.verify_source_integrity(iso["store"])
    assert bad["passed"] is False
    assert bad["failed"] == [{"doc_ids": [doc.doc_id],
                              "reason_code": "source_missing"}]
    # output carries doc_ids + reason codes only -- never paths
    assert "w2-renamed" not in json.dumps(bad)
    assert str(iso["src"]) not in json.dumps(bad)


def test_source_integrity_detects_byte_swap(tmp_path):
    iso = _iso(tmp_path)
    src = iso["src"] / "w2.txt"
    src.write_text(W2_TEXT)
    doc = ingest.ingest_file(src, iso["store"])[0]
    # same path, different bytes
    src.write_bytes(b"tampered bytes, same path")
    bad = verify.verify_source_integrity(iso["store"])
    assert bad["passed"] is False
    assert bad["failed"] == [{"doc_ids": [doc.doc_id],
                              "reason_code": "hash_mismatch"}]


def test_source_integrity_in_verify_all(tmp_path):
    iso = _iso(tmp_path)
    src = iso["src"] / "w2.txt"
    src.write_text(W2_TEXT)
    ingest.ingest_file(src, iso["store"])
    report = verify.verify_all(iso["store"])
    assert report["checks"]["source_integrity"]["passed"] is True


# -- P3: transcript fields have non-empty verbatim spans with offsets ---

def test_transcript_fields_have_verbatim_spans():
    fields, _status = ingest._fields_from_transcript(
        "WAGE_AND_INCOME", W2_TEXT, 2024)
    assert fields, "expected extracted fields"
    for key, f in fields.items():
        if key.startswith("_"):
            continue
        raw = f.get("raw_text")
        assert isinstance(raw, str) and raw != "", \
            f"{key}: raw_text must never be empty (P3)"
        span = f.get("_extract_span")
        assert span is not None, f"{key}: missing extraction span"
        start, end = span
        assert 0 <= start < end <= len(W2_TEXT), \
            f"{key}: span {span} out of range"
        # the span addresses the verbatim source text -- nothing synthesized
        assert W2_TEXT[start:end] == raw, \
            f"{key}: span does not recover raw_text"


def test_ingested_doc_provenance_shape(tmp_path):
    # after ingest the transient span is replaced by the R15 contract shape
    iso = _iso(tmp_path)
    src = iso["src"] / "w2.txt"
    src.write_text(W2_TEXT)
    doc = ingest.ingest_file(src, iso["store"])[0]
    assert "_extract_span" not in json.dumps(doc.fields)
    for key, f in doc.fields.items():
        if key.startswith("_") or not isinstance(f, dict):
            continue
        prov = f.get("provenance")
        assert prov is not None, f"{key}: missing provenance"
        assert set(prov) == {"page", "bbox_pdf", "bbox_source",
                             "char_span", "extractor"}, \
            f"{key}: provenance shape drifted: {sorted(prov)}"
        cs = prov["char_span"]
        if cs is not None:
            assert set(cs) == {"page", "start", "end"}
            assert 0 <= cs["start"] < cs["end"]
        if prov["bbox_pdf"] is not None:
            assert prov["bbox_source"] in ("pdfplumber", "tesseract",
                                           "acroform")
            x0, y0, x1, y1 = prov["bbox_pdf"]
            assert x0 <= x1 and y0 <= y1
        # .txt source: no layout source, char spans only
        assert prov["bbox_pdf"] is None
        assert prov["bbox_source"] is None
        assert prov["extractor"] == "extractors:3"


# -- P4: highlight marks exactly one span per field ---------------------

def test_highlight_marks_exactly_one_span_per_field():
    text = "amount 100.00 then amount 100.00 again"
    fields = {
        "a": {"provenance": {
            "page": 0, "bbox_pdf": None, "bbox_source": None,
            "char_span": {"page": 0, "start": 7, "end": 13},
            "extractor": "transcript:1"}},
    }
    out = review.highlight_ocr(text, fields)
    assert out.count("<mark>") == 1
    assert "<mark>100.00</mark>" in out
    assert out.count("100.00") == 2  # the other occurrence stays unmarked


# -- P5: edits preserve the original value -----------------------------

def _val_doc(tmp_path):
    store = DocumentStore(tmp_path / "data")
    doc = Document(
        doc_id="d1", tax_year=2024, form_type="W-2",
        source_path="/tmp/d1.txt", ocr_text_ref="",
        fields={"wages": {"value": "85000.00", "confidence": "high",
                          "raw_text": "Wages 85000.00"}},
        status="needs_review")
    doc.ocr_text_ref = store.save_ocr("d1", "Wages 85000.00")
    store.upsert(doc)
    return store


def test_field_edit_preserves_original_value(tmp_path):
    store = _val_doc(tmp_path)
    kw = dict(confirm_form_type=True, confirm_tax_year=True)
    doc = review.apply_validation(store, "d1", {"wages": "85001.00"},
                                  ["wages"], **kw)
    f = doc.fields["wages"]
    assert f["value"] == "85001.00"
    assert f["original_value"] == "85000.00"
    assert f["edited_by"] == "operator"
    assert f["edited_at"]
    assert f["raw_text"] == "Wages 85000.00"  # evidence untouched by edits


def test_identity_edit_preserves_original_value_twice(tmp_path):
    # two successive identity edits: original_value is the FIRST value,
    # history records every edit (R2 {timestamp, old, new} convention)
    store = _val_doc(tmp_path)
    doc = store.get("d1")
    ts = "2026-10-04T00:00:00+00:00"
    review._record_identity_edit(doc, "__form_type__", "W-2", "1099-INT", ts)
    review._record_identity_edit(doc, "__form_type__", "1099-INT", "1099-R",
                                 ts)
    entry = doc.fields["__form_type__"]
    assert entry["value"] == "1099-R"
    assert entry["original_value"] == "W-2"
    assert len(entry["history"]) == 2
    assert entry["history"][0]["old"] == "W-2"
    assert entry["history"][1]["new"] == "1099-R"


# -- geometry sources ---------------------------------------------------

def test_native_pdf_produces_pdfplumber_bbox(tmp_path):
    iso = _iso(tmp_path)
    pdf = iso["src"] / "w2.pdf"
    _native_w2_pdf(pdf)
    doc = ingest.ingest_file(pdf, iso["store"])[0]
    assert doc.text_source == "native"
    prov = doc.fields["1"]["provenance"]
    assert prov["bbox_source"] == "pdfplumber"
    assert prov["bbox_pdf"] is not None
    x0, y0, x1, y1 = prov["bbox_pdf"]
    assert x0 <= x1 and y0 <= y1
    cs = prov["char_span"]
    assert cs["page"] == 0 and cs["start"] < cs["end"]
    # a box the extractor could not find records honest nulls, never a guess
    missing = doc.fields["3"]["provenance"]
    assert missing["bbox_pdf"] is None
    assert missing["bbox_source"] is None
    assert missing["char_span"] is None
    assert missing["extractor"] == "extractors:3"


def test_words_from_tsv_parses_word_boxes():
    header = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
              "left\ttop\twidth\theight\tconf\ttext")
    tsv = "\n".join([
        header,
        "5\t1\t1\t1\t1\t1\t300\t600\t240\t36\t96.0\tWages",
        "5\t1\t1\t1\t1\t2\t600\t600\t300\t36\t95.0\t85000.00",
        "4\t1\t1\t1\t1\t0\t300\t600\t540\t36\t95.0\t",  # line row: skipped
        "5\t1\t1\t1\t1\t3\t0\t0\t10\t10\t-1\t",  # blank: skipped
    ])
    words = words_from_tsv(tsv, page_width_px=2550, page_height_px=3300,
                           dpi=300)
    assert len(words) == 2
    assert words[0]["text"] == "Wages"
    assert words[0]["conf"] == 96.0
    # 300px @300dpi = 72pt; y flipped to bottom-left origin
    x0, y0, x1, y1 = words[0]["bbox"]
    assert (x0, x1) == (72.0, 129.6)
    assert y0 < y1
    assert words[1]["text"] == "85000.00"


def test_acroform_rects_read(tmp_path):
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    pdf = tmp_path / "fillable.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 740, "Fillable test form")
    c.acroForm.textfield(name="wages_box1", x=72, y=700, width=200,
                         height=20, value="85000.00")
    c.save()
    rects = ingest._acroform_rects(PdfReader(str(pdf)))
    assert rects["wages_box1"]["page"] == 0
    assert rects["wages_box1"]["bbox"] == [72.0, 700.0, 272.0, 720.0]


# -- geometry is PII-adjacent: never in blind outputs --------------------

def test_geometry_keys_rejected_by_blind_sweep():
    from tests.test_mcp_server import _pii_free
    with pytest.raises(AssertionError):
        _pii_free({"provenance": {"bbox_pdf": [1, 2, 3, 4],
                                  "bbox_source": "pdfplumber",
                                  "char_span": {"page": 0, "start": 1,
                                                "end": 2}}})
