"""R12 -- Operator console (loopback only).

Extends the R10-hardened review server (taxprep/review.py): every route
below is served through that server's handler, so the R10 gates (Host
allowlist, JSON-only POST, same-origin, per-run token) apply to EVERY
new endpoint without exception. This module holds the view rendering
and the POST dispatch; review.py only routes to it.

Views (GET, all under /console):

  /console               hub with per-view counts
  /console/sources       R11 rev2 source discovery: register roots
                         (stored mode 0600), metadata scan, duplicate
                         hints, route prediction, checked-file ingest
  /console/runs          machine runs (gold_run) + decision counts
  /console/queue         review queue (links into /console/doc/<id>)
  /console/doc/<id>      Queue & Review document page -- hosts the
                         evidence pane (sibling workstream, see
                         evidence_pane_html); lifecycle state + event
                         history; links to the legacy /doc/<id>
                         validator for the actual validation POST
  /console/checks        verify_all results
  /console/carryforward  gold carryforward outputs + gate status
  /console/decisions     Arc B dup groups + conflicts with side-by-side
                         evidence; rulings go through rule_on_group /
                         choose_conflict (no other disposal path)
  /console/bus           recent bus messages, METADATA ONLY
  /console/activity      R13 per-document event log (sibling workstream)

POST (JSON, same-origin, under /console/api):

  /console/api/sources/roots/register    {path}
  /console/api/sources/roots/unregister   {root_id}
  /console/api/sources/ingest             {file_ids: [...]}
  /console/api/sources/exclude            {file_ids: [...]}
  /console/api/decisions/rule_group       {group_id, ruling, primary?, reason?}
  /console/api/decisions/choose_conflict  {conflict_id, choice, reason?}

Every POST above is served through the R10-hardened review server
(taxprep/review.py _Handler.do_POST): Host allowlist, JSON-only POST,
same-origin, and the per-run /t/<token> prefix apply to every console
endpoint without exception. The doc page also accepts ?lot_page=N to
page the evidence pane's lot table (B3).

Cross-links (Operator decision, source selection stays a separate
/console/sources endpoint -- never embedded in the queue):

* queue rows carry a source column linking to /console/sources
  (anchored to the doc's source root when the bronze linkage is known);
* source scan rows link to the documents they produced (bronze SHA ->
  docs) with per-doc lifecycle state;
* the hub shows a documents-by-status funnel (indexed aggregate query,
  never list-all);
* the queue's empty state says "No documents — select sources." (never
  "all validated") with a re-scan banner pointing at Sources;
* unchecking an ingested source (the per-row "exclude" control) fires
  the R13 exclude event on its documents with the standing reason
  "operator-excluded" (the decision note's "operator-unselected" is the
  same intent; the codebase taxonomy keeps "operator-excluded");
* every console ingest records a gold_run row (kind=source_ingest).

Values plane: the console is OPERATOR-ONLY (loopback). Agent surfaces
(MCP tools, bus payloads) stay metadata-only; the Bus view renders
message metadata (ids, timestamps, senders, payload KEY names) and
never payload values.

Sibling contracts (see doc/console-contracts.md):

* evidence pane -- taxprep/evidence_pane.py with
  ``pane_html(store, doc) -> str``; mounted inside
  ``<section id="evidence-pane" data-doc-id="...">``. Absent -> the
  console shows a "pane pending" note with a link to the legacy
  /doc/<id> evidence.
* R13 lifecycle -- taxprep/lifecycle.py with ``record_event``,
  ``events_for`` and ``state_of`` (consumed via taxprep/sources.py
  lifecycle_record / lifecycle_events / lifecycle_state). Absent ->
  the console says so instead of inventing events.
"""

from __future__ import annotations

import html
import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import bus as _bus
from . import duplicates as _duplicates
from . import sources as _sources

# NOTE: taxprep.verify is imported lazily inside the view functions that
# need it (checks_html, carryforward_html) rather than at module level:
# the Checks/Carryforward views are the only console consumers, and a
# hard import would couple every console route to the verify module's
# import-time health.

_CSS = """
body{font-family:system-ui,-apple-system,sans-serif;max-width:1400px;margin:0 auto;padding:16px;color:#1a1a1a}
table{border-collapse:collapse;width:100%;margin:8px 0}
th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;font-size:13px}
th{background:#f4f4f4}
nav.cons{margin:12px 0;padding:8px;background:#f7f7f7;border:1px solid #ddd}
nav.cons a{margin-right:14px}
nav.cons a.here{font-weight:bold;color:#000}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;color:#fff}
.b-ok{background:#2e7d32}.b-warn{background:#d9930d}.b-bad{background:#c62828}.b-info{background:#1565c0}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}
.card{border:1px solid #ddd;padding:12px;min-width:180px;background:#fafafa}
.card .n{font-size:24px;font-weight:bold}
.mono{font-family:ui-monospace,monospace;font-size:12px}
.pend{background:#fff8e1;border:1px solid #d9930d;padding:10px;margin:8px 0}
.side{display:flex;gap:12px}.side>div{flex:1;border:1px solid #ddd;padding:8px;min-width:0}
button{font-size:14px;padding:6px 14px;margin:2px}
input[type=text]{font-size:14px;padding:6px;width:420px;max-width:90%}
.banner{background:#fdecea;border:2px solid #c62828;padding:12px;margin-bottom:12px;font-size:14px}
pre{white-space:pre-wrap;background:#fafafa;border:1px solid #ddd;padding:10px;font-size:12px}
h2{margin-top:28px}
"""

_NAV = [
    ("sources", "Sources"),
    ("runs", "Runs"),
    ("queue", "Queue & Review"),
    ("checks", "Checks"),
    ("carryforward", "Carryforward"),
    ("decisions", "Decisions"),
    ("bus", "Bus"),
    ("activity", "Activity Log"),
]


def _token_url_base(token: str | None) -> str:
    return "/t/" + quote(token, safe="") if token else ""


def _nav_html(base: str, active: str) -> str:
    links = [f'<a href="{base}/console">⌂ console</a>']
    for slug, label in _NAV:
        cls = ' class="here"' if slug == active else ""
        links.append(f'<a href="{base}/console/{slug}"{cls}>{label}</a>')
    return f'<nav class="cons">{" ".join(links)}</nav>'


def _page(title: str, token: str | None, active: str, body: str) -> str:
    base = _token_url_base(token)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(title)} — taxprep console</title><style>{_CSS}</style></head><body>
