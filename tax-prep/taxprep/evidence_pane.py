"""R19/R19a evidence pane adapter for the R12 console.

Contract (from the R12 workstream's ``doc/console-contracts.md``):
``taxprep/evidence_pane.py`` defines ``pane_html(store, doc) -> str`` and the
console mounts the result verbatim in
``<section id="evidence-pane" data-doc-id="...">`` on the doc page.

This module is a thin adapter over the W3 evidence layer
(``taxprep/evidence.py``) and the review page's pane renderers
(``taxprep/review.py``): the left page viewer with bbox overlays plus a
field table with per-field evidence cells (snapshot / lineage /
no-evidence), bidirectional selection, zoom, and the fail-closed
"verified against original" escape hatch. All image URLs are relative
(the console and the review server share one loopback origin), and every
endpoint they hit is R10-hardened.
"""

from __future__ import annotations

import html
from urllib.parse import quote

from . import evidence as _evidence
from . import review as _review

_CSS = """
<style>
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
.noev{font-size:12px;color:#666}
.vok{font-size:12px;color:#2e7d32}
.orignote{font-size:12px;color:#666;font-style:italic}
.edithist{font-size:11px;color:#555}
.banner{background:#fdecea;border:2px solid #c62828;padding:12px;margin-bottom:12px;font-size:14px}
.evnote{color:#666;font-size:12px;font-style:italic;margin:0 0 8px}
tr.field-row{cursor:default}
tr.selrow{background:#e3f2fd}
table.evtable{border-collapse:collapse;font-size:13px}
table.evtable td,table.evtable th{border:1px solid #ccc;padding:4px 8px;vertical-align:top}
tr.lotnav td{background:#f4f8ff;font-size:12px;color:#333}
tr.lotnav a{margin:0 6px}
span.lotnavdis{color:#aaa;margin:0 6px}
</style>
"""

_JS = """
<script>
(function(){
const docId = document.querySelector('#evidence-pane').dataset.docId;
function flashRow(row){row.classList.add("selrow");setTimeout(()=>row.classList.remove("selrow"),1200);}
document.querySelectorAll("#evidence-pane .bbox").forEach(bx=>{
  bx.addEventListener("click",()=>{
    document.querySelectorAll("#evidence-pane .bbox.sel").forEach(o=>o.classList.remove("sel"));
    bx.classList.add("sel");
    const row=document.getElementById("row-"+bx.dataset.box);
    if(row){row.scrollIntoView({block:"center"});flashRow(row);}
  });
});
document.querySelectorAll("#evidence-pane tr.field-row td.fcode").forEach(td=>{
  td.addEventListener("click",()=>{
    const box=td.closest("tr").dataset.box;
    const bx=document.querySelector('#evidence-pane .bbox[data-box="'+box+'"]');
    if(bx){document.querySelectorAll("#evidence-pane .bbox.sel").forEach(o=>o.classList.remove("sel"));
      bx.classList.add("sel");bx.scrollIntoView({block:"center"});}
  });
});
let zoomPct=100;
function setZoom(z){zoomPct=Math.min(300,Math.max(50,z));
  document.querySelectorAll("#evidence-pane .pageimg").forEach(im=>{
    const apply=()=>{im.style.width=Math.round(im.naturalWidth*zoomPct/100)+"px";};
    if(im.complete&&im.naturalWidth)apply();else im.addEventListener("load",apply,{once:true});});
  const lbl=document.getElementById("zoomLabel");if(lbl)lbl.textContent=zoomPct+"%";}
const zi=document.getElementById("zoomIn");
if(zi){zi.addEventListener("click",()=>setZoom(zoomPct+25));
  document.getElementById("zoomOut").addEventListener("click",()=>setZoom(zoomPct-25));
  document.getElementById("zoomReset").addEventListener("click",()=>setZoom(100));}
document.querySelectorAll("#evidence-pane button.vorig").forEach(btn=>{
  btn.addEventListener("click",async()=>{
    const box=btn.dataset.box;
    const r=await fetch("/api/evidence/verify-original",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({doc_id:docId,field:box})});
    if(r.ok){const row=document.getElementById("row-"+box);
      const chk=row&&row.querySelector("input.fchk");if(chk)chk.disabled=false;
      btn.outerHTML='<div class="vok">✓ verified against original (logged)</div>';}
  });
});
})();
</script>
"""


# B3: the lot table is paginated -- a 2000-lot document renders a 100-lot
# window, not 2000 sub-rows. Lot numbers stay document-wide (stable
# across windows); the lots FIELD row itself is never paginated.
_LOT_WINDOW = 100


