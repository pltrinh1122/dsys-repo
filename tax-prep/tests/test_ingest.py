"""Ingest tests (wave-2 workstream F): R4 stable identity + non-destructive
re-ingest, R5 gate, R6 intake/accounting, R8 positional payer keys.

All fixtures synthetic (reportlab PDFs, PIL images, plain text).
"""

import hashlib
import shutil
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep import extractors, ingest
from taxprep.ingest import (
    RC_ENCRYPTED,
    RC_HEIC_UNSUPPORTED,
    RC_IMAGE_SUPPORT_MISSING,
    RC_NEEDS_OCR,
    RC_UNSUPPORTED_TYPE,
    ingest_dir,
    ingest_file,
    source_doc_id,
)
from taxprep.models import Document
from taxprep.store import DocumentStore

W2_TEXT = (
    "Form W-2 Wage and Tax Statement\n"
    "Tax Year 2024\n"
    "Box 1 Wages, tips, other compensation $10,000.00\n"
    "Box 2 Federal income tax withheld $1,500.00\n"
)

WAGE_TRANSCRIPT = (
    "WAGE AND INCOME TRANSCRIPT Tax Year 2024\n"
    "Payer: ACME CORPORATION 12-3456789\n"
    "Form W-2\n"
    "Box 1 Wages: $85,000.00\n"
    "Box 2 Withheld: $12,340.00\n"
    "Payer: EXAMPLE BANK\n"
    "Form 1099-INT\n"
    "Box 1 Interest: $420.50\n"
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _pdf(path: Path, text: str) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 720
    for line in text.splitlines():
        c.drawString(72, y, line)
        y -= 16
    c.save()
    return path


def _image(path: Path, size=(400, 400)) -> Path:
    Image.new("RGB", size, "white").save(str(path))
    return path


@pytest.fixture()
def iso(tmp_path):
    src = tmp_path / "incoming"
    src.mkdir()
    data = tmp_path / "data"
    return {"src": src, "store": DocumentStore(data)}


# -- R4: stable identity -----------------------------------------------------

def test_doc_id_derives_from_source_bytes_not_filename(iso):
    a = _write(iso["src"] / "return_a.txt", W2_TEXT)
    b = _write(iso["src"] / "totally-different-name.txt", W2_TEXT)
    da, db = ingest_file(a, iso["store"])[0], ingest_file(b, iso["store"])[0]
    assert da.doc_id == db.doc_id
    assert da.doc_id == hashlib.sha256(W2_TEXT.encode()).hexdigest()[:16]
    assert len(da.doc_id) == 16
    # different bytes -> different id
    c = _write(iso["src"] / "return_a.txt", W2_TEXT + "x")
    dc = ingest_file(c, iso["store"])[0]
    assert dc.doc_id != da.doc_id


def test_rename_file_keeps_doc_id(iso):
    a = _write(iso["src"] / "old-name.txt", W2_TEXT)
    d1 = ingest_file(a, iso["store"])[0]
    a.rename(iso["src"] / "new-name.txt")
    d2 = ingest_file(iso["src"] / "new-name.txt", iso["store"])[0]
    assert d1.doc_id == d2.doc_id
    assert len(iso["store"]) == 1  # no duplicate


def test_validate_then_reingest_preserves_validation(iso):
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    doc = ingest_file(src, iso["store"])[0]
    # operator validates (confirms the extracted values as-is)
    doc.status = "validated"
    doc.validated_at = "2026-10-03T00:00:00+00:00"
    validated_fields = {k: dict(v) for k, v in doc.fields.items()}
    iso["store"].upsert(doc)

    again = ingest_file(src, iso["store"])[0]
    assert again.status == "validated"
    assert again.validated_at == "2026-10-03T00:00:00+00:00"
    assert again.fields == validated_fields
    assert again.re_review is False
    assert len(iso["store"]) == 1


def test_numeric_string_correction_agrees_with_float_extraction(iso):
    # Operator corrections are Decimal-safe strings; the extractor yields
    # floats -- agreement is numeric, so this must NOT flag re_review.
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    doc = ingest_file(src, iso["store"])[0]
    doc.status = "validated"
    doc.fields["1"]["value"] = "10000.00"
    iso["store"].upsert(doc)
    again = ingest_file(src, iso["store"])[0]
    assert again.status == "validated"
    assert again.re_review is False
    assert again.fields["1"]["value"] == "10000.00"  # operator edit kept


def test_reingest_disagreement_keeps_validated_values_flags_rereview(
        iso, monkeypatch):
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    doc = ingest_file(src, iso["store"])[0]
    doc.status = "validated"
    validated_value = doc.fields["1"]["value"]
    iso["store"].upsert(doc)

    # re-extraction (e.g. better OCR sidecar) disagrees on a value.
    # Disagreement is only reachable through a derivation change: same
    # bytes always re-derive identically (I2 no-op), so the disagreeing
    # extractor rides a version bump (I6).
    def _disagree(form_type, text, year):
        fields = {"1": {"value": "99999.99", "confidence": "high",
                        "raw_text": ""}}
        return fields, "transcribed"

    monkeypatch.setattr(ingest, "_extract_for_type", _disagree)
    monkeypatch.setattr(extractors, "EXTRACTOR_VERSION", "9")
    again = ingest_file(src, iso["store"])[0]
    # R13: disagreement moves validated -> rereview (validated values
    # kept); it no longer stays "validated".
    assert again.status == "rereview"
    assert again.fields["1"]["value"] == validated_value  # kept
    assert again.re_review is True
    assert again.status_reason == "extraction-disagrees"


def test_sidecar_text_attaches_to_same_doc_id(iso):
    pdf = _pdf(iso["src"] / "scan.pdf", "Form W-2\nTax Year 2024\n")
    d1 = ingest_file(pdf, iso["store"])[0]
    first_id = d1.doc_id

    # the OCR sidecar arrives later: same source bytes -> same doc_id,
    # provenance recorded, no duplicate record
    (iso["src"] / "scan.txt").write_text(W2_TEXT, encoding="utf-8")
    rep = ingest_dir(iso["src"], iso["store"])
    assert len(iso["store"]) == 1
    d2 = iso["store"].get(first_id)
    assert d2 is not None
    # R15/P1: text_source names the sidecar that was actually used
    assert d2.text_source == "sidecar:scan.txt"
    assert "Box 1 Wages" in iso["store"].load_ocr(first_id)
    assert rep.files_seen == 1  # the sidecar is claimed, not a 2nd file


def test_child_ids_compose_from_source_hash(iso):
    text = ("Form 1099-INT Interest Income\n1 Interest income $10.00\n"
            "Tax Year 2024\n"
            "Form 1099-DIV Dividends and Distributions\n"
            "1a Total ordinary dividends $20.00\n")
    src = _write(iso["src"] / "consolidated.txt", text)
    docs = ingest_file(src, iso["store"])
    assert len(docs) == 2
    parent_hash = source_doc_id(text.encode())
    # <bytes-hash>-p<page_range>-<section-hash>; unique per section even
    # though both sections sit on page "1" of the single-page text
    assert len({d.doc_id for d in docs}) == 2
    assert all(d.doc_id.startswith(f"{parent_hash}-p1-") for d in docs)
    assert all(d.parent_doc_id == parent_hash for d in docs)
    assert all(d.page_range == "1" for d in docs)


# -- R8: positional payer keys -----------------------------------------------

def test_transcript_payer_keys_are_positional(iso):
    src = _write(iso["src"] / "wage.txt", WAGE_TRANSCRIPT)
    doc = ingest_file(src, iso["store"])[0]
    assert doc.form_type == "WAGE_INCOME_TRANSCRIPT"
    codes = set(doc.fields)
    # no payer name embedded in any key
    assert not any("ACME" in c or "EXAMPLE" in c for c in codes)
    assert "payer1.1" in codes and "payer2.1" in codes
    # the name survives as a VALUE on payerN.name
    assert doc.fields["payer1.name"]["value"] == "ACME CORPORATION"
    assert doc.fields["payer2.name"]["value"] == "EXAMPLE BANK"


# -- R5: gate -----------------------------------------------------------------

def test_encrypted_pdf_is_blocked(iso):
    pdf = iso["src"] / "enc.pdf"
    _pdf(pdf, W2_TEXT)
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("secret")
    with open(pdf, "wb") as fh:
        writer.write(fh)

    doc = ingest_file(pdf, iso["store"])[0]
    assert doc.status == "BLOCKED"
    assert doc.reason_code == RC_ENCRYPTED
    assert doc.status_reason == RC_ENCRYPTED
    assert doc.fields == {}
    assert doc.encryption is None  # X1: only user-password PDFs land here


def _owner_only_pdf(path: Path, text: str, algorithm: str) -> Path:
    """Synthetic owner-password-only PDF: empty user password unlocks it."""
    _pdf(path, text)
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="", owner_password="synthetic-owner",
                   algorithm=algorithm)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-128", "AES-256"])