<h1>{html.escape(title)}</h1>
{_nav_html(base, active)}
{body}
</body></html>"""


def _ok_badge(ok: bool, true_label: str = "ok", false_label: str = "fail") -> str:
    cls = "b-ok" if ok else "b-bad"
    return f'<span class="badge {cls}">{true_label if ok else false_label}</span>'


# -- evidence pane adapter (sibling: R19/R19a) ------------------------------

def evidence_pane_html(store, doc, lot_page: int = 0) -> str | None:
    """Sibling evidence pane HTML, or None when not installed.

    Contract: taxprep/evidence_pane.py defines
    ``pane_html(store, doc) -> str`` -- self-contained HTML for the
    source-evidence pane (rendered pages + bbox overlays + per-field-set
    snapshots). The console mounts it verbatim inside
    ``<section id="evidence-pane" data-doc-id="...">``.

    B3: ``lot_page`` pages the pane's lot table. It is an OPTIONAL
    extension of the sibling contract -- siblings that still declare
    ``pane_html(store, doc)`` get the unpaged call, so older panes keep
    working (and the pane-stub contract test keeps its meaning).
    """
    try:
        from . import evidence_pane as _ep
    except ImportError:
        return None
    render = getattr(_ep, "pane_html", None)
    if not callable(render):
        return None
    try:
        params = inspect.signature(render).parameters
    except (TypeError, ValueError):
        params = {}
    if "lot_page" in params:
        return render(store, doc, lot_page=lot_page)
    return render(store, doc)


# -- data helpers ------------------------------------------------------------

def _open_groups(store) -> list[dict]:
    with store.txn() as conn:
        rows = conn.execute(
            "SELECT group_id, class, created_at FROM dup_group "
            "WHERE status = 'open' ORDER BY created_at, group_id").fetchall()
        out = []
        for gid, cls, created in rows:
            members = conn.execute(
                "SELECT member_key, role FROM dup_member WHERE group_id = ? "
                "ORDER BY role, member_key", (gid,)).fetchall()
            out.append({"group_id": gid, "class": cls, "created_at": created,
                        "members": [{"key": k, "role": r} for k, r in members]})
    return out


def _open_conflicts(store) -> list[dict]:
    with store.txn() as conn:
        rows = conn.execute(
            "SELECT conflict_id, class, field, created_at FROM conflict "
            "WHERE status = 'open' ORDER BY created_at, conflict_id").fetchall()
        out = []
        for cid, cls, field, created in rows:
            opts = conn.execute(
                "SELECT option_key, value_json, evidence_ref FROM conflict_option "
                "WHERE conflict_id = ? ORDER BY option_key", (cid,)).fetchall()
            out.append({"conflict_id": cid, "class": cls, "field": field,
                        "created_at": created,
                        "options": [{"option_key": k, "value_json": v,
                                     "evidence_ref": e} for k, v, e in opts]})
    return out


def _resolve_member(store, member_key: str) -> dict:
    """Side-by-side evidence for one dup-group member.

    A member_key is a bronze hash, a doc id, or (L3) an artifact id.
    Returns a small evidence dict -- values are OPERATOR-visible here.
    """
    with store.txn() as conn:
        brow = conn.execute(
            "SELECT hash, size, first_seen, last_seen, source_root, encryption, "
            "blocked_reason FROM bronze WHERE hash = ?", (member_key,)).fetchone()
        if brow is not None:
            return {"kind": "bronze",
                    "hash": brow[0], "size": brow[1],
                    "first_seen": brow[2], "last_seen": brow[3],
                    "source_root": brow[4], "encryption": brow[5],
                    "blocked_reason": brow[6]}
        srow = conn.execute(
            "SELECT doc_id, form_type, tax_year, status, relevance "
            "FROM silver_doc WHERE doc_id = ?", (member_key,)).fetchone()
        if srow is not None:
            nfields = conn.execute(
                "SELECT COUNT(*) FROM silver_artifact WHERE doc_id = ? "
                "AND artifact_type = 'field'", (member_key,)).fetchone()[0]
            return {"kind": "document", "doc_id": srow[0],
                    "form_type": srow[1], "tax_year": srow[2],
                    "status": srow[3], "relevance": srow[4],
                    "n_fields": nfields}
        arow = conn.execute(
            "SELECT artifact_id, doc_id, artifact_type, anchor "
            "FROM silver_artifact WHERE artifact_id = ?",
            (member_key,)).fetchone()
        if arow is not None:
            return {"kind": "artifact", "artifact_id": arow[0],
                    "doc_id": arow[1], "artifact_type": arow[2],
                    "anchor": arow[3]}
    return {"kind": "unknown", "key": member_key}


def _gold_runs(store, kind: str | None = None, limit: int = 20) -> list[dict]:
    with store.txn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT run_id, ts, kind, params_json, input_digest, "
                "output_digest, output_json FROM gold_run WHERE kind = ? "
                "ORDER BY ts DESC LIMIT ?", (kind, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT run_id, ts, kind, params_json, input_digest, "
                "output_digest, output_json FROM gold_run "
                "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [{"run_id": r[0], "ts": r[1], "kind": r[2], "params_json": r[3],
             "input_digest": r[4], "output_digest": r[5],
             "output_json": r[6]} for r in rows]


def _decision_counts(store) -> list[tuple[str, int]]:
    with store.txn() as conn:
        rows = conn.execute(
            "SELECT kind, COUNT(*) FROM decision_log GROUP BY kind "
            "ORDER BY kind").fetchall()
    return [(str(k), int(n)) for k, n in rows]


# -- cross-link helpers (Operator decision) -------------------------------

def _docs_for_bronze(store, sha: str) -> list[str]:
    """Doc ids produced from one bronze SHA (indexed, never list-all).

    [] when the store has no silver_doc table (non-medallion).
    """
    try:
        with store.txn() as conn:
            rows = conn.execute(
                "SELECT doc_id FROM silver_doc WHERE bronze_hash = ? "
                "ORDER BY doc_id", (sha,)).fetchall()
    except Exception:
        return []
    return [str(r[0]) for r in rows]


def _bronze_source_root(store, doc) -> str | None:
    """The source-root registry id for a doc, or None.

    Primary: ``bronze.source_root`` for the doc's bronze. Fallback: the
    registered root whose path is the longest prefix of the doc's
    source path. The fallback exists because ``register_bronze`` is
    INSERT OR IGNORE -- a bronze row first created by ``ingest_file``
    keeps ``source_root`` NULL when the console's later
    ``ingest_checked`` re-registers it (pre-existing ingest behavior,
    not something the console changes).

    Metadata only (root id + path basename) -- never values.
    """
    sha = getattr(doc, "source_sha256", None)
    if sha:
        try:
            with store.txn() as conn:
                row = conn.execute(
                    "SELECT source_root FROM bronze WHERE hash = ?",
                    (sha,)).fetchone()
        except Exception:
            row = None
        if row and row[0]:
            return row[0]
    src = getattr(doc, "source_path", "") or ""
    if not src:
        return None
    try:
        roots = _sources.load_roots()
    except Exception:
        return None
    best: tuple[str, str | None] | None = None
    for r in roots:
        rp = r.get("path", "")
        if rp and (src == rp or src.startswith(rp.rstrip("/") + "/")):
            if best is None or len(rp) > len(best[0]):
                best = (rp, r.get("root_id"))
    return best[1] if best else None


def _status_counts(store) -> list[tuple[str, int]]:
    """Documents per status via one indexed aggregate -- never list-all.

    [] when the store has no silver_doc table (non-medallion).
    """
    try:
        with store.txn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM silver_doc "
                "GROUP BY status ORDER BY status").fetchall()
    except Exception:
        return []
    return [(str(s), int(n)) for s, n in rows]


def _record_gold_run(store, kind: str, params: dict,
                     output: dict) -> str | None:
    """Persist one gold_run row (best-effort, metadata only).

    Same row shape as gold.gated_carryforward: canonical-JSON params
    and output with sha256 digests. Returns the run_id, or None when
    the store has no gold_run table -- the caller's operation still
    succeeds; the run simply is not recorded.
    """
    import hashlib
    from datetime import datetime, timezone

    params_c = json.dumps(params, sort_keys=True)
    output_c = json.dumps(output, sort_keys=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = hashlib.sha256(
        f"{kind}:{ts}:{params_c}".encode()).hexdigest()[:32]
    try:
        with store.txn() as conn:
            conn.execute(
                "INSERT INTO gold_run (run_id, ts, kind, params_json, "
                "input_digest, output_json, output_digest) VALUES "
                "(?, ?, ?, ?, ?, ?, ?)",
                (run_id, ts, kind, params_c,
                 hashlib.sha256(params_c.encode()).hexdigest(),
                 output_c,
                 hashlib.sha256(output_c.encode()).hexdigest()))
    except Exception:
        return None
    return run_id


def _queue_source_cell(store, doc, base: str) -> str:
    """Source cell for a queue row.

    The source file's basename links to /console/sources, anchored to
    the doc's source root when the bronze linkage is known. Ids/paths
    only -- never values (blind-orchestrator contract).
    """
    label = (Path(doc.source_path).name if getattr(doc, "source_path", "")
             else "—")
    root_id = _bronze_source_root(store, doc)
    anchor = f"#root-{root_id}" if root_id else ""
    title = html.escape(getattr(doc, "source_path", "") or "", quote=True)
    return (f'<td><a href="{base}/console/sources{anchor}" '
            f'title="{title}">{html.escape(label)}</a></td>')


def _file_sha_map(store) -> dict[str, str]:
    """file_id -> sha256 for the current scan (public scan_roots only)."""
    mapping: dict[str, str] = {}
    for root in _sources.scan_roots(store):
        for f in root["files"]:
            mapping[f["file_id"]] = f["sha256"]
    return mapping


def _exclude_checked(store, file_ids: list[str]) -> list[dict]:
    """Exclude every document produced from the given scan file_ids.

    The Operator's "uncheck": each produced doc goes through the R13
    ``exclude`` event (actor=operator) with the STANDING reason
    ``operator-excluded`` -- the decision note's "operator-unselected"
    is the same intent, but the codebase taxonomy keeps the existing
    "operator-excluded" code rather than minting a duplicate reason.
    Mirrors cmd_exclude: exclusion sidecar + lifecycle transition +
    silver persist + decision-log entry, per doc.
    """
    from . import exclusions as _excl
    from . import lifecycle as _lc
    from . import silver as _silver

    sha_map = _file_sha_map(store)
    out: list[dict] = []
    for fid in file_ids:
        sha = sha_map.get(fid)
        if sha is None:
            out.append({"file_id": fid, "ok": False, "docs": [],
                        "excluded": [],
                        "errors": ["unknown file_id (re-scan and retry)"]})
            continue
        doc_ids = _docs_for_bronze(store, sha)
        excluded: list[str] = []
        errors: list[dict] = []
        for doc_id in doc_ids:
            doc = store.get(doc_id)
            if doc is None:
                errors.append({"doc_id": doc_id, "error": "not found"})
                continue
            try:
                _excl.record_exclusion(store.data_dir, doc_id,
                                       "operator-excluded")
            except ValueError as exc:
                errors.append({"doc_id": doc_id, "error": str(exc)})
                continue
            with store.txn():
                res = _lc.transition(
                    doc, _lc.EXCLUDE, actor=_lc.OPERATOR,
                    event_input=_lc.ExcludeInput(reason="operator-excluded"),
                    store=store)
                if not res.ok:
                    errors.append({"doc_id": doc_id,
                                   "error": res.reason_code
                                   or "exclude_refused"})
                    continue
                bronze_hash = _silver.bronze_hash_for_doc(store, doc)
                if bronze_hash is None:
                    store.upsert(doc)
                else:
                    _silver.persist_silver_doc(
                        store, doc,
                        _silver.derivation_for_doc(store, doc.doc_id),
                        bronze_hash)
                logd = getattr(store, "log_decision", None)
                if callable(logd):
                    logd(actor="operator", kind="exclude", doc_id=doc_id,
                         payload={"doc_id": doc_id,
                                  "reason": "operator-excluded",
                                  "via": "console-uncheck"})
            excluded.append(doc_id)
        out.append({"file_id": fid, "ok": not errors, "docs": doc_ids,
                    "excluded": excluded, "errors": errors})
    return out


# -- hub ---------------------------------------------------------------------

def hub_html(store, token: str | None = None) -> str:
    base = _token_url_base(token)
    docs = store.list()
    need_review = sum(1 for d in docs if d.status in ("transcribed", "needs_review"))
    groups = _open_groups(store)
    conflicts = _open_conflicts(store)
    roots = _sources.load_roots()
    gold = _gold_runs(store, limit=1)
    cards = [
        ("Sources", str(len(roots)), "registered roots", "sources"),
        ("Queue", str(need_review), "documents awaiting review", "queue"),
        ("Decisions", str(len(groups)), "open duplicate groups", "decisions"),
        ("Decisions", str(len(conflicts)), "open conflicts", "decisions"),
        ("Runs", gold[0]["kind"] if gold else "—",
         f"latest run {gold[0]['ts']}" if gold else "no runs recorded", "runs"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="n">{html.escape(n)}</div>'
        f'<div>{html.escape(label)}</div>'
        f'<div><a href="{base}/console/{slug}">{html.escape(title)}</a></div></div>'
        for title, n, label, slug in cards)
    funnel_rows = "".join(
        f"<tr><td class=\"mono\">{html.escape(status)}</td><td>{n}</td></tr>"
        for status, n in _status_counts(store)
    ) or '<tr><td colspan="2"><i>no documents</i></td></tr>'
    return _page("Operator console", token, "",
                 f'<p>Loopback Operator console. Every view below is served '
                 f'by the R10-hardened review server (Host allowlist, '
                 f'JSON-only POST, same-origin, per-run token).</p>'
                 f'<div class="cards">{cards_html}</div>'
                 f'<h2>Documents by status</h2>'
                 f'<table><tr><th>status</th><th>count</th></tr>'
                 f'{funnel_rows}</table>')


# -- Sources (R11 rev2) --------------------------------------------------------

def sources_html(store, token: str | None = None) -> str:
    base = _token_url_base(token)
    roots = _sources.load_roots()
    scans = _sources.scan_roots(store, roots)

    root_rows = "".join(
        f"<tr><td class=\"mono\">{html.escape(r['root_id'])}</td>"
        f"<td class=\"mono\">{html.escape(r['path'])}</td>"
        f"<td>{html.escape(r['added_ts'])}</td>"
        f"<td><button data-unreg=\"{html.escape(r['root_id'])}\">remove</button></td></tr>"
        for r in roots) or '<tr><td colspan="4"><i>No source roots registered.</i></td></tr>'

    scan_sections = []
    for scan in scans:
        if not scan["ok"]:
            scan_sections.append(
                f"<h3 class=\"mono\">{html.escape(scan['path'])}</h3>"
                f"<p class=\"pend\">scan failed: {html.escape(scan['error'] or '?')}</p>")
            continue
        files = scan["files"]
        n_ing = sum(1 for f in files if f["ingested"])
        total = sum(f["size_bytes"] for f in files)
        frows = []
        for f in files:
            hint = f["dup_hint"]
            if hint is None:
                hint_html = "—"
            elif hint["level"] == "L1":
                hint_html = '<span class="badge b-info">L1 exact bytes ingested</span>'
            else:
                hint_html = (f'<span class="badge b-warn">L2 same text as '
                             f'{html.escape(hint["bronze_hash"][:8])}…</span>')
            ing = ('<span class="badge b-ok">ingested</span>' if f["ingested"]
                   else '<span class="badge b-warn">new</span>')
            if f["ingested"]:
                # The Operator's "uncheck": excluding an ingested source
                # fires the R13 exclude event on its documents (standing
                # reason "operator-excluded").
                ing += (f' <button data-exclude-file="'
                        f'{html.escape(f["file_id"])}">exclude</button>')
            # Cross-link: the documents this file produced (bronze SHA ->
            # docs) plus each doc's pipeline state. Ids/statuses only.
            doc_ids = _docs_for_bronze(store, f["sha256"])
            if doc_ids:
                docs_html = "<br>".join(
                    f'<a href="{base}/console/doc/{quote(did)}">'
                    f'{html.escape(did)}</a>' for did in doc_ids)
                lc_html = "<br>".join(
                    html.escape(_sources.lifecycle_state(store, did) or "—")
                    for did in doc_ids)
            else:
                docs_html = "—"
                lc_html = "—"
            frows.append(
                f"<tr>"
                f'<td><input type="checkbox" class="fchk" value="{html.escape(f["file_id"])}"'
                f'{" disabled" if f["ingested"] else ""}></td>'
                f"<td class=\"mono\">{html.escape(f['rel'])}</td>"
                f"<td>{html.escape(f['ext'] or '—')}</td>"
                f"<td>{f['size_bytes']:,}</td>"
                f"<td class=\"mono\">{html.escape(f['route'])}</td>"
                f"<td>{hint_html}</td>"
                f"<td>{ing}</td>"
                f"<td>{docs_html}</td>"
                f"<td>{lc_html}</td></tr>")
        scan_sections.append(
            f"<h3 class=\"mono\" id=\"root-{html.escape(scan['root_id'])}\">"
            f"{html.escape(scan['path'])}</h3>"
            f"<p>{len(files)} files, {total:,} bytes, {n_ing} already ingested</p>"
            f"<table><tr><th></th><th>file</th><th>type</th><th>size</th>"
            f"<th>predicted route</th><th>duplicate hint</th><th>status</th>"
            f"<th>documents</th><th>lifecycle</th></tr>"
            + "\n".join(frows) + "</table>")
    scans_html = "\n".join(scan_sections) or "<p><i>No roots to scan.</i></p>"

    return _page("Sources — R11 rev2 discovery", token, "sources", f"""
