"""Tests for the R19/R19a source-evidence pane. Synthetic fixtures only.

Covers: geometry consumption (fail-closed), evidence-state
classification, deterministic page rendering + snapshot caching, the
bbox overlay mapping, the blind extraction_yield evidence check, the
review-UI pane + new loopback endpoints (R10-hardened), the
no-evidence confirm gate, and the PII privacy boundary (no image
bytes/paths in MCP tool outputs or bus payloads).
"""

from __future__ import annotations

import hashlib
import http.client
import inspect
import json
import os
import shutil
import stat
import threading
from urllib.parse import quote, urlparse

import pytest

from taxprep import evidence as E
from taxprep import mcp_server as MCP
from taxprep import review as R
from taxprep import verify as V
from taxprep.models import Document
from taxprep.store import DocumentStore

JPEG_MAGIC = b"\xff\xd8\xff"

GEOM = {"page": 0, "bbox_pdf": [100.0, 690.0, 260.0, 705.0],
        "bbox_source": "pdfplumber", "char_span": None,
        "extractor": "pdfplumber:0.11"}


# -- synthetic PDF + store fixtures -----------------------------------

def _make_pdf(path):
    """One-page letter PDF with text at a KNOWN position.

    Returns the expected geometry inputs (bottom-left origin, points).
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    text = "Box 1 Wages 85000.00"
    x, baseline = 100.0, 700.0
    c.drawString(x, baseline, text)
    w = stringWidth(text, "Helvetica", 12)
    c.showPage()
    c.save()
    return {"bbox": [x, baseline - 3.0, x + w, baseline + 12.0],
            "page_w": 612.0, "page_h": 792.0}


@pytest.fixture()
def pstore(tmp_path):
    """Store with one PDF doc linked to immutable bronze bytes.

    box1_wages carries recorded geometry (the sibling contract);
    box9_lonely has none (fail-closed path).
    """
    store = DocumentStore(tmp_path / "data")
    pdf_path = tmp_path / "w2.pdf"
    info = _make_pdf(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    store.store_bronze_bytes(sha, pdf_bytes)
    doc = Document(
        doc_id="w2-ev-2024", tax_year=2024, form_type="W-2",
        source_path=str(pdf_path), ocr_text_ref="", status="transcribed",
        fields={
            "box1_wages": {
                "value": "85000.00", "confidence": "high",
                "raw_text": "Box 1 Wages 85000.00",
                "geometry": {"page": 0, "bbox_pdf": info["bbox"],
                             "bbox_source": "pdfplumber",
                             "char_span": None,
                             "extractor": "pdfplumber:0.11"}},
            "box9_lonely": {
                "value": "100.00", "confidence": "low",
                "raw_text": "Box 9 100.00"},
        })
    doc.source_sha256 = sha
    # OCR text saved so the degraded-evidence path (renderer absent) is
    # reachable: without it a missing renderer reads as "unavailable".
    doc.ocr_text_ref = store.save_ocr(
        doc.doc_id, "Form W-2 synthetic fixture\nBox 1 Wages 85000.00\n")
    store.upsert(doc)
    return store, doc, info, pdf_bytes


def _serve(store, token=None):
    srv = R.make_server(store, port=0, token=token)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _teardown(srv):
    srv.shutdown()
    srv.server_close()


def _raw(srv, target, method="GET", headers=None, data=None):
    host, port = srv.server_address
    conn = http.client.HTTPConnection(host, port, timeout=30)
    hdrs = dict(headers or {})
    host_hdr = hdrs.pop("Host", f"{host}:{port}")
    conn.putrequest(method, target, skip_host=True)
    conn.putheader("Host", host_hdr)
    for k, v in hdrs.items():
        conn.putheader(k, v)
    if data is not None:
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    resp = conn.getresponse()
    body = resp.read()
    ctype = resp.getheader("Content-Type")
    conn.close()
    return resp.status, ctype, body


def _post(srv, target, payload, origin=True, ctype="application/json"):
    host, port = srv.server_address
    headers = {"Content-Type": ctype}
    if origin:
        headers["Origin"] = f"http://{host}:{port}"
    return _raw(srv, target, "POST", headers,
                json.dumps(payload).encode())


# -- A. geometry consumption -------------------------------------------

def test_valid_geometry_accepts_contract_shape():
    assert E.valid_geometry(GEOM) is True
    assert E.field_geometry({"geometry": GEOM}) == GEOM


def test_field_geometry_prefers_provenance_key():
    # The landed R15 producer stores the record under "provenance";
    # the R19 task text named the same shape "geometry". Both are read.
    prov = dict(GEOM, extractor="sibling:9")
    f = {"geometry": GEOM, "provenance": prov}
    assert E.field_geometry(f) == prov
    assert E.field_geometry({"provenance": prov}) == prov
    # bbox_pdf None under either key: no visual evidence, never a guess.
    assert E.field_geometry(
        {"provenance": dict(prov, bbox_pdf=None)}) is None


@pytest.mark.parametrize("bad", [
    {"page": -1}, {"page": True}, {"page": "0"},
    {"bbox_pdf": [10, 10, 5, 30]},          # x0 >= x1
    {"bbox_pdf": [10, 10, 50]},             # wrong length
    {"bbox_pdf": [10, 10, float("nan"), 30]},
    {"bbox_pdf": [10, 10, float("inf"), 30]},
    {"bbox_source": "magic"},
    {"extractor": ""}, {"extractor": None},
    "not-a-dict", None,
])
def test_valid_geometry_rejects_malformed(bad):
    g = dict(GEOM)
    if isinstance(bad, dict):
        g.update(bad)
        assert E.valid_geometry(g) is False
    else:
        assert E.valid_geometry(bad) is False


def test_field_geometry_none_bbox_is_no_evidence():
    # Geometry metadata without a locatable region: fail-closed.
    g = dict(GEOM, bbox_pdf=None)
    assert E.field_geometry({"geometry": g}) is None


def test_field_geometry_absent_is_none():
    assert E.field_geometry({"value": "x"}) is None
    assert E.field_geometry({}) is None


# -- B. evidence-state classification -----------------------------------

def test_state_snapshot():
    ev = E.field_evidence({"value": "1", "geometry": GEOM})
    assert ev["state"] == E.STATE_SNAPSHOT
    assert ev["reason"] is None


def test_state_lineage_and_missing_lineage():
    f = {"computed": True, "formula": "1d - 1e + 1g",
         "inputs": ["proceeds", "cost"]}
    ev = E.field_evidence(f)
    assert ev["state"] == E.STATE_LINEAGE
    assert ev["lineage"] == {"formula": "1d - 1e + 1g",
                             "inputs": ["proceeds", "cost"]}
    for bad in ({"computed": True},
                {"computed": True, "formula": "", "inputs": ["a"]},
                {"computed": True, "formula": "a", "inputs": []}):
        ev = E.field_evidence(bad)
        assert ev["state"] == E.STATE_NO_EVIDENCE
        assert ev["reason"] == E.REASON_NO_LINEAGE


def test_state_edited_needs_geometry_for_original():
    f = {"value": "y", "geometry": GEOM,
         "history": [{"ts": "t", "old": "x", "new": "y"}]}
    assert E.field_evidence(f)["state"] == E.STATE_EDITED
    f2 = {"value": "y",
          "history": [{"ts": "t", "old": "x", "new": "y"}]}
    ev = E.field_evidence(f2)
    assert ev["state"] == E.STATE_NO_EVIDENCE
    assert ev["reason"] == E.REASON_NO_GEOMETRY


def test_state_manual_entry_reason():
    ev = E.field_evidence({"value": "y", "confidence": "human-corrected"})
    assert (ev["state"], ev["reason"]) == (
        E.STATE_NO_EVIDENCE, E.REASON_MANUAL_ENTRY)
    ev = E.field_evidence({"value": "y"})  # plain: no geometry recorded
    assert (ev["state"], ev["reason"]) == (
        E.STATE_NO_EVIDENCE, E.REASON_NO_GEOMETRY)


def test_was_edited_distinguishes_added():
    added = {"value": "y",
             "history": [{"ts": "t", "old": None, "new": "y"}]}
    assert E.was_edited(added) is False
    edited = {"value": "y",
              "history": [{"ts": "t", "old": "x", "new": "y"}]}
    assert E.was_edited(edited) is True


# -- C. rendering, mapping, snapshots ------------------------------------

def test_pdf_to_px_exact_mapping():
    # 72pt box on a 792pt page at 110dpi: hand-computed integers.
    assert E.pdf_to_px([72, 72, 144, 144], 792.0, 110) == (
        110, 990, 220, 1100)


def test_padded_crop_keeps_row_context():
    # Cell 15pt tall -> crop height is 3x (the row stays visible).
    # padded_crop_pt returns (x0, y0, x1, y1) in PDF points.
    crop = E.padded_crop_pt([100, 690, 260, 705], (612.0, 792.0))
    assert abs((crop[3] - crop[1]) - 45.0) < 1e-9
    # x pads 10% of the page width each side.
    assert abs(crop[0] - (100 - 61.2)) < 1e-9
    assert abs(crop[2] - (260 + 61.2)) < 1e-9
    # Clamped to the page.
    crop2 = E.padded_crop_pt([1, 1, 611, 791], (612.0, 792.0))
    assert crop2[0] >= 0 and crop2[2] <= 612.0
    assert crop2[1] >= 0 and crop2[3] <= 792.0


def test_render_page_caches_deterministically(pstore):
    store, doc, info, _ = pstore
    p1, e1 = E.render_page(store, doc, 0)
    assert e1 is None and p1 is not None
    p2, e2 = E.render_page(store, doc, 0)
    assert p2 == p1 and e2 is None
    assert p1.read_bytes() == p2.read_bytes()
    assert p1.read_bytes()[:3] == JPEG_MAGIC


def test_render_page_modes(pstore):
    store, doc, _, _ = pstore
    evdir = E.evidence_dir(store)
    assert stat.S_IMODE(os.stat(evdir).st_mode) == 0o700
    p, _ = E.render_page(store, doc, 0)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    s, _ = E.field_snapshot(store, doc, "box1_wages")
    assert s is not None
    # Every level under evidence/ is 700 -- no listing leaks.
    for root, dirs, files in os.walk(evdir):
        assert stat.S_IMODE(os.stat(root).st_mode) == 0o700, root
        for fn in files:
            assert stat.S_IMODE(
                os.stat(os.path.join(root, fn)).st_mode) == 0o600, fn
    # No bronze linkage -> fail-closed.
    doc2 = Document(doc_id="x", tax_year=2024, form_type="W-2",
                    source_path="x.pdf", ocr_text_ref="", fields={})
    path, err = E.render_page(store, doc2, 0)
    assert path is None and err == E.REASON_NO_BRONZE


def test_render_page_degrades_without_renderer(pstore, monkeypatch):
    store, doc, _, _ = pstore
    monkeypatch.setattr(E, "_convert_from_path", None)
    path, err = E.render_page(store, doc, 0)
    assert path is None and err == E.REASON_NO_RENDERER
    # Snapshot degrades too -- never a fake page.
    path, err = E.field_snapshot(store, doc, "box1_wages")
    assert path is None and err == E.REASON_NO_RENDERER


def test_snapshot_crop_matches_padded_geometry(pstore):
    from PIL import Image
    store, doc, info, _ = pstore
    path, err = E.field_snapshot(store, doc, "box1_wages")
    assert err is None and path is not None
    size = E.page_size_pt(E.bronze_path_for_doc(store, doc), 0)
    assert size is not None
    crop_pt = E.padded_crop_pt(info["bbox"], size)
    x0, y0, x1, y1 = E.pdf_to_px(crop_pt, size[1], E.SNAPSHOT_DPI)
    with Image.open(path) as im:
        w, h = im.size
    # Clamped to the rendered page; allow 2px rounding.
    assert abs(w - (x1 - x0)) <= 2
    assert abs(h - (y1 - y0)) <= 2
    # >=2x zoom vs the page view (220dpi vs 110dpi), not an upscale.
    assert E.SNAPSHOT_DPI >= 2 * E.PAGE_DPI


def test_snapshot_cache_key_stability_and_no_drift(pstore):
    store, doc, info, _ = pstore
    sha = doc.source_sha256
    k1 = E.snapshot_cache_key(bronze_hash=sha, page=0,
                              bbox_pdf=info["bbox"], dpi=E.SNAPSHOT_DPI,
                              extractor="pdfplumber:0.11")
    k2 = E.snapshot_cache_key(bronze_hash=sha, page=0,
                              bbox_pdf=info["bbox"], dpi=E.SNAPSHOT_DPI,
                              extractor="pdfplumber:0.11")
    assert k1 == k2
    # Re-extraction that moves the box -> a NEW key (no drift).
    moved = [v + 5.0 for v in info["bbox"]]
    k3 = E.snapshot_cache_key(bronze_hash=sha, page=0,
                              bbox_pdf=moved, dpi=E.SNAPSHOT_DPI,
                              extractor="pdfplumber:0.11")
    assert k3 != k1
    k4 = E.snapshot_cache_key(bronze_hash=sha, page=0,
                              bbox_pdf=info["bbox"], dpi=E.SNAPSHOT_DPI,
                              extractor="pdfplumber:0.12")
    assert k4 != k1
    # End to end: changing the recorded geometry changes the file served.
    p1, _ = E.field_snapshot(store, doc, "box1_wages")
    doc.fields["box1_wages"]["geometry"]["bbox_pdf"] = moved
    p2, err = E.field_snapshot(store, doc, "box1_wages")
    assert err is None and p2 != p1 and p2.exists()
    # Deleting the cache regenerates byte-identical output.
    p2.unlink()
    p3, err = E.field_snapshot(store, doc, "box1_wages")
    assert err is None and p3 == p2 and p3.exists()


def test_snapshot_fail_closed(pstore):
    store, doc, _, _ = pstore
    path, err = E.field_snapshot(store, doc, "box9_lonely")
    assert path is None and err == E.REASON_NO_GEOMETRY
    path, err = E.field_snapshot(store, doc, "no_such_field")
    assert path is None


def test_snapshot_out_of_bounds_refused(pstore):
    store, doc, _, _ = pstore
    doc.fields["box1_wages"]["geometry"]["bbox_pdf"] = [700, 700, 800, 800]
    path, err = E.field_snapshot(store, doc, "box1_wages")
    assert path is None and err == E.REASON_OUT_OF_BOUNDS


def test_crop_text_matches_field_raw_text(pstore):
    # R19 test 9b: the text inside the recorded bbox equals the field's
    # raw_text, verified against the immutable bronze PDF with
    # pdfplumber's within-bbox extraction. Hard import -- pdfplumber is
    # the bbox source for native PDFs; when it is absent this test must
    # FAIL, never skip (P2: missing geometry is a failure, not a gap).
    import pdfplumber

    store, doc, _, _ = pstore
    g = doc.fields["box1_wages"]["geometry"]
    raw = doc.fields["box1_wages"]["raw_text"]
    bronze = E.bronze_path_for_doc(store, doc)
    assert bronze is not None
    x0, y0, x1, y1 = g["bbox_pdf"]
    with pdfplumber.open(str(bronze)) as pdf:
        page = pdf.pages[E.bronze_page_for(doc, g["page"])]
        h = float(page.height)
        crop = page.within_bbox((x0, h - y1, x1, h - y0))
        text = " ".join((crop.extract_text() or "").split())
    assert " ".join(raw.split()) in text


def test_verify_original_roundtrip(pstore):
    store, doc, _, _ = pstore
    assert E.verify_original_recorded(store, doc.doc_id, "box9_lonely") is False
    seq = E.record_verify_original(store, doc.doc_id, "box9_lonely")
    assert isinstance(seq, int)
    assert E.verify_original_recorded(store, doc.doc_id, "box9_lonely") is True
    assert E.verify_original_recorded(store, doc.doc_id, "box1_wages") is False
    rows = store.decisions_for(doc_id=doc.doc_id, kind="verify_original")
    assert len(rows) == 1
    assert rows[0]["payload"]["field"] == "box9_lonely"


# -- D. blind evidence check ---------------------------------------------

def _pii_free(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        assert "85000" not in obj and "Acme" not in obj


def test_verify_evidence_missing_geometry_fails(tmp_path):
    # P2: missing geometry FAILS the blind check -- never a skip. This
    # is the clean-install shape: native PDF, no bbox source, so no
    # field carries geometry.
    store = DocumentStore(tmp_path / "data")
    doc = Document(doc_id="t1", tax_year=2024, form_type="W-2",
                   source_path="t.txt", ocr_text_ref="",
                   fields={"a": {"value": "1"}},
                   status="transcribed")
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["applicable"] is True
    assert r["passed"] is False
    assert r["n_fields_without_geometry"] == 1
    assert r["reason"] is None
    _pii_free(r)


def test_verify_evidence_vacuum_not_applicable(tmp_path):
    # The only "not applicable" case is a year with no fields at all --
    # a vacuum stays green. (Any extracted field without geometry
    # fails; see above.)
    store = DocumentStore(tmp_path / "data")
    doc = Document(doc_id="t0", tax_year=2024, form_type="W-2",
                   source_path="t.txt", ocr_text_ref="",
                   fields={}, status="transcribed")
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["passed"] is True and r["applicable"] is False
    assert r["reason"] == "no_fields"
    _pii_free(r)


def test_verify_evidence_counts_when_applicable(pstore):
    store, doc, _, _ = pstore
    r = V.verify_evidence(store, 2024)
    assert r["applicable"] is True
    d = r["docs"]["w2-ev-2024"]
    assert d["n_fields"] == 2 and d["n_with_geometry"] == 1
    # box9_lonely has no geometry -> without snapshot -> FAIL.
    assert r["n_extracted_fields_without_snapshot"] == 1
    assert r["passed"] is False
    _pii_free(r)


def test_verify_evidence_all_snapshottable_passes(pstore):
    store, doc, info, _ = pstore
    doc.fields["box9_lonely"]["geometry"] = {
        "page": 0, "bbox_pdf": [100.0, 600.0, 200.0, 615.0],
        "bbox_source": "pdfplumber", "char_span": None,
        "extractor": "pdfplumber:0.11"}
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["n_extracted_fields_without_snapshot"] == 0
    assert r["n_bbox_out_of_bounds"] == 0
    assert r["passed"] is True


def test_verify_evidence_out_of_bounds_fails(pstore):
    store, doc, _, _ = pstore
    doc.fields["box9_lonely"]["geometry"] = {
        "page": 0, "bbox_pdf": [700.0, 700.0, 800.0, 800.0],
        "bbox_source": "pdfplumber", "char_span": None,
        "extractor": "pdfplumber:0.11"}
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["passed"] is False
    assert r["n_bbox_out_of_bounds"] == 1
    assert r["out_of_bounds"] == [{"doc_id": "w2-ev-2024",
                                   "field": "box9_lonely"}]
    _pii_free(r)


def test_verify_evidence_computed_without_lineage_fails(pstore):
    store, doc, _, _ = pstore
    doc.fields["gain"] = {"value": "5", "computed": True}  # no lineage
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["passed"] is False
    assert r["n_computed_fields_without_lineage"] == 1
    # With lineage the computed field is satisfied.
    doc.fields["gain"] = {"value": "5", "computed": True,
                          "formula": "1d - 1e", "inputs": ["a", "b"]}
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["n_computed_fields_without_lineage"] == 0


def test_verify_evidence_scrubs_payer_codes(pstore):
    store, doc, info, _ = pstore
    doc.fields["payer1.ACME CORP.1"] = {
        "value": "9", "geometry": {
            "page": 0, "bbox_pdf": [700.0, 700.0, 800.0, 800.0],
            "bbox_source": "pdfplumber", "char_span": None,
            "extractor": "pdfplumber:0.11"}}
    store.upsert(doc)
    r = V.verify_evidence(store, 2024)
    assert r["out_of_bounds"][0]["field"] == "payer1.[payer].1"
    assert "ACME" not in json.dumps(r)


def test_extraction_yield_includes_evidence(pstore):
    store, doc, _, _ = pstore
    r = V.verify_extraction_yield(store, 2024)
    assert "evidence" in r["checks"]
    assert r["checks"]["evidence"]["applicable"] is True


# -- E. review UI + endpoints ---------------------------------------------

def test_doc_html_evidence_pane(pstore):
    store, doc, _, _ = pstore
    html = R.doc_html(store, doc)
    # Page viewer with zoom/pan + overlays.
    assert 'id="pageview"' in html
    assert 'id="zoomIn"' in html
    assert 'class="bbox"' in html and 'data-box="box1_wages"' in html
    # Per-field snapshot for the geometry field...
    assert "/api/evidence/snapshot?doc_id=w2-ev-2024&field=box1_wages" in html
    # ...explicit no-evidence state + disabled confirm for the other.
    assert "no visual evidence" in html
    assert 'data-box="box9_lonely"' in html
    assert 'id="row-box1_wages"' in html
    # "Open original" serves the immutable bronze copy.
    assert "/api/evidence/original?doc_id=w2-ev-2024" in html
    # Fail-closed: the no-evidence row's checkbox is disabled server-side.
    assert 'data-box="box9_lonely"' in html


def test_doc_html_confirm_disabled_without_evidence(pstore):
    store, doc, _, _ = pstore
    html = R.doc_html(store, doc)
    # The box9_lonely row's checkbox carries disabled; box1_wages' does not.
    import re
    for m in re.finditer(r'<tr class="[^"]*" data-box="([^"]+)"[^>]*>(.*?)</tr>',
                         html, re.S):
        code, row = m.group(1), m.group(2)
        chk = re.search(r'<input type="checkbox" class="fchk"([^>]*)>', row)
        assert chk is not None, code
        if code == "box9_lonely":
            assert "disabled" in chk.group(1), "no-evidence row must disable confirm"
        elif code == "box1_wages":
            assert "disabled" not in chk.group(1)


def test_doc_html_edited_field_shows_original_and_history(pstore):
    store, doc, _, _ = pstore
    doc.fields["box1_wages"]["history"] = [
        {"ts": "2026-10-04T00:00:00+00:00", "old": "84000.00",
         "new": "85000.00"}]
    store.upsert(doc)
    html = R.doc_html(store, doc)
    assert "the image never proves the edited value" in html
    assert "84000.00" in html and "85000.00" in html


def test_doc_html_computed_field_shows_lineage(pstore):
    store, doc, _, _ = pstore
    doc.fields["gain"] = {"value": "5", "computed": True,
                          "formula": "1d - 1e", "inputs": ["box1_wages"]}
    store.upsert(doc)
    html = R.doc_html(store, doc)
    assert "computed" in html and "1d - 1e" in html
    assert 'href="#row-box1_wages"' in html


def test_doc_html_degrades_without_renderer(pstore, monkeypatch):
    # No renderer anywhere: the pane degrades to the blocking banner --
    # a fake page is never synthesized.
    store, doc, _, _ = pstore
    monkeypatch.setattr(E, "_convert_from_path", None)
    monkeypatch.setattr(R, "_convert_from_path", None)
    html = R.doc_html(store, doc)
    assert "Page images unavailable" in html
    assert "Validation is <b>BLOCKED</b>" in html


def test_queue_html_evidence_column(pstore):
    store, doc, _, _ = pstore
    html = R.queue_html(store, None, None)
    assert "<th>evidence</th>" in html
    assert ">1/2<" in html  # one of two fields carries geometry


def test_endpoint_page_serves_jpeg(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store)
    try:
        st, ctype, body = _raw(
            srv, "/api/evidence/page?doc_id=w2-ev-2024&page=0&dpi=110")
        assert st == 200 and ctype == "image/jpeg"
        assert body[:3] == JPEG_MAGIC
        # Bad params are refused, not guessed.
        st, _, _ = _raw(
            srv, "/api/evidence/page?doc_id=w2-ev-2024&page=-1&dpi=110")
        assert st == 400
        st, _, _ = _raw(srv, "/api/evidence/page?doc_id=nope&page=0")
        assert st == 404
    finally:
        _teardown(srv)


def test_endpoint_snapshot_and_fail_closed(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store)
    try:
        st, ctype, body = _raw(
            srv, "/api/evidence/snapshot?doc_id=w2-ev-2024&field=box1_wages")
        assert st == 200 and ctype == "image/jpeg"
        assert body[:3] == JPEG_MAGIC
        # No geometry -> JSON 404, never a placeholder image.
        st, ctype, body = _raw(
            srv, "/api/evidence/snapshot?doc_id=w2-ev-2024&field=box9_lonely")
        assert st == 404
        assert json.loads(body)["error"] == E.REASON_NO_GEOMETRY
    finally:
        _teardown(srv)


def test_endpoint_fields_is_value_free(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store)
    try:
        st, ctype, body = _raw(
            srv, "/api/evidence/fields?doc_id=w2-ev-2024")
        assert st == 200
        payload = json.loads(body)
        assert payload["fields"]["box1_wages"]["state"] == "snapshot"
        assert payload["fields"]["box9_lonely"]["state"] == "no_evidence"
        assert "overlay_pct" in payload["fields"]["box1_wages"]
        blob = json.dumps(payload)
        assert '"value"' not in blob and '"raw_text"' not in blob
        assert "85000" not in blob
    finally:
        _teardown(srv)


def test_endpoint_original_serves_bronze_pdf(pstore):
    store, doc, _, pdf_bytes = pstore
    srv = _serve(store)
    try:
        st, ctype, body = _raw(
            srv, "/api/evidence/original?doc_id=w2-ev-2024")
        assert st == 200 and ctype == "application/pdf"
        assert body == pdf_bytes  # the immutable bronze bytes, exactly
    finally:
        _teardown(srv)


def test_endpoints_inherit_r10_gates(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store)
    try:
        host, port = srv.server_address
        # Hostile Host header -> 403 on every new route.
        st, _, _ = _raw(
            srv, "/api/evidence/page?doc_id=w2-ev-2024&page=0",
            headers={"Host": f"evil.example:{port}"})
        assert st == 403
        st, _, _ = _raw(
            srv, "/api/evidence/fields?doc_id=w2-ev-2024",
            headers={"Host": f"evil.example:{port}"})
        assert st == 403
        # POST without JSON content-type -> 415; foreign origin -> 403.
        st, _, body = _post(srv, "/api/evidence/verify-original",
                            {"doc_id": "w2-ev-2024", "field": "box9_lonely"},
                            ctype="text/plain")
        assert st == 415
        st, _, _ = _post(srv, "/api/evidence/verify-original",
                         {"doc_id": "w2-ev-2024", "field": "box9_lonely"},
                         origin=False)
        assert st == 403
    finally:
        _teardown(srv)


def test_endpoints_inherit_token_mode(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store, token="sekret")
    try:
        st, _, _ = _raw(srv, "/api/evidence/page?doc_id=w2-ev-2024&page=0")
        assert st == 404  # missing token prefix: indistinguishable 404
        st, _, body = _raw(
            srv, "/t/sekret/api/evidence/fields?doc_id=w2-ev-2024")
        assert st == 200
    finally:
        _teardown(srv)


def test_verify_original_unblocks_confirm(pstore):
    store, doc, _, _ = pstore
    srv = _serve(store)
    try:
        payload = {"doc_id": "w2-ev-2024", "field": "box9_lonely"}
        # Fail-closed first: confirming the no-evidence field is refused.
        with pytest.raises(R.ValidationRefused) as ei:
            R.apply_validation(store, "w2-ev-2024", {}, ["box9_lonely"],
                               confirm_form_type=True, confirm_tax_year=True)
        assert "no_evidence_unverified" in ei.value.reasons
        # The geometry field confirms fine without any record.
        R.apply_validation(store, "w2-ev-2024", {}, ["box1_wages"],
                           confirm_form_type=True, confirm_tax_year=True)
        # Operator records "verified against original" via the endpoint.
        st, _, body = _post(srv, "/api/evidence/verify-original", payload)
        assert st == 200 and json.loads(body)["ok"] is True
        # Now the confirm goes through (fresh doc: re-fetch not needed;
        # apply_validation reads the decision log).
        doc.status = "transcribed"
        store.upsert(doc)
        out = R.apply_validation(store, "w2-ev-2024", {}, ["box9_lonely"],
                                 confirm_form_type=True, confirm_tax_year=True)
        assert out.status == "validated"
        rows = store.decisions_for(doc_id="w2-ev-2024",
                                   kind="verify_original")
        assert len(rows) == 1
    finally:
        _teardown(srv)


# -- F. privacy boundary -----------------------------------------------

def _mcp_tool_functions():
    return {name: fn for name, fn in vars(MCP).items()
            if inspect.isfunction(fn)
            and fn.__module__ == "taxprep.mcp_server"
            and not name.startswith("_")}


def _tool_args(name, sig, tmp_path, data_dir, doc_id):
    """Benign, synthetic arguments per parameter name."""
    args = {}
    for pname, p in sig.parameters.items():
        if pname == "data_dir":
            args[pname] = data_dir
        elif pname == "doc_id":
            args[pname] = doc_id
        elif pname == "tax_year":
            args[pname] = 2024
        elif pname == "form_type":
            args[pname] = None
        elif pname == "include_irrelevant":
            args[pname] = False
        elif pname == "topic":
            args[pname] = "tax-prep.test"
        elif pname == "type":
            args[pname] = "privacy_probe"
        elif pname == "payload":
            args[pname] = {"probe": "privacy", "n_fields": 2}
        elif pname == "timeout_seconds":
            args[pname] = 0
        elif pname == "correlation_id":
            args[pname] = None
        elif pname == "verdict":
            args[pname] = "relevant"
        elif pname == "reason":
            args[pname] = "privacy probe"
        elif pname in ("input_dir", "filing_status_by_year"):
            return None  # heavyweight / needs validated docs: not probed
        elif p.default is inspect.Parameter.empty:
            return None  # unknown required arg: do not guess
        # else: leave the default
    return args


def test_mcp_and_bus_carry_no_images_or_paths(tmp_path, monkeypatch):
    """R19 item 7: page images and snapshots are PII.

    Seeds the evidence dir with real JPEG bytes, then calls every MCP
    tool and scans all outputs (plus a bus publish/poll round-trip) for
    image bytes or evidence paths. Any leak fails the test.
    """
    data_dir = str(tmp_path / "data")
    store = DocumentStore(data_dir)
    doc = Document(
        doc_id="pii-doc-2024", tax_year=2024, form_type="W-2",
        source_path="s.pdf", ocr_text_ref="",
        fields={"box1_wages": {
            "value": "85000.00", "confidence": "high",
            "raw_text": "Box 1 Wages 85000.00", "geometry": GEOM}},
        status="transcribed")
    store.upsert(doc)
    # Seed the evidence cache with JPEG-magic bytes an exfiltration
    # would have to carry.
    evdir = E.evidence_dir(store)
    seed = evdir / "seed.jpg"
    seed.write_bytes(JPEG_MAGIC + b"\x00" * 64)
    os.chmod(seed, 0o600)
    bus_dir = tmp_path / "bus"
    bus_dir.mkdir()
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(bus_dir))

    blobs = []
    for name, fn in sorted(_mcp_tool_functions().items()):
        args = _tool_args(name, inspect.signature(fn), tmp_path,
                          data_dir, doc.doc_id)
        if args is None:
            continue
        try:
            out = fn(**args)
        except Exception as exc:  # tool refusals are fine; scan them too
            out = {"error": str(exc)}
        blobs.append((name, json.dumps(out, default=str).encode()))
    for name, blob in blobs:
        assert JPEG_MAGIC not in blob, f"image bytes in {name}"
        assert b"\x89PNG" not in blob, f"PNG bytes in {name}"
        assert b"data:image" not in blob, f"data URI in {name}"
        assert b"evidence/" not in blob, f"evidence path in {name}"
        assert b".jpg" not in blob, f"image path in {name}"
    assert blobs, "no MCP tools were probed"


def test_scrub_doc_drops_geometry():
    scrubbed = MCP._scrub_doc({
        "doc_id": "d", "tax_year": 2024, "form_type": "W-2",
        "status": "transcribed", "validated_at": None,
        "fields": {"box1_wages": {"value": "1", "confidence": "high",
                                  "raw_text": "t", "geometry": GEOM}}})
    field = scrubbed["fields"]["box1_wages"]
    assert set(field) == {"confidence", "has_value"}
    assert "geometry" not in json.dumps(scrubbed)


def test_doc_page_window_parsing():
    class D:
        def __init__(self, pr):
            self.page_range = pr
    assert E.doc_page_window(D("3-5")) == (2, 3)
    assert E.doc_page_window(D("3")) == (2, 1)
    assert E.doc_page_window(D((2, 3))) == (1, 2)  # tuple form also in use
    assert E.doc_page_window(D([2, 3])) == (1, 2)
    assert E.doc_page_window(D(None)) == (0, None)
    assert E.doc_page_window(D("bogus")) == (0, None)
    assert E.doc_page_window(D("0-2")) == (0, None)  # 1-based: 0 invalid
    assert E.page_range_pair((2, 3)) == (2, 3)
    assert E.page_range_pair("3-5") == (3, 5)
    assert E.page_range_pair(None) is None
    assert E.bronze_page_for(D("3-5"), 0) == 2
    assert E.bronze_page_for(D(None), 4) == 4


def test_viewer_respects_split_window(pstore):
    store, doc, _, _ = pstore
    doc.page_range = "1"
    store.upsert(doc)
    html = R.doc_html(store, doc)
    assert html.count('class="pagewrap"') == 1
    assert ">1 page(s)<" in html
    assert 'data-box="box1_wages"' in html  # overlay still drawn


# -- G. overlay/selection wiring -----------------------------------------
def test_bidirectional_wiring_present(pstore):
    """Static wiring check: rows <-> overlays <-> JS handlers.

    Live click behavior is exercised in the loopback browser; here we
    assert every half of the wiring exists and shares the same keys.
    """
    store, doc, _, _ = pstore
    html = R.doc_html(store, doc)
    # Row side: id + data-box per field row.
    assert 'id="row-box1_wages"' in html
    assert 'id="row-box9_lonely"' in html
    # Overlay side: one .bbox per geometry-carrying field.
    assert html.count('class="bbox"') == 1
    assert 'data-box="box1_wages"' in html
    # JS side: both directions + zoom + verify-original handlers.
    assert 'document.querySelectorAll(".bbox").forEach' in html
    assert 'tr.field-row td:first-child' in html
    assert 'button.vorig' in html
    assert 'getElementById("zoomIn")' in html