def test_owner_password_only_pdf_ingests_with_provenance(iso, algorithm):
    # X1: owner-only PDFs proceed like ordinary PDFs; the encryption
    # provenance is recorded on the Document (operational metadata).
    pdf = _owner_only_pdf(iso["src"] / f"owner-{algorithm}.pdf", W2_TEXT,
                          algorithm)
    doc = ingest_file(pdf, iso["store"])[0]
    assert doc.status != "BLOCKED"
    assert doc.encryption == "owner-only"
    assert "Box 1 Wages" in iso["store"].load_ocr(doc.doc_id)
    # store round-trip preserves the new field (from_dict)
    assert iso["store"].get(doc.doc_id).encryption == "owner-only"


def test_owner_only_pdf_crosses_mcp_boundary_as_metadata(iso):
    # X1: encryption rides with the other R5 provenance keys (non-PII).
    from taxprep import mcp_server
    pdf = _owner_only_pdf(iso["src"] / "owner-mcp.pdf", W2_TEXT, "AES-128")
    doc = ingest_file(pdf, iso["store"])[0]
    view = mcp_server._scrub_doc(doc.to_dict())
    assert view["encryption"] == "owner-only"


def test_form_field_pdf_extracts_values(iso):
    pdf = iso["src"] / "fillable.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 740, "Form W-2 Wage and Tax Statement Tax Year 2024")
    c.acroForm.textfield(name="box1_wages", x=72, y=700, width=200,
                         height=20, value="12345")
    c.save()

    doc = ingest_file(pdf, iso["store"])[0]
    assert doc.text_source == "form-field"
    assert "box1_wages: 12345" in iso["store"].load_ocr(doc.doc_id)