<p>Register filesystem roots (stored mode 0600 in the machine-local
config). The scan reports <b>metadata only</b> — file count, types,
sizes — plus the predicted text route and L1/L2 duplicate hints from
Arc B. Check files and ingest them: ingest runs the R13
select&nbsp;→&nbsp;ingest lifecycle transitions.</p>
<h2>Registered roots</h2>
<table><tr><th>root_id</th><th>path</th><th>added</th><th></th></tr>{root_rows}</table>
<p><input type="text" id="newRoot" placeholder="/absolute/path/to/source/dir">
<button id="regBtn">Register root</button> <span id="rootMsg"></span></p>
<h2>Scan</h2>
{scans_html}
<p><button id="ingestBtn">Ingest checked files</button> <span id="ingMsg"></span></p>
<script>
const base = {json.dumps(base)};
async function post(path, payload) {{
  const r = await fetch(base + path, {{method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload)}});
  const j = await r.json().catch(() => ({{}}));
  if (!r.ok) throw new Error("HTTP " + r.status + ": " + (j.error || JSON.stringify(j)));
  return j;
}}
document.getElementById("regBtn").addEventListener("click", async () => {{
  const msg = document.getElementById("rootMsg");
  try {{
    const j = await post("/console/api/sources/roots/register",
      {{path: document.getElementById("newRoot").value}});
    msg.textContent = "registered " + j.root.root_id + " — reloading";
    setTimeout(() => location.reload(), 600);
  }} catch (e) {{ msg.textContent = "refused: " + e.message; }}
}});
document.querySelectorAll("[data-unreg]").forEach(b =>
  b.addEventListener("click", async () => {{
    if (!confirm("Remove this source root from the registry?")) return;
    try {{
      await post("/console/api/sources/roots/unregister",
        {{root_id: b.dataset.unreg}});
      location.reload();
    }} catch (e) {{ alert("refused: " + e.message); }}
  }}));
