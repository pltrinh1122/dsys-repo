"""Visual validation UI — localhost-only HTTP server.

Workflow: ``taxprep ingest`` populates the store; ``taxprep review`` serves
a browser UI where each document's extracted fields are checked against the
source evidence (OCR text with extracted spans highlighted, or PDF page
images when a renderer is available). Corrections are written back through
``POST /api/validate`` and flip the document to ``validated``.

Security: binds 127.0.0.1 ONLY. Any other host is refused.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .models import Document
from .store import DocumentStore

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
"""


# -- HTML rendering -------------------------------------------------

def _badge(conf: str) -> str:
    cls = {"high": "b-high", "medium": "b-medium", "low": "b-low"}.get(conf, "b-medium")
    return f'<span class="badge {cls}">{html.escape(conf or "?")}</span>'


def highlight_ocr(text: str, fields: dict) -> str:
    """Escape OCR text to HTML and <mark> each field's raw_text span.

    Case-insensitive, longest-first, single pass (no nested marks).
    Degrades to plain escaped text when no spans match.
    """
    spans = {
        (f.get("raw_text") or "").strip()
        for f in fields.values()
        if isinstance(f, dict)
    }
    spans.discard("")
    if not spans:
        return html.escape(text)
    escaped = sorted((html.escape(s) for s in spans), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(p) for p in escaped), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", html.escape(text))


def _pdf_page_images(doc: Document, max_pages: int = 3) -> list[str]:
    """Render source PDF pages to JPEG data URIs. [] when unavailable."""
    src = doc.source_path or ""
    if not src.lower().endswith(".pdf"):
        return []
    pdf_path = Path(src)
    if not pdf_path.exists():
        return []
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return []
    try:
        images = convert_from_path(str(pdf_path), dpi=110,
                                   first_page=1, last_page=max_pages)
    except Exception:
        return []
    out = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


def _source_evidence_html(store: DocumentStore, doc: Document) -> str:
    pages = _pdf_page_images(doc)
    if pages:
        imgs = "".join(
            f'<img src="data:image/jpeg;base64,{p}" alt="source page">' for p in pages
        )
        return f'<div class="src">{imgs}</div>'
    try:
        text = store.load_ocr(doc.doc_id)
    except (FileNotFoundError, OSError):
        return '<div class="src"><i>No source text available.</i></div>'
    return f'<div class="src">{highlight_ocr(text, doc.fields)}</div>'