def test_garbled_text_triggers_ocr_route(iso, monkeypatch):
    # a text layer of (cid:) runs with no engine -> BLOCKED needs-ocr.
    # Engine discovery (taxprep.ocr.available, consulted by
    # ingest._pdf_page_bundle) is mocked absent so this holds where a
    # real engine (tesseract) is installed too.
    monkeypatch.setattr("taxprep.ocr.available", lambda: False)
    garbled = ("Form W-2 (cid:72)(cid:73)(cid:74) " * 40).strip()
    pdf = _pdf(iso["src"] / "garbled.pdf", garbled)
    doc = ingest_file(pdf, iso["store"])[0]
    assert doc.status == "BLOCKED"
    assert doc.reason_code == RC_NEEDS_OCR


def test_ocr_path_records_provenance(iso, monkeypatch):
    png = _image(iso["src"] / "photo.png")

    def _fake_ocr(pdf_path, mode, work_dir):
        return {
            "ok": True,
            "text": W2_TEXT,
            "mean_confidence": 87.5,
            "attempts": [{"mode": mode, "engine": "tesseract",
                          "engine_version": "5.3.4", "ok": True,
                          "chars": len(W2_TEXT), "mean_confidence": 87.5,
                          "reason_code": None}],
            "reason_code": None,
            "engine": "tesseract",
            "engine_version": "5.3.4",
        }

    monkeypatch.setattr(ingest, "_ocr_pdf", _fake_ocr)
    monkeypatch.setattr(ingest, "_ocr_escalate",
                        lambda p, w, m: _fake_ocr(p, m[0], w))
    monkeypatch.setattr("taxprep.ocr.available", lambda: True)

    doc = ingest_file(png, iso["store"])[0]
    # R15: text_source names the engine and mode actually used
    assert doc.text_source == f"ocr:tesseract/{doc.ocr_mode}"
    assert doc.text_source.startswith("ocr:")
    assert doc.ocr_engine == "tesseract"
    assert doc.engine_version == "5.3.4"
    assert doc.ocr_mode in ("skip-text", "redo-ocr", "force-ocr")
    assert doc.attempts and doc.attempts[0]["mode"] == doc.ocr_mode
    assert doc.mean_confidence == 87.5
    assert doc.form_type == "W-2"
    assert "Box 1 Wages" in iso["store"].load_ocr(doc.doc_id)
    # converted PDF lives under the data dir; the original is untouched
    assert (iso["store"].data_dir / "converted").is_dir()
    assert Image.open(png).size == (400, 400)