document.getElementById("ingestBtn").addEventListener("click", async () => {{
  const msg = document.getElementById("ingMsg");
  const ids = [...document.querySelectorAll("input.fchk:checked")].map(c => c.value);
  if (!ids.length) {{ msg.textContent = "check at least one file"; return; }}
  msg.textContent = "ingesting " + ids.length + " file(s)…";
  try {{
    const j = await post("/console/api/sources/ingest", {{file_ids: ids}});
    const s = j.summary;
    msg.textContent = `done: ${{s.ingested}}/${{s.requested}} ingested`;
    setTimeout(() => location.reload(), 800);
  }} catch (e) {{ msg.textContent = "refused: " + e.message; }}
}});
document.querySelectorAll("[data-exclude-file]").forEach(b =>
  b.addEventListener("click", async () => {{
    if (!confirm("Exclude every document produced from this file? "
      + "They leave the review queue with reason operator-excluded.")) return;
    try {{
      const j = await post("/console/api/sources/exclude",
        {{file_ids: [b.dataset.excludeFile]}});
      const f = j.files[0] || {{excluded: [], errors: []}};
      alert("excluded " + f.excluded.length + " document(s)"
        + (f.errors.length ? "; " + f.errors.length + " refused" : ""));
      location.reload();
    }} catch (e) {{ alert("refused: " + e.message); }}
  }}));
