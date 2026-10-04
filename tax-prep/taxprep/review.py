"""Visual validation UI — localhost-only HTTP server.

Workflow: ``taxprep ingest`` populates the store; ``taxprep review`` serves
a browser UI where each document's extracted fields are checked against the
source evidence (OCR text with extracted spans highlighted, or PDF page
images when a renderer is available). Corrections are written back through
``POST /api/validate`` and flip the document to ``validated``.

Security: binds 127.0.0.1 ONLY. Any other host is refused.

Request hardening (R10 — survivor of the workstation's falsification of
"no one is getting access", dsys-store bus tax-prep.ops 2026-10-03):

* Host allowlist — only ``127.0.0.1:<port>`` and ``localhost:<port>``
  (port = the bound port) are accepted, on EVERY route, GET and POST.
  Any other (or missing) Host header -> 403. This kills the DNS-rebinding
  precondition: a rebound ``Host: attacker.example:<port>`` is refused.
* POST gates — ``POST /api/validate`` requires
  ``Content-Type: application/json`` (anything else, e.g. text/plain,
  -> 415 Unsupported Media Type) AND a same-origin ``Origin`` header whose
  host:port matches the Host allowlist (missing or foreign -> 403). This
  kills the simple-request CSRF precondition; legitimate JSON POSTs from
  the served page already carry Origin, and cross-origin JSON POSTs need
  a preflight the server never answers (OPTIONS -> 501).
* Optional per-run token — ``--token`` on ``taxprep review``: every route
  then requires the ``/t/<token>`` URL prefix, and the startup banner
  prints the full tokenized URL. Wrong or missing token prefix -> 404,
  indistinguishable from any unknown path (no oracle for guessing).

Reject codes, stable and documented: 403 = hostile/missing Host, or
missing/foreign Origin; 415 = POST without application/json; 404 =
unknown path, including a wrong/missing token prefix.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import lifecycle
from . import silver
from . import console as _console
from . import evidence as _evidence
from .models import FORM_TYPES, Document
from .store import DocumentStore

try:
    # Declared in pyproject dependencies. Poppler's ``pdftoppm``
    # (poppler-utils) is the system prerequisite for rendering.
    from pdf2image import convert_from_path as _convert_from_path
except ImportError:  # pragma: no cover - exercised via monkeypatch
    _convert_from_path = None

DEFAULT_PORT = 8471
BIND_HOST = "127.0.0.1"

_CSS = """
body{font-family:system-ui,-apple-system,sans-serif;max-width:1400px;margin:0 auto;padding:16px;color:#1a1a1a}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f4f4f4}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;color:#fff}
.b-high{background:#2e7d32}.b-medium{background:#d9930d}.b-low{background:#c62828}
tr.lowconf{background:#fdecea}
tr.edited td.valcell{background:#e8f5e9}
mark{background:#fff176}
.cols{display:flex;gap:16px}
.left{flex:1;min-width:0}.right{flex:1;min-width:0}
.src{white-space:pre-wrap;background:#fafafa;border:1px solid #ddd;padding:12px;max-height:80vh;overflow:auto;font-size:13px}
.src img{max-width:100%;border:1px solid #ccc;margin-bottom:12px;display:block}
input.fval{width:100%;box-sizing:border-box;font-size:14px}
.filters{margin:12px 0}
.filters a{margin-right:12px}
button{font-size:15px;padding:8px 18px}
button:disabled{opacity:.4;cursor:not-allowed}
.prog{margin:8px 0;font-size:14px}
.banner{background:#fdecea;border:2px solid #c62828;padding:12px;margin-bottom:12px;font-size:14px}
.evnote{color:#666;font-size:12px;font-style:italic;margin:0 0 8px}
/* R19 evidence pane */
#pageview{max-height:82vh;overflow:auto;background:#333;padding:12px;border:1px solid #999}
.pagewrap{position:relative;display:inline-block;min-width:100%;margin:0 auto 16px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.4)}
.pageimg{display:block;height:auto}
.bbox{position:absolute;border:2px solid #ff3d00;background:rgba(255,61,0,.12);cursor:pointer;box-sizing:border-box}
.bbox:hover{background:rgba(255,61,0,.30)}
.bbox.sel{border-color:#1565c0;background:rgba(21,101,192,.25);box-shadow:0 0 0 2px #90caf9}
.pagenav{display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.pagenav button{font-size:13px;padding:4px 12px}
.zoomlabel{font-size:13px;color:#555}
img.snap{max-width:220px;border:1px solid #888;display:block;margin:2px 0}
.lineage{font-size:12px;background:#e8f0fe;border:1px solid #90caf9;padding:6px;max-width:260px}
.lineage code{background:#fff;padding:0 4px}
.noev{font-size:12px;color:#8a1c1c;background:#fdecea;border:1px solid #e0a0a0;padding:6px;max-width:260px}
.vorig{font-size:12px;margin-top:4px;padding:3px 10px}
.vok{font-size:12px;color:#2e7d32;margin-top:4px}
.orignote{font-size:11px;color:#5d4037;font-style:italic}
.edithist{font-size:11px;color:#5d4037}
tr.field-row.selrow td{box-shadow:inset 0 0 0 2px #1565c0}
tr.field-row{cursor:pointer}
.evcell{min-width:180px}
"""

# -- HTML rendering -------------------------------------------------

def _badge(conf: str) -> str:
    cls = {"high": "b-high", "medium": "b-medium", "low": "b-low"}.get(conf, "b-medium")
    return f'<span class="badge {cls}">{html.escape(conf or "?")}</span>'


def highlight_page(page_text: str, fields: dict, page_0: int) -> str:
    """Escape page text to HTML and <mark> each field's char_span.

    R15/P4: highlighting is by exact character offset, never by string
    search -- exactly one span per field, from the field's provenance
    ``char_span``. Repeated amounts or labels can finally be tied to the
    occurrence the value came from. Fields without a char_span on this
    page are not marked. Overlapping spans resolve longest-first; a span
    overlapping an already-placed one is skipped (no nested marks).
    Degrades to plain escaped text when no spans match.
    """
    spans: list[tuple[int, int]] = []
    for f in fields.values():
        if not isinstance(f, dict):
            continue
        prov = f.get("provenance") or {}
        cs = prov.get("char_span") or {}
        if cs.get("page") == page_0:
            s, e = cs.get("start"), cs.get("end")
            if (isinstance(s, int) and isinstance(e, int)
                    and 0 <= s < e <= len(page_text)):
                spans.append((s, e))
    # Longest-first placement (deterministic); overlaps skipped.
    spans.sort(key=lambda se: (-(se[1] - se[0]), se[0]))
    placed: list[tuple[int, int]] = []
    for s, e in spans:
        if all(e <= ps or s >= pe for ps, pe in placed):
            placed.append((s, e))
    placed.sort()
    out: list[str] = []
    pos = 0
    for s, e in placed:
        out.append(html.escape(page_text[pos:s]))
        out.append(f"<mark>{html.escape(page_text[s:e])}</mark>")
        pos = e
    out.append(html.escape(page_text[pos:]))
    return "".join(out)


def highlight_pages(pages: list[str], fields: dict) -> list[str]:
    """Highlight each page's text by the fields' char_spans (R15/P4)."""
    return [highlight_page(page, fields, i)
            for i, page in enumerate(pages)]


def highlight_ocr(text: str, fields: dict) -> str:
    """Highlight a single page of text (page 0) by field char_spans.

    Backward-compatible shim over :func:`highlight_page`; for
    multi-page documents use :func:`highlight_pages` so page boundaries
    survive (P4).
    """
    return highlight_page(text or "", fields, 0)


def _doc_page_texts(store: DocumentStore,
                    doc: Document) -> list[str] | None:
    """Per-page stored text for a document, or None when unavailable.

    Authoritative source: the ``bronze_text`` rows for the doc's bronze
    at its current derivation, in page order (the char_span page indexes
    address exactly these pages). Falls back to the joined OCR text as a
    single page.
    """
    sha = silver.bronze_hash_for_doc(store, doc)
    if sha:
        try:
            ctx = silver.derivation_for_doc(store, doc.doc_id)
            rows = store.read_bronze_text(
                sha, derivation_version=ctx.derivation_version,
                config_hash=ctx.config_hash)
            if rows:
                return [r["text"] for r in rows]
        except Exception:
            pass
    try:
        return [store.load_ocr(doc.doc_id)]
    except (FileNotFoundError, OSError):
        return None


def _pdf_page_images(store, doc: Document) -> tuple[list[str], str | None]:
    """Render source PDF pages to JPEG data URIs.

    Renders ALL pages, or the split document's page range when
    ``Document.page_range`` is present (a (first, last) 1-based pair).

    Returns ``(images, error)``: ``error`` is None on success, otherwise a
    short reason string. Poppler's ``pdftoppm`` (poppler-utils) is the
    system prerequisite; ``pdf2image`` is a declared project dependency.

    B4 privacy: pdftoppm's scratch files go to a private dir under the
    data dir (700), never the system temp dir -- PII page images must
    not touch /tmp. Same pattern as evidence.render_page.
    """
    import shutil
    import tempfile

    src = doc.source_path or ""
    if not src.lower().endswith(".pdf"):
        return [], "not a PDF source"
    pdf_path = Path(src)
    if not pdf_path.exists():
        return [], f"source file missing: {src}"
    if _convert_from_path is None:
        return [], "pdf2image not installed (page-image evidence unavailable)"
    page_range = getattr(doc, "page_range", None)
    kwargs: dict = {"dpi": 110}
    # page_range arrives as a (first, last) tuple or a "3-5"/"3" string.
    pair = _evidence.page_range_pair(page_range)
    if pair is not None:
        kwargs["first_page"], kwargs["last_page"] = pair
    tmp = tempfile.mkdtemp(prefix="review-",
                           dir=str(_evidence.evidence_dir(store)))
    try:
        kwargs["output_folder"] = tmp
        kwargs["paths_only"] = True
        try:
            paths = _convert_from_path(str(pdf_path), **kwargs)
        except Exception as exc:
            # Reason only; exception text never surfaces (no PII/paths leak).
            return [], f"page render failed ({type(exc).__name__})"
        from PIL import Image
        out = []
        for p in paths:
            with Image.open(p) as img:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out, None


def evidence_status(store: DocumentStore, doc: Document) -> dict:
    """Classify the source evidence available for a document.

    Returns ``{"mode", "reason"}`` with mode one of:

    - ``"images"`` — PDF page images rendered (the mandatory evidence path).
    - ``"text"`` — non-PDF source; the stored text IS the document, so it
      stands as evidence on its own.
    - ``"degraded"`` — page images failed; extracted text is shown ONLY as
      a flagged fallback, and validation is REFUSED in this state (text
      alone would verify OCR against itself).
    - ``"unavailable"`` — no evidence at all; validation is REFUSED.
    """
    src = doc.source_path or ""
    if src.lower().endswith(".pdf"):
        images, error = _pdf_page_images(store, doc)
        if error is None:
            return {"mode": "images", "reason": None}
        try:
            store.load_ocr(doc.doc_id)
        except (FileNotFoundError, OSError):
            return {"mode": "unavailable", "reason": error}
        return {"mode": "degraded", "reason": error}
    try:
        store.load_ocr(doc.doc_id)
    except (FileNotFoundError, OSError):
        return {"mode": "unavailable", "reason": "no source text available"}
    return {"mode": "text", "reason": None}


def _source_evidence_html(store: DocumentStore, doc: Document) -> tuple[str, bool]:
    """Evidence panel HTML plus a blocked flag.

    ``blocked`` is True when page images are missing: the text shown is a
    degraded fallback (or nothing), the UI must surface a blocking banner,
    and ``apply_validation`` refuses to flip the document in this state.
    """
    ev = evidence_status(store, doc)
    if ev["mode"] == "images":
        images, _ = _pdf_page_images(store, doc)
        imgs = "".join(
            f'<img src="data:image/jpeg;base64,{p}" alt="source page">' for p in images
        )
        return f'<div class="src">{imgs}</div>', False
    # Text evidence is rendered per page (R15/P4): char_spans address
    # per-page text, so pages are never joined into one blob here.
    pages = _doc_page_texts(store, doc)
    if ev["mode"] == "text":
        if not pages:
            banner = ('<div class="banner">⚠ No source evidence is '
                      "available. Validation is <b>BLOCKED</b>.</div>")
            return banner + ('<div class="src"><i>No source evidence '
                             "available.</i></div>"), True
        body = "".join(
            f'<div class="srcpage">{p}</div>'
            for p in highlight_pages(pages, doc.fields))
        note = '<p class="evnote">Text evidence: the source is a text file.</p>'
        return f'<div class="src">{note}{body}</div>', False
    # degraded or unavailable: blocking banner, fail closed
    if pages is None:
        text_pages: list[str] = []
    else:
        text_pages = highlight_pages(pages, doc.fields)
    banner = (
        '<div class="banner">⚠ Page images unavailable'
        f' ({html.escape(ev["reason"] or "unknown reason")}). '
        + ("Extracted text is shown ONLY as a degraded fallback — it cannot "
           "verify the extraction. " if text_pages
           else "No source evidence is available. ")
        + "Validation is <b>BLOCKED</b> until page images render.</div>"
    )
    if not text_pages:
        return banner + '<div class="src"><i>No source evidence available.</i></div>', True
    body = "".join(f'<div class="srcpage">{p}</div>' for p in text_pages)
    return banner + f'<div class="src">{body}</div>', True


# -- R19/R19a evidence pane --------------------------------------------

_NOEV_TEXT = {
    _evidence.REASON_NO_GEOMETRY: "no geometry recorded at extraction",
    _evidence.REASON_MANUAL_ENTRY: "manually added — no source region",
    _evidence.REASON_NO_LINEAGE: "computed field without lineage",
    _evidence.REASON_OUT_OF_BOUNDS: "recorded box lies outside the page",
    _evidence.REASON_SNAPSHOT_FAILED: "snapshot could not be derived",
    _evidence.REASON_NO_RENDERER: "no PDF renderer available",
    _evidence.REASON_NO_BRONZE: "no immutable bronze copy linked",
}


def _overlays_for_page(store: DocumentStore, doc: Document,
                       page_0based: int) -> str:
    """Bounding-box overlay divs for one page (% coordinates).

    Boxes whose recorded bbox falls outside the page are SKIPPED, never
    drawn -- a wrong box is worse than no box (fail-closed).
    """
    bronze_path = _evidence.bronze_path_for_doc(store, doc)
    if bronze_path is None:
        return ""
    size = _evidence.page_size_pt(bronze_path, page_0based)
    if size is None:
        return ""
    w_pt, h_pt = size
    w_px = w_pt * _evidence.PAGE_DPI / 72.0
    h_px = h_pt * _evidence.PAGE_DPI / 72.0
    divs = []
    for code, f in _field_rows(doc).items():
        g = _evidence.field_geometry(f if isinstance(f, dict) else None)
        if g is None:
            continue
        # page_0based is bronze-frame; geometry pages are document-relative.
        if _evidence.bronze_page_for(doc, g["page"]) != page_0based:
            continue
        if _evidence.bbox_within_bounds(g["bbox_pdf"], size) is False:
            continue
        x0, y0, x1, y1 = _evidence.pdf_to_px(
            g["bbox_pdf"], h_pt, _evidence.PAGE_DPI)
        divs.append(
            f'<div class="bbox" data-box="{html.escape(code)}" title="{html.escape(code)}" '
            f'style="left:{x0 / w_px * 100:.3f}%;top:{y0 / h_px * 100:.3f}%;'
            f'width:{(x1 - x0) / w_px * 100:.3f}%;'
            f'height:{(y1 - y0) / h_px * 100:.3f}%"></div>')
    return "".join(divs)


def _page_viewer_html(store: DocumentStore, doc: Document,
                      base: str) -> tuple[str, bool]:
    """R19 left pane: rendered pages, zoom/pan, bbox overlays.

    Page images are served per-page from the bronze bytes (lazy
    ``loading="lazy"`` -- a 200-page PDF does not render up front).
    Returns ``(html, blocked)``; blocked=True degrades to the legacy
    evidence path (same contract as :func:`_source_evidence_html`).
    """
    bronze_path = _evidence.bronze_path_for_doc(store, doc)
    if bronze_path is None:
        return "", True
    n_bronze = _evidence.page_count(bronze_path)
    if not n_bronze:
        return "", True
    # Commit to the viewer only when the first page actually renders;
    # a render failure here degrades instead of showing a broken pane.
    offset, count = _evidence.doc_page_window(doc)
    first_bronze = offset
    if first_bronze >= n_bronze:
        return "", True
    first, err = _evidence.render_page(store, doc, first_bronze)
    if first is None:
        return "", True
    last_bronze = (first_bronze + count - 1) if count else (n_bronze - 1)
    last_bronze = min(last_bronze, n_bronze - 1)
    pages = []
    for p in range(first_bronze, last_bronze + 1):
        src = (f"{base}/api/evidence/page?doc_id={quote(doc.doc_id)}"
               f"&page={p}&dpi={_evidence.PAGE_DPI}")
        pages.append(
            f'<div class="pagewrap" data-page="{p}">'
            f'<img class="pageimg" loading="lazy" src="{src}" '
            f'alt="source page {p + 1}">'
            f"{_overlays_for_page(store, doc, p)}</div>")
    n_shown = last_bronze - first_bronze + 1
    orig = (f"{base}/api/evidence/original?doc_id={quote(doc.doc_id)}")
    nav = (f'<div class="pagenav">'
           f'<button id="zoomOut">−</button>'
           f'<button id="zoomIn">+</button>'
           f'<button id="zoomReset">reset</button>'
           f'<span class="zoomlabel" id="zoomLabel">100%</span>'
           f'<span class="zoomlabel">{n_shown} page(s)</span>'
           f'<a href="{orig}" target="_blank" rel="noopener">'
           f'Open original (immutable bronze)</a>'
           f'</div>')
    return nav + f'<div id="pageview">{"".join(pages)}</div>', False


def _field_evidence_cell(store: DocumentStore, doc: Document, code: str,
                         f: dict, base: str,
                         images_mode: bool,
                         input_anchor=None) -> tuple[str, bool]:
    """One field row's evidence cell.

    Returns ``(cell_html, confirm_disabled)``. The disabled flag is
    computed server-side so the fail-closed rule never depends on JS.

    ``input_anchor`` (optional): ``code -> href`` for the lineage
    view's input links. Default anchors each input to its own field
    row (``#row-<code>``); per-lot computed rows pass an anchor to the
    parent lots row, where the lot's inputs actually live.
    """
    ev = _evidence.field_evidence(f)
    state = ev["state"]
    snap_url = (f"{base}/api/evidence/snapshot?doc_id={quote(doc.doc_id)}"
                f"&field={quote(code)}")
    if state == _evidence.STATE_LINEAGE:
        lin = ev["lineage"]

        def _href(c):
            if input_anchor is not None:
                return input_anchor(c)
            return f"#row-{html.escape(c)}"

        inputs = " ".join(
            f'<a href="{_href(c)}" class="inplink" '
            f'data-box="{html.escape(c)}">{html.escape(c)}</a>'
            for c in lin["inputs"])
        # R19a: a computed field that was itself operator-edited shows
        # the lineage AND the edit record (the lineage view is never
        # the "no visual evidence" state).
        hist = "".join(
            f'<div class="edithist">edited {html.escape(str(e.get("ts", "")))}: '
            f'{html.escape(str(e.get("old")))} → '
            f'{html.escape(str(e.get("new")))} (operator)</div>'
            for e in ev["history"]
            if isinstance(e, dict) and e.get("old") is not None)
        cell = (f'<div class="lineage"><b>computed</b> — no source region.<br>'
                f'formula: <code>{html.escape(lin["formula"])}</code>'
                f'<br>inputs: {inputs}</div>{hist}')
        return cell, False
    if state in (_evidence.STATE_SNAPSHOT, _evidence.STATE_EDITED):
        note = ""
        if state == _evidence.STATE_EDITED:
            hist = "".join(
                f'<div class="edithist">edited {html.escape(str(e.get("ts", "")))}: '
                f'{html.escape(str(e.get("old")))} → '
                f'{html.escape(str(e.get("new")))} (operator)</div>'
                for e in ev["history"]
                if isinstance(e, dict) and e.get("old") is not None)
            note = (f'<div class="orignote">original evidence — '
                    f'the image never proves the edited value.</div>{hist}')
        cell = (f'{note}<img class="snap" loading="lazy" src="{snap_url}" '
                f'alt="source snapshot for {html.escape(code)}" '
                f'onerror="this.outerHTML=\'<div class=&quot;noev&quot;>'
                f'snapshot unavailable</div>\'">')
        return cell, False
    # STATE_NO_EVIDENCE -- explicit, never a guess.
    reason = _NOEV_TEXT.get(ev["reason"], "no visual evidence")
    verified = _evidence.verify_original_recorded(store, doc.doc_id, code)
    cell = (f'<div class="noev"><b>no visual evidence</b><br>'
            f'<span>{html.escape(reason)}</span></div>')
    if verified:
        cell += ('<div class="vok">✓ verified against original '
                 '(logged)</div>')
        return cell, False
    cell += (f'<br><button type="button" class="vorig" '
             f'data-box="{html.escape(code)}">'
             f'verified against original</button>')
    # Fail-closed: in images mode the confirm control stays disabled
    # until evidence exists or the Operator records the verdict. Text
    # sources keep their standing behavior (the text IS the evidence).
    return cell, images_mode


def evidence_fields_payload(store: DocumentStore, doc: Document) -> dict:
    """Per-field evidence metadata for the pane (loopback only).

    Deliberately value-free: states, reasons, page/bbox/extractor
    metadata, overlay geometry, lineage, edit history stamps, and the
    verified-against-original flag. No field values, no raw_text, and
    never image bytes -- images travel only as served files.
    """
    bronze_path = _evidence.bronze_path_for_doc(store, doc)
    out: dict = {}
    for code, f in _field_rows(doc).items():
        ev = _evidence.field_evidence(f)
        entry: dict = {"state": ev["state"], "reason": ev["reason"]}
        g = ev["geometry"]
        if g is not None:
            entry["page"] = g["page"]  # document-relative (contract)
            bronze_page = _evidence.bronze_page_for(doc, g["page"])
            entry["bronze_page"] = bronze_page
            entry["bbox_source"] = g["bbox_source"]
            entry["extractor"] = g["extractor"]
            if bronze_path is not None:
                size = _evidence.page_size_pt(bronze_path, bronze_page)
                if (size is not None
                        and _evidence.bbox_within_bounds(
                            g["bbox_pdf"], size) is not False):
                    x0, y0, x1, y1 = _evidence.pdf_to_px(
                        g["bbox_pdf"], size[1], _evidence.PAGE_DPI)
                    w_px = size[0] * _evidence.PAGE_DPI / 72.0
                    h_px = size[1] * _evidence.PAGE_DPI / 72.0
                    entry["overlay_pct"] = {
                        "left": x0 / w_px * 100, "top": y0 / h_px * 100,
                        "width": (x1 - x0) / w_px * 100,
                        "height": (y1 - y0) / h_px * 100,
                    }
        if ev["lineage"] is not None:
            entry["lineage"] = ev["lineage"]
        if ev["history"]:
            # Stamps only (who/when/that-an-edit-happened); the values
            # live in the field record the Operator already sees.
            entry["edits"] = [
                {"ts": e.get("ts"), "edited": e.get("old") is not None}
                for e in ev["history"] if isinstance(e, dict)]
        entry["verified_original"] = _evidence.verify_original_recorded(
            store, doc.doc_id, code)
        out[code] = entry
    return {"doc_id": doc.doc_id, "fields": out}


def queue_html(store: DocumentStore, year: int | None, form: str | None,
               token: str | None = None,
               include_irrelevant: bool = False) -> str:
    docs = [d for d in store.list()
            if d.status in lifecycle.UNVALIDATED_EXTRACTED]
    if year is not None:
        docs = [d for d in docs if d.tax_year == year]
    if form:
        docs = [d for d in docs if d.form_type == form]
    # Relevance triage hides irrelevants from the review queue by default
    # (falsification fix: the operator never has to look at what the
    # mechanical rules already dropped). Irrelevant docs remain
    # listed/auditable with their reason codes -- never invisible --
    # and are restorable via the override path.
    hidden = [d for d in docs if d.relevance == "irrelevant"]
    if not include_irrelevant:
        docs = [d for d in docs if d.relevance != "irrelevant"]
    base = _token_url_base(token)

    # progress per year over ALL documents
    years = sorted({d.tax_year for d in store.list()}, key=lambda v: (v is None, v))
    prog = []
    for y in years:
        all_y = [d for d in store.list() if d.tax_year == y]
        done = sum(1 for d in all_y if d.status == "validated")
        ylab = str(y) if y is not None else "????"
        prog.append(f"{ylab}: {done}/{len(all_y)} validated")
    prog_html = " &nbsp;·&nbsp; ".join(prog) if prog else "no documents"

    # filter options
    forms = sorted({d.form_type for d in store.list()})
    flinks = [f'<a href="{base}/">all</a>']
    for y in years:
        flinks.append(f'<a href="{base}/?tax_year={y if y is not None else ""}">{y if y is not None else "????"}</a>')
    for f in forms:
        flinks.append(f'<a href="{base}/?form_type={quote(f)}">{html.escape(f)}</a>')

    rows = []
    for d in docs:
        low = sum(1 for f in d.fields.values()
                  if isinstance(f, dict) and f.get("confidence") == "low")
        nfields = sum(1 for c, f in d.fields.items()
                      if isinstance(f, dict) and not c.startswith("__"))
        # R19: per-doc evidence coverage (geometry presence only --
        # metadata, no rendering).
        ngeom = sum(1 for c, f in d.fields.items()
                    if isinstance(f, dict) and not c.startswith("__")
                    and _evidence.field_geometry(f) is not None)
        rows.append(
            "<tr>"
            f'<td><a href="{base}/doc/{quote(d.doc_id)}">{html.escape(d.doc_id)}</a></td>'
            f"<td>{d.tax_year if d.tax_year is not None else '????'}</td>"
            f"<td>{html.escape(d.form_type)}</td>"
            f"<td>{html.escape(d.status)}</td>"
            f"<td>{html.escape(d.relevance)}</td>"
            f"<td>{nfields}</td>"
            f"<td>{low}</td>"
            f"<td>{ngeom}/{nfields}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else '<tr><td colspan="8"><i>Queue empty — all validated.</i></td></tr>'
    hide_note = ""
    if hidden and not include_irrelevant:
        hide_note = (f'<div class="prog">{len(hidden)} irrelevant '
                     'document(s) hidden — <a href="?include_irrelevant=1">'
                     "audit them</a></div>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>taxprep review queue</title><style>{_CSS}</style></head><body>
<h1>Review queue</h1>
<div class="prog">{prog_html}</div>
{hide_note}
<div class="filters">{' '.join(flinks)}</div>
<table><tr><th>doc_id</th><th>year</th><th>form</th><th>status</th>
<th>relevance</th><th>fields</th><th>low-conf</th><th>evidence</th></tr>{body}</table>
</body></html>"""


def _fmt_value(v) -> str:
    if v is None:
        return ""
    return str(v)


def doc_html(store: DocumentStore, doc: Document,
             token: str | None = None) -> str:
    base = _token_url_base(token)
    # R19: PDF sources get the evidence pane (rendered pages + bbox
    # overlays + per-field snapshots); everything else keeps the
    # standing evidence path.
    images_mode = evidence_status(store, doc)["mode"] == "images"
    if images_mode:
        evidence, evidence_blocked = _page_viewer_html(store, doc, base)
        if evidence_blocked:
            # Renderer failed despite the status check -- degrade to the
            # legacy path, which surfaces the blocking banner.
            evidence, evidence_blocked = _source_evidence_html(store, doc)
            images_mode = False
    else:
        evidence, evidence_blocked = _source_evidence_html(store, doc)
    rows = []
    orig = {}
    for code, f in doc.fields.items():
        if not isinstance(f, dict) or code.startswith("__"):
            continue  # review bookkeeping entries are not field rows
        val = _fmt_value(f.get("value"))
        conf = f.get("confidence") or "?"
        orig[code] = val
        low = conf == "low"
        checked = "" if low else "checked"
        rowcls = "field-row lowconf" if low else "field-row"
        evcell, ev_disabled = _field_evidence_cell(
            store, doc, code, f, base, images_mode)
        dis = "disabled" if ev_disabled else ""
        rows.append(
            f'<tr class="{rowcls}" data-box="{html.escape(code)}" '
            f'id="row-{html.escape(code)}">'
            f"<td>{html.escape(code)}</td>"
            f'<td class="valcell"><input class="fval" value="{html.escape(val, quote=True)}"></td>'
            f"<td>{_badge(conf)}</td>"
            f'<td><input type="checkbox" class="fchk" {checked} {dis}></td>'
            f'<td class="evcell">{evcell}</td>'
            "</tr>"
        )
    fields_html = "\n".join(rows) if rows else \
        '<tr><td colspan="5"><i>No extracted fields.</i></td></tr>'
    orig_json = json.dumps(orig)
    form_opts = "".join(
        f'<option value="{t}"{" selected" if t == doc.form_type else ""}>{t}</option>'
        for t in FORM_TYPES if t != "UNKNOWN"
    )
    year_val = "" if doc.tax_year is None else str(doc.tax_year)
    blocked_js = "true" if evidence_blocked else "false"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>review {html.escape(doc.doc_id)}</title><style>{_CSS}</style></head><body>
<h1>{html.escape(doc.form_type)} {doc.tax_year if doc.tax_year is not None else '????'}
  <small>({html.escape(doc.doc_id)})</small></h1>
<p><a href="{base}/">&larr; queue</a> &nbsp; status: <b>{html.escape(doc.status)}</b></p>
<div class="cols">
<div class="left"><h2>Source</h2>{evidence}</div>
<div class="right">
<h2>Document identity (confirm or correct)</h2>
<table><tr><th>item</th><th>value</th><th>confirm</th></tr>
<tr><td>form_type</td>
<td><select id="formType">{form_opts}</select></td>
<td><input type="checkbox" id="formChk"></td></tr>
<tr><td>tax_year</td>
<td><input id="taxYear" type="number" min="1900" max="2100" value="{html.escape(year_val, quote=True)}"></td>
<td><input type="checkbox" id="yearChk"></td></tr>
</table>
<h2>Extracted fields</h2>
<table><tr><th>box</th><th>value (editable)</th><th>confidence</th><th>confirm</th><th>source evidence</th></tr>
{fields_html}</table>
<p><button id="validateBtn" disabled>Mark validated</button>
<span id="msg"></span></p>
</div></div>
<script>
const orig = {orig_json};
const docId = {json.dumps(doc.doc_id)};
const origForm = {json.dumps(doc.form_type)};
const origYear = {json.dumps(doc.tax_year)};
const evidenceBlocked = {blocked_js};
const formSel = document.getElementById("formType");
const yearIn = document.getElementById("taxYear");
const formChk = document.getElementById("formChk");
const yearChk = document.getElementById("yearChk");
function refresh() {{
  let ok = !evidenceBlocked;
  document.querySelectorAll("tr.field-row").forEach(tr => {{
    const box = tr.dataset.box;
    const input = tr.querySelector("input.fval");
    const chk = tr.querySelector("input.fchk");
    const edited = input.value !== (orig[box] ?? "");
    tr.classList.toggle("edited", edited);
    if (!(chk.checked || edited)) ok = false;
  }});
  // identity is a required confirm/correct item (server refuses without it)
  const formOk = formChk.checked || formSel.value !== origForm;
  const yearOk = yearChk.checked || yearIn.value !== String(origYear ?? "");
  if (!(formOk && yearOk)) ok = false;
  document.getElementById("validateBtn").disabled = !ok;
  const msg = document.getElementById("msg");
  if (evidenceBlocked) msg.textContent = "validation blocked: page images unavailable";
}}
[formSel, yearIn, formChk, yearChk].forEach(el =>
  el.addEventListener("input", refresh));
document.querySelectorAll("input.fval,input.fchk").forEach(el =>
  el.addEventListener("input", refresh));
refresh();
// R19: bidirectional selection between field rows and bbox overlays
function flashRow(row) {{
  row.classList.add("selrow");
  setTimeout(() => row.classList.remove("selrow"), 1200);
}}
document.querySelectorAll(".bbox").forEach(bx => {{
  bx.addEventListener("click", () => {{
    document.querySelectorAll(".bbox.sel").forEach(o => o.classList.remove("sel"));
    bx.classList.add("sel");
    const row = document.getElementById("row-" + bx.dataset.box);
    if (row) {{ row.scrollIntoView({{block: "center"}}); flashRow(row); }}
  }});
}});
document.querySelectorAll("tr.field-row td:first-child").forEach(td => {{
  td.addEventListener("click", () => {{
    const box = td.closest("tr").dataset.box;
    const bx = document.querySelector('.bbox[data-box="' + box + '"]');
    if (bx) {{
      document.querySelectorAll(".bbox.sel").forEach(o => o.classList.remove("sel"));
      bx.classList.add("sel");
      bx.scrollIntoView({{block: "center"}});
    }}
  }});
}});
// R19: zoom -- overlays use % coordinates, so they track the image;
// explicit pixel widths keep the shrink-wrapped page container aligned.
let zoomPct = 100;
function setZoom(z) {{
  zoomPct = Math.min(300, Math.max(50, z));
  document.querySelectorAll(".pageimg").forEach(im => {{
    const apply = () => {{
      im.style.width = Math.round(im.naturalWidth * zoomPct / 100) + "px";
    }};
    if (im.complete && im.naturalWidth) apply();
    else im.addEventListener("load", apply, {{once: true}});
  }});
  const lbl = document.getElementById("zoomLabel");
  if (lbl) lbl.textContent = zoomPct + "%";
}}
if (document.getElementById("zoomIn")) {{
  document.getElementById("zoomIn").addEventListener("click", () => setZoom(zoomPct + 25));
  document.getElementById("zoomOut").addEventListener("click", () => setZoom(zoomPct - 25));
  document.getElementById("zoomReset").addEventListener("click", () => setZoom(100));
}}
// R19: "verified against original" -- the fail-closed escape hatch for
// fields with no visual evidence (logged to the decision log).
document.querySelectorAll("button.vorig").forEach(btn => {{
  btn.addEventListener("click", async () => {{
    const box = btn.dataset.box;
    const r = await fetch("{base}/api/evidence/verify-original", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{doc_id: docId, field: box}})
    }});
    if (r.ok) {{
      const row = document.getElementById("row-" + box);
      row.querySelector("input.fchk").disabled = false;
      btn.outerHTML = '<div class="vok">✓ verified against original (logged)</div>';
      refresh();
    }} else {{
      btn.textContent = "recording failed — retry";
    }}
  }});
}});
document.getElementById("validateBtn").addEventListener("click", async () => {{
  const fields = {{}};
  const confirmed = [];
  document.querySelectorAll("tr.field-row").forEach(tr => {{
    const box = tr.dataset.box;
    const input = tr.querySelector("input.fval");
    if (input.value !== (orig[box] ?? "")) fields[box] = input.value;
    if (tr.querySelector("input.fchk").checked) confirmed.push(box);
  }});
  const payload = {{doc_id: docId, fields, confirmed,
    confirm_form_type: formChk.checked, confirm_tax_year: yearChk.checked}};
  if (formSel.value !== origForm) payload.form_type = formSel.value;
  if (yearIn.value !== String(origYear ?? ""))
    payload.tax_year = yearIn.value === "" ? null : parseInt(yearIn.value, 10);
  const r = await fetch("{base}/api/validate", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload)
  }});
  const msg = document.getElementById("msg");
  if (r.ok) {{ msg.textContent = "saved ✓"; setTimeout(() => location.href = "{base}/", 600); }}
  else {{
    let detail = "";
    try {{ const e = await r.json(); detail = ": " + (e.reasons || [e.error]).join(", "); }} catch (_e) {{}}
    msg.textContent = "refused (HTTP " + r.status + ")" + detail;
  }}
}});
</script>
</body></html>"""


# -- validation API -------------------------------------------------

def _coerce(value: str):
    """'1,234.56' -> '1234.56' ; '1234' -> '1234' ; else the string as-is.

    Numeric corrections stay STRINGS (never float): downstream consumers
    (carryforward.from_store) parse via Decimal and loudly reject floats,
    so a float here would break the validate -> carryforward pipeline.
    """
    s = value.strip().replace(",", "").replace("$", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return s
    return value


class ValidationRefused(Exception):
    """Structured refusal: validation was NOT applied.

    ``reasons`` is a list of stable reason codes; the document's status is
    never flipped when this is raised. The HTTP layer maps it to 422.
    """

    def __init__(self, doc_id: str, reasons: list[str]):
        self.doc_id = doc_id
        self.reasons = list(reasons)
        super().__init__(
            f"validation refused for {doc_id}: {', '.join(self.reasons)}")


_UNSET = object()  # "no correction supplied" marker for form_type/tax_year

# Field keys with this prefix are review-managed bookkeeping, not field rows:
# form_type / tax_year corrections are audited here so the original value is
# retained in per-field history exactly like any other Operator edit.
_FORM_TYPE_KEY = "__form_type__"
_TAX_YEAR_KEY = "__tax_year__"


def _field_rows(doc: Document) -> dict:
    """Extracted field rows (excludes review bookkeeping entries)."""
    return {c: f for c, f in doc.fields.items()
            if isinstance(f, dict) and not c.startswith("__")}


def _coerce_year(value) -> int | None:
    """Coerce a tax-year correction to int; None when invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and re.fullmatch(r"\d{4}", value.strip()):
        year = int(value.strip())
    else:
        return None
    return year if 1900 <= year <= 2100 else None


def _record_identity_edit(doc: Document, key: str, old, new, ts: str) -> None:
    """Audit a form_type/tax_year correction, retaining the original value.

    R15/P5: the first edit records ``original_value``/``edited_by``/
    ``edited_at``; later edits append to ``history`` but never overwrite
    the original. The corrected value stays traceable to its original.
    """
    entry = doc.fields.get(key)
    if not isinstance(entry, dict):
        entry = {"value": old, "confidence": "human-corrected",
                 "raw_text": "", "history": []}
        doc.fields[key] = entry
    entry.setdefault("history", []).append({"ts": ts, "old": old, "new": new})
    if "original_value" not in entry:
        entry["original_value"] = old
        entry["edited_by"] = "operator"
        entry["edited_at"] = ts
    entry["value"] = new


def apply_validation(store: DocumentStore, doc_id: str,
                     fields: dict, confirmed: list, *,
                     form_type=_UNSET, tax_year=_UNSET,
                     confirm_form_type: bool = False,
                     confirm_tax_year: bool = False) -> Document:
    """Write corrections into the store and flip the document to validated.

    Fail closed: raises :class:`ValidationRefused` (structured reason codes,
    status never flipped) when the evidence is unavailable/degraded, the
    document has zero field rows, form_type is UNKNOWN, tax_year is None,
    form_type/tax_year were neither confirmed nor corrected, or no field
    was confirmed or edited.

    ``fields`` may introduce box keys not already present — they are created
    with the corrected value and ``human-corrected`` confidence. Every
    Operator edit appends to the field's ``history`` ([{ts, old, new}, ...]);
    history is never overwritten. R15/P5: the first edit of a field
    additionally records ``original_value``/``edited_by``/``edited_at`` --
    the original extracted value survives every later edit, and the
    corrected value stays traceable to its original evidence
    (raw_text/provenance are extraction evidence and are never touched
    by edits).
    """
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(doc_id)

    reasons: list[str] = []

    # --- evidence gate: page images mandatory, fail closed ---
    ev = evidence_status(store, doc)
    if ev["mode"] == "unavailable":
        reasons.append("evidence_unavailable")
    elif ev["mode"] == "degraded":
        reasons.append("degraded_evidence")

    # --- identity: form_type / tax_year are required confirm/correct items ---
    new_form = doc.form_type
    if form_type is not _UNSET:
        if form_type not in FORM_TYPES or form_type == "UNKNOWN":
            reasons.append("invalid_form_type")
        else:
            new_form = form_type
    new_year = doc.tax_year
    if tax_year is not _UNSET:
        coerced = _coerce_year(tax_year)
        if coerced is None:
            reasons.append("invalid_tax_year")
        else:
            new_year = coerced
    form_changed = form_type is not _UNSET and "invalid_form_type" not in reasons
    year_changed = tax_year is not _UNSET and "invalid_tax_year" not in reasons

    if "invalid_form_type" not in reasons:
        if new_form == "UNKNOWN":
            reasons.append("unknown_form")
        elif not (confirm_form_type or form_changed):
            reasons.append("unconfirmed_form")
    if "invalid_tax_year" not in reasons:
        if new_year is None:
            reasons.append("missing_year")
        elif not (confirm_tax_year or year_changed):
            reasons.append("unconfirmed_year")

    # --- field rows: refused when empty, and when nothing was confirmed ---
    rows = _field_rows(doc)
    new_boxes = [b for b in fields if not str(b).startswith("__")]
    if not rows and not new_boxes:
        reasons.append("empty_fields")
    confirmed_boxes = {b for b in confirmed if b in rows or b in new_boxes}
    edited = bool(new_boxes) or form_changed or year_changed
    if not confirmed_boxes and not edited:
        reasons.append("nothing_confirmed")

    # --- R19: per-field evidence gate (images mode only) ---
    # A confirmed field must have visual evidence (a snapshot, lineage
    # for computed fields, or original evidence for an edited field) or
    # an Operator "verified against original" record in the decision
    # log. Text-mode documents keep their standing behavior: the source
    # text IS the evidence.
    if ev["mode"] == "images":
        for box in sorted(confirmed_boxes):
            f = rows.get(box)
            st = _evidence.field_evidence(
                f if isinstance(f, dict) else {})
            if st["state"] in (_evidence.STATE_SNAPSHOT,
                               _evidence.STATE_LINEAGE,
                               _evidence.STATE_EDITED):
                continue
            if _evidence.verify_original_recorded(store, doc_id, box):
                continue
            reasons.append("no_evidence_unverified")
            break

    if reasons:
        raise ValidationRefused(doc_id, reasons)

    # --- apply: all gates passed ---
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # R13: the validate/fix_form_year events go through the lifecycle
    # state machine (actor=operator -- this localhost UI is an Operator
    # surface). The machine re-checks the identity/field guards as a
    # backstop; a refusal raises ValidationRefused and flips nothing.
    form_attested = confirm_form_type or form_changed
    year_attested = confirm_tax_year or year_changed
    validate_input = lifecycle.ValidateInput(
        n_fields=len(rows) + len(new_boxes),
        form_known=new_form != "UNKNOWN",
        year_known=new_year is not None,
        form_confirmed_or_corrected=form_attested,
        year_confirmed_or_corrected=year_attested,
        field_confirmed_or_edited=bool(confirmed_boxes) or edited)
    old_form, old_year = doc.form_type, doc.tax_year
    edit_records: list[tuple[str, object, object]] = []
    with store.txn():
        if doc.status == lifecycle.BLOCKED:
            # R13: a BLOCKED doc re-enters via fix_form_year (operator
            # supplies the missing identity) before validate.
            fix = lifecycle.transition(
                doc, lifecycle.FIX_FORM_YEAR, actor=lifecycle.OPERATOR,
                event_input=lifecycle.FixInput(form_type=new_form,
                                              tax_year=new_year),
                store=store)
            if not fix.ok:
                raise ValidationRefused(
                    doc_id, [fix.reason_code or "fix_refused"])
            # The transition applied the identity fix; audit it once
            # here so the field-edit section below does not duplicate it.
            if form_changed:
                _record_identity_edit(doc, _FORM_TYPE_KEY, old_form,
                                      new_form, ts)
                edit_records.append((_FORM_TYPE_KEY, old_form, new_form))
                form_changed = False
            if year_changed:
                _record_identity_edit(doc, _TAX_YEAR_KEY, old_year,
                                      new_year, ts)
                edit_records.append((_TAX_YEAR_KEY, old_year, new_year))
                year_changed = False
        for box in new_boxes:
            new_val = _coerce(str(fields[box]))
            if box in rows:
                f = rows[box]
                old = f.get("value")
                if old != new_val:
                    f.setdefault("history", []).append(
                        {"ts": ts, "old": old, "new": new_val})
                    # R15/P5: the original extracted value survives every
                    # edit (recorded once, on the first edit).
                    if "original_value" not in f:
                        f["original_value"] = old
                        f["edited_by"] = "operator"
                        f["edited_at"] = ts
                    f["value"] = new_val
                    edit_records.append((box, old, new_val))
            else:
                doc.fields[box] = {
                    "value": new_val,
                    "confidence": "human-corrected",
                    "raw_text": "",
                    "history": [{"ts": ts, "old": None, "new": new_val}],
                }
                edit_records.append((box, None, new_val))
        if form_changed:
            _record_identity_edit(doc, _FORM_TYPE_KEY, old_form, new_form,
                                  ts)
            doc.form_type = new_form
            edit_records.append((_FORM_TYPE_KEY, old_form, new_form))
        if year_changed:
            _record_identity_edit(doc, _TAX_YEAR_KEY, old_year, new_year,
                                  ts)
            doc.tax_year = new_year
            edit_records.append((_TAX_YEAR_KEY, old_year, new_year))
        done = lifecycle.transition(
            doc, lifecycle.VALIDATE, actor=lifecycle.OPERATOR,
            event_input=validate_input, store=store, now=ts)
        if not done.ok:
            raise ValidationRefused(
                doc_id, [done.reason_code or "validate_refused"])
        validated_fields = sorted(
            set(confirmed_boxes)
            | {box for box, _, _ in edit_records
               if not box.startswith(silver.BOOKKEEPING_PREFIX)})
        bronze_hash = silver.bronze_hash_for_doc(store, doc)
        page = silver.best_page_for_doc(doc)
        # Contract section 5: fields_json + artifact mirror + decision
        # log are updated together, in one transaction. The derivation
        # stamp is preserved (upsert_silver_doc, never the facade "1"
        # path) whenever the bronze linkage resolves; tombstone docs
        # without artifacts fall back to the facade upsert, whose bronze
        # handling re-attaches them.
        if bronze_hash is None:
            store.upsert(doc)
            bronze_hash = silver.bronze_hash_for_doc(store, doc)
        else:
            silver.persist_silver_doc(
                store, doc, silver.derivation_for_doc(store, doc.doc_id),
                bronze_hash)
        store.log_decision(
            actor="operator", kind="validate", doc_id=doc.doc_id,
            payload={"doc_id": doc.doc_id,
                     "validated_fields": validated_fields, "ts": ts})
        for box, old, new in edit_records:
            artifact_id = None
            if (bronze_hash is not None
                    and not box.startswith(silver.BOOKKEEPING_PREFIX)):
                artifact_id = silver.artifact_id_for(
                    doc.doc_id, bronze_hash, page, silver.FIELD, box)
            store.log_decision(
                actor="operator", kind="edit", artifact_id=artifact_id,
                doc_id=doc.doc_id,
                payload={"field": box, "old": old, "new": new, "ts": ts})
        _sync_field_artifacts(store, doc)
    return doc


def _sync_field_artifacts(store: DocumentStore, doc: Document) -> None:
    """Mirror validated/edited fields into silver_artifact rows.

    Each field artifact's value_json is refreshed to the canonical
    current field entry; operator-added fields gain artifacts;
    payer/lot/section artifacts pass through untouched. Full replace
    per doc (contract section 5).
    """
    bronze_hash = silver.bronze_hash_for_doc(store, doc)
    if bronze_hash is None:
        return
    page = silver.best_page_for_doc(doc)
    ctx = silver.derivation_for_doc(store, doc.doc_id)
    arts = store.get_artifacts(doc.doc_id) or []
    by_key = {(a["artifact_type"], a["anchor"]): dict(a) for a in arts}
    changed = False
    for code, f in _field_rows(doc).items():
        key = (silver.FIELD, code)
        value_json = silver.field_artifact_value(f)
        if key in by_key:
            if by_key[key].get("value_json") != value_json:
                by_key[key]["value_json"] = value_json
                changed = True
        else:
            by_key[key] = {
                "artifact_id": silver.artifact_id_for(
                    doc.doc_id, bronze_hash, page, silver.FIELD, code),
                "page": page,
                "artifact_type": silver.FIELD,
                "anchor": code,
                "value_json": value_json,
                "offsets_json": None,
                "derivation_version": ctx.derivation_version,
                "config_hash": ctx.config_hash,
            }
            changed = True
    if changed:
        store.replace_artifacts(doc.doc_id, list(by_key.values()))


# -- request hardening (R10) -----------------------------------------

def _resolve_token(flag) -> str | None:
    """Normalize the ``--token`` flag: None -> token mode off; True or ""
    (bare flag) -> auto-generate via ``secrets.token_urlsafe``; any other
    value -> used verbatim as the URL token."""
    if flag is None:
        return None
    if flag is True or flag == "":
        return secrets.token_urlsafe(16)
    return str(flag)


def _token_url_base(token: str | None) -> str:
    """URL prefix every route lives under when token mode is on."""
    return "/t/" + quote(token, safe="") if token else ""


def add_token_argument(parser) -> None:
    """Register ``--token`` on the ``review`` subparser. Called from cli.py::

        pr = sub.add_parser("review", ...)
        add_token_argument(pr)          # <-- add this line
        ...
        # in cmd_review:
        serve_forever(store, port=args.port, token=args.token)   # <-- pass through
    """
    parser.add_argument(
        "--token", nargs="?", const="", default=None, metavar="TOKEN",
        help="require a per-run URL token on every route "
             "(bare flag auto-generates one, printed at startup)")


# -- HTTP layer -----------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    store: DocumentStore  # set by factory
    token: str | None = None  # set by factory; None = token mode off

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: str | bytes, ctype: str) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code: int, body: str) -> None:
        self._send(code, body, "text/html; charset=utf-8")

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj), "application/json")

    # -- R10 hardening gates (applied to every route) ----------------

    def _bound_port(self) -> int:
        return self.server.server_address[1]

    def _deny(self, code: int, message: str) -> None:
        """Reject in the response shape of the request method."""
        if self.command == "POST":
            self._json(code, {"ok": False, "error": message})
        else:
            self._html(code, f"<h1>{code} — {html.escape(message)}</h1>")

    def _check_host(self) -> bool:
        """Strict Host allowlist: only 127.0.0.1:<port> / localhost:<port>.

        Kills the DNS-rebinding precondition — a rebound request arrives
        with ``Host: <attacker-domain>:<port>`` and is refused before any
        route logic runs. Missing Host is refused too.
        """
        host = (self.headers.get("Host") or "").strip().lower()
        port = self._bound_port()
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self._deny(403, "forbidden host")
            return False
        return True

    def _check_json_content(self) -> bool:
        """POST requires Content-Type: application/json.

        A text/plain simple-request POST from a foreign page can no longer
        reach the validate logic. 415 (not 403): the media type is
        unsupported, not the requester's identity.
        """
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._json(415, {"ok": False, "error": "unsupported_media_type",
                             "detail": "POST requires Content-Type: application/json"})
            return False
        return True

    def _check_origin(self) -> bool:
        """Same-origin gate: the Origin host:port must match the allowlist.

        Blocks simple-request CSRF — a foreign page's POST carries
        ``Origin: http(s)://attacker...`` (or none at all from non-browser
        clients), never the loopback origin the page was served from.
        """
        origin = self.headers.get("Origin")
        port = self._bound_port()
        if origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self._json(403, {"ok": False, "error": "forbidden_origin"})
            return False
        return True

    def _effective_path(self) -> str | None:
        """Request path with the ``/t/<token>`` prefix stripped.

        Returns None when token mode is on and the prefix is missing or
        wrong — the caller 404s, indistinguishable from an unknown path.
        """
        parsed = urlparse(self.path)
        path = parsed.path
        if self.token is not None:
            prefix = "/t/" + quote(self.token, safe="")
            if path == prefix:
                path = "/"
            elif path.startswith(prefix + "/"):
                path = path[len(prefix):]
            else:
                return None
        if parsed.query:
            path += "?" + parsed.query
        return path

    def do_GET(self) -> None:
        if not self._check_host():
            return
        eff = self._effective_path()
        if eff is None:
            self._deny(404, "not found")
            return
        parsed = urlparse(eff)
        if parsed.path == "/":
            qs = parse_qs(parsed.query)
            year = None
            if qs.get("tax_year", [""])[0].strip():
                try:
                    year = int(qs["tax_year"][0])
                except ValueError:
                    pass
            form = qs.get("form_type", [""])[0] or None
            include_irr = (qs.get("include_irrelevant", [""])[0] or ""
                           ).strip().lower() in ("1", "true", "yes")
            self._html(200, queue_html(self.store, year, form, self.token,
                                       include_irrelevant=include_irr))
        elif parsed.path.startswith("/doc/"):
            doc_id = unquote(parsed.path[len("/doc/"):])
            doc = self.store.get(doc_id)
            if doc is None:
                self._html(404, "<h1>404 — no such document</h1>")
            else:
                self._html(200, doc_html(self.store, doc, self.token))
        elif parsed.path.startswith("/api/evidence/"):
            # R19 evidence endpoints -- the R10 gates above (Host
            # allowlist, per-run token prefix) already ran.
            self._serve_evidence(parsed)
        elif parsed.path == "/console" or parsed.path.startswith("/console/"):
            # R12 Operator console. The R10 gates above (Host allowlist,
            # per-run token prefix) already ran -- every console GET
            # inherits them.
            page = _console.dispatch_get(self.store, parsed, self.token)
            if page is None:
                self._html(404, "<h1>404</h1>")
            else:
                self._html(200, page)
        else:
            self._html(404, "<h1>404</h1>")

    def _send_file(self, path: Path, ctype: str) -> None:
        """Serve a file from disk (evidence images, bronze originals)."""
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Deterministic content (content-addressed cache) -- private,
        # never shared caches: this is PII on a loopback server.
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _serve_evidence(self, parsed) -> None:
        """R19 evidence endpoints (loopback only, R10-hardened).

        GET /api/evidence/page?doc_id=&page=&dpi=  -> image/jpeg
        GET /api/evidence/snapshot?doc_id=&field=  -> image/jpeg
        GET /api/evidence/fields?doc_id=            -> application/json
        GET /api/evidence/original?doc_id=          -> bronze bytes

        Images are PII: served ONLY here, never from MCP tools, never
        on the bus. Every failure is fail-closed (JSON error, never a
        placeholder or guessed image).
        """
        qs = parse_qs(parsed.query)
        doc_id = qs.get("doc_id", [""])[0]
        doc = self.store.get(doc_id)
        if doc is None:
            self._json(404, {"ok": False, "error": "no such document"})
            return
        sub = parsed.path[len("/api/evidence/"):]
        if sub == "page":
            try:
                page = int(qs.get("page", ["0"])[0])
                dpi = int(qs.get("dpi", [str(_evidence.PAGE_DPI)])[0])
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad page/dpi"})
                return
            if page < 0 or dpi not in (72, 110, 150, 220, 300):
                self._json(400, {"ok": False, "error": "bad page/dpi"})
                return
            path, err = _evidence.render_page(self.store, doc, page, dpi=dpi)
            if path is None:
                self._json(503, {"ok": False,
                                 "error": err or "render_failed"})
                return
            self._send_file(path, "image/jpeg")
        elif sub == "snapshot":
            field = qs.get("field", [""])[0]
            path, err = _evidence.field_snapshot(self.store, doc, field)
            if path is None:
                self._json(404, {"ok": False,
                                 "error": err or "no_evidence"})
                return
            self._send_file(path, "image/jpeg")
        elif sub == "fields":
            self._json(200, evidence_fields_payload(self.store, doc))
        elif sub == "original":
            bronze_path = _evidence.bronze_path_for_doc(self.store, doc)
            if bronze_path is None:
                self._json(404, {"ok": False, "error": "no bronze copy"})
                return
            # Bronze objects are stored extensionless -- sniff, don't guess.
            ctype, suffix = _evidence.bronze_mime(bronze_path)
            data = bronze_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header(
                "Content-Disposition",
                f'inline; filename="{doc.doc_id}{suffix}"')
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self._check_host():
            return
        eff = self._effective_path()
        path = urlparse(eff).path if eff is not None else None
        if eff is None or (path != "/api/validate"
                           and path != "/api/evidence/verify-original"
                           and not path.startswith("/console/api/")):
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._check_json_content():
            return
        if not self._check_origin():
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid JSON"})
            return
        if path.startswith("/console/api/"):
            # R12 console API -- same R10 gates as /api/validate.
            status, obj = _console.dispatch_post(self.store, path, payload)
            self._json(status, obj)
            return
        if path == "/api/evidence/verify-original":
            # R19 fail-closed escape hatch: the Operator records
            # "verified against original" for a field with no visual
            # evidence. Logged to the append-only decision log.
            doc_id = payload.get("doc_id", "")
            field = payload.get("field", "")
            doc = self.store.get(doc_id)
            if doc is None or not isinstance(field, str) or not field:
                self._json(404, {"ok": False, "error": "not found"})
                return
            try:
                seq = _evidence.record_verify_original(
                    self.store, doc_id, field)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "seq": seq})
            return
        doc_id = payload.get("doc_id", "")
        form_type = payload.get("form_type")
        if form_type is None:
            form_type = _UNSET  # JSON null == not supplied; never a correction
        tax_year = payload.get("tax_year")
        if tax_year is None:
            tax_year = _UNSET
        try:
            apply_validation(self.store, doc_id,
                             payload.get("fields", {}) or {},
                             payload.get("confirmed", []) or [],
                             form_type=form_type, tax_year=tax_year,
                             confirm_form_type=bool(
                                 payload.get("confirm_form_type", False)),
                             confirm_tax_year=bool(
                                 payload.get("confirm_tax_year", False)))
        except KeyError:
            self._json(404, {"ok": False, "error": f"no such document: {doc_id}"})
            return
        except ValidationRefused as e:
            self._json(422, {"ok": False, "error": "validation_refused",
                             "reasons": e.reasons})
            return
        self._json(200, {"ok": True})


def _handler_factory(store: DocumentStore, token: str | None = None):
    class Handler(_Handler):
        pass
    Handler.store = store
    Handler.token = token
    return Handler


def make_server(store: DocumentStore, port: int = DEFAULT_PORT,
                host: str = BIND_HOST, token=None) -> ThreadingHTTPServer:
    """Create (not yet serving) the review server. Binds loopback only.

    ``token`` follows :func:`_resolve_token`: None = token mode off,
    True/"" = auto-generate, a string = use verbatim. When on, every route
    requires the ``/t/<token>`` URL prefix.
    """
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(f"refusing to bind non-loopback host: {host!r}")
    return ThreadingHTTPServer(
        (host, port), _handler_factory(store, token=_resolve_token(token)))


def serve_forever(store: DocumentStore, port: int = DEFAULT_PORT,
                  token=None) -> None:
    """Serve the review UI until Ctrl-C. ``token``: see :func:`make_server`.

    The startup banner prints the full URL (including the token prefix
    when token mode is on) — the single place the per-run token appears.
    """
    token = _resolve_token(token)
    server = make_server(store, port, token=token)
    url = f"http://127.0.0.1:{server.server_address[1]}{_token_url_base(token)}/"
    print(f"taxprep review at {url}  (localhost only — Ctrl-C to stop)")
    if token:
        print("URL token required on every route — keep this URL private to this session.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
