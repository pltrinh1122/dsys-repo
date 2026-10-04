"""R11 rev2 -- Operator-only source discovery and selection.

Source roots are registered by the Operator through the Operator console
(loopback only) and stored in the machine-local config file
``~/.config/taxprep/source_roots.json`` with mode 0600: the registry
holds absolute filesystem paths, so it is never committed, never synced,
and readable only by the owner.

What lives where:

* root registry  -- ``source_roots.json`` (mode 0600), written by
  :func:`register_root` / :func:`unregister_root` only;
* per-file scan  -- computed on demand by :func:`scan_roots`, never
  persisted: file count, types, sizes, content sha256, predicted text
  route, and L1/L2 duplicate hints against the bronze store. No file
  CONTENT is read beyond what duplicate-hinting and route prediction
  need (sizes, hashes, text-layer presence), and none of it is stored;
* ingest bookkeeping -- ``bronze.source_root`` / ``bronze.selection_state``
  (already in the medallion schema; set by :func:`ingest_checked`).

Values plane: the registry and scan results are OPERATOR-ONLY. Agent
surfaces (MCP tools, bus payloads) never see paths or filenames -- only
counts, hashes, and statuses. The one exception is inside the loopback
console itself, which is the Operator's own values plane.

Lifecycle: checked-file ingest runs the R13 select -> ingest transitions
through the sibling lifecycle module when it is installed (see
:func:`lifecycle_record` / :func:`lifecycle_events`); when it is not,
ingest still works and the adapter reports ``recorded=False`` so the
console can say so honestly instead of dropping events silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REGISTRY_VERSION = 1
_FILE_ID_LEN = 16


# -- root registry (mode 0600) ---------------------------------------------

def _config_dir() -> Path:
    """Machine-local taxprep config dir. Monkeypatchable in tests."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "taxprep"


def roots_path() -> Path:
    """Path of the source-roots registry file."""
    return _config_dir() / "source_roots.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _enforce_mode_600(path: Path) -> None:
    """Ensure the registry file is owner-read/write only.

    Repairs the mode when it drifted (umask races, restores) -- the
    registry holds absolute filesystem paths, so world/group readability
    is a leak, not a warning.
    """
    try:
        if (path.stat().st_mode & 0o777) != 0o600:
            os.chmod(path, 0o600)
    except OSError:
        pass  # best effort on odd filesystems; write path sets it


def _read_registry() -> dict:
    p = roots_path()
    if not p.is_file():
        return {"version": _REGISTRY_VERSION, "roots": []}
    _enforce_mode_600(p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"source-roots registry unreadable: {p}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("roots"), list):
        raise ValueError(f"source-roots registry malformed: {p}")
    return data


def _write_registry(data: dict) -> None:
    """Atomic write with mode 0600 from creation (no readable window)."""
    p = roots_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".roots-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # fd was created 0600 by mkstemp; make the requirement explicit.
            os.fchmod(fh.fileno(), 0o600)
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    _enforce_mode_600(p)


def _root_id(resolved: str) -> str:
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:_FILE_ID_LEN]


def load_roots() -> list[dict]:
    """Registered source roots, oldest first.

    Each entry: {root_id, path, added_ts, added_by}. Mode 0600 is
    enforced on the registry file as a side effect of loading.
    """
    roots = _read_registry()["roots"]
    return sorted(roots, key=lambda r: r.get("added_ts", ""))


def register_root(path: str | Path, *, actor: str = "operator") -> dict:
    """Register a source root. Returns the registry entry.

    The path must resolve to an existing directory; duplicates (same
    resolved path) return the existing entry. Fail closed on anything
    else.
    """
    resolved = str(Path(path).expanduser().resolve())
    p = Path(resolved)
    if not p.exists():
        raise FileNotFoundError(f"source root does not exist: {resolved}")
    if not p.is_dir():
        raise NotADirectoryError(f"source root is not a directory: {resolved}")
    data = _read_registry()
    for entry in data["roots"]:
        if entry.get("path") == resolved:
            return dict(entry)
    entry = {
        "root_id": _root_id(resolved),
        "path": resolved,
        "added_ts": _utcnow(),
        "added_by": actor,
    }
    data["roots"].append(entry)
    data["version"] = _REGISTRY_VERSION
    _write_registry(data)
    return dict(entry)