</script>""")


# -- Runs ----------------------------------------------------------------------

def runs_html(store, token: str | None = None) -> str:
    runs = _gold_runs(store, limit=50)
    rows = "".join(
        f"<tr><td class=\"mono\">{html.escape(r['run_id'][:16])}…</td>"
        f"<td>{html.escape(r['ts'])}</td>"
        f"<td>{html.escape(r['kind'])}</td>"
        f"<td class=\"mono\">{html.escape((r['input_digest'] or '')[:12])}…</td>"
        f"<td class=\"mono\">{html.escape((r['output_digest'] or '')[:12])}…</td></tr>"
        for r in runs) or '<tr><td colspan="5"><i>No machine runs recorded.</i></td></tr>'
    drows = "".join(
        f"<tr><td class=\"mono\">{html.escape(k)}</td><td>{n}</td></tr>"
        for k, n in _decision_counts(store))
    return _page("Runs", token, "runs", f"""
<h2>Machine runs (gold_run)</h2>
<table><tr><th>run_id</th><th>ts</th><th>kind</th><th>input digest</th>
<th>output digest</th></tr>{rows}</table>
<h2>Decision log counts</h2>
<table><tr><th>kind</th><th>count</th></tr>{drows or '<tr><td colspan="2"><i>empty</i></td></tr>'}</table>""")


# -- Queue & Review --------------------------------------------------------------

def queue_html(store, token: str | None = None) -> str:
    base = _token_url_base(token)
    from . import lifecycle as _lc
    _unval = getattr(_lc, "UNVALIDATED_EXTRACTED", ("transcribed", "needs_review"))
    docs = [d for d in store.list() if d.status in _unval]
    rows = []
    for d in docs:
        state = _sources.lifecycle_state(store, d.doc_id)
        rows.append(
            "<tr>"
            f'<td><a href="{base}/console/doc/{quote(d.doc_id)}">{html.escape(d.doc_id)}</a></td>'
            f"<td>{d.tax_year if d.tax_year is not None else '????'}</td>"
            f"<td>{html.escape(d.form_type)}</td>"
            f"<td>{html.escape(d.status)}</td>"
            f"<td>{html.escape(state or '—')}</td>"
            f"<td>{html.escape(d.relevance)}</td>"
            f"{_queue_source_cell(store, d, base)}"
            "</tr>")
    if rows:
        banner = ""
        body = "\n".join(rows)
    else:
        # F5 empty-queue wording: the queue never claims "all validated" --
        # a non-closed run may still be holding the (principal, scope)
        # slot unseen. The re-scan banner points at Sources.
        banner = (f'<div class="banner">No documents in the review queue. '
                  f'<a href="{base}/console/sources">Re-scan sources →</a>'
                  f'</div>')
        body = ('<tr><td colspan="7"><i>No documents — select sources.</i>'
                '</td></tr>')
    return _page("Queue & Review", token, "queue", f"""
<p>Per-document pages host the evidence pane (sibling workstream) and the
R13 lifecycle state with its event history. Validation itself still goes
through the <span class="mono">/doc/&lt;id&gt;</span> flow
(<span class="mono">POST /api/validate</span>).</p>
{banner}
<table><tr><th>doc_id</th><th>year</th><th>form</th><th>status</th>
<th>lifecycle</th><th>relevance</th><th>source</th></tr>{body}</table>""")


def doc_review_html(store, doc, token: str | None = None,
                    lot_page: int = 0) -> str | None:
    """Queue & Review document page. None when the doc does not exist.

    ``lot_page`` pages the evidence pane's lot table (B3); it travels
    as ``?lot_page=N`` on the page URL.
    """
    if doc is None:
        return None
    base = _token_url_base(token)
    pane = evidence_pane_html(store, doc, lot_page=lot_page)
    if pane is None:
        pane_html = (
            '<div class="pend">Evidence pane pending — the R19/R19a sibling '
            'workstream has not installed <span class="mono">taxprep/evidence_pane.py</span> '
            'yet. The current evidence rendering remains available at '
            f'<a href="{base}/doc/{quote(doc.doc_id)}">/doc/{html.escape(doc.doc_id)}</a>.</div>')
    else:
        pane_html = pane
    events = _sources.lifecycle_events(store, doc_id=doc.doc_id, limit=100)
    if events is None:
        ev_html = ('<div class="pend">Lifecycle event log pending — the R13 '
                   'sibling workstream has not installed '
                   '<span class="mono">taxprep/lifecycle.py</span> yet.</div>')
    else:
        erows = "".join(
            f"<tr><td>{html.escape(str(e['ts']))}</td>"
            f"<td class=\"mono\">{html.escape(str(e['event']))}</td>"
            f"<td>{html.escape(str(e['actor']))}</td>"
            f"<td class=\"mono\">{html.escape(str(e['from']))} → {html.escape(str(e['to']))}</td>"
            f"<td class=\"mono\">{html.escape(str(e['reason_code']))}</td></tr>"
            for e in events) or '<tr><td colspan="5"><i>No lifecycle events recorded.</i></td></tr>'
        ev_html = (f"<table><tr><th>ts</th><th>event</th><th>actor</th>"
                   f"<th>transition</th><th>reason</th></tr>{erows}</table>")
    state = _sources.lifecycle_state(store, doc.doc_id)
    nfields = sum(1 for c, f in doc.fields.items()
                  if isinstance(f, dict) and not c.startswith("__"))
    return _page(f"Review {doc.doc_id}", token, "queue", f"""
