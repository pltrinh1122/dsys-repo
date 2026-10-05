"""Tests for B3 (console doc-view memory) + the lot-table pager.

Synthetic fixtures only. No wall-clock or RSS assertions -- the memory
acceptance (doc view < 300ms, RSS growth < 50MB) is structural: the
pane renders a bounded lot window and the page viewer never
pre-renders. What we assert here:

* the lot table renders exactly one window (100) of per-lot sub-rows,
  never all 2000;
* prev/next navigation links are server-rendered plain ?lot_page=N;
* lot numbering stays document-wide (stable row ids across windows);
* the lots FIELD row itself always renders;
* review._page_viewer_html invokes evidence.render_page at most once
  per doc-view request (no eager pre-render);
* ?lot_page=N threads from the console doc URL into the pane.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

import pytest

from taxprep import console as C
from taxprep import evidence as E
from taxprep import evidence_pane as EP
from taxprep import review as R
from taxprep.carryforward import tag_lot_gain_loss
from taxprep.models import Document
from taxprep.store import DocumentStore

GEOM = {"page": 0, "bbox_pdf": [100.0, 690.0, 260.0, 705.0],
        "bbox_source": "pdfplumber", "char_span": None,
        "extractor": "pdfplumber:0.11"}


def _make_pdf(path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(100.0, 700.0, "Box 1 Wages 85000.00")
    c.showPage()
    c.save()


def _ev_store(tmp_path):
    store = DocumentStore(tmp_path / "data")
    pdf_path = tmp_path / "ev.pdf"
    _make_pdf(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    store.store_bronze_bytes(sha, pdf_bytes)
    return store, sha


def _syn_lot(i: int):
    lot = {"description": None, "date_acquired": "01/15/2024",
           "date_sold": "06/20/2024",
           "proceeds_1d": f"{1000 + i}.00",
           "basis_1e": f"{900 + i}.00",
           "wash_1g": "0.00",
           "accrued_market_discount_1f": None, "fed_withheld_4": None,
           "term": "short", "covered": "covered"}
    lot["gain_loss"] = tag_lot_gain_loss(lot)
    assert lot["gain_loss"] is not None
    return lot


def _b1099_doc(store, sha, n_lots: int, doc_id="b-b3-2024"):
    lots = [_syn_lot(i) for i in range(n_lots)]
    doc = Document(
        doc_id=doc_id, tax_year=2024, form_type="1099-B",
        source_path="b.pdf", ocr_text_ref="", status="transcribed",
        fields={
            "lots": {"value": lots, "confidence": "high",
                     "raw_text": "synthetic lots", "geometry": dict(GEOM)},
            "broker": {"value": "SYNTH BROKER", "confidence": "high",
                       "raw_text": "Broker: SYNTH", "geometry": dict(GEOM)},
        })
    doc.source_sha256 = sha
    doc.ocr_text_ref = store.save_ocr(
        doc_id, "Form 1099-B synthetic fixture\n")
    store.upsert(doc)
    return doc


def _lot_row_ids(html: str) -> list[str]:
    """Row ids of the rendered per-lot sub-rows, in order."""
    import re
    return re.findall(r'id="row-(lots\.lot\d+\.gain_loss)"', html)


# -- lot-table pagination ------------------------------------------------

def test_lot_table_default_window_renders_100_not_all(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    html = EP.pane_html(store, doc)
    ids = _lot_row_ids(html)
    assert len(ids) == 100, f"expected one 100-lot window, got {len(ids)}"
    assert ids[0] == "lots.lot1.gain_loss"
    assert ids[-1] == "lots.lot100.gain_loss"
    # The 101st lot is NOT rendered eagerly.
    assert 'id="row-lots.lot101.gain_loss"' not in html
    # The lots FIELD row itself stays.
    assert 'id="row-lots"' in html
    # Server-rendered pager, plain links, no JS framework.
    assert 'href="?lot_page=1"' in html
    assert 'href="?lot_page=0"' not in html  # prev disabled on page 0


def test_lot_table_second_window(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    html = EP.pane_html(store, doc, lot_page=1)
    ids = _lot_row_ids(html)
    assert len(ids) == 100
    # Document-wide numbering: stable row ids across windows.
    assert ids[0] == "lots.lot101.gain_loss"
    assert ids[-1] == "lots.lot200.gain_loss"
    assert 'id="row-lots.lot100.gain_loss"' not in html
    assert 'href="?lot_page=0"' in html  # prev
    assert 'href="?lot_page=2"' in html  # next
    assert 'id="row-lots"' in html  # the field row stays


def test_lot_table_last_window_partial(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    html = EP.pane_html(store, doc, lot_page=2)
    ids = _lot_row_ids(html)
    assert len(ids) == 50
    assert ids[0] == "lots.lot201.gain_loss"
    assert ids[-1] == "lots.lot250.gain_loss"
    assert 'href="?lot_page=1"' in html
    assert 'href="?lot_page=3"' not in html  # next disabled on last page


def test_lot_page_clamps_out_of_range(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    html = EP.pane_html(store, doc, lot_page=99)
    ids = _lot_row_ids(html)
    # Clamped to the last window -- never an empty page.
    assert len(ids) == 50
    assert ids[0] == "lots.lot201.gain_loss"
    html = EP.pane_html(store, doc, lot_page=-3)
    assert len(_lot_row_ids(html)) == 100  # negative clamps to 0


def test_small_lot_table_has_no_pager(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 2)
    html = EP.pane_html(store, doc)
    ids = _lot_row_ids(html)
    assert ids == ["lots.lot1.gain_loss", "lots.lot2.gain_loss"]
    assert '<tr class="lotnav">' not in html  # everything fits: no pager row


def test_lot_window_keeps_lineage_subrows(tmp_path):
    # The windowed sub-rows are still the LINEAGE-1 lineage view --
    # formula + input links anchored to the parent lots row, never
    # "no visual evidence".
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 150)
    html = EP.pane_html(store, doc)
    assert html.count('class="lineage"') == 100
    assert 'href="#row-lots"' in html
    assert "no visual evidence" not in html


# -- page viewer: no eager pre-render --------------------------------------

def test_page_viewer_invokes_render_page_exactly_once(tmp_path, monkeypatch):
    calls: list[int] = []

    def spy(store_, doc_, page_0based: int, dpi: int = 110):
        calls.append(page_0based)
        return None, "spy-no-render"

    monkeypatch.setattr(E, "render_page", spy)
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 3)
    # Directly exercise the viewer: the ONLY render it may trigger is
    # the first page (the commit render); every other page is a lazy
    # <img> the browser fetches on scroll.
    R._page_viewer_html(store, doc, "")
    assert calls == [0]


def test_pane_html_renders_at_most_one_page(tmp_path, monkeypatch):
    calls: list[int] = []

    def spy(store_, doc_, page_0based: int, dpi: int = 110):
        calls.append(page_0based)
        return None, "spy-no-render"

    monkeypatch.setattr(E, "render_page", spy)
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    EP.pane_html(store, doc)
    assert len(calls) <= 1


# -- console threading -----------------------------------------------------

def test_console_doc_url_threads_lot_page(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    parsed = urlparse(f"/console/doc/{doc.doc_id}?lot_page=1")
    html = C.dispatch_get(store, parsed, None)
    assert html is not None
    ids = _lot_row_ids(html)
    assert len(ids) == 100
    assert ids[0] == "lots.lot101.gain_loss"
    # Invalid lot_page degrades to 0, never raises.
    parsed = urlparse(f"/console/doc/{doc.doc_id}?lot_page=bogus")
    html = C.dispatch_get(store, parsed, None)
    assert len(_lot_row_ids(html)) == 100


def test_console_doc_review_html_lot_page_kwarg(tmp_path):
    store, sha = _ev_store(tmp_path)
    doc = _b1099_doc(store, sha, 250)
    html = C.doc_review_html(store, doc, None, lot_page=2)
    assert html is not None
    ids = _lot_row_ids(html)
    assert len(ids) == 50
    assert ids[-1] == "lots.lot250.gain_loss"