def test_image_without_engine_is_blocked_needs_ocr(iso, monkeypatch):
    png = _image(iso["src"] / "photo.png")
    monkeypatch.setattr("taxprep.ocr.available", lambda: False)
    doc = ingest_file(png, iso["store"])[0]
    assert doc.status == "BLOCKED"
    assert doc.reason_code == RC_NEEDS_OCR
    assert doc.status_reason == RC_NEEDS_OCR
    assert doc.fields == {}


# -- R6: intake + accounting ----------------------------------------------------

def test_uppercase_extension_ingested(iso):
    src = _write(iso["src"] / "W2.PDF", "x")
    _pdf(src, W2_TEXT)
    docs = ingest_file(src, iso["store"])
    assert len(docs) == 1
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.files_seen == 1 and rep.ingested == 1


def test_unsupported_type_skipped_with_reason(iso):
    _write(iso["src"] / "notes.docx", "not a tax doc")
    _write(iso["src"] / "w2.txt", W2_TEXT)
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.files_seen == 2
    assert rep.ingested == 1
    assert rep.skipped == [{"file": "notes.docx",
                            "reason_code": RC_UNSUPPORTED_TYPE}]
    assert rep.errored == []
    assert len(rep.docs) == 1


def test_errored_uses_reason_code_not_exception_text(iso, monkeypatch):
    _write(iso["src"] / "w2.txt", W2_TEXT)

    def _boom(*a, **k):
        raise RuntimeError(" Kaboom: /secret/path exploded ")

    monkeypatch.setattr(ingest, "_build_documents", _boom)
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.files_seen == 1
    assert rep.errored == [{"file": "w2.txt",
                            "reason_code": "extract-failed"}]
    # no exception text anywhere in the accounting or the stored text
    blob = repr(rep.summary())
    assert "Kaboom" not in blob and "secret" not in blob
    err_doc = rep.docs[0]
    # R13: the error route is its own lifecycle state (was needs_review).
    assert err_doc.status == "errored"
    assert err_doc.status_reason == "extract-failed"
    assert "Kaboom" not in iso["store"].load_ocr(err_doc.doc_id)


def test_image_support_missing_fails_closed(iso, monkeypatch):
    _image(iso["src"] / "photo.png")
    monkeypatch.setattr(ingest, "_pil_image", lambda: None)
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.skipped == [{"file": "photo.png",
                            "reason_code": RC_IMAGE_SUPPORT_MISSING}]
    assert len(iso["store"]) == 0  # fail closed: no phantom document


def test_heic_without_heif_support_skipped(iso):
    (iso["src"] / "photo.heic").write_bytes(b"not-a-real-heic")
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.skipped == [{"file": "photo.heic",
                            "reason_code": RC_HEIC_UNSUPPORTED}]


def test_split_children_count_under_source_file(iso):
    text = ("Form 1099-INT Interest Income\n1 Interest income $10.00\n"
            "Tax Year 2024\n"
            "Form 1099-DIV Dividends and Distributions\n"
            "1a Total ordinary dividends $20.00\n")
    _write(iso["src"] / "consolidated.txt", text)
    _write(iso["src"] / "w2.txt", W2_TEXT)
    rep = ingest_dir(iso["src"], iso["store"])
    assert rep.files_seen == 2
    assert rep.ingested == 2          # children count under their file
    assert len(rep.docs) == 3
    s = rep.summary()
    assert s["files_seen"] == s["ingested"] + len(s["skipped"]) + \
        len(s["errored"])


def test_report_backward_compat_len_and_iter(iso):
    _write(iso["src"] / "w2.txt", W2_TEXT)
    rep = ingest_dir(iso["src"], iso["store"])
    assert len(rep) == 1
    assert [d.form_type for d in rep] == ["W-2"]