<p><a href="{base}/console/queue">&larr; queue</a> &nbsp;
status: <b>{html.escape(doc.status)}</b> &nbsp;
lifecycle: <b>{html.escape(state or '—')}</b> &nbsp;
form: <b>{html.escape(doc.form_type)}</b> &nbsp;
year: <b>{doc.tax_year if doc.tax_year is not None else '????'}</b> &nbsp;
fields: <b>{nfields}</b> &nbsp;
<a href="{base}/doc/{quote(doc.doc_id)}">validate &rarr;</a></p>
<h2>Evidence</h2>
<section id="evidence-pane" data-doc-id="{html.escape(doc.doc_id, quote=True)}">
{pane_html}
</section>
<h2>Lifecycle events</h2>
{ev_html}""")


# -- Checks ----------------------------------------------------------------------

def checks_html(store, token: str | None = None, year: int | None = None) -> str:
    from . import verify as _verify
    result = _verify.verify_all(store, year)
    passed = result.get("passed", False)
    rows = []
    for name in sorted(result.get("checks", {})):
        c = result["checks"][name] or {}
        detail = {k: v for k, v in c.items() if k != "passed"}
        detail_str = html.escape(json.dumps(detail, sort_keys=True)[:300])
        rows.append(
            f"<tr><td class=\"mono\">{html.escape(name)}</td>"
            f"<td>{_ok_badge(bool(c.get('passed')))}</td>"
            f"<td class=\"mono\">{detail_str}</td></tr>")
    scope = f" for {year}" if year is not None else " (all years)"
    return _page("Checks", token, "checks", f"""
<p>Mechanical verification{html.escape(scope)}: {_ok_badge(passed, 'ALL PASSED', 'FAILURES PRESENT')}</p>
<table><tr><th>check</th><th>passed</th><th>detail (counts and doc_ids only — never values)</th></tr>
{"".join(rows)}</table>""")


# -- Carryforward ------------------------------------------------------------------

def carryforward_html(store, token: str | None = None) -> str:
    from . import verify as _verify
    runs = _gold_runs(store, kind="carryforward", limit=5)
    if runs:
        latest = runs[0]
        try:
            pretty = json.dumps(json.loads(latest["output_json"] or "{}"),
                                indent=2, sort_keys=True)
        except (ValueError, TypeError):
            pretty = latest["output_json"] or ""
        gold_html = (
            f"<p>Latest carryforward run <span class=\"mono\">{html.escape(latest['run_id'][:16])}…</span> "
            f"at {html.escape(latest['ts'])} "
            f"(input <span class=\"mono\">{html.escape((latest['input_digest'] or '')[:12])}…</span>, "
            f"output <span class=\"mono\">{html.escape((latest['output_digest'] or '')[:12])}…</span>)</p>"
            f"<pre>{html.escape(pretty)}</pre>")
    else:
        gold_html = "<p><i>No carryforward gold run recorded.</i></p>"
    years = sorted({d.tax_year for d in store.list() if d.tax_year is not None})
    grows = []
    for y in years:
        ready = _verify.verify_carryforward_ready(store, y)
        gate = _verify.verify_validation_gate(store, y)
        grows.append(
            f"<tr><td>{y}</td>"
            f"<td>{_ok_badge(bool(ready.get('passed')))}</td>"
            f"<td>{_ok_badge(bool(gate.get('passed')))}</td></tr>")
    gate_html = ("<table><tr><th>year</th><th>carryforward_ready</th>"
                 "<th>validation_gate</th></tr>" + "".join(grows) + "</table>"
                 if grows else "<p><i>No years in store.</i></p>")
    return _page("Carryforward", token, "carryforward", f"""
<h2>Gold outputs</h2>{gold_html}
<h2>Gate status</h2>{gate_html}""")


# -- Decisions ---------------------------------------------------------------------

def _member_evidence_html(store, member: dict) -> str:
    ev = _resolve_member(store, member["key"])
    kind = ev.get("kind")
    head = (f"<b>{html.escape(member['role'] or '?')}</b> "
            f"<span class=\"mono\">{html.escape(member['key'][:24])}…</span>")
    if kind == "bronze":
        rows = (f"size {ev['size']:,} · first seen {html.escape(str(ev['first_seen']))} · "
                f"source_root <span class=\"mono\">{html.escape(str(ev['source_root'])[:24])}…</span>"
                + (f" · <b>blocked: {html.escape(str(ev['blocked_reason']))}</b>"
                   if ev.get("blocked_reason") else ""))
    elif kind == "document":
        rows = (f"{html.escape(str(ev['form_type']))} {html.escape(str(ev['tax_year']))} · "
                f"status {html.escape(str(ev['status']))} · "
                f"{ev['n_fields']} fields")
    elif kind == "artifact":
        rows = (f"artifact {html.escape(str(ev['artifact_type']))}:"
                f"{html.escape(str(ev['anchor']))} of "
                f"<span class=\"mono\">{html.escape(str(ev['doc_id']))}</span>")
    else:
        rows = "unresolvable member key"
    return f"<div>{head}<br>{rows}</div>"


def decisions_html(store, token: str | None = None) -> str:
    base = _token_url_base(token)
    groups = _open_groups(store)
    conflicts = _open_conflicts(store)

    gsections = []
    for g in groups:
        allowed = _duplicates._RULINGS.get(g["class"], ())  # noqa: SLF001 -- UI mirrors rule_on_group
        opts = "".join(
            f'<option value="{r}">{r}</option>' for r in allowed)
        need_primary = any(r in ("keep_one", "merge", "authoritative")
                           for r in allowed)
        members_html = "".join(
            f"<div>{_member_evidence_html(store, m)}</div>" for m in g["members"])
        gsections.append(f"""
