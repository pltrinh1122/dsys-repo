"""Tests for the visual validation UI (Phase 2). Synthetic fixtures only."""

from __future__ import annotations

import json
import re
import shutil
import threading
import http.client
import urllib.request
import urllib.error
from urllib.parse import urlparse

import pytest

from taxprep.models import Document
from taxprep.review import (
    ValidationRefused,
    apply_validation,
    evidence_status,
    highlight_ocr,
    make_server,
    queue_html,
)
from taxprep.store import DocumentStore

W2_OCR = """Form W-2 Wage and Tax Statement 2024
Employer: Acme Corp EIN 12-3456789
Employee: Jane Doe SSN 000-00-0000
Box 1 Wages 85000.00
Box 2 Federal income tax withheld 12750.00
Box 5 Medicare wages 85000.00
"""

INT_OCR = """Form 1099-INT Interest Income 2024
Payer: First Bank
Box 1 Interest income 412.55
"""


def _fixture_store(tmp_path) -> DocumentStore:
    store = DocumentStore(tmp_path / "data")
    w2 = Document(
        doc_id="w2-acme-2024",
        tax_year=2024,
        form_type="W-2",
        source_path="/tmp/w2.pdf",
        ocr_text_ref="",
        fields={
            "box1_wages": {"value": 85000.0, "confidence": "high",
                           "raw_text": "Box 1 Wages 85000.00"},
            "box2_withheld": {"value": 12750.0, "confidence": "medium",
                              "raw_text": "Box 2 Federal income tax withheld 12750.00"},
            "employer_ein": {"value": "12-3456789", "confidence": "low",
                             "raw_text": "EIN 12-3456789"},
        },
        status="transcribed",
    )
    w2.ocr_text_ref = store.save_ocr(w2.doc_id, W2_OCR)
    store.upsert(w2)
    i1099 = Document(
        doc_id="int-bank-2024",
        tax_year=2024,
        form_type="1099-INT",
        source_path="/tmp/i.txt",
        ocr_text_ref="",
        fields={
            "box1_interest": {"value": 412.55, "confidence": "high",
                              "raw_text": "Box 1 Interest income 412.55"},
        },
        status="needs_review",
    )
    i1099.ocr_text_ref = store.save_ocr(i1099.doc_id, INT_OCR)
    store.upsert(i1099)
    done = Document(
        doc_id="w2-old-2023",
        tax_year=2023,
        form_type="W-2",
        source_path="/tmp/o.txt",
        ocr_text_ref="",
        fields={},
        status="validated",
    )
    done.ocr_text_ref = store.save_ocr(done.doc_id, "old")
    store.upsert(done)
    # refusal-case fixtures: text sources with saved OCR so the evidence
    # gate passes and each refusal test isolates its own reason codes
    empty = Document(
        doc_id="empty-2025",
        tax_year=2025,
        form_type="W-2",
        source_path="/tmp/e.txt",
        ocr_text_ref="",
        fields={},
        status="transcribed",
    )
    empty.ocr_text_ref = store.save_ocr(empty.doc_id, "empty doc")
    store.upsert(empty)
    unknown = Document(
        doc_id="unknown-form-2025",
        tax_year=2025,
        form_type="UNKNOWN",
        source_path="/tmp/u.txt",
        ocr_text_ref="",
        fields={"box1_x": {"value": "10", "confidence": "high",
                           "raw_text": "Box 1 10"}},
        status="transcribed",
    )
    unknown.ocr_text_ref = store.save_ocr(unknown.doc_id, "unknown form text")
    store.upsert(unknown)
    noyear = Document(
        doc_id="noyear-2025",
        tax_year=None,
        form_type="W-2",
        source_path="/tmp/n.txt",
        ocr_text_ref="",
        fields={"box1_y": {"value": "20", "confidence": "high",
                           "raw_text": "Box 1 20"}},
        status="transcribed",
    )
    noyear.ocr_text_ref = store.save_ocr(noyear.doc_id, "no year text")
    store.upsert(noyear)
    return store


@pytest.fixture()
def server(tmp_path):
    store = _fixture_store(tmp_path)
    srv = make_server(store, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}", store
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _post(url: str, payload: dict) -> tuple[int, dict]:
    # R10: POSTs must carry the loopback Origin, like the review page's
    # fetch() does; without it the server 403s.
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _split_base(base: str) -> tuple[str, int]:
    parts = urlparse(base)
    return parts.hostname, parts.port