# -- sync / ORPHANED --------------------------------------------------------------
# (sync behavior lives in tests/test_sync.py; the unit seam is imported
# here only for the report-shape assertions above)


# -- D4/R15: return-transcript fields carry verbatim raw_text -----------------

def test_transcript_fields_carry_verbatim_raw_text():
    text = ("TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
            "Adjusted Gross Income: $85,420.00\n"
            "Total Tax: $12,340.00\n")
    fields, status = ingest._fields_from_transcript(
        "RETURN_TRANSCRIPT", text, 2024)
    assert fields["agi"]["value"] == "85420.00"
    assert fields["agi"]["raw_text"] == "Adjusted Gross Income: $85,420.00"
    assert fields["total_tax"]["raw_text"] == "Total Tax: $12,340.00"
    assert status == "transcribed"


# -- R17: account-transcript + record-of-account branches -------------------

ACCOUNT_TEXT = ("TAX ACCOUNT TRANSCRIPT\nTax Year: 2024\n"
                "Account Balance: $1,234.56\n"
                "Accrued Interest: $12.34 as of 09/22/2025\n"
                "150 Tax return filed 20241205 04-15-2025 $1,234.56\n"
                "846 Refund issued 20243207 10-05-2025 $384.56\n")

ROA_TEXT = ("RECORD OF ACCOUNT\nTax Year: 2024\n"
            "TAX RETURN TRANSCRIPT\n"
            "Adjusted Gross Income: $85,420.00\n"
            "150 Tax return filed 04-15-2025 $12,340.00\n"
            "TAX ACCOUNT TRANSCRIPT\n"
            "Account Balance: $0.00\n"
            "846 Refund issued 20243207 10-05-2025 $0.00\n")


def test_account_transcript_fields_branch():
    fields, status = ingest._fields_from_transcript(
        "ACCOUNT_TRANSCRIPT", ACCOUNT_TEXT, 2024)
    # balance/accrual lines: derived confidence, verbatim raw_text (R15)
    assert fields["account_balance"]["value"] == "1234.56"
    assert fields["account_balance"]["confidence"] == "high"
    assert fields["account_balance"]["raw_text"] == \
        "Account Balance: $1,234.56"
    # the extraction span addresses the verbatim line in the input text
    span = fields["account_balance"].pop("_extract_span")
    assert ACCOUNT_TEXT[span[0]:span[1]] == "Account Balance: $1,234.56"
    assert fields["accrued_interest"]["value"] == "12.34"
    assert fields["accrued_interest"]["confidence"] == "high"
    # tc_<code> transaction fields: verbatim raw line (R15/P3), never the
    # code/date/amount-stripped description
    tc150 = fields["tc_150"]
    assert tc150["value"] == "1234.56"
    assert tc150["confidence"] == "medium"
    assert tc150["raw_text"] == \
        "150 Tax return filed 20241205 04-15-2025 $1,234.56"
    span = tc150.pop("_extract_span")
    assert ACCOUNT_TEXT[span[0]:span[1]] == tc150["raw_text"]
    assert fields["tc_846"]["value"] == "384.56"
    assert "_unparsed_lines" not in fields
    assert status == "transcribed"


def test_account_transcript_fields_needs_review():
    fields, status = ingest._fields_from_transcript(
        "ACCOUNT_TRANSCRIPT", ACCOUNT_TEXT + "mystery footer\n", 2024)
    assert fields["_unparsed_lines"]["value"] == ["mystery footer"]
    assert fields["_unparsed_lines"]["confidence"] == "low"
    assert status == "needs_review"