<h3><span class="mono">{html.escape(g['group_id'][:16])}…</span>
class <b>{html.escape(g['class'])}</b> · created {html.escape(g['created_at'])}</h3>
<div class="side">{members_html}</div>
<p><label>ruling <select id="ruling-{html.escape(g['group_id'])}">{opts}</select></label>
{"<label>primary <input type=\"text\" id=\"primary-" + html.escape(g['group_id']) + "\" placeholder=\"member key\" size=\"30\"></label>" if need_primary else ""}
<label>reason <input type="text" id="reason-{html.escape(g['group_id'])}" size="40"></label>
<button data-rule-group="{html.escape(g['group_id'])}" data-need-primary="{1 if need_primary else 0}">Apply ruling</button>
<span id="msg-{html.escape(g['group_id'])}"></span></p>""")
    groups_html = "\n".join(gsections) or "<p><i>No open duplicate groups.</i></p>"

    csections = []
    for c in conflicts:
        opts = c["options"]
        opt_html = "".join(
            f"<div><b class=\"mono\">{html.escape(o['option_key'])}</b>: "
            f"<span class=\"mono\">{html.escape(str(o['value_json'])[:200])}</span>"
            + (f" <i>(evidence: <span class=\"mono\">{html.escape(str(o['evidence_ref']))}</span>)</i>"
               if o.get("evidence_ref") else "") + "</div>"
            for o in opts)
        sel = "".join(
            f'<option value="{html.escape(o["option_key"])}">{html.escape(o["option_key"])}</option>'
            for o in opts)
        csections.append(f"""
<h3><span class="mono">{html.escape(c['conflict_id'][:16])}…</span>
class <b>{html.escape(c['class'])}</b>
{f"field <b class=\"mono\">{html.escape(c['field'])}</b>" if c.get("field") else ""}</h3>
<div class="side">{opt_html}</div>
<p><label>choice <select id="choice-{html.escape(c['conflict_id'])}">{sel}</select></label>
<label>reason <input type="text" id="creason-{html.escape(c['conflict_id'])}" size="40"></label>
<button data-choose-conflict="{html.escape(c['conflict_id'])}">Apply choice</button>
<span id="cmsg-{html.escape(c['conflict_id'])}"></span></p>""")
    conflicts_html = "\n".join(csections) or "<p><i>No open conflicts.</i></p>"

    return _page("Decisions", token, "decisions", f"""
<p>Arc B duplicates and conflicts. Disposal is ONLY through the explicit
APIs — there is no default ruling and no auto-disposition anywhere.</p>
<h2>Duplicate groups ({len(groups)} open)</h2>
{groups_html}
<h2>Conflicts ({len(conflicts)} open)</h2>
{conflicts_html}
<script>
const base = {json.dumps(base)};
async function post(path, payload) {{
  const r = await fetch(base + path, {{method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload)}});
  const j = await r.json().catch(() => ({{}}));
  if (!r.ok) throw new Error("HTTP " + r.status + ": " + (j.error || JSON.stringify(j)));
  return j;
}}
document.querySelectorAll("[data-rule-group]").forEach(b =>
  b.addEventListener("click", async () => {{
    const gid = b.dataset.ruleGroup, msg = document.getElementById("msg-" + gid);
    const payload = {{group_id: gid,
      ruling: document.getElementById("ruling-" + gid).value,
      reason: document.getElementById("reason-" + gid).value || null}};
    if (b.dataset.needPrimary === "1")
      payload.primary = document.getElementById("primary-" + gid).value;
    try {{
      const j = await post("/console/api/decisions/rule_group", payload);
      msg.textContent = "disposed (decision seq " + j.seq + ") — reloading";
      setTimeout(() => location.reload(), 700);
    }} catch (e) {{ msg.textContent = "refused: " + e.message; }}
  }}));
document.querySelectorAll("[data-choose-conflict]").forEach(b =>
  b.addEventListener("click", async () => {{
    const cid = b.dataset.chooseConflict, msg = document.getElementById("cmsg-" + cid);
    try {{
      const j = await post("/console/api/decisions/choose_conflict", {{conflict_id: cid,
        choice: document.getElementById("choice-" + cid).value,
        reason: document.getElementById("creason-" + cid).value || null}});
      msg.textContent = "disposed (decision seq " + j.seq + ") — reloading";
      setTimeout(() => location.reload(), 700);
    }} catch (e) {{ msg.textContent = "refused: " + e.message; }}
  }}));