def _raw_request(base: str, target: str, method: str = "GET",
                 headers: dict | None = None,
                 data: bytes | None = None) -> tuple[int, str]:
    """Full-control request: Host/Origin/Content-Type are sent exactly as
    given. Omit "Host" from headers to send no Host at all (urllib always
    sends one, so http.client with skip_host is used here)."""
    host, port = _split_base(base)
    conn = http.client.HTTPConnection(host, port)
    hdrs = dict(headers or {})
    host_hdr = hdrs.pop("Host", None)
    conn.putrequest(method, target, skip_host=True)
    if host_hdr is not None:
        conn.putheader("Host", host_hdr)
    for k, v in hdrs.items():
        conn.putheader(k, v)
    if data is not None and not any(k.lower() == "content-length"
                                    for k in hdrs):
        # endheaders(body) does not set this itself; without it the
        # server reads Content-Length: 0 and sees an empty body
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    conn.close()
    return resp.status, body


def _raw_get(base: str, target: str = "/",
             headers: dict | None = None) -> tuple[int, str]:
    return _raw_request(base, target, "GET", headers)


def _good_post_headers(base: str, **overrides) -> dict:
    """Valid R10 POST headers; overrides replace or (value None) remove."""
    _host, port = _split_base(base)
    hdrs = {"Host": f"127.0.0.1:{port}",
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}"}
    for k, v in overrides.items():
        if v is None:
            hdrs.pop(k, None)
        else:
            hdrs[k] = v
    return hdrs


VALIDATE_PAYLOAD = {
    "doc_id": "int-bank-2024",
    "fields": {"box1_interest": "420.00"},
    "confirmed": ["box1_interest"],
    "confirm_form_type": True,
    "confirm_tax_year": True,
}


# -- highlighting ---------------------------------------------------

def test_highlight_marks_raw_spans():
    out = highlight_ocr(W2_OCR, {
        "a": {"raw_text": "Box 1 Wages 85000.00"},
        "b": {"raw_text": ""},
    })
    assert "<mark>Box 1 Wages 85000.00</mark>" in out
    assert "EIN 12-3456789" in out  # unmatched text survives unmarked


def test_highlight_escapes_html():
    out = highlight_ocr("<b>Box 1</b> Wages 5", {"a": {"raw_text": "Box 1"}})
    assert "<b>" not in out and "&lt;b&gt;" in out
    assert "<mark>Box 1</mark>" in out


# -- queue page -----------------------------------------------------

def test_queue_lists_pending_docs(server):
    base, _store = server
    code, body = _get(base + "/")
    assert code == 200
    assert "w2-acme-2024" in body
    assert "int-bank-2024" in body
    assert "w2-old-2023" not in body  # validated docs leave the queue


def test_queue_progress_header(server):
    base, _store = server
    _code, body = _get(base + "/")
    assert "2024: 0/2 validated" in body
    assert "2023: 1/1 validated" in body


def test_queue_year_filter(server):
    base, _store = server
    _code, body = _get(base + "/?tax_year=2023")
    assert "w2-acme-2024" not in body
    assert "int-bank-2024" not in body


def test_queue_form_filter(server):
    base, _store = server
    _code, body = _get(base + "/?form_type=1099-INT")
    assert "int-bank-2024" in body
    assert "w2-acme-2024" not in body


# -- review page ----------------------------------------------------

def test_review_page_field_table(server):
    base, _store = server
    code, body = _get(base + "/doc/w2-acme-2024")
    assert code == 200
    assert "box1_wages" in body
    assert "85000.0" in body
    assert "b-low" in body      # low-confidence badge present
    assert "b-high" in body
    assert "<mark>" in body     # source spans highlighted


def test_review_page_unknown_doc(server):
    base, _store = server
    code, _body = _get(base + "/doc/nope")
    assert code == 404


# -- validate API ---------------------------------------------------

def test_validate_updates_store(server):
    base, store = server
    code, resp = _post(base + "/api/validate", {
        "doc_id": "int-bank-2024",
        "fields": {"box1_interest": "420.00"},
        "confirmed": ["box1_interest"],
        "confirm_form_type": True,
        "confirm_tax_year": True,
    })
    assert code == 200 and resp == {"ok": True}
    doc = DocumentStore(store.data_dir).get("int-bank-2024")
    assert doc.status == "validated"
    assert doc.fields["box1_interest"]["value"] == "420.00"  # Decimal-safe string, never float
    hist = doc.fields["box1_interest"]["history"]
    assert len(hist) == 1 and hist[0]["old"] == 412.55 and hist[0]["new"] == "420.00"
    assert hist[0]["ts"]
    assert doc.validated_at is not None


