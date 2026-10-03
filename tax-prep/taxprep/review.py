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


def _pdf_page_images(doc: Document) -> tuple[list[str], str | None]:
    """Render source PDF pages to JPEG data URIs.

    Renders ALL pages, or the split document's page range when
    ``Document.page_range`` is present (a (first, last) 1-based pair).

    Returns ``(images, error)``: ``error`` is None on success, otherwise a
    short reason string. Poppler's ``pdftoppm`` (poppler-utils) is the
    system prerequisite; ``pdf2image`` is a declared project dependency.
    """
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
    if page_range:
        kwargs["first_page"] = int(page_range[0])
        kwargs["last_page"] = int(page_range[1])
    try:
        images = _convert_from_path(str(pdf_path), **kwargs)
    except Exception as exc:
        # Reason only; exception text never surfaces (no PII/paths leak).
        return [], f"page render failed ({type(exc).__name__})"
    out = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
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
        images, error = _pdf_page_images(doc)
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
        images, _ = _pdf_page_images(doc)
        imgs = "".join(
            f'<img src="data:image/jpeg;base64,{p}" alt="source page">' for p in images
        )
        return f'<div class="src">{imgs}</div>', False
    try:
        text = store.load_ocr(doc.doc_id)
    except (FileNotFoundError, OSError):
        text = None
    if ev["mode"] == "text":
        body = highlight_ocr(text or "", doc.fields)
        note = '<p class="evnote">Text evidence: the source is a text file.</p>'
        return f'<div class="src">{note}{body}</div>', False
    # degraded or unavailable: blocking banner, fail closed
    banner = (
        '<div class="banner">⚠ Page images unavailable'
        f' ({html.escape(ev["reason"] or "unknown reason")}). '
        + ("Extracted text is shown ONLY as a degraded fallback — it cannot "
           "verify the extraction. " if text is not None
           else "No source evidence is available. ")
        + "Validation is <b>BLOCKED</b> until page images render.</div>"
    )
    if text is None:
        return banner + '<div class="src"><i>No source evidence available.</i></div>', True
    return banner + f'<div class="src">{highlight_ocr(text, doc.fields)}</div>', True


def queue_html(store: DocumentStore, year: int | None, form: str | None,
               token: str | None = None,
               include_irrelevant: bool = False) -> str:
    docs = [d for d in store.list() if d.status in ("transcribed", "needs_review")]
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
        rows.append(
            "<tr>"
            f'<td><a href="{base}/doc/{quote(d.doc_id)}">{html.escape(d.doc_id)}</a></td>'
            f"<td>{d.tax_year if d.tax_year is not None else '????'}</td>"
            f"<td>{html.escape(d.form_type)}</td>"
            f"<td>{html.escape(d.status)}</td>"
            f"<td>{html.escape(d.relevance)}</td>"
            f"<td>{nfields}</td>"
            f"<td>{low}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else '<tr><td colspan="7"><i>Queue empty — all validated.</i></td></tr>'
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
<th>relevance</th><th>fields</th><th>low-conf</th></tr>{body}</table>
</body></html>"""


def _fmt_value(v) -> str:
    if v is None:
        return ""
    return str(v)


def doc_html(store: DocumentStore, doc: Document,
             token: str | None = None) -> str:
    evidence, evidence_blocked = _source_evidence_html(store, doc)
    base = _token_url_base(token)
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
<table><tr><th>box</th><th>value (editable)</th><th>confidence</th><th>confirm</th></tr>
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
    """Audit a form_type/tax_year correction, retaining the original value."""
    entry = doc.fields.get(key)
    if not isinstance(entry, dict):
        entry = {"value": old, "confidence": "human-corrected",
                 "raw_text": "", "history": []}
        doc.fields[key] = entry
    entry.setdefault("history", []).append({"ts": ts, "old": old, "new": new})
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
    history is never overwritten.
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

    if reasons:
        raise ValidationRefused(doc_id, reasons)

    # --- apply: all gates passed ---
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for box in new_boxes:
        new_val = _coerce(str(fields[box]))
        if box in rows:
            f = rows[box]
            old = f.get("value")
            if old != new_val:
                f.setdefault("history", []).append(
                    {"ts": ts, "old": old, "new": new_val})
                f["value"] = new_val
        else:
            doc.fields[box] = {
                "value": new_val,
                "confidence": "human-corrected",
                "raw_text": "",
                "history": [{"ts": ts, "old": None, "new": new_val}],
            }
    if form_changed:
        _record_identity_edit(doc, _FORM_TYPE_KEY, doc.form_type, new_form, ts)
        doc.form_type = new_form
    if year_changed:
        _record_identity_edit(doc, _TAX_YEAR_KEY, doc.tax_year, new_year, ts)
        doc.tax_year = new_year
    doc.status = "validated"
    doc.validated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.upsert(doc)
    return doc


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
        else:
            self._html(404, "<h1>404</h1>")

    def do_POST(self) -> None:
        if not self._check_host():
            return
        eff = self._effective_path()
        if eff is None or urlparse(eff).path != "/api/validate":
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