def unregister_root(root_id: str) -> dict:
    """Remove a source root from the registry. Returns the removed entry."""
    data = _read_registry()
    for i, entry in enumerate(data["roots"]):
        if entry.get("root_id") == root_id:
            removed = data["roots"].pop(i)
            _write_registry(data)
            return dict(removed)
    raise KeyError(f"unknown source root: {root_id}")


# -- route prediction ------------------------------------------------------

# Mirrors the ingest route decision (taxprep/ingest.py _page_bundle_for /
# ingest_file) without reading file content: extension + sidecar presence
# determine the predicted text route. Honest about what it cannot know:
# a PDF's native-vs-OCR split is decided by the text-sufficiency gate at
# ingest time, so PDFs predict "pdf-text-gate", not a specific branch.
ROUTE_NATIVE_TEXT = "native-text"        # .txt: bytes ARE the text
ROUTE_PDF_GATE = "pdf-text-gate"         # .pdf: text-sufficiency gate decides
ROUTE_SIDECAR = "sidecar-text"           # pdf/image with same-basename .txt
ROUTE_IMAGE_OCR = "image-to-pdf-ocr"     # image -> pdf -> OCR path
ROUTE_BROKER_CSV = "broker-csv"          # .csv: separate ingest_csv path
ROUTE_SKIP = "skip-unsupported"          # ingest_file would _SkipFile


def predict_route(path: str | Path) -> dict:
    """Predict which text route a file would take at ingest.

    Returns {route, detail}. Deterministic, content-free (only the
    suffix and the presence of a same-basename .txt sidecar are read).
    """
    from . import ingest as _ingest

    p = Path(path)
    suffix = p.suffix.lower()
    sidecar = p.with_suffix(".txt")
    has_sidecar = (
        suffix != ".txt"
        and sidecar.is_file()
        and sidecar.resolve() != p.resolve()
    )
    if suffix in _ingest.PDF_EXTS:
        if has_sidecar:
            return {"route": ROUTE_SIDECAR,
                    "detail": "same-basename .txt sidecar supplies the text"}
        return {"route": ROUTE_PDF_GATE,
                "detail": "text-sufficiency gate decides native vs OCR at ingest"}
    if suffix in _ingest.TXT_EXTS:
        return {"route": ROUTE_NATIVE_TEXT,
                "detail": "file bytes are the document text"}
    if suffix in _ingest.IMAGE_EXTS:
        if has_sidecar:
            return {"route": ROUTE_SIDECAR,
                    "detail": "same-basename .txt sidecar supplies the text"}
        return {"route": ROUTE_IMAGE_OCR,
                "detail": "image converted to PDF, then OCR"}
    if suffix == ".csv":
        return {"route": ROUTE_BROKER_CSV,
                "detail": "broker CSV goes through the separate ingest_csv path"}
    return {"route": ROUTE_SKIP,
            "detail": f"ingest_file skips {suffix or '(no extension)'}"}


# -- metadata scan ----------------------------------------------------------

def _file_id(root_id: str, rel: str) -> str:
    return hashlib.sha256(f"{root_id}:{rel}".encode("utf-8")).hexdigest()[:_FILE_ID_LEN]


def _bronze_known(store, sha: str) -> bool:
    with store.txn() as conn:
        row = conn.execute(
            "SELECT 1 FROM bronze WHERE hash = ?", (sha,)).fetchone()
    return row is not None


def _l2_hint(store, sha: str, text: str | None) -> dict | None:
    """L2 duplicate hint: same normalized text, different bytes, already ingested.

    Returns {level: "L2", bronze_hash} or None. ``text`` is the file's
    extractable text (None when unavailable -- then no hint is made,
    rather than a wrong one).
    """
    if not text or not text.strip():
        return None
    from . import duplicates as _dup
    fp = _dup.text_fingerprint([text])
    with store.txn() as conn:
        row = conn.execute(
            "SELECT hash FROM bronze WHERE text_fingerprint = ? AND hash <> ? "
            "ORDER BY hash LIMIT 1", (fp, sha)).fetchone()
    if row is None:
        return None
    return {"level": "L2", "bronze_hash": row[0]}


