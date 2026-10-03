"""Tests for the visual validation UI (Phase 2). Synthetic fixtures only."""

from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error

import pytest

from taxprep.models import Document
from taxprep.review import (
    apply_validation,
    highlight_ocr,
    make_server,
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
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


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
    })
    assert code == 200 and resp == {"ok": True}
    doc = DocumentStore(store.data_dir).get("int-bank-2024")
    assert doc.status == "validated"
    assert doc.fields["box1_interest"]["value"] == "420.00"  # Decimal-safe string, never float
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