def test_roa_fields_merge_both_sections_with_provenance():
    fields, status = ingest._fields_from_transcript(
        "RECORD_OF_ACCOUNT", ROA_TEXT, 2024)
    # R15: raw_text is the verbatim source line (never a synthesized
    # "section: <raw>" tag); section provenance rides the extraction
    # span, which addresses the verbatim line in the input text.
    assert fields["agi"]["value"] == "85420.00"
    assert fields["agi"]["raw_text"] == \
        "Adjusted Gross Income: $85,420.00"
    assert fields["agi"]["confidence"] == "high"
    span = fields["agi"].pop("_extract_span")
    assert ROA_TEXT[span[0]:span[1]] == fields["agi"]["raw_text"]
    assert fields["account_balance"]["value"] == "0.00"
    assert fields["account_balance"]["raw_text"] == \
        "Account Balance: $0.00"
    span = fields["account_balance"].pop("_extract_span")
    assert ROA_TEXT[span[0]:span[1]] == "Account Balance: $0.00"
    # tc_<code> fields from both sections, verbatim raw lines
    assert fields["tc_150"]["raw_text"] == \
        "150 Tax return filed 04-15-2025 $12,340.00"
    span = fields["tc_150"].pop("_extract_span")
    assert ROA_TEXT[span[0]:span[1]] == fields["tc_150"]["raw_text"]
    assert fields["tc_846"]["raw_text"] == \
        "846 Refund issued 20243207 10-05-2025 $0.00"
    span = fields["tc_846"].pop("_extract_span")
    assert ROA_TEXT[span[0]:span[1]] == fields["tc_846"]["raw_text"]
    assert status == "transcribed"


def test_roa_fields_top_level_unparsed_needs_review():
    text = ROA_TEXT.replace("Tax Year: 2024\n",
                            "Tax Year: 2024\nSome cover-page notice\n")
    fields, status = ingest._fields_from_transcript(
        "RECORD_OF_ACCOUNT", text, 2024)
    assert fields["_unparsed_lines"]["value"] == ["Some cover-page notice"]
    assert status == "needs_review"
    # sections still merged
    assert fields["agi"]["value"] == "85420.00"
    assert fields["account_balance"]["value"] == "0.00"


def test_roa_fields_section_unparsed_tagged():
    text = ROA_TEXT.replace("TAX ACCOUNT TRANSCRIPT\n",
                            "TAX ACCOUNT TRANSCRIPT\nmystery acct line\n")
    fields, status = ingest._fields_from_transcript(
        "RECORD_OF_ACCOUNT", text, 2024)
    # R15: unparsed lines stay verbatim (no synthesized section tag);
    # the span locates the line in the input text.
    assert fields["_unparsed_lines"]["value"] == ["mystery acct line"]
    span = fields["_unparsed_lines"].pop("_extract_span")
    assert text[span[0]:span[1]] == "mystery acct line"
    assert status == "needs_review"


# -- R17 integration: TRANSCRIPT_FORMS routes the new forms end to end --------

def test_account_transcript_ingests_end_to_end(iso):
    # R17: reachable through _extract_for_type (TRANSCRIPT_FORMS), not just
    # direct _fields_from_transcript calls — classification + routing.
    src = _write(iso["src"] / "account-transcript-2024.txt", ACCOUNT_TEXT)
    doc = ingest_file(src, iso["store"])[0]
    assert doc.form_type == "ACCOUNT_TRANSCRIPT"
    assert doc.status == "transcribed"
    assert doc.fields["account_balance"]["value"] == "1234.56"
    assert doc.fields["tc_150"]["value"] == "1234.56"
    assert doc.fields["tc_846"]["value"] == "384.56"


def test_record_of_account_ingests_end_to_end(iso):
    src = _write(iso["src"] / "record-of-account-2024.txt", ROA_TEXT)
    doc = ingest_file(src, iso["store"])[0]
    assert doc.form_type == "RECORD_OF_ACCOUNT"
    assert doc.status == "transcribed"
    # both sections present; R15: verbatim raw_text + real char_spans
    # (the transient _extract_span is replaced by provenance at ingest)
    assert doc.fields["agi"]["value"] == "85420.00"  # D2: Decimal-safe strings
    assert doc.fields["agi"]["raw_text"] == \
        "Adjusted Gross Income: $85,420.00"
    prov = doc.fields["agi"]["provenance"]
    assert prov["extractor"] == "transcript:2"
    cs = prov["char_span"]
    assert cs["page"] == 0
    assert ROA_TEXT[cs["start"]:cs["end"]] == \
        "Adjusted Gross Income: $85,420.00"
    assert "_extract_span" not in doc.fields["agi"]
    assert doc.fields["tc_846"]["value"] == "0.00"
    assert doc.fields["tc_846"]["raw_text"] == \
        "846 Refund issued 20243207 10-05-2025 $0.00"
    cs = doc.fields["tc_846"]["provenance"]["char_span"]
    assert ROA_TEXT[cs["start"]:cs["end"]] == \
        doc.fields["tc_846"]["raw_text"]
