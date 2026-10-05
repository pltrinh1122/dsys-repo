"""Tests for the R12 Operator console + R11 rev2 source discovery.

Synthetic fixtures only. The console is Operator-only (loopback); the
values-plane boundary (agent surfaces stay metadata-only) is pinned in
tests/test_values_plane.py.
"""

from __future__ import annotations

import http.client
import json
import os
import stat
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest

from taxprep import console, duplicates, sources
from taxprep.review import make_server
from taxprep.store import DocumentStore

TXT_A = "Form W-2 Wage and Tax Statement 2024\nBox 1 Wages 85000.00\n"
TXT_B = TXT_A + "\n\n"  # same normalized text, different bytes (L2, not L1)


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "data")


@pytest.fixture()
def cfgdir(tmp_path, monkeypatch):
    d = tmp_path / "cfg"
    monkeypatch.setattr("taxprep.sources._config_dir", lambda: d)
    return d


def _write(root: Path, name: str, text: str) -> Path:
    p = root / name
    p.write_text(text, encoding="utf-8")
    return p


def _ingest_txt(store, path: Path):
    from taxprep import ingest as _ingest
    return _ingest.ingest_file(path, store)


# -- root registry -----------------------------------------------------

def test_register_root_roundtrip(cfgdir, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    entry = sources.register_root(root)
    assert entry["path"] == str(root.resolve())
    assert len(entry["root_id"]) == 16
    assert entry["added_by"] == "operator"
    assert entry["added_ts"]
    loaded = sources.load_roots()
    assert len(loaded) == 1
    assert loaded[0]["root_id"] == entry["root_id"]
    mode = stat.S_IMODE(sources.roots_path().stat().st_mode)
    assert mode == 0o600, f"registry mode is {oct(mode)}, expected 0o600"


def test_register_root_dedupe(cfgdir, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    a = sources.register_root(root)
    b = sources.register_root(str(root) + "/.")  # same dir, different spelling
    assert a["root_id"] == b["root_id"]
    assert len(sources.load_roots()) == 1


def test_register_root_refuses_missing(cfgdir, tmp_path):
    with pytest.raises(FileNotFoundError):
        sources.register_root(tmp_path / "nope")


def test_register_root_refuses_file(cfgdir, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        sources.register_root(f)


def test_unregister_root(cfgdir, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    entry = sources.register_root(root)
    removed = sources.unregister_root(entry["root_id"])
    assert removed["root_id"] == entry["root_id"]
    assert sources.load_roots() == []
    with pytest.raises(KeyError):
        sources.unregister_root(entry["root_id"])


def test_registry_mode_repaired_on_load(cfgdir, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    sources.register_root(root)
    p = sources.roots_path()
    os.chmod(p, 0o644)
    sources.load_roots()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


# -- route prediction ----------------------------------------------------

def test_predict_route_pdf(tmp_path):
    r = sources.predict_route(tmp_path / "scan.pdf")
    assert r["route"] == sources.ROUTE_PDF_GATE


def test_predict_route_pdf_sidecar(tmp_path):
    _write(tmp_path, "scan.txt", "ocr text")
    r = sources.predict_route(tmp_path / "scan.pdf")
    assert r["route"] == sources.ROUTE_SIDECAR


def test_predict_route_txt(tmp_path):
    assert sources.predict_route(tmp_path / "a.txt")["route"] == sources.ROUTE_NATIVE_TEXT


def test_predict_route_image(tmp_path):
    assert sources.predict_route(tmp_path / "a.jpg")["route"] == sources.ROUTE_IMAGE_OCR


def test_predict_route_csv(tmp_path):
    assert sources.predict_route(tmp_path / "a.csv")["route"] == sources.ROUTE_BROKER_CSV


def test_predict_route_unsupported(tmp_path):
    assert sources.predict_route(tmp_path / "a.xyz")["route"] == sources.ROUTE_SKIP


# -- metadata scan ---------------------------------------------------------

def _registered(store, cfgdir, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    sources.register_root(root)
    return root


def test_scan_reports_metadata_only(store, cfgdir, tmp_path):
    root = _registered(store, cfgdir, tmp_path)
    _write(root, "a.txt", "SECRET_VALUE_XYZ 123-45-6789\n")
    _write(root, "b.pdf", "%PDF-1.4 fake\n")
    scans = sources.scan_roots(store)
    assert len(scans) == 1
    files = scans[0]["files"]
    assert len(files) == 2
    # Deterministic order, expected keys, no content anywhere.
    assert [f["rel"] for f in files] == ["a.txt", "b.pdf"]
    blob = json.dumps(scans)
    assert "SECRET_VALUE_XYZ" not in blob
    assert "123-45-6789" not in blob
    f0 = files[0]
    assert set(f0) == {"file_id", "rel", "ext", "size_bytes", "mtime",
                       "sha256", "route", "route_detail", "ingested", "dup_hint"}
    assert f0["route"] == sources.ROUTE_NATIVE_TEXT
    assert f0["ingested"] is False
    assert f0["dup_hint"] is None


def test_scan_l1_hint_after_ingest(store, cfgdir, tmp_path):
    root = _registered(store, cfgdir, tmp_path)
    p = _write(root, "a.txt", TXT_A)
    _ingest_txt(store, p)
    files = sources.scan_roots(store)[0]["files"]
    assert files[0]["ingested"] is True
    assert files[0]["dup_hint"]["level"] == "L1"


def test_scan_l2_hint_same_text_different_bytes(store, cfgdir, tmp_path):
    root = _registered(store, cfgdir, tmp_path)
    pa = _write(root, "a.txt", TXT_A)
    pb = _write(root, "b.txt", TXT_B)
    _ingest_txt(store, pa)
    files = {f["rel"]: f for f in sources.scan_roots(store)[0]["files"]}
    hint = files["b.txt"]["dup_hint"]
    assert hint is not None and hint["level"] == "L2"
    assert len(hint["bronze_hash"]) == 64


def test_scan_skips_escaping_symlink(store, cfgdir, tmp_path):
    root = _registered(store, cfgdir, tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    (root / "evil.txt").symlink_to(outside)
    files = sources.scan_roots(store)[0]["files"]
    assert files == []


# -- checked-file ingest -----------------------------------------------------

def test_ingest_checked(store, cfgdir, tmp_path):
    root = _registered(store, cfgdir, tmp_path)
    _write(root, "a.txt", TXT_A)
    _write(root, "b.txt", TXT_B)
    scan = sources.scan_roots(store)[0]["files"]
    ids = [f["file_id"] for f in scan]
    result = sources.ingest_checked(store, ids)
    assert result["summary"] == {"requested": 2, "ingested": 2, "failed": 0}
    assert all(r["ok"] and len(r["docs"]) == 1 for r in result["files"])
    assert all(r["rel"] in ("a.txt", "b.txt") for r in result["files"])


def test_ingest_checked_unknown_file_id(store, cfgdir, tmp_path):
    _registered(store, cfgdir, tmp_path)
    result = sources.ingest_checked(store, ["deadbeefdeadbeef"])
    assert result["summary"]["failed"] == 1
    assert result["files"][0]["ok"] is False


def _stub_lifecycle(monkeypatch):
    recorded = []

    mod = types.ModuleType("taxprep.lifecycle")

    def record_event(store, *, doc_id, event, actor, from_state, to_state,
                     reason_code):
        recorded.append({"doc_id": doc_id, "event": event, "actor": actor,
                         "from": from_state, "to": to_state,
                         "reason_code": reason_code})
        return True

    def events_for(store, *, doc_id=None, limit=200):
        rows = [dict(r, ts="2026-10-04T00:00:00+00:00") for r in recorded]
        if doc_id is not None:
            rows = [r for r in rows if r["doc_id"] == doc_id]
        return rows[:limit]

    def state_of(store, doc_id):
        return "ingested" if any(r["doc_id"] == doc_id for r in recorded) else None

    mod.record_event = record_event
    mod.events_for = events_for
    mod.state_of = state_of
    # Both the sys.modules entry AND the package attribute: a previous
    # test may have already imported the real sibling module, in which
    # case `from . import lifecycle` resolves via the package attribute.
    monkeypatch.setitem(sys.modules, "taxprep.lifecycle", mod)
    monkeypatch.setattr("taxprep.lifecycle", mod, raising=False)
    return recorded


def test_ingest_checked_drives_lifecycle_select_ingest(store, cfgdir, tmp_path, monkeypatch):
    from taxprep import ingest as _ingest
    real_lc = _ingest.lifecycle  # bound at import; the stub below must not affect it
    recorded = _stub_lifecycle(monkeypatch)
    root = _registered(store, cfgdir, tmp_path)
    _write(root, "a.txt", TXT_A)
    fid = sources.scan_roots(store)[0]["files"][0]["file_id"]
    result = sources.ingest_checked(store, [fid])
    assert result["files"][0]["lifecycle_recorded"] is True
    # file-level select goes through the adapter (stubbed here)
    assert [r["event"] for r in recorded] == ["select"]
    assert recorded[0]["reason_code"] == "operator_checked"
    assert recorded[0]["to"] == "selected"
    # per-doc ingest went through the REAL transition() inside ingest_file;
    # the chain holds a real ingest event and no raw "ingested" row.
    doc_id = result["files"][0]["docs"][0]
    evs = real_lc.events_for(store, doc_id=doc_id)
    assert any(e["event"] == "ingest" for e in evs)
    assert not any(e.get("to") == "ingested" for e in evs)


def test_ingest_checked_without_lifecycle_module(store, cfgdir, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "taxprep.lifecycle", None)  # None in sys.modules -> ImportError
    monkeypatch.delattr("taxprep.lifecycle", raising=False)  # defeat the package-attr fallback (review.py imports it)
    root = _registered(store, cfgdir, tmp_path)
    _write(root, "a.txt", TXT_A)
    fid = sources.scan_roots(store)[0]["files"][0]["file_id"]
    result = sources.ingest_checked(store, [fid])
    # Ingest still works; the adapter reports the lifecycle gap honestly.
    assert result["summary"]["ingested"] == 1
    assert result["files"][0]["lifecycle_recorded"] is False
    assert sources.lifecycle_events(store) is None
    assert sources.lifecycle_state(store, "whatever") is None


# -- HTTP layer (R10 hardening applies to every console endpoint) -------------

def _get(url: str):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _post(url: str, payload: dict, *, origin=None, ctype="application/json"):
    origin = origin or f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": ctype, "Origin": origin}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _raw(base, target, method="GET", headers=None, data=None):
    host, port = urlparse(base).hostname, urlparse(base).port
    conn = http.client.HTTPConnection(host, port)
    hdrs = dict(headers or {})
    host_hdr = hdrs.pop("Host", None)
    conn.putrequest(method, target, skip_host=True)
    if host_hdr is not None:
        conn.putheader("Host", host_hdr)
    for k, v in hdrs.items():
        conn.putheader(k, v)
    if data is not None:
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    conn.close()
    return resp.status, body


@pytest.fixture()
def server(tmp_path, cfgdir, monkeypatch):
    # Hermetic bus: never resolve the real ~/workspace/dsys-store --
    # test_console_views_200 must pass on machines without the checkout.
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(tmp_path / "bus"))
    store = DocumentStore(tmp_path / "data")
    srv = make_server(store, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}", store
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


@pytest.fixture()
def token_server(tmp_path, cfgdir, monkeypatch):
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(tmp_path / "bus"))
    store = DocumentStore(tmp_path / "data")
    srv = make_server(store, port=0, token="sekret")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}", store
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


_CONSOLE_VIEWS = ["sources", "runs", "queue", "checks", "carryforward",
                  "decisions", "bus", "activity"]


def test_console_hub_200(server):
    base, _ = server
    code, body = _get(base + "/console")
    assert code == 200
    assert "Operator console" in body
    for view in _CONSOLE_VIEWS:
        assert f"/console/{view}" in body


def test_console_views_200(server):
    base, _ = server
    for view in _CONSOLE_VIEWS:
        code, _ = _get(base + f"/console/{view}")
        assert code == 200, view


def test_console_bus_view_renders_metadata_only(server, tmp_path, monkeypatch):
    # Hermetic: the bus dir is the fixture's temp TAXPREP_BUS_DIR, never
    # the real ~/workspace/dsys-store checkout.
    from taxprep import bus as _bus
    base, _ = server
    bus_dir = Path(os.environ["TAXPREP_BUS_DIR"])
    _bus.publish("tax-prep.build", "code_landed",
                 {"head": "abc123", "kind": "test"},
                 from_id="op-synth", bus_dir=bus_dir)
    code, body = _get(base + "/console/bus")
    assert code == 200
    assert "tax-prep.build" in body and "code_landed" in body
    assert "op-synth" in body
    # metadata only: payload keys render, payload values never do
    assert "head" in body
    assert "abc123" not in body


def test_console_bus_view_missing_store_renders_error_panel(
        server, tmp_path, monkeypatch):
    # No dsys-store checkout anywhere: the Bus view must render an
    # error panel (HTTP 200), never raise unhandled FileNotFoundError
    # and drop the connection (RemoteDisconnected).
    monkeypatch.delenv("TAXPREP_BUS_DIR")
    monkeypatch.setenv("TAXPREP_STORE_DIR", str(tmp_path / "no-such-store"))
    base, _ = server
    code, body = _get(base + "/console/bus")
    assert code == 200, "bus view must not drop the connection"
    assert "Bus unavailable" in body
    assert "dsys-store checkout not found" in body


def test_console_doc_404(server):
    base, _ = server
    code, _ = _get(base + "/console/doc/does-not-exist")
    assert code == 404


def test_console_unknown_path_404(server):
    base, _ = server
    code, _ = _get(base + "/console/nope")
    assert code == 404


def test_console_host_allowlist_get(server):
    base, _ = server
    _, port = urlparse(base).hostname, urlparse(base).port
    code, _ = _raw(base, "/console/sources", "GET",
                   {"Host": f"attacker.example:{port}"})
    assert code == 403


def test_console_post_register_and_unregister(server, tmp_path):
    base, _ = server
    root = tmp_path / "src"
    root.mkdir()
    code, resp = _post(base + "/console/api/sources/roots/register",
                       {"path": str(root)})
    assert code == 200
    assert resp["ok"] is True
    rid = resp["root"]["root_id"]
    code, body = _get(base + "/console/sources")
    assert code == 200 and str(root.resolve()) in body
    code, resp = _post(base + "/console/api/sources/roots/unregister",
                       {"root_id": rid})
    assert code == 200 and resp["ok"] is True


def test_console_post_register_missing_path(server):
    base, _ = server
    code, resp = _post(base + "/console/api/sources/roots/register",
                       {"path": "/no/such/dir/xyz"})
    assert code == 404
    assert resp["ok"] is False


def test_console_post_requires_json_content_type(server, tmp_path):
    base, _ = server
    _, port = urlparse(base).hostname, urlparse(base).port
    code, _ = _raw(
        base, "/console/api/sources/roots/register", "POST",
        {"Host": f"127.0.0.1:{port}", "Content-Type": "text/plain",
         "Origin": base},
        data=b'{"path": "/tmp"}')
    assert code == 415


def test_console_post_requires_same_origin(server, tmp_path):
    base, _ = server
    code, resp = _post(base + "/console/api/sources/roots/register",
                       {"path": str(tmp_path)},
                       origin="http://evil.example")
    assert code == 403
    assert resp["ok"] is False


def test_console_post_ingest_checked_files(server, tmp_path):
    base, store = server
    root = tmp_path / "src"
    root.mkdir()
    _write(root, "a.txt", TXT_A)
    code, resp = _post(base + "/console/api/sources/roots/register",
                       {"path": str(root)})
    assert code == 200
    code, body = _get(base + "/console/sources")
    assert code == 200 and "a.txt" in body  # operator plane shows filenames
    scans = sources.scan_roots(store)
    fid = scans[0]["files"][0]["file_id"]
    code, resp = _post(base + "/console/api/sources/ingest",
                       {"file_ids": [fid]})
    assert code == 200
    assert resp["summary"] == {"requested": 1, "ingested": 1, "failed": 0}
    assert len(store.list()) == 1


def test_console_token_mode(token_server):
    base, _ = token_server
    code, _ = _get(base + "/console")
    assert code == 404  # token prefix missing
    code, body = _get(base + "/t/sekret/console")
    assert code == 200 and "Operator console" in body
    code, resp = _post(base + "/t/sekret/console/api/sources/roots/register",
                       {"path": "/no/such/dir"})
    assert code == 404  # routed past the token gate, then refused as missing


def _l2_group_id(store):
    with store.txn() as conn:
        row = conn.execute(
            "SELECT group_id FROM dup_group WHERE status = 'open' "
            "ORDER BY group_id LIMIT 1").fetchone()
    return row[0] if row else None


def test_decisions_rule_group_http(server, tmp_path):
    base, store = server
    d = tmp_path / "d"
    d.mkdir()
    _write(d, "a.txt", TXT_A)
    _write(d, "b.txt", TXT_B)
    _ingest_txt(store, d / "a.txt")
    _ingest_txt(store, d / "b.txt")
    gid = _l2_group_id(store)
    assert gid is not None
    code, body = _get(base + "/console/decisions")
    assert code == 200 and gid[:16] in body
    code, resp = _post(base + "/console/api/decisions/rule_group",
                       {"group_id": gid, "ruling": "distinct",
                        "reason": "different scans"})
    assert code == 200
    assert resp["ok"] is True and isinstance(resp["seq"], int)
    with store.txn() as conn:
        status = conn.execute(
            "SELECT status FROM dup_group WHERE group_id = ?", (gid,)).fetchone()[0]
        kinds = [r[0] for r in conn.execute(
            "SELECT kind FROM decision_log WHERE group_id = ?", (gid,))]
    assert status == "disposed"
    assert "duplicate_ruling" in kinds


def test_decisions_rule_group_bad_ruling_422(server, tmp_path):
    base, store = server
    d = tmp_path / "d"
    d.mkdir()
    _write(d, "a.txt", TXT_A)
    _write(d, "b.txt", TXT_B)
    _ingest_txt(store, d / "a.txt")
    _ingest_txt(store, d / "b.txt")
    gid = _l2_group_id(store)
    code, resp = _post(base + "/console/api/decisions/rule_group",
                       {"group_id": gid, "ruling": "nuke_it"})
    assert code == 422
    assert resp["ok"] is False


def test_decisions_choose_conflict_http(server):
    base, store = server
    cid = duplicates.raise_conflict(
        store, cls="parser", field="box1",
        options=[{"option_key": "a", "value_json": "1"},
                 {"option_key": "b", "value_json": "2"}])
    code, body = _get(base + "/console/decisions")
    assert code == 200 and cid[:16] in body
    code, resp = _post(base + "/console/api/decisions/choose_conflict",
                       {"conflict_id": cid, "choice": "b",
                        "reason": "operator picked b"})
    assert code == 200 and resp["ok"] is True
    with store.txn() as conn:
        status = conn.execute(
            "SELECT status FROM conflict WHERE conflict_id = ?",
            (cid,)).fetchone()[0]
    assert status == "disposed"


def test_decisions_unknown_group_404(server):
    base, _ = server
    code, resp = _post(base + "/console/api/decisions/rule_group",
                       {"group_id": "nope", "ruling": "distinct"})
    assert code == 404


# -- sibling contracts ---------------------------------------------------

def test_activity_view_with_lifecycle_stub(server, monkeypatch):
    base, store = server
    recorded = _stub_lifecycle(monkeypatch)
    recorded.append({"doc_id": "doc-1", "event": "ingest", "actor": "operator",
                     "from": "selected", "to": "ingested",
                     "reason_code": "checked_file_ingest"})
    code, body = _get(base + "/console/activity")
    assert code == 200
    assert "checked_file_ingest" in body
    assert "doc-1" in body


def test_activity_view_pending_without_lifecycle(server, monkeypatch):
    base, _ = server
    monkeypatch.setitem(sys.modules, "taxprep.lifecycle", None)  # None in sys.modules -> ImportError
    monkeypatch.delattr("taxprep.lifecycle", raising=False)  # defeat the package-attr fallback (review.py imports it)
    code, body = _get(base + "/console/activity")
    assert code == 200
    assert "lifecycle.py" in body and "pending" in body.lower()


def test_doc_page_mounts_evidence_pane_stub(server, monkeypatch):
    base, store = server
    d = Path("/tmp")
    assert store.list() == []
    from taxprep import ingest as _ingest
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text(TXT_A)
        docs = _ingest.ingest_file(p, store)
    doc_id = docs[0].doc_id
    mod = types.ModuleType("taxprep.evidence_pane")
    mod.pane_html = lambda s, d: "<div>EVIDENCE-PANE-STUB</div>"
    monkeypatch.setitem(sys.modules, "taxprep.evidence_pane", mod)
    monkeypatch.setattr("taxprep.evidence_pane", mod, raising=False)
    code, body = _get(base + f"/console/doc/{doc_id}")
    assert code == 200
    assert "EVIDENCE-PANE-STUB" in body
    assert f'id="evidence-pane" data-doc-id="{doc_id}"' in body


def test_doc_page_pane_pending_without_sibling(server, monkeypatch):
    base, store = server
    monkeypatch.setitem(sys.modules, "taxprep.evidence_pane", None)  # None -> ImportError
    monkeypatch.delattr("taxprep.evidence_pane", raising=False)  # defeat the package-attr fallback
    from taxprep import ingest as _ingest
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text(TXT_A)
        docs = _ingest.ingest_file(p, store)
    code, body = _get(base + f"/console/doc/{docs[0].doc_id}")
    assert code == 200
    assert "pane pending" in body.lower()


# -- cross-links (Operator decision) + B3/R10 ---------------------------------
#
# Source selection stays a SEPARATE /console/sources endpoint -- it is
# never embedded in the queue. The queue links OUT to it instead, and
# source rows link back to the documents they produced.


def _ingest_via_console(base, store, tmp_path, name="a.txt", text=None):
    """Register a root, scan, and ingest one file through the console API.

    Returns (root_id, file_id, doc_id).
    """
    root = tmp_path / "src"
    root.mkdir(exist_ok=True)
    _write(root, name, text if text is not None else TXT_A)
    code, resp = _post(base + "/console/api/sources/roots/register",
                       {"path": str(root)})
    assert code == 200
    root_id = resp["root"]["root_id"]
    scans = sources.scan_roots(store)
    fid = scans[0]["files"][0]["file_id"]
    code, resp = _post(base + "/console/api/sources/ingest",
                       {"file_ids": [fid]})
    assert code == 200
    return root_id, fid, resp


def test_queue_source_column_links_to_sources(server, tmp_path):
    base, store = server
    root_id, _fid, _resp = _ingest_via_console(base, store, tmp_path)
    code, body = _get(base + "/console/queue")
    assert code == 200
    # Source column: the file's basename, linking to /console/sources
    # anchored to the doc's source root.
    assert "a.txt" in body
    assert f"/console/sources#root-{root_id}" in body


def test_queue_empty_text_and_rescan_banner(server):
    base, _ = server
    code, body = _get(base + "/console/queue")
    assert code == 200
    assert "No documents — select sources." in body
    assert "all validated" not in body  # never claimed
    assert "Re-scan sources" in body
    assert 'href="/console/sources"' in body


def test_sources_rows_link_docs_and_lifecycle(server, tmp_path):
    base, store = server
    _rid, _fid, resp = _ingest_via_console(base, store, tmp_path)
    doc_id = resp["files"][0]["docs"][0]
    code, body = _get(base + "/console/sources")
    assert code == 200
    # The scan row links to the produced document...
    assert f"/console/doc/{doc_id}" in body
    # ...with its pipeline (lifecycle) state.
    assert "needs_review" in body
    # Ingested files carry the "uncheck" (exclude) control.
    assert "data-exclude-file" in body


def test_sources_root_sections_have_anchors(server, tmp_path):
    base, store = server
    root_id, _fid, _resp = _ingest_via_console(base, store, tmp_path)
    code, body = _get(base + "/console/sources")
    assert code == 200
    assert f'id="root-{root_id}"' in body


def test_hub_documents_by_status_funnel(server, tmp_path):
    base, store = server
    _rid, _fid, _resp = _ingest_via_console(base, store, tmp_path)
    code, body = _get(base + "/console")
    assert code == 200
    assert "Documents by status" in body
    # The indexed aggregate counts the ingested doc exactly once.
    assert "needs_review</td><td>1</td>" in body


def test_console_ingest_records_gold_run(server, tmp_path):
    base, store = server
    _rid, _fid, resp = _ingest_via_console(base, store, tmp_path)
    run_id = resp.get("gold_run_id")
    assert run_id, "console ingest must record a gold_run"
    with store.txn() as conn:
        row = conn.execute(
            "SELECT kind FROM gold_run WHERE run_id = ?", (run_id,)).fetchone()
    assert row is not None and row[0] == "source_ingest"
    # ...and it shows up on the Runs view.
    code, body = _get(base + "/console/runs")
    assert code == 200 and "source_ingest" in body


def test_console_exclude_unchecks_source(server, tmp_path):
    base, store = server
    _rid, fid, resp = _ingest_via_console(base, store, tmp_path)
    doc_id = resp["files"][0]["docs"][0]
    code, resp = _post(base + "/console/api/sources/exclude",
                       {"file_ids": [fid]})
    assert code == 200 and resp["ok"] is True
    f = resp["files"][0]
    assert f["excluded"] == [doc_id]
    assert f["errors"] == []
    # The R13 exclude event fired with the STANDING reason
    # "operator-excluded" (the decision note's "operator-unselected" is
    # reconciled to the existing taxonomy -- no duplicate reason).
    doc = store.get(doc_id)
    assert doc.status == "excluded"
    assert doc.status_reason == "operator-excluded"
    # Excluded docs leave the review queue.
    code, body = _get(base + "/console/queue")
    assert code == 200 and doc_id not in body
    # The exclusion is in the decision log.
    with store.txn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM decision_log WHERE kind = 'exclude' "
            "AND doc_id = ?", (doc_id,)).fetchone()
    assert row[0] >= 1


def test_console_exclude_unknown_file_id(server, tmp_path):
    base, _ = server
    code, resp = _post(base + "/console/api/sources/exclude",
                       {"file_ids": ["nope-nope-nope-nope"]})
    assert code == 200 and resp["ok"] is True
    assert resp["files"][0]["excluded"] == []
    assert resp["files"][0]["errors"]  # loud, never silent


def test_console_exclude_rejects_bad_payload(server):
    base, _ = server
    code, resp = _post(base + "/console/api/sources/exclude",
                       {"file_ids": "not-a-list"})
    assert code == 400 and resp["ok"] is False


# -- R10 on the console POST surface ------------------------------------
#
# The review surface (/api/validate) already pins token rejection in
# test_review.py. Both surfaces route through review._Handler.do_POST,
# which applies the token prefix check BEFORE any route logic.


def test_console_token_mode_post_without_token_404(token_server):
    base, _ = token_server
    code, _resp = _post(base + "/console/api/sources/roots/register",
                        {"path": "/no/such/dir"})
    assert code == 404  # missing /t/<token> prefix: indistinguishable from 404


def test_console_token_mode_post_wrong_token_404(token_server):
    base, _ = token_server
    code, _resp = _post(base + "/t/wrong/console/api/sources/roots/register",
                        {"path": "/no/such/dir"})
    assert code == 404


def test_console_token_mode_exclude_without_token_404(token_server):
    base, _ = token_server
    code, _resp = _post(base + "/console/api/sources/exclude",
                        {"file_ids": ["x"]})
    assert code == 404