def _extractable_text(path: Path, suffix: str) -> str | None:
    """Best-effort text for L2 hinting. None when unavailable."""
    try:
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            from .ingest import extract_pdf_text
            return extract_pdf_text(path)
    except Exception:
        return None
    return None


def scan_roots(store, roots: list[dict] | None = None) -> list[dict]:
    """Metadata scan of every registered root (or the given roots).

    Returns one dict per root: {root_id, path, ok, error, files}, where
    each file entry is {file_id, rel, ext, size_bytes, mtime,
    sha256, route, route_detail, ingested, dup_hint}.

    Metadata only: file COUNT, TYPES, SIZES -- no values. ``sha256`` is
    the content hash (needed for L1 matching), not content. Symlinks
    escaping the root are skipped (never followed). Deterministic:
    files sorted by relative path.
    """
    from . import ingest as _ingest

    if roots is None:
        roots = load_roots()
    results = []
    for root in roots:
        root_id = root.get("root_id", "")
        base = Path(root.get("path", ""))
        entry: dict = {"root_id": root_id, "path": str(base),
                       "ok": True, "error": None, "files": []}
        if not base.is_dir():
            entry.update(ok=False, error="root directory missing")
            results.append(entry)
            continue
        try:
            base_resolved = base.resolve()
        except OSError as exc:
            entry.update(ok=False, error=f"cannot resolve root: {exc}")
            results.append(entry)
            continue
        paths: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(base_resolved):
            dirnames.sort()
            for name in sorted(filenames):
                full = Path(dirpath) / name
                try:
                    # Never follow symlinks out of the root.
                    if full.is_symlink() and base_resolved not in full.resolve().parents:
                        continue
                    rel = str(full.relative_to(base_resolved))
                except (OSError, ValueError):
                    continue
                paths.append(full)
        for full in paths:
            rel = str(full.relative_to(base_resolved))
            suffix = full.suffix.lower()
            try:
                stat = full.stat()
            except OSError:
                continue
            route = predict_route(full)
            try:
                digest = hashlib.sha256()
                with full.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        digest.update(chunk)
                sha = digest.hexdigest()
            except OSError:
                continue
            ingested = _bronze_known(store, sha)
            dup_hint = None
            if ingested:
                dup_hint = {"level": "L1", "note": "exact bytes already ingested"}
            elif suffix in _ingest.TXT_EXTS | _ingest.PDF_EXTS:
                dup_hint = _l2_hint(store, sha, _extractable_text(full, suffix))
            entry["files"].append({
                "file_id": _file_id(root_id, rel),
                "rel": rel,
                "ext": suffix,
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
                "sha256": sha,
                "route": route["route"],
                "route_detail": route["detail"],
                "ingested": ingested,
                "dup_hint": dup_hint,
            })
        results.append(entry)
    return results


# -- lifecycle adapter (R13 contract) ----------------------------------------

def _lifecycle_module():
    """The sibling R13 module, or None when not installed.

    The module may also be present but partial (mid-build): callers
    must getattr-guard the specific function they need rather than
    assuming the full contract.
    """
    try:
        from . import lifecycle as _lc
    except ImportError:
        return None
    return _lc


def lifecycle_record(store, *, doc_id: str, event: str, actor: str,
                     from_state: str | None, to_state: str | None,
                     reason_code: str) -> bool:
    """Record one lifecycle event through the sibling R13 module.

    Returns True when the event was recorded. Returns False when the
    R13 module (or its ``record_event`` entry point) is not available
    yet -- the caller must surface that honestly (event pending, not
    dropped).
    """
    mod = _lifecycle_module()
    fn = getattr(mod, "record_event", None) if mod is not None else None
    if not callable(fn):
        return False
    return bool(fn(
        store, doc_id=doc_id, event=event, actor=actor,
        from_state=from_state, to_state=to_state, reason_code=reason_code))