def _lot_gain_loss_rows(store, doc, lots_field: dict,
                        base: str, images_mode: bool, *,
                        lot_page: int = 0) -> list[str]:
    """Per-lot gain_loss sub-rows under the lots field (LINEAGE-1).

    Each lot's tagged gain_loss is a computed field: it renders the
    lineage view (formula + input links), never the "no visual
    evidence" state. The inputs are the lot's own proceeds/basis/wash
    cells, which live in the parent lots row -- so every input link
    anchors there.

    B3: only the ``lot_page`` window (``_LOT_WINDOW`` lots) renders.
    ``lot_page`` is clamped to >= 0; the pane clamps it to the last
    window. Lot numbering (``lots.lot{n}.gain_loss``) is document-wide
    so row ids are stable across windows.
    """
    v = lots_field.get("value") if isinstance(lots_field, dict) else None
    if not isinstance(v, list):
        return []
    start = max(0, lot_page) * _LOT_WINDOW
    end = start + _LOT_WINDOW
    rows = []
    for n, lot in enumerate(v, start=1):
        if n <= start or n > end:
            continue
        if not isinstance(lot, dict):
            continue
        gl = lot.get("gain_loss")
        if not isinstance(gl, dict) or gl.get("computed") is not True:
            continue
        code = f"lots.lot{n}.gain_loss"
        val = gl.get("value")
        vtxt = "" if val is None else str(val)
        cell, ev_disabled = _review._field_evidence_cell(
            store, doc, code, gl, base, images_mode,
            input_anchor=lambda _c: "#row-lots")
        dis = "disabled" if ev_disabled else ""
        rows.append(
            f'<tr class="field-row lot-computed" data-box="{html.escape(code)}" '
            f'id="row-{html.escape(code)}">'
            f'<td class="fcode">{html.escape(code)}</td>'
            f"<td>{html.escape(vtxt)}</td>"
            f"<td>{cell}</td>"
            f'<td><input type="checkbox" class="fchk" {dis}></td>'
            "</tr>"
        )
    return rows


def _lot_nav_row(lot_page: int, n_pages: int, n_lots: int) -> str:
    """Server-rendered lot-table pager (plain links, no JS framework)."""
    lo = lot_page * _LOT_WINDOW + 1
    hi = min(n_lots, (lot_page + 1) * _LOT_WINDOW)
    prev = (f'<a href="?lot_page={lot_page - 1}">&larr; prev {_LOT_WINDOW}</a>'
            if lot_page > 0 else '<span class="lotnavdis">&larr; prev</span>')
    nxt = (f'<a href="?lot_page={lot_page + 1}">next {_LOT_WINDOW} &rarr;</a>'
           if lot_page < n_pages - 1
           else '<span class="lotnavdis">next &rarr;</span>')
    return (f'<tr class="lotnav"><td colspan="4">'
            f"lots {lo}&ndash;{hi} of {n_lots} &nbsp;{prev} &nbsp;{nxt}"
            f"</td></tr>")


def pane_html(store, doc, *, lot_page: int = 0) -> str:
    """Evidence section HTML for one document (console mount point).

    Returns the left page viewer (rendered pages + bbox overlays, or the
    degraded evidence path) plus a field table with per-field evidence
    cells. Never raises for missing geometry -- fields without a
    locatable source render the explicit "no visual evidence" state.

    B3: the per-lot lineage sub-rows render one ``_LOT_WINDOW`` window
    (``lot_page``, 0-based); the pager is plain ``?lot_page=N`` links.
    The lots field row itself always renders in full.
    """
    base = ""  # relative URLs: console and review share one loopback origin
    images_mode = _review.evidence_status(store, doc)["mode"] == "images"
    if images_mode:
        left, blocked = _review._page_viewer_html(store, doc, base)
        if blocked:
            left, _ = _review._source_evidence_html(store, doc)
            images_mode = False
    else:
        left, _ = _review._source_evidence_html(store, doc)

    rows = []
    for code, f in (doc.fields or {}).items():
        if not isinstance(f, dict) or code.startswith("__"):
            continue
        val = f.get("value")
        vtxt = "" if val is None else str(val)
        cell, ev_disabled = _review._field_evidence_cell(
            store, doc, code, f, base, images_mode)
        dis = "disabled" if ev_disabled else ""
        rows.append(
            f'<tr class="field-row" data-box="{html.escape(code)}" '
            f'id="row-{html.escape(code)}">'
            f'<td class="fcode">{html.escape(code)}</td>'
            f"<td>{html.escape(vtxt)}</td>"
            f"<td>{cell}</td>"
            f'<td><input type="checkbox" class="fchk" {dis}></td>'
            "</tr>"
        )
        if code == "lots":
            v = f.get("value") if isinstance(f, dict) else None
            n_lots = len(v) if isinstance(v, list) else 0
            n_pages = max(1, -(-n_lots // _LOT_WINDOW))
            page = min(max(0, lot_page), n_pages - 1)
            rows.extend(_lot_gain_loss_rows(store, doc, f, base,
                                            images_mode, lot_page=page))
            if n_pages > 1:
                rows.append(_lot_nav_row(page, n_pages, n_lots))
    table = (
        '<table class="evtable"><tr><th>field</th><th>value</th>'
        "<th>evidence</th><th>confirm</th></tr>"
        + ("\n".join(rows) if rows else
           '<tr><td colspan="4"><i>No extracted fields.</i></td></tr>')
        + "</table>"
    )
    return _CSS + left + table + _JS