</script>""")


# -- Bus ---------------------------------------------------------------------------

def bus_html(store, token: str | None = None, bus_dir=None,
             limit_per_topic: int = 20) -> str:
    """Recent bus messages, METADATA ONLY.

    Renders ids, timestamps, senders, topics, types, correlation ids and
    payload KEY names. Payload VALUES are never rendered -- agent
    surfaces stay metadata-only even inside the Operator console.

    The bus accretes to the dsys-store checkout, which may be absent on
    this machine. A missing (or non-git) checkout renders an error panel
    instead of raising -- an unhandled exception here would drop the
    review server's connection mid-request.
    """
    intro = ("<p>Broadcast bus — metadata only. Payload values are never shown here;\n"
             "the bus itself refuses SSN/EIN-shaped payloads at publish time.</p>")
    try:
        sections = []
        for topic in _bus.topics(bus_dir=bus_dir):
            msgs = _bus.list_messages(topic, bus_dir=bus_dir)[-limit_per_topic:]
            rows = "".join(
                f"<tr><td class=\"mono\">{html.escape(m.get('id', ''))}</td>"
                f"<td>{html.escape(str(m.get('ts', '')))}</td>"
                f"<td class=\"mono\">{html.escape(str(m.get('from', '')))}</td>"
                f"<td class=\"mono\">{html.escape(str(m.get('type', '')))}</td>"
                f"<td class=\"mono\">{html.escape(str(m.get('correlation_id') or '—'))}</td>"
                f"<td class=\"mono\">{html.escape(', '.join(sorted((m.get('payload') or {}).keys())))}</td></tr>"
                for m in msgs) or '<tr><td colspan="6"><i>no messages</i></td></tr>'
            sections.append(
                f"<h3><span class=\"mono\">{html.escape(topic)}</span> "
                f"({len(msgs)} recent)</h3>"
                f"<table><tr><th>id</th><th>ts</th><th>from</th><th>type</th>"
                f"<th>correlation</th><th>payload keys</th></tr>{rows}</table>")
        body = "\n".join(sections) or "<p><i>No bus topics.</i></p>"
    except (FileNotFoundError, ValueError) as exc:
        # _require_store_checkout: missing or non-git dsys-store checkout.
        body = (f"<div class=\"pend\">Bus unavailable: "
                f"{html.escape(str(exc))}</div>")
    return _page("Bus", token, "bus", f"{intro}\n{body}")


# -- Activity log (R13) --------------------------------------------------------------

def activity_html(store, token: str | None = None,
                  doc_id: str | None = None, limit: int = 200) -> str:
    base = _token_url_base(token)
    events = _sources.lifecycle_events(store, doc_id=doc_id, limit=limit)
    if events is None:
        body = ('<div class="pend">Lifecycle event log pending — the R13 '
                'sibling workstream has not installed '
                '<span class="mono">taxprep/lifecycle.py</span> yet. '
                'Contract: <span class="mono">events_for(store, doc_id=None, '
                'limit) -&gt; [{ts, doc_id, event, actor, from, to, reason_code}]</span>.</div>')
    else:
        rows = "".join(
            f"<tr><td>{html.escape(str(e['ts']))}</td>"
            f"<td><a href=\"{base}/console/doc/{quote(str(e['doc_id'] or ''))}\">"
            f"{html.escape(str(e['doc_id']))}</a></td>"
            f"<td class=\"mono\">{html.escape(str(e['event']))}</td>"
            f"<td>{html.escape(str(e['actor']))}</td>"
            f"<td class=\"mono\">{html.escape(str(e['from']))} → {html.escape(str(e['to']))}</td>"
            f"<td class=\"mono\">{html.escape(str(e['reason_code']))}</td></tr>"
            for e in events) or '<tr><td colspan="6"><i>No events.</i></td></tr>'
        filt = (f" for <span class=\"mono\">{html.escape(doc_id)}</span>"
                if doc_id else "")
        body = (f"<p>{len(events)} event(s){filt}, oldest first.</p>"
                f"<table><tr><th>ts</th><th>doc</th><th>event</th><th>actor</th>"
                f"<th>transition</th><th>reason</th></tr>{rows}</table>")
    return _page("Activity Log", token, "activity", body)


# -- GET dispatch ----------------------------------------------------------------------

def dispatch_get(store, parsed, token: str | None = None, **kwargs):
    """Render a console page. Returns the HTML string, or None when the
    path is not a console path (caller 404s)."""
    path = parsed.path
    if path == "/console":
        return hub_html(store, token)
    if path == "/console/sources":
        return sources_html(store, token)
    if path == "/console/runs":
        return runs_html(store, token)
    if path == "/console/queue":
        return queue_html(store, token)
    if path.startswith("/console/doc/"):
        from urllib.parse import unquote
        doc_id = unquote(path[len("/console/doc/"):])
        qs = parse_qs(parsed.query)
        try:
            lot_page = max(0, int(qs.get("lot_page", ["0"])[0]))
        except (TypeError, ValueError):
            lot_page = 0
        page = doc_review_html(store, store.get(doc_id), token,
                               lot_page=lot_page)
        return page  # None -> caller 404s
    if path == "/console/checks":
        qs = parse_qs(parsed.query)
        year = None
        if qs.get("year", [""])[0].strip():
            try:
                year = int(qs["year"][0])
            except ValueError:
                pass
        return checks_html(store, token, year)
    if path == "/console/carryforward":
        return carryforward_html(store, token)
    if path == "/console/decisions":
        return decisions_html(store, token)
    if path == "/console/bus":
        return bus_html(store, token, bus_dir=kwargs.get("bus_dir"))
    if path == "/console/activity":
        qs = parse_qs(parsed.query)
        doc_id = qs.get("doc_id", [""])[0] or None
        return activity_html(store, token, doc_id)
    return None


# -- POST dispatch -----------------------------------------------------------------------

def _err(code: int, error: str, **extra) -> tuple[int, dict]:
    out = {"ok": False, "error": error}
    out.update(extra)
    return code, out


def dispatch_post(store, path: str, payload: dict) -> tuple[int, dict]:
    """Console API dispatch. Returns (http_status, response_dict).

    Called AFTER the R10 gates (Host allowlist, JSON content type,
    same-origin) have passed -- see review._Handler.do_POST.
    """
    if not isinstance(payload, dict):
        return _err(400, "payload must be a JSON object")

    if path == "/console/api/sources/roots/register":
        p = payload.get("path", "")
        if not isinstance(p, str) or not p.strip():
            return _err(400, "path is required")
        try:
            root = _sources.register_root(p.strip())
        except FileNotFoundError as exc:
            return _err(404, str(exc))
        except (NotADirectoryError, ValueError) as exc:
            return _err(422, str(exc))
        return 200, {"ok": True, "root": root}

    if path == "/console/api/sources/roots/unregister":
        rid = payload.get("root_id", "")
        try:
            removed = _sources.unregister_root(rid)
        except KeyError as exc:
            return _err(404, str(exc))
        return 200, {"ok": True, "removed": removed}

    if path == "/console/api/sources/ingest":
        fids = payload.get("file_ids")
        if not isinstance(fids, list) or not all(isinstance(x, str) for x in fids):
            return _err(400, "file_ids must be a list of strings")
        if len(fids) > 500:
            return _err(422, "too many files in one request (max 500)")
        try:
            result = _sources.ingest_checked(store, fids)
        except Exception as exc:
            return _err(500, f"ingest failed: {type(exc).__name__}")
        result["ok"] = True
        # Source ingests appear as Runs: one gold_run row per console
        # ingest (best-effort -- a missing table never fails the ingest).
        doc_ids = sorted({d for f in result["files"] for d in f["docs"]})
        result["gold_run_id"] = _record_gold_run(
            store, "source_ingest",
            {"file_ids": sorted(fids)},
            {"summary": result["summary"], "doc_ids": doc_ids})
        return 200, result

    if path == "/console/api/sources/exclude":
        fids = payload.get("file_ids")
        if not isinstance(fids, list) or not all(isinstance(x, str) for x in fids):
            return _err(400, "file_ids must be a list of strings")
        if len(fids) > 500:
            return _err(422, "too many files in one request (max 500)")
        files = _exclude_checked(store, fids)
        return 200, {"ok": True, "files": files}

    if path == "/console/api/decisions/rule_group":
        gid = payload.get("group_id", "")
        ruling = payload.get("ruling", "")
        try:
            seq = _duplicates.rule_on_group(
                store, gid, ruling=ruling,
                primary=payload.get("primary"),
                reason=payload.get("reason"))
        except KeyError as exc:
            return _err(404, str(exc))
        except ValueError as exc:
            return _err(422, str(exc))
        return 200, {"ok": True, "seq": seq}

    if path == "/console/api/decisions/choose_conflict":
        cid = payload.get("conflict_id", "")
        choice = payload.get("choice", "")
        try:
            seq = _duplicates.choose_conflict(
                store, cid, choice=choice, reason=payload.get("reason"))
        except KeyError as exc:
            return _err(404, str(exc))
        except ValueError as exc:
            return _err(422, str(exc))
        return 200, {"ok": True, "seq": seq}

    return _err(404, "unknown console API path")