def queue_html(store: DocumentStore, year: int | None, form: str | None) -> str:
    docs = [d for d in store.list() if d.status in ("transcribed", "needs_review")]
    if year is not None:
        docs = [d for d in docs if d.tax_year == year]
    if form:
        docs = [d for d in docs if d.form_type == form]

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
    flinks = [f'<a href="/">all</a>']
    for y in years:
        flinks.append(f'<a href="/?tax_year={y if y is not None else ""}">{y if y is not None else "????"}</a>')
    for f in forms:
        flinks.append(f'<a href="/?form_type={quote(f)}">{html.escape(f)}</a>')

    rows = []
    for d in docs:
        low = sum(1 for f in d.fields.values()
                  if isinstance(f, dict) and f.get("confidence") == "low")
        rows.append(
            "<tr>"
            f'<td><a href="/doc/{quote(d.doc_id)}">{html.escape(d.doc_id)}</a></td>'
            f"<td>{d.tax_year if d.tax_year is not None else '????'}</td>"
            f"<td>{html.escape(d.form_type)}</td>"
            f"<td>{html.escape(d.status)}</td>"
            f"<td>{len(d.fields)}</td>"
            f"<td>{low}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else '<tr><td colspan="6"><i>Queue empty — all validated.</i></td></tr>'
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>taxprep review queue</title><style>{_CSS}</style></head><body>
<h1>Review queue</h1>
<div class="prog">{prog_html}</div>
<div class="filters">{' '.join(flinks)}</div>
<table><tr><th>doc_id</th><th>year</th><th>form</th><th>status</th>
<th>fields</th><th>low-conf</th></tr>{body}</table>
</body></html>"""


def _fmt_value(v) -> str:
    if v is None:
        return ""
    return str(v)


def doc_html(store: DocumentStore, doc: Document) -> str:
    evidence = _source_evidence_html(store, doc)
    rows = []
    orig = {}
    for code, f in doc.fields.items():
        if not isinstance(f, dict):
            continue
        val = _fmt_value(f.get("value"))
        conf = f.get("confidence") or "?"
        orig[code] = val
        low = conf == "low"
        checked = "" if low else "checked"
        rowcls = "field-row lowconf" if low else "field-row"
        rows.append(
            f'<tr class="{rowcls}" data-box="{html.escape(code)}">'
            f"<td>{html.escape(code)}</td>"
            f'<td class="valcell"><input class="fval" value="{html.escape(val, quote=True)}"></td>'
            f"<td>{_badge(conf)}</td>"
            f'<td><input type="checkbox" class="fchk" {checked}></td>'
            "</tr>"
        )
    fields_html = "\n".join(rows) if rows else \
        '<tr><td colspan="4"><i>No extracted fields.</i></td></tr>'
    orig_json = json.dumps(orig)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>review {html.escape(doc.doc_id)}</title><style>{_CSS}</style></head><body>
<h1>{html.escape(doc.form_type)} {doc.tax_year if doc.tax_year is not None else '????'}
  <small>({html.escape(doc.doc_id)})</small></h1>
<p><a href="/">&larr; queue</a> &nbsp; status: <b>{html.escape(doc.status)}</b></p>
<div class="cols">
<div class="left"><h2>Source</h2>{evidence}</div>
<div class="right"><h2>Extracted fields</h2>
<table><tr><th>box</th><th>value (editable)</th><th>confidence</th><th>confirm</th></tr>
{fields_html}</table>
<p><button id="validateBtn" disabled>Mark validated</button>
<span id="msg"></span></p>
</div></div>
<script>
const orig = {orig_json};
const docId = {json.dumps(doc.doc_id)};
function refresh() {{
  let ok = true;
  document.querySelectorAll("tr.field-row").forEach(tr => {{
    const box = tr.dataset.box;
    const input = tr.querySelector("input.fval");
    const chk = tr.querySelector("input.fchk");
    const edited = input.value !== (orig[box] ?? "");
    tr.classList.toggle("edited", edited);
    if (!(chk.checked || edited)) ok = false;
  }});
  document.getElementById("validateBtn").disabled = !ok;
}}
document.querySelectorAll("input.fval,input.fchk").forEach(el =>
  el.addEventListener("input", refresh));
refresh();
document.getElementById("validateBtn").addEventListener("click", async () => {{
  const fields = {{}};
  const confirmed = [];
  document.querySelectorAll("tr.field-row").forEach(tr => {{
    const box = tr.dataset.box;
    const input = tr.querySelector("input.fval");
    if (input.value !== (orig[box] ?? "")) fields[box] = input.value;
    if (tr.querySelector("input.fchk").checked) confirmed.push(box);
  }});
  const r = await fetch("/api/validate", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{doc_id: docId, fields, confirmed}})
  }});
  const msg = document.getElementById("msg");
  if (r.ok) {{ msg.textContent = "saved ✓"; setTimeout(() => location.href = "/", 600); }}
  else {{ msg.textContent = "error: " + r.status; }}
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


def apply_validation(store: DocumentStore, doc_id: str,
                     fields: dict, confirmed: list) -> Document:
    """Write corrections into the store and flip the document to validated."""
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    for box, corrected in fields.items():
        if box in doc.fields and isinstance(doc.fields[box], dict):
            doc.fields[box]["value"] = _coerce(str(corrected))
    doc.status = "validated"
    doc.validated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.upsert(doc)
    return doc


# -- HTTP layer -----------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    store: DocumentStore  # set by factory

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            qs = parse_qs(parsed.query)
            year = None
            if qs.get("tax_year", [""])[0].strip():
                try:
                    year = int(qs["tax_year"][0])
                except ValueError:
                    pass
            form = qs.get("form_type", [""])[0] or None
            self._html(200, queue_html(self.store, year, form))
        elif parsed.path.startswith("/doc/"):
            doc_id = unquote(parsed.path[len("/doc/"):])
            doc = self.store.get(doc_id)
            if doc is None:
                self._html(404, "<h1>404 — no such document</h1>")
            else:
                self._html(200, doc_html(self.store, doc))
        else:
            self._html(404, "<h1>404</h1>")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/validate":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid JSON"})
            return
        doc_id = payload.get("doc_id", "")
        try:
            apply_validation(self.store, doc_id,
                             payload.get("fields", {}) or {},
                             payload.get("confirmed", []) or [])
        except KeyError:
            self._json(404, {"ok": False, "error": f"no such document: {doc_id}"})
            return
        self._json(200, {"ok": True})


def _handler_factory(store: DocumentStore):
    class Handler(_Handler):
        pass
    Handler.store = store
    return Handler


def make_server(store: DocumentStore, port: int = DEFAULT_PORT,
                host: str = BIND_HOST) -> ThreadingHTTPServer:
    """Create (not yet serving) the review server. Binds loopback only."""
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(f"refusing to bind non-loopback host: {host!r}")
    return ThreadingHTTPServer((host, port), _handler_factory(store))


def serve_forever(store: DocumentStore, port: int = DEFAULT_PORT) -> None:
    server = make_server(store, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"taxprep review at {url}  (localhost only — Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