def test_validate_unknown_doc_404(server):
    base, _store = server
    code, resp = _post(base + "/api/validate", {"doc_id": "nope"})
    assert code == 404 and resp["ok"] is False


def test_apply_validation_rejects_unknown_doc(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(KeyError):
        apply_validation(store, "nope", {}, [])


# -- binding ----------------------------------------------------------

def test_refuses_non_loopback_bind(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValueError):
        make_server(store, port=0, host="0.0.0.0")


def test_binds_loopback_only(server):
    base, _store = server
    host = base.split("://")[1].rsplit(":", 1)[0]
    assert host == "127.0.0.1"


# -- fail-closed refusal gates --------------------------------------

def test_refuse_empty_fields(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "empty-2025", {}, [],
                         confirm_form_type=True, confirm_tax_year=True)
    assert ei.value.reasons == ["empty_fields", "nothing_confirmed"]
    assert store.get("empty-2025").status != "validated"  # never flipped


def test_refuse_unknown_form(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "unknown-form-2025", {}, ["box1_x"],
                         confirm_form_type=True, confirm_tax_year=True)
    assert "unknown_form" in ei.value.reasons
    assert store.get("unknown-form-2025").status != "validated"  # never flipped


def test_refuse_missing_year(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "noyear-2025", {}, ["box1_y"],
                         confirm_form_type=True, confirm_tax_year=True)
    assert ei.value.reasons == ["missing_year"]
    assert store.get("noyear-2025").status != "validated"  # never flipped


def test_refuse_nothing_confirmed(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "int-bank-2024", {}, [],
                         confirm_form_type=True, confirm_tax_year=True)
    assert ei.value.reasons == ["nothing_confirmed"]
    assert store.get("int-bank-2024").status != "validated"  # never flipped


def test_refuse_unconfirmed_identity(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "int-bank-2024",
                         {"box1_interest": "412.55"}, [])
    assert ei.value.reasons == ["unconfirmed_form", "unconfirmed_year"]
    assert store.get("int-bank-2024").status != "validated"  # never flipped


def test_refuse_invalid_form_correction(tmp_path):
    store = _fixture_store(tmp_path)
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "int-bank-2024", {}, ["box1_interest"],
                         form_type="NOPE", confirm_tax_year=True)
    assert ei.value.reasons == ["invalid_form_type"]
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "int-bank-2024", {}, ["box1_interest"],
                         form_type="UNKNOWN", confirm_tax_year=True)
    assert ei.value.reasons == ["invalid_form_type"]


def test_refuse_invalid_year_correction(tmp_path):
    store = _fixture_store(tmp_path)
    for bad in ("abc", 1800, 2200, True):
        with pytest.raises(ValidationRefused) as ei:
            apply_validation(store, "int-bank-2024", {}, ["box1_interest"],
                             tax_year=bad, confirm_form_type=True)
        assert ei.value.reasons == ["invalid_tax_year"], bad
    assert store.get("int-bank-2024").status != "validated"  # never flipped


# -- form_type / tax_year confirm-or-correct --------------------------

def test_correct_unknown_form(tmp_path):
    store = _fixture_store(tmp_path)
    doc = apply_validation(store, "unknown-form-2025", {}, ["box1_x"],
                           form_type="W-2", confirm_tax_year=True)
    assert doc.status == "validated"
    assert doc.form_type == "W-2"
    hist = doc.fields["__form_type__"]["history"]
    assert len(hist) == 1
    assert hist[0]["old"] == "UNKNOWN" and hist[0]["new"] == "W-2"
    assert hist[0]["ts"]


def test_correct_missing_year(tmp_path):
    store = _fixture_store(tmp_path)
    doc = apply_validation(store, "noyear-2025", {}, ["box1_y"],
                           tax_year=2025, confirm_form_type=True)
    assert doc.status == "validated"
    assert doc.tax_year == 2025
    hist = doc.fields["__tax_year__"]["history"]
    assert len(hist) == 1
    assert hist[0]["old"] is None and hist[0]["new"] == 2025