def lifecycle_events(store, *, doc_id: str | None = None,
                     limit: int = 200) -> list[dict] | None:
    """Per-document lifecycle events, normalized to the contract shape.

    Returns None when the R13 module (or its ``events_for`` entry
    point) is not available yet; otherwise a list of
    {ts, doc_id, event, actor, from, to, reason_code}, oldest first.
    Missing keys in a sibling row are normalized to None rather than
    raising -- the contract names the keys, not their presence.
    """
    mod = _lifecycle_module()
    fn = getattr(mod, "events_for", None) if mod is not None else None
    if not callable(fn):
        return None
    rows = fn(store, doc_id=doc_id, limit=limit) or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({
            "ts": r.get("ts"),
            "doc_id": r.get("doc_id", doc_id),
            "event": r.get("event"),
            "actor": r.get("actor"),
            "from": r.get("from"),
            "to": r.get("to"),
            "reason_code": r.get("reason_code"),
        })
    return out


def lifecycle_state(store, doc_id: str) -> str | None:
    """Current lifecycle state of a document, or None when unknown."""
    mod = _lifecycle_module()
    fn = getattr(mod, "state_of", None) if mod is not None else None
    if not callable(fn):
        return None
    try:
        return fn(store, doc_id)
    except Exception:
        return None


# -- checked-file ingest -----------------------------------------------------

def _resolve_scan(store) -> dict[str, dict]:
    """Map file_id -> (path, root_id) for the current scan."""
    mapping: dict[str, dict] = {}
    for root in scan_roots(store):
        for f in root["files"]:
            mapping[f["file_id"]] = {
                "path": str(Path(root["path"]) / f["rel"]),
                "root_id": root["root_id"],
                "rel": f["rel"],
                "route": f["route"],
            }
    return mapping


def ingest_checked(store, file_ids: list[str], *,
                   actor: str = "operator") -> dict:
    """Ingest the Operator-checked files, driving R13 select -> ingest.

    ``file_ids`` are scan file_ids (never paths -- the POST payload stays
    path-free). For each file: record the ``select`` lifecycle transition,
    run ``ingest_file`` (idempotent: already-ingested bytes are an I2
    no-op), record the ``ingest`` transition per produced document, and
    stamp ``bronze.source_root`` + selection on the new bronze rows.

    Returns {files: [{file_id, rel, ok, docs, skipped_reason, error,
    lifecycle_recorded}], summary}.
    """
    from . import ingest as _ingest

    mapping = _resolve_scan(store)
    results: list[dict] = []
    for fid in file_ids:
        info = mapping.get(fid)
        if info is None:
            results.append({"file_id": fid, "rel": None, "ok": False,
                            "docs": [], "skipped_reason": None,
                            "error": "unknown file_id (re-scan and retry)",
                            "lifecycle_recorded": False})
            continue
        path = Path(info["path"])
        rec = {"file_id": fid, "rel": info["rel"], "ok": True, "docs": [],
               "skipped_reason": None, "error": None,
               "lifecycle_recorded": lifecycle_record(
                   store, doc_id=fid, event="select", actor=actor,
                   from_state=None, to_state="selected",
                   reason_code="operator_checked")}
        try:
            docs = _ingest.ingest_file(path, store)
        except _ingest._SkipFile as exc:  # noqa: SLF001 -- reason code is the API
            rec["ok"] = False
            rec["skipped_reason"] = str(exc)
            results.append(rec)
            continue
        except Exception as exc:
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}"
            results.append(rec)
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        store.register_bronze(sha, path.stat().st_size,
                              source_root=info["root_id"])
        for d in docs:
            rec["docs"].append(d.doc_id)
        # No raw lifecycle record here: ingest_file already fired the real
        # select -> ingest transition() per document (R13). A raw
        # "ingested" row would corrupt replay_lifecycle chain integrity
        # ("ingested" is not a table state).
        results.append(rec)
    ok = sum(1 for r in results if r["ok"])
    return {"files": results,
            "summary": {"requested": len(file_ids), "ingested": ok,
                        "failed": len(results) - ok}}