def test_correct_year_accepts_digit_string(tmp_path):
    store = _fixture_store(tmp_path)
    doc = apply_validation(store, "noyear-2025", {}, ["box1_y"],
                           tax_year="2025", confirm_form_type=True)
    assert doc.tax_year == 2025 and isinstance(doc.tax_year, int)


# -- add a missing box / lot ------------------------------------------

def test_add_missing_box(tmp_path):
    store = _fixture_store(tmp_path)
    doc = apply_validation(store, "int-bank-2024", {"box2_new": "50.25"}, [],
                           confirm_form_type=True, confirm_tax_year=True)
    assert doc.status == "validated"
    f = doc.fields["box2_new"]
    assert f["value"] == "50.25"            # Decimal-safe string, never float
    assert f["confidence"] == "human-corrected"
    assert len(f["history"]) == 1
    assert f["history"][0]["old"] is None and f["history"][0]["new"] == "50.25"


def test_add_box_satisfies_empty_fields(tmp_path):
    store = _fixture_store(tmp_path)
    doc = apply_validation(store, "empty-2025", {"box1_wages": "1000"}, [],
                           confirm_form_type=True, confirm_tax_year=True)
    assert doc.status == "validated"
    assert doc.fields["box1_wages"]["value"] == "1000"


# -- audit trail ------------------------------------------------------

def test_audit_trail_appends_history(tmp_path):
    store = _fixture_store(tmp_path)
    kw = dict(confirm_form_type=True, confirm_tax_year=True)
    apply_validation(store, "int-bank-2024",
                     {"box1_interest": "420.00"}, ["box1_interest"], **kw)
    doc = apply_validation(store, "int-bank-2024",
                           {"box1_interest": "421.00"}, ["box1_interest"], **kw)
    hist = doc.fields["box1_interest"]["history"]
    assert len(hist) == 2  # appended, never overwritten
    assert hist[0]["old"] == 412.55 and hist[0]["new"] == "420.00"
    assert hist[1]["old"] == "420.00" and hist[1]["new"] == "421.00"
    assert all(h["ts"] for h in hist)


def test_audit_trail_survives_store_roundtrip(tmp_path):
    store = _fixture_store(tmp_path)
    apply_validation(store, "int-bank-2024", {"box1_interest": "420.00"},
                     ["box1_interest"],
                     confirm_form_type=True, confirm_tax_year=True)
    doc2 = DocumentStore(store.data_dir).get("int-bank-2024")
    hist = doc2.fields["box1_interest"]["history"]
    assert hist[0]["old"] == 412.55 and hist[0]["new"] == "420.00"


# -- HTTP: 422 with reason codes --------------------------------------

def test_validate_refused_422(server):
    base, store = server
    code, resp = _post(base + "/api/validate",
                       {"doc_id": "empty-2025", "fields": {}, "confirmed": []})
    assert code == 422
    assert resp["ok"] is False
    assert resp["error"] == "validation_refused"
    assert "empty_fields" in resp["reasons"]
    assert store.get("empty-2025").status == "transcribed"


def test_validate_with_identity_corrections(server):
    base, store = server
    code, resp = _post(base + "/api/validate", {
        "doc_id": "unknown-form-2025",
        "fields": {"box9_added": "7.50"},
        "confirmed": ["box1_x"],
        "form_type": "W-2",
        "confirm_tax_year": True,
    })
    assert code == 200 and resp == {"ok": True}
    doc = DocumentStore(store.data_dir).get("unknown-form-2025")
    assert doc.form_type == "W-2"
    assert doc.status == "validated"
    assert doc.fields["box9_added"]["confidence"] == "human-corrected"
    assert doc.fields["__form_type__"]["history"][0]["old"] == "UNKNOWN"


def test_validate_refused_422_bad_year(server):
    base, _store = server
    code, resp = _post(base + "/api/validate", {
        "doc_id": "noyear-2025",
        "fields": {}, "confirmed": ["box1_y"],
        "confirm_form_type": True, "tax_year": "not-a-year",
    })
    assert code == 422
    assert "invalid_tax_year" in resp["reasons"]


# -- review page: identity controls + evidence banner ------------------

def test_review_page_identity_controls(server):
    base, _store = server
    code, body = _get(base + "/doc/int-bank-2024")
    assert code == 200
    assert 'id="formType"' in body
    assert 'id="taxYear"' in body
    assert 'id="formChk"' in body and 'id="yearChk"' in body
    assert "confirm_form_type" in body      # client mirrors the server gate
    assert "__form_type__" not in body      # bookkeeping never rendered


def test_review_page_blocks_validation_without_images(server):
    base, _store = server
    # w2-acme-2024 points at a PDF that does not exist -> degraded evidence
    code, body = _get(base + "/doc/w2-acme-2024")
    assert code == 200
    assert "BLOCKED" in body
    assert "evidenceBlocked = true" in body


def test_queue_counts_exclude_bookkeeping(tmp_path):
    store = _fixture_store(tmp_path)
    doc = store.get("int-bank-2024")
    doc.fields["__form_type__"] = {"value": "W-2", "history": []}
    store.upsert(doc)
    body = queue_html(store, None, None)
    m = re.search(
        r"int-bank-2024</a></td><td>2024</td><td>1099-INT</td>"
        r"<td>needs_review</td><td>([^<]+)</td><td>(\d+)</td>", body)
    assert m and m.group(2) == "1"  # bookkeeping rows excluded from count


# -- page-image evidence (fail closed) ---------------------------------

def _make_pdf_bytes(pages: int) -> bytes:
    """Minimal valid multi-page PDF (synthetic fixture, no reportlab)."""
    out = [b"%PDF-1.4\n"]
    offsets = {}

    def obj(num: int, body: bytes):
        offsets[num] = sum(len(x) for x in out)
        out.append(str(num).encode() + b" 0 obj\n" + body + b"\nendobj\n")

    nums = iter(range(1, 3 + pages * 3))
    next(nums)
    next(nums)
    triples = [(next(nums), next(nums), next(nums)) for _ in range(pages)]
    kids = " ".join(f"{p} 0 R" for p, _, _ in triples)
    obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for i, (p, c, f) in enumerate(triples):
        obj(p, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {c} 0 R /Resources << /Font << /F1 {f} 0 R >> >> >>"
             .encode())
        stream = f"BT /F1 24 Tf 72 720 Td (Page {i + 1}) Tj ET".encode()
        obj(c, f"<< /Length {len(stream)} >>\nstream\n".encode()
               + stream + b"\nendstream")
        obj(f, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    xref_pos = sum(len(x) for x in out)
    n = max(offsets) + 1
    out.append(f"xref\n0 {n}\n".encode())
    out.append(b"0000000000 65535 f \n")
    for num in range(1, n):
        out.append(f"{offsets[num]:010d} 00000 n \n".encode())
    out.append(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n"
               f"{xref_pos}\n%%EOF\n".encode())
    return b"".join(out)


def _needs_renderer():
    pytest.importorskip("pdf2image")
    if shutil.which("pdftoppm") is None:
        pytest.skip("pdftoppm (poppler-utils) not available")


def _pdf_doc(tmp_path, pages=2, **kw):
    store = DocumentStore(tmp_path / "data")
    pdf = tmp_path / "src.pdf"
    pdf.write_bytes(_make_pdf_bytes(pages))
    doc = Document(doc_id=kw.pop("doc_id", "pdfdoc"),
                   tax_year=2024, form_type="W-2",
                   source_path=str(pdf), ocr_text_ref="",
                   fields={"a": {"value": "1", "confidence": "high"}},
                   status="transcribed", **kw)
    doc.ocr_text_ref = store.save_ocr(doc.doc_id, "page one page two")
    store.upsert(doc)
    return store, doc


def test_render_all_pages(tmp_path):
    _needs_renderer()
    import taxprep.review as review
    store, doc = _pdf_doc(tmp_path, pages=2)
    assert evidence_status(store, doc)["mode"] == "images"
    images, error = review._pdf_page_images(doc)
    assert error is None
    assert len(images) == 2  # ALL pages, not a max_pages cap


def test_page_range_passed_to_renderer(tmp_path, monkeypatch):
    import taxprep.review as review
    seen = {}

    def spy(path, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(review, "_convert_from_path", spy)
    store, doc = _pdf_doc(tmp_path, pages=3)
    doc.page_range = (2, 3)  # split document's page range
    images, error = review._pdf_page_images(doc)
    assert error is None and images == []
    assert seen["first_page"] == 2 and seen["last_page"] == 3


def test_degraded_evidence_blocks_validation(tmp_path, monkeypatch):
    import taxprep.review as review

    def boom(path, **kwargs):
        raise RuntimeError("poppler exploded")

    monkeypatch.setattr(review, "_convert_from_path", boom)
    store, doc = _pdf_doc(tmp_path)
    assert evidence_status(store, doc)["mode"] == "degraded"
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, doc.doc_id, {}, ["a"],
                         confirm_form_type=True, confirm_tax_year=True)
    assert ei.value.reasons == ["degraded_evidence"]
    assert store.get(doc.doc_id).status != "validated"  # never flipped
    panel, blocked = review._source_evidence_html(store, doc)
    assert blocked is True and "BLOCKED" in panel


def test_missing_pdf2image_is_degraded(tmp_path, monkeypatch):
    import taxprep.review as review
    monkeypatch.setattr(review, "_convert_from_path", None)
    store, doc = _pdf_doc(tmp_path)
    assert evidence_status(store, doc)["mode"] == "degraded"


def test_unavailable_evidence_blocks_validation(tmp_path):
    store = DocumentStore(tmp_path / "data")
    doc = Document(doc_id="gone", tax_year=2024, form_type="W-2",
                   source_path=str(tmp_path / "missing.pdf"),
                   ocr_text_ref="",  # no OCR saved either
                   fields={"a": {"value": "1", "confidence": "high"}},
                   status="transcribed")
    store.upsert(doc)
    assert evidence_status(store, doc)["mode"] == "unavailable"
    with pytest.raises(ValidationRefused) as ei:
        apply_validation(store, "gone", {}, ["a"],
                         confirm_form_type=True, confirm_tax_year=True)
    assert "evidence_unavailable" in ei.value.reasons
    assert store.get("gone").status != "validated"  # never flipped


def test_text_source_needs_no_images(tmp_path):
    store = _fixture_store(tmp_path)
    doc = store.get("int-bank-2024")  # .txt source with saved OCR
    assert evidence_status(store, doc)["mode"] == "text"
    out = apply_validation(store, "int-bank-2024", {}, ["box1_interest"],
                           confirm_form_type=True, confirm_tax_year=True)
    assert out.status == "validated"


# -- R10: request hardening (falsification survivor fixes) ------------

def test_host_allowlist_rejects_attacker_host_get(server):
    base, _store = server
    _host, port = _split_base(base)
    code, _body = _raw_get(base, "/", {"Host": f"attacker.example:{port}"})
    assert code == 403  # DNS-rebinding precondition killed


def test_host_allowlist_rejects_attacker_host_post(server):
    base, _store = server
    _host, port = _split_base(base)
    code, body = _raw_request(
        base, "/api/validate", "POST",
        {"Host": f"attacker.example:{port}",
         "Content-Type": "application/json",
         "Origin": f"http://127.0.0.1:{port}"},
        json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 403  # host gate runs before any route logic


def test_host_allowlist_rejects_missing_host(server):
    base, _store = server
    code, _body = _raw_get(base, "/")  # no Host header at all
    assert code == 403


def test_host_allowlist_accepts_localhost(server):
    base, _store = server
    _host, port = _split_base(base)
    code, body = _raw_get(base, "/", {"Host": f"localhost:{port}"})
    assert code == 200
    assert "Review queue" in body


def test_post_text_plain_rejected_415(server):
    # the falsification's exact hostile case: simple-request CSRF shape
    base, _store = server
    hdrs = _good_post_headers(base, **{"Content-Type": "text/plain"})
    code, body = _raw_request(base, "/api/validate", "POST", hdrs,
                              json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 415
    assert json.loads(body)["error"] == "unsupported_media_type"


def test_post_missing_content_type_rejected_415(server):
    base, _store = server
    hdrs = _good_post_headers(base, **{"Content-Type": None})
    code, _body = _raw_request(base, "/api/validate", "POST", hdrs,
                               json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 415


def test_post_missing_origin_403(server):
    base, _store = server
    hdrs = _good_post_headers(base, **{"Origin": None})
    code, body = _raw_request(base, "/api/validate", "POST", hdrs,
                              json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 403
    assert json.loads(body)["error"] == "forbidden_origin"


def test_post_foreign_origin_403(server):
    base, _store = server
    hdrs = _good_post_headers(base, Origin="http://attacker.example")
    code, body = _raw_request(base, "/api/validate", "POST", hdrs,
                              json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 403
    assert json.loads(body)["error"] == "forbidden_origin"


def test_post_null_origin_403(server):
    base, _store = server
    hdrs = _good_post_headers(base, Origin="null")
    code, _body = _raw_request(base, "/api/validate", "POST", hdrs,
                               json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 403


def test_post_origin_wrong_port_403(server):
    base, _store = server
    hdrs = _good_post_headers(base, Origin="http://127.0.0.1:1")
    code, _body = _raw_request(base, "/api/validate", "POST", hdrs,
                               json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 403


def test_post_localhost_origin_ok(server):
    base, _store = server
    _host, port = _split_base(base)
    hdrs = _good_post_headers(base, Origin=f"http://localhost:{port}")
    code, body = _raw_request(base, "/api/validate", "POST", hdrs,
                              json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 200
    assert json.loads(body) == {"ok": True}


# -- R10: optional per-run URL token ----------------------------------

@pytest.fixture()
def token_server(tmp_path):
    store = _fixture_store(tmp_path)
    srv = make_server(store, port=0, token="sekret")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}", store, "sekret"
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def test_token_mode_root_without_token_404(token_server):
    base, _store, _tok = token_server
    _host, port = _split_base(base)
    code, _body = _raw_get(base, "/", {"Host": f"127.0.0.1:{port}"})
    assert code == 404


def test_token_mode_wrong_token_404(token_server):
    base, _store, _tok = token_server
    _host, port = _split_base(base)
    code, _body = _raw_get(base, "/t/wrong/", {"Host": f"127.0.0.1:{port}"})
    assert code == 404


def test_token_mode_post_without_token_404(token_server):
    base, _store, _tok = token_server
    hdrs = _good_post_headers(base)
    code, _body = _raw_request(base, "/api/validate", "POST", hdrs,
                               json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 404


def test_token_mode_correct_token_queue_200(token_server):
    base, _store, tok = token_server
    _host, port = _split_base(base)
    code, body = _raw_get(base, f"/t/{tok}/", {"Host": f"127.0.0.1:{port}"})
    assert code == 200
    assert "Review queue" in body
    assert f"/t/{tok}/doc/" in body  # internal links carry the token prefix


def test_token_mode_correct_token_post_200(token_server):
    base, store, tok = token_server
    hdrs = _good_post_headers(base)
    code, body = _raw_request(base, f"/t/{tok}/api/validate", "POST", hdrs,
                              json.dumps(VALIDATE_PAYLOAD).encode())
    assert code == 200
    assert json.loads(body) == {"ok": True}
    assert store.get("int-bank-2024").status == "validated"


def test_token_mode_host_check_still_applies(token_server):
    base, _store, tok = token_server
    _host, port = _split_base(base)
    code, _body = _raw_get(base, f"/t/{tok}/",
                           {"Host": f"attacker.example:{port}"})
    assert code == 403


def test_token_mode_default_off(server):
    # no token: plain routes work as before
    base, _store = server
    code, _body = _get(base + "/")
    assert code == 200


def _run_serve_forever_banner(tmp_path, monkeypatch, **kwargs):
    import taxprep.review as review
    store = _fixture_store(tmp_path)
    holder = {}
    monkeypatch.setattr(review.ThreadingHTTPServer, "serve_forever",
                        lambda self: holder.setdefault("server", self))
    review.serve_forever(store, port=0, **kwargs)
    holder["server"].server_close()
    return holder


def test_token_printed_at_startup(tmp_path, capsys, monkeypatch):
    _run_serve_forever_banner(tmp_path, monkeypatch, token="tokABC")
    out = capsys.readouterr().out
    assert "http://127.0.0.1:" in out
    assert "/t/tokABC/" in out  # full tokenized URL in the banner


def test_token_autogenerated_when_flag_bare(tmp_path, capsys, monkeypatch):
    _run_serve_forever_banner(tmp_path, monkeypatch, token=True)
    out = capsys.readouterr().out
    m = re.search(r"/t/([A-Za-z0-9_-]{16,})/", out)
    assert m, out  # auto-generated token printed in the banner URL


def test_resolve_token_semantics():
    from taxprep.review import _resolve_token
    assert _resolve_token(None) is None
    assert _resolve_token("sekret") == "sekret"
    a, b = _resolve_token(True), _resolve_token("")
    assert a and b and a != b  # auto-generated, unique per call
