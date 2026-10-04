"""Gated gold layer (Arc B, W4).

Gold is a pure function of (validated silver, decisions, parameters)
(R16 I8). Every gold computation runs through a gate first: while any
probable-duplicate, supersedes, conflict, blocked, excluded-lot, or
incomplete-lot item touching the year's documents is unresolved, gold
REFUSES with structured reason codes (extends the R3 guard) -- never a
silent omission, never a silent pass.

Blind-orchestrator contract: every output of this module is metadata
only -- reason codes, counts, doc/group/conflict ids, digests. No
field values, no names, no amounts. The recursive PII sweep in
tests/test_medallion_w4.py covers gate_check, gated_carryforward, and
blind_audit outputs.

Conventions this module defines (W1 owns mstore.py, W3 owns
duplicates.py; flagged to the coordinator):

- Store access: gold.py works against the contract-§4 MedallionStore
  (taxprep/mstore.py). It reaches SQLite through ``_connection(store)``,
  which accepts the connection on ``store._conn`` / ``store.conn`` /
  ``store._db`` / ``store.db`` or a ``store.medallion_connection()``
  method. Writes go through ``store.txn()`` when present, else a local
  commit/rollback. If the medallion tables are absent (pre-migration
  store), the medallion-specific checks are skipped and only the G2
  wire-through runs; ``gold["medallion"]`` in the output envelope
  records which gate ran. Reads bypass the store's ``_op_lock``:
  single-threaded use (CLI, tests, workstation checks) is the
  documented assumption.
- Corroboration agreement: an open dup_group of class 'corroboration'
  blocks only when a member DISAGREES. Disagreement is recorded on
  ``dup_member.role``: 'disagree' (or 'DISAGREEMENT') blocks; 'agree'
  (the default, and the legacy candidate|reference roles) does not. An
  open corroboration group whose members all agree is NOT a blocker.
- Conflict year-scoping: an open conflict touches a year when one of
  its options' evidence_ref resolves (artifact_id -> doc_id, or a
  direct doc_id) to a silver_doc of that year. A conflict whose
  evidence_refs resolve to nothing is fail-closed: it blocks every
  year, with detail 'scope_unresolved'.
- G2 wire-through mapping (carryforward.carryforward_blockers ->
  gold reason codes):
      blocked                                   -> blocked_document
      zero_lots | lot_term_unknown |
        lot_missing_amounts                     -> incomplete_lot,
                                                   unless the doc carries
                                                   a medallion exclusion
                                                   (decision_log
                                                   kind='exclude') ->
                                                   excluded_lot
      unknown_form | multi_form | orphaned |
        missing_year                            -> incomplete_lot (the
                                                   doc's gold contribution
                                                   cannot be completed;
                                                   the original g2 reason
                                                   is preserved in detail)
  Additionally, a 1099-B of the year that IS validated but carries a
  medallion-native exclusion decision is an ``excluded_lot`` blocker:
  the operator excluded it, but carryforward.from_store cannot honor
  decision-log exclusions, so gold refuses rather than mis-sum. This
  is fail-closed pending exclusion-aware sums (flagged follow-up).
- The gate is per-year. Document-level G2 entries whose doc cannot be
  resolved to the gated year are excluded; docs with tax_year NULL are
  included (fail-closed). Legacy store-wide R3 behavior is preserved
  by from_store's own guard, which still raises ValueError post-gate;
  cmd_carryforward reports that loudly too.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import carryforward

# -- reason-code vocabulary (binding for W4 outputs) -------------------

UNRESOLVED_DUPLICATE = "unresolved_duplicate"
UNRESOLVED_SUPERSEDES = "unresolved_supersedes"
UNRESOLVED_CONFLICT = "unresolved_conflict"
BLOCKED_DOCUMENT = "blocked_document"
EXCLUDED_LOT = "excluded_lot"
INCOMPLETE_LOT = "incomplete_lot"
# R13 (Arc C, W1): an in-scope doc whose lifecycle state is neither
# validated nor excluded.
LIFECYCLE_NOT_READY = "lifecycle_not_ready"

GOLD_REASON_CODES = (
    UNRESOLVED_DUPLICATE,
    UNRESOLVED_SUPERSEDES,
    UNRESOLVED_CONFLICT,
    BLOCKED_DOCUMENT,
    EXCLUDED_LOT,
    INCOMPLETE_LOT,
    LIFECYCLE_NOT_READY,
)

# R13: lifecycle states that let gold run. Everything else --
# discovered, selected, unselected, transcribed, needs_review,
# validated-by-nobody, BLOCKED, errored, rereview, ORPHANED,
# MULTI_FORM -- refuses with lifecycle_not_ready. Relevance is
# orthogonal and never exempts: an irrelevant doc still needs
# validated or excluded.
_GOLD_READY_STATES = frozenset({"validated", "excluded"})

# carryforward_blockers reason codes that are lot-integrity (G2) failures.
_G2_LOT_CODES = frozenset({"zero_lots", "lot_term_unknown",
                           "lot_missing_amounts"})
# carryforward_blockers document-level codes.
_G2_DOC_CODES = frozenset({"unknown_form", "multi_form", "orphaned",
                           "missing_year"})

# dup_group classes that refuse as duplicates vs supersedes.
_DUP_CLASSES = frozenset({"L2", "L3"})

# dup_member.role values that record corroboration disagreement.
_DISAGREE_ROLES = frozenset({"disagree", "DISAGREEMENT"})


class GoldRefused(Exception):
    """Raised when the gold gate finds unresolved blockers.

    ``reason_codes`` is a list of ``{"code": <vocabulary code>,
    "detail": <metadata-only detail string>, ...}`` sorted
    deterministically by (code, group_id, conflict_id, doc_id, detail).
    """

    def __init__(self, reason_codes: list[dict[str, Any]]) -> None:
        self.reason_codes = list(reason_codes)
        summary = "; ".join(
            f"[{r['code']}] {r.get('detail', '')}" for r in self.reason_codes)
        super().__init__(
            f"gold refused: {len(self.reason_codes)} blocker(s): {summary}")


# -- store access ------------------------------------------------------

def _connection(store: Any) -> Any | None:
    """The store's SQLite connection, or None on a legacy store."""
    for attr in ("_conn", "conn", "_db", "db"):
        c = getattr(store, attr, None)
        if c is not None:
            return c
    meth = getattr(store, "medallion_connection", None)
    if callable(meth):
        return meth()
    return None


def _has_medallion(store: Any) -> bool:
    conn = _connection(store)
    if conn is None:
        return False
    tables = {r[0] for r in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"silver_doc", "dup_group", "conflict", "decision_log",
            "gold_run"} <= tables


@contextlib.contextmanager
def _txn(store: Any) -> Any:
    txn = getattr(store, "txn", None)
    if txn is not None:
        with txn():
            yield
        return
    conn = _connection(store)
    if conn is None:
        raise TypeError("gold.py needs a medallion store with a txn() "
                        "or an exposed SQLite connection")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# -- canonical JSON / digests ------------------------------------------

def _jsonable(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _canonical(obj: Any) -> str:
    return json.dumps(_jsonable(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- membership resolution helpers -------------------------------------

def _doc_years(conn: Any) -> dict[str, Any]:
    return {r[0]: r[1] for r in
            conn.execute("SELECT doc_id, tax_year FROM silver_doc")}


def _group_member_keys(conn: Any, group_id: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT member_key FROM dup_member WHERE group_id = ?",
        (group_id,))]


def _ruled_out_doc_ids(conn: Any) -> set[str]:
    """Doc ids excluded from gold by disposed duplicate/supersedes rulings.

    Reads the latest ruling per group from the append-only decision log:
    - duplicate_ruling keep_one|merge with primary P -> every member doc
      except P's docs is out;
    - supersedes_ruling with authoritative A -> every member doc except
      A's docs is out;
    - distinct / corroborates -> nothing out (all members count).
    Member keys (bronze hash | doc id | artifact id) resolve via
    _member_doc_ids. Deterministic.
    """
    out: set[str] = set()
    rows = conn.execute(
        "SELECT group_id, kind, payload_json FROM decision_log "
        "WHERE kind IN ('duplicate_ruling', 'supersedes_ruling') "
        "ORDER BY seq DESC").fetchall()
    seen: set[str] = set()
    for group_id, kind, payload_json in rows:
        if group_id in seen:
            continue
        seen.add(group_id)
        try:
            payload = json.loads(payload_json or "{}")
        except ValueError:
            continue
        members = _group_member_keys(conn, group_id)
        if kind == "supersedes_ruling":
            primary = payload.get("authoritative")
            if primary:
                primary_docs = _member_doc_ids(conn, [primary])
                out.update(_member_doc_ids(conn, members) - primary_docs)
        elif payload.get("ruling") in ("keep_one", "merge"):
            primary = payload.get("primary")
            if primary:
                primary_docs = _member_doc_ids(conn, [primary])
                out.update(_member_doc_ids(conn, members) - primary_docs)
        # distinct / corroborates: every member counts; nothing ruled out.
    return out


def _member_doc_ids(conn: Any, member_keys: list[str]) -> set[str]:
    """Resolve dup_member keys (doc_id | bronze hash | artifact id) to doc_ids."""
    doc_ids = {r[0] for r in conn.execute("SELECT doc_id FROM silver_doc")}
    bronze_to_docs: dict[str, set[str]] = {}
    for doc_id, bhash in conn.execute(
            "SELECT doc_id, bronze_hash FROM silver_doc"):
        bronze_to_docs.setdefault(bhash, set()).add(doc_id)
    artifact_to_doc = {r[0]: r[1] for r in
                       conn.execute("SELECT artifact_id, doc_id "
                                    "FROM silver_artifact")}
    out: set[str] = set()
    for key in member_keys:
        if key in doc_ids:
            out.add(key)
        out.update(bronze_to_docs.get(key, ()))
        if key in artifact_to_doc:
            out.add(artifact_to_doc[key])
    return out


def _group_docs_touching_year(conn: Any, group_id: str,
                              doc_years: dict[str, Any],
                              year: int) -> list[str]:
    keys = _group_member_keys(conn, group_id)
    return sorted(d for d in _member_doc_ids(conn, keys)
                  if doc_years.get(d) == year)


def _conflict_docs_touching_year(conn: Any, conflict_id: str,
                                 doc_years: dict[str, Any],
                                 year: int) -> tuple[list[str], bool]:
    """(year doc_ids, scope_resolved). Unresolvable scope is fail-closed."""
    refs = [r[0] for r in conn.execute(
        "SELECT evidence_ref FROM conflict_option WHERE conflict_id = ? "
        "AND evidence_ref IS NOT NULL", (conflict_id,))]
    artifact_to_doc = {r[0]: r[1] for r in
                       conn.execute("SELECT artifact_id, doc_id "
                                    "FROM silver_artifact")}
    doc_ids = {r[0] for r in conn.execute("SELECT doc_id FROM silver_doc")}
    resolved: set[str] = set()
    for ref in refs:
        if ref in doc_ids:
            resolved.add(ref)
        elif ref in artifact_to_doc:
            resolved.add(artifact_to_doc[ref])
    if refs and not resolved:
        return [], False  # evidence present but unresolvable: fail closed
    return sorted(d for d in resolved if doc_years.get(d) == year), True


def _has_medallion_exclusion(conn: Any, doc_id: str) -> bool:
    """True when decision_log kind='exclude' names the doc or its artifacts."""
    rows = conn.execute(
        "SELECT 1 FROM decision_log WHERE kind = 'exclude' AND "
        "(doc_id = ? OR artifact_id IN (SELECT artifact_id FROM "
        "silver_artifact WHERE doc_id = ?)) LIMIT 1",
        (doc_id, doc_id)).fetchall()
    return bool(rows)


# -- the gate ----------------------------------------------------------

def _dup_group_blockers(conn: Any, year: int) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    doc_years = _doc_years(conn)
    for group_id, class_ in conn.execute(
            "SELECT group_id, class FROM dup_group WHERE status = 'open' "
            "ORDER BY group_id"):
        if class_ in _DUP_CLASSES or class_ == "supersedes":
            docs = _group_docs_touching_year(conn, group_id, doc_years, year)
            if not docs:
                continue
            code = (UNRESOLVED_SUPERSEDES if class_ == "supersedes"
                    else UNRESOLVED_DUPLICATE)
            blockers.append({
                "code": code,
                "group_id": group_id,
                "detail": (f"open {class_} group with {len(docs)} "
                           f"unresolved doc(s) for {year}"),
                "doc_ids": docs,
                "n_docs": len(docs),
            })
        elif class_ == "corroboration":
            # Open corroboration blocks only on member DISAGREEMENT; a
            # group whose members all agree is not a blocker.
            roles = [r[0] for r in conn.execute(
                "SELECT role FROM dup_member WHERE group_id = ?",
                (group_id,))]
            disagreeing = sum(1 for r in roles if r in _DISAGREE_ROLES)
            if not disagreeing:
                continue
            keys = [r[0] for r in conn.execute(
                "SELECT member_key FROM dup_member WHERE group_id = ?",
                (group_id,))]
            docs = sorted(d for d in _member_doc_ids(conn, keys)
                          if doc_years.get(d) == year)
            if not docs:
                continue
            blockers.append({
                "code": UNRESOLVED_CONFLICT,
                "group_id": group_id,
                "detail": (f"open corroboration group with "
                           f"{disagreeing} disagreeing member(s) for {year}"),
                "doc_ids": docs,
                "n_disagreeing": disagreeing,
            })
    return blockers


def _conflict_blockers(conn: Any, year: int) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    doc_years = _doc_years(conn)
    for conflict_id, class_, field in conn.execute(
            "SELECT conflict_id, class, field FROM conflict "
            "WHERE status = 'open' ORDER BY conflict_id"):
        docs, scope_ok = _conflict_docs_touching_year(conn, conflict_id,
                                                      doc_years, year)
        if not scope_ok:
            blockers.append({
                "code": UNRESOLVED_CONFLICT,
                "conflict_id": conflict_id,
                "detail": ("open conflict with unresolvable evidence scope: "
                           "fail-closed, blocks every year"),
                "doc_ids": [],
                "n_options": _n_options(conn, conflict_id),
            })
        elif docs:
            blockers.append({
                "code": UNRESOLVED_CONFLICT,
                "conflict_id": conflict_id,
                "detail": (f"open {class_} conflict touching {len(docs)} "
                           f"doc(s) for {year}"),
                "doc_ids": docs,
                "n_options": _n_options(conn, conflict_id),
            })
    return blockers


def _n_options(conn: Any, conflict_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM conflict_option WHERE conflict_id = ?",
        (conflict_id,)).fetchone()[0]


def _blocked_doc_blockers(conn: Any, year: int) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for doc_id, reason in conn.execute(
            "SELECT doc_id, status_reason FROM silver_doc "
            "WHERE status = 'BLOCKED' AND tax_year = ? ORDER BY doc_id",
            (year,)):
        blockers.append({
            "code": BLOCKED_DOCUMENT,
            "doc_id": doc_id,
            "detail": f"silver_doc status BLOCKED for {year}"
                      + (f" ({reason})" if reason else ""),
        })
    return blockers


def _lifecycle_gate_blockers(store: Any, year: int,
                             medallion: bool) -> list[dict[str, Any]]:
    """R13: gold runs only when every in-scope doc is validated/excluded.

    In-scope: docs with tax_year == year, plus tax_year NULL
    (fail-closed, mirroring the G2 year scoping). Exempt: docs ruled
    out by disposed duplicate/supersedes rulings, and docs the Operator
    excluded (lifecycle status "excluded", the exclusions file, or a
    medallion doc-level exclude decision). Relevance never exempts.
    Metadata only -- doc ids, statuses, counts.
    """
    from . import exclusions as _excl

    conn = _connection(store) if medallion else None
    ruled_out: set[str] = set()
    excluded: set[str] = set()
    rows: list[tuple[str, Any, str]] = []  # (doc_id, tax_year, status)
    if medallion and conn is not None:
        ruled_out = _ruled_out_doc_ids(conn)
        for doc_id, tax_year, status in conn.execute(
                "SELECT doc_id, tax_year, status FROM silver_doc "
                "ORDER BY doc_id"):
            rows.append((doc_id, tax_year, status))
    else:
        try:
            for d in store.list():
                rows.append((d.doc_id, getattr(d, "tax_year", None),
                             getattr(d, "status", None)))
        except Exception:
            return []
    data_dir = getattr(store, "data_dir", None)
    if data_dir is not None:
        try:
            excluded = {e["doc_id"]
                        for e in _excl.list_exclusions(data_dir)}
        except Exception:
            excluded = set()
    excluded |= carryforward._medallion_doc_exclusions(store)
    blockers: list[dict[str, Any]] = []
    for doc_id, tax_year, status in rows:
        if tax_year is not None and tax_year != year:
            continue  # another year's doc: out of scope for this gate
        if doc_id in ruled_out or doc_id in excluded:
            continue
        if status in _GOLD_READY_STATES:
            continue
        blockers.append({
            "code": LIFECYCLE_NOT_READY,
            "doc_id": doc_id,
            "status": status,
            "detail": f"lifecycle state {status!r} is not "
                      f"validated/excluded for {year}",
        })
    return blockers


def _g2_blockers(store: Any, year: int, medallion: bool) -> list[dict[str, Any]]:
    """Wire carryforward.carryforward_blockers through the gold vocabulary.

    Entries are scoped to the gated year (docs with tax_year NULL are
    included, fail-closed); document-level entries for other years are
    out of scope for this year's gate.
    """
    entries = carryforward.carryforward_blockers(store,
                                                 chained_years=[year])
    conn = _connection(store) if medallion else None
    ruled_out: set[str] = set()
    doc_years: dict[str, Any] = {}
    if medallion and conn is not None:
        doc_years = _doc_years(conn)
        ruled_out = _ruled_out_doc_ids(conn)
    else:
        try:
            for d in store.list():
                doc_years[d.doc_id] = getattr(d, "tax_year", None)
        except Exception:
            doc_years = {}
    blockers: list[dict[str, Any]] = []
    seen_blocked: set[str] = set()
    for e in entries:
        doc_id = e["doc_id"]
        if doc_id in ruled_out:
            continue  # disposed duplicate/supersedes loser: not gold input
        dy = doc_years.get(doc_id, None)
        if dy is not None and dy != year:
            continue  # another year's doc: out of scope for this gate
        rc = e["reason_code"]
        if rc == carryforward.REASON_BLOCKED:
            # Deduped against the direct silver_doc BLOCKED check below.
            seen_blocked.add(doc_id)
            continue
        if rc in _G2_LOT_CODES:
            # Doc-level exclusions (file-based or decision-log) are already
            # skipped by carryforward_blockers; a surviving exclusion here
            # is artifact-level, which sums cannot honor yet -> fail-closed.
            excluded = (medallion and conn is not None
                        and _has_medallion_exclusion(conn, doc_id))
            code = EXCLUDED_LOT if excluded else INCOMPLETE_LOT
            blockers.append({
                "code": code,
                "doc_id": doc_id,
                "detail": f"G2 lot-integrity blocker ({rc}) for {year}",
                "g2_reason": rc,
            })
        elif rc in _G2_DOC_CODES:
            blockers.append({
                "code": INCOMPLETE_LOT,
                "doc_id": doc_id,
                "detail": f"G2 document-level blocker ({rc}): the doc's "
                          f"gold contribution cannot be completed for {year}",
                "g2_reason": rc,
            })
        # Any other carryforward reason code is a loud unknown: refuse
        # rather than silently pass it.
        else:
            blockers.append({
                "code": INCOMPLETE_LOT,
                "doc_id": doc_id,
                "detail": f"unmapped carryforward blocker ({rc}) for {year}: "
                          f"fail-closed",
                "g2_reason": rc,
            })
    if medallion and conn is not None:
        # An ARTIFACT-level decision-log exclusion (e.g. one lot) cannot
        # be honored by the sum path yet: refuse loudly instead of
        # mis-summing. Doc-level exclusions are honored by
        # carryforward (skipped in guard and sums), so they never block.
        for (doc_id,) in conn.execute(
                "SELECT doc_id FROM silver_doc WHERE tax_year = ? AND "
                "form_type = '1099-B' AND status = 'validated' "
                "ORDER BY doc_id", (year,)):
            rows = conn.execute(
                "SELECT 1 FROM decision_log WHERE kind = 'exclude' AND "
                "artifact_id IN (SELECT artifact_id FROM silver_artifact "
                "WHERE doc_id = ?) LIMIT 1", (doc_id,)).fetchall()
            if rows:
                blockers.append({
                    "code": EXCLUDED_LOT,
                    "doc_id": doc_id,
                    "detail": ("artifact-level operator exclusion in "
                               "decision log; exclusion not applied to the "
                               "sum path -- resolve or rescind before gold"),
                })
        for doc_id in seen_blocked:
            # carryforward saw BLOCKED docs the direct check may have
            # missed (e.g. tax_year NULL): report once.
            rows = conn.execute(
                "SELECT 1 FROM silver_doc WHERE doc_id = ? AND "
                "status = 'BLOCKED' AND tax_year = ?",
                (doc_id, year)).fetchall()
            if not rows:
                blockers.append({
                    "code": BLOCKED_DOCUMENT,
                    "doc_id": doc_id,
                    "detail": "carryforward guard reports BLOCKED doc",
                })
    return blockers


def gate_check(store: Any, year: int) -> list[dict[str, Any]]:
    """Return the gold gate blockers for ``year`` (metadata only).

    Empty list = gate passes. Each blocker is
    ``{"code": <vocabulary>, "detail": <metadata-only string>, ...}``
    with doc_id / group_id / conflict_id and counts as applicable --
    never field values, names, or amounts.
    """
    medallion = _has_medallion(store)
    blockers: list[dict[str, Any]] = []
    if medallion:
        conn = _connection(store)
        blockers.extend(_dup_group_blockers(conn, year))
        blockers.extend(_conflict_blockers(conn, year))
        blockers.extend(_blocked_doc_blockers(conn, year))
    blockers.extend(_lifecycle_gate_blockers(store, year, medallion))
    blockers.extend(_g2_blockers(store, year, medallion))
    # Dedupe on (code, primary id); deterministic order.
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for b in blockers:
        key = (b["code"], b.get("group_id", ""), b.get("conflict_id", ""),
               b.get("doc_id", ""), b.get("detail", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    unique.sort(key=lambda b: (b["code"], b.get("group_id", ""),
                               b.get("conflict_id", ""), b.get("doc_id", ""),
                               b.get("detail", "")))
    return unique


# -- input digest (I8 pure-function record) -----------------------------

def input_digest_for(store: Any, year: int,
                     params: dict[str, Any] | None = None) -> str:
    """sha256 over canonical JSON of (validated silver, decisions, params).

    Validated silver_doc rows for the year: doc_id, form_type, tax_year,
    fields_json, validated_at. Deduped by bronze_hash (L1-merged aliases
    count once -- structural, belt-and-braces). Relevant decision_log
    rows: seq, kind, doc_id, artifact_id, payload for decisions touching
    any silver_doc of the year. Deterministic: identical inputs ->
    identical digest.
    """
    if not _has_medallion(store):
        raise TypeError("input_digest_for requires a medallion store")
    params = dict(params or {})
    conn = _connection(store)
    ruled_out = _ruled_out_doc_ids(conn)
    rows = conn.execute(
        "SELECT doc_id, bronze_hash, form_type, tax_year, fields_json, "
        "validated_at FROM silver_doc WHERE tax_year = ? AND "
        "status = 'validated' ORDER BY bronze_hash, doc_id",
        (year,)).fetchall()
    seen_hashes: set[str] = set()
    silver: list[dict[str, Any]] = []
    for doc_id, bronze_hash, form_type, tax_year, fields_json, validated_at \
            in rows:
        if doc_id in ruled_out:
            continue  # disposed duplicate/supersedes loser: not gold input
        if bronze_hash in seen_hashes:
            continue  # L1-merged alias: count once
        seen_hashes.add(bronze_hash)
        silver.append({
            "doc_id": doc_id,
            "form_type": form_type,
            "tax_year": tax_year,
            "fields_json": fields_json,
            "validated_at": validated_at,
        })
    doc_ids_year = {r[0] for r in conn.execute(
        "SELECT doc_id FROM silver_doc WHERE tax_year = ?", (year,))}
    artifact_to_doc = {r[0]: r[1] for r in conn.execute(
        "SELECT artifact_id, doc_id FROM silver_artifact")}
    group_docs: dict[str, set[str]] = {}
    for group_id in {r[0] for r in
                     conn.execute("SELECT group_id FROM dup_group")}:
        keys = [r[0] for r in conn.execute(
            "SELECT member_key FROM dup_member WHERE group_id = ?",
            (group_id,))]
        group_docs[group_id] = _member_doc_ids(conn, keys)
    decisions: list[dict[str, Any]] = []
    for seq, kind, artifact_id, doc_id, group_id, payload in conn.execute(
            "SELECT seq, kind, artifact_id, doc_id, group_id, payload_json "
            "FROM decision_log ORDER BY seq"):
        touches = (
            (doc_id is not None and doc_id in doc_ids_year)
            or (artifact_id is not None
                and artifact_to_doc.get(artifact_id) in doc_ids_year)
            or (group_id is not None
                and bool(group_docs.get(group_id, set()) & doc_ids_year))
        )
        if touches:
            decisions.append({
                "seq": seq,
                "kind": kind,
                "doc_id": doc_id,
                "artifact_id": artifact_id,
                "payload": payload,
            })
    digest_input = {
        "v": 1,
        "year": year,
        "silver": silver,
        "decisions": decisions,
        "params": params,
    }
    return _sha256_hex(_canonical(digest_input))


# -- gated computation -------------------------------------------------

def gated_carryforward(store: Any, year: int,
                       params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the carryforward for ``year`` through the gold gate.

    Raises GoldRefused (with structured reason_codes) on any blocker.
    Otherwise computes via the existing carryforward.from_store (the math
    is not reimplemented), attaches the ``gold`` envelope
    {input_digest, output_digest, computed_at, run_id?, medallion}, and
    persists a gold_run row (kind=carryforward) on medallion stores.
    Recomputing with identical inputs yields identical digests.
    """
    params = dict(params or {})
    blockers = gate_check(store, year)
    if blockers:
        raise GoldRefused(blockers)
    medallion = _has_medallion(store)
    ruled_out: set[str] = set()
    if medallion:
        ruled_out = _ruled_out_doc_ids(_connection(store))
    result = carryforward.from_store(store, year, exclude_doc_ids=ruled_out)
    # Digests run over the canonical JSON encoding; the returned result
    # keeps the original Python values (Decimals intact) so existing
    # consumers (compute_chain, CLI formatting) are undisturbed.
    body_json = {k: _jsonable(v) for k, v in result.items()}
    output_digest = _sha256_hex(_canonical(body_json))
    computed_at = datetime.now(timezone.utc).isoformat()
    gold: dict[str, Any] = {
        "computed_at": computed_at,
        "output_digest": output_digest,
        "medallion": medallion,
        "input_digest": (input_digest_for(store, year, params)
                         if medallion else None),
    }
    if medallion:
        conn = _connection(store)
        run_id = _sha256_hex(
            f"carryforward:{computed_at}:{gold['input_digest']}")[:32]
        with _txn(store):
            conn.execute(
                "INSERT INTO gold_run (run_id, ts, kind, params_json, "
                "input_digest, output_json, output_digest) VALUES "
                "(?, ?, 'carryforward', ?, ?, ?, ?)",
                (run_id, computed_at, _canonical(params),
                 gold["input_digest"], _canonical(body_json), output_digest))
        gold["run_id"] = run_id
    out = dict(result)
    out["gold"] = gold
    return out


# -- blind audit (workstation invariants, metadata only) ----------------

def _to_decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        v = value.strip().replace(",", "").replace("$", "")
        if not v:
            return None
        try:
            return Decimal(v)
        except Exception:
            return None
    return None  # floats and anything else: never guessed


def _audit_bronze_accounted(conn: Any, year: int | None) -> dict[str, Any]:
    """Every bronze object is accounted for, store-wide by nature.

    Bronze rows are not year-attributed unless they have silver docs, so
    this invariant always evaluates every bronze row: each must have >=1
    silver doc or a blocked_reason (an exclusion decision keeps the
    silver docs it excludes, so it is subsumed by the silver-doc arm).
    The ``year`` parameter is accepted for signature symmetry and
    ignored.
    """
    _ = year
    bronze = {r[0]: r[1] for r in
              conn.execute("SELECT hash, blocked_reason FROM bronze")}
    silver_by_bronze: dict[str, list[str]] = {}
    for doc_id, bhash in conn.execute(
            "SELECT doc_id, bronze_hash FROM silver_doc"):
        silver_by_bronze.setdefault(bhash, []).append(doc_id)
    scope = set(bronze)
    unaccounted: list[str] = []
    n_with_silver = 0
    n_blocked = 0
    for h in sorted(scope):
        docs = silver_by_bronze.get(h, [])
        if docs:
            n_with_silver += 1
        elif bronze[h]:
            n_blocked += 1
        else:
            unaccounted.append(h)
    return {
        "status": "pass" if not unaccounted else "fail",
        "n_bronze": len(scope),
        "n_with_silver": n_with_silver,
        "n_blocked": n_blocked,
        "n_unaccounted": len(unaccounted),
        "unaccounted_hashes": unaccounted,
    }


def _audit_files_accounted(conn: Any) -> dict[str, Any]:
    bronze_hashes = {r[0] for r in conn.execute("SELECT hash FROM bronze")}
    bytes_refs = {r[0] for r in
                  conn.execute("SELECT hash FROM bronze_bytes_ref")}
    aliases = [(r[0], r[1]) for r in
               conn.execute("SELECT hash, path FROM bronze_alias")]
    missing_bytes_ref = sorted(bronze_hashes - bytes_refs)
    dangling_aliases = sorted(
        f"{h}::{p}" for h, p in aliases if h not in bronze_hashes)
    # Informational only: on-disk presence is W2's sync/orphan domain.
    import os
    n_missing_on_disk = sum(1 for _, p in aliases if not os.path.exists(p))
    ok = not missing_bytes_ref and not dangling_aliases
    return {
        "status": "pass" if ok else "fail",
        "n_bronze": len(bronze_hashes),
        "n_bytes_refs": len(bytes_refs),
        "n_aliases": len(aliases),
        "n_missing_bytes_ref": len(missing_bytes_ref),
        "missing_bytes_ref": missing_bytes_ref,
        "n_dangling_aliases": len(dangling_aliases),
        "dangling_aliases": dangling_aliases,
        "n_paths_missing_on_disk": n_missing_on_disk,
    }


def _fields_lots(fields: dict[str, Any]) -> list[dict[str, Any]]:
    lots = fields.get("lots")
    v = lots.get("value") if isinstance(lots, dict) else lots
    return [l for l in v if isinstance(l, dict)] if isinstance(v, list) else []


def _fields_totals(fields: dict[str, Any]) -> dict[str, Any]:
    totals = fields.get("summary_totals")
    v = totals.get("value") if isinstance(totals, dict) else totals
    return v if isinstance(v, dict) else {}


def _audit_lot_sums(conn: Any, year: int | None) -> dict[str, Any]:
    """Per 1099-B doc: sum(lots) vs statement totals within 1 cent.

    A doc whose statement shows no comparable totals is NOT EVALUATED
    (V1: a vacuous check is not a pass). Metadata only.
    """
    sql = ("SELECT doc_id, fields_json FROM silver_doc "
           "WHERE form_type = '1099-B'")
    args: tuple = ()
    if year is not None:
        sql += " AND tax_year = ?"
        args = (year,)
    sql += " ORDER BY doc_id"
    mismatched: list[str] = []
    not_evaluated: list[str] = []
    n_docs = 0
    cent = Decimal("0.01")
    for doc_id, fields_json in conn.execute(sql, args):
        n_docs += 1
        try:
            fields = json.loads(fields_json or "{}")
        except Exception:
            fields = {}
        lots = _fields_lots(fields)
        totals = _fields_totals(fields)
        comparable = 0
        bad = False
        for term in ("short", "long"):
            cat = totals.get(term)
            if not isinstance(cat, dict):
                continue
            for key in ("proceeds_1d", "basis_1e"):
                target = _to_decimal_or_none(cat.get(key))
                if target is None:
                    continue
                s = Decimal("0")
                ok = True
                for lot in lots:
                    if lot.get("term") != term:
                        continue
                    d = _to_decimal_or_none(lot.get(key))
                    if d is None:
                        ok = False
                        break
                    s += d
                if not ok:
                    continue  # cannot confirm: not comparable, never guessed
                comparable += 1
                if abs(s - target) > cent:
                    bad = True
        if comparable == 0:
            not_evaluated.append(doc_id)
        elif bad:
            mismatched.append(doc_id)
    n_evaluated = n_docs - len(not_evaluated)
    if mismatched:
        status = "fail"
    elif n_evaluated == 0:
        status = "not_evaluated"
    else:
        status = "pass"
    return {
        "status": status,
        "n_docs": n_docs,
        "n_evaluated": n_evaluated,
        "n_reconciled": n_evaluated - len(mismatched),
        "n_mismatched": len(mismatched),
        "mismatched_ids": mismatched,
        "n_not_evaluated": len(not_evaluated),
        "not_evaluated_ids": not_evaluated,
    }


def _audit_gold_inputs_validated(conn: Any, year: int | None) -> dict[str, Any]:
    """Every doc feeding gold (non-excluded 1099-B in scope) is validated."""
    ruled_out = _ruled_out_doc_ids(conn)
    sql = ("SELECT doc_id, status FROM silver_doc "
           "WHERE form_type = '1099-B'")
    args: tuple = ()
    if year is not None:
        sql += " AND tax_year = ?"
        args = (year,)
    sql += " ORDER BY doc_id"
    feeding: list[str] = []
    unvalidated: list[str] = []
    for doc_id, status in conn.execute(sql, args):
        if _has_medallion_exclusion(conn, doc_id):
            continue  # operator-excluded: does not feed gold
        if doc_id in ruled_out:
            continue  # disposed duplicate/supersedes loser: not gold input
        feeding.append(doc_id)
        if status != "validated":
            unvalidated.append(doc_id)
    if not feeding:
        status = "not_evaluated"
    elif unvalidated:
        status = "fail"
    else:
        status = "pass"
    return {
        "status": status,
        "n_feeding": len(feeding),
        "n_validated": len(feeding) - len(unvalidated),
        "n_unvalidated": len(unvalidated),
        "unvalidated_ids": unvalidated,
    }


def _audit_zero_unresolved(conn: Any, year: int | None) -> dict[str, Any]:
    """No open dup groups / conflicts (corroboration: only on disagreement)."""
    doc_years = _doc_years(conn)
    open_groups: list[str] = []
    for group_id, class_ in conn.execute(
            "SELECT group_id, class FROM dup_group WHERE status = 'open' "
            "ORDER BY group_id"):
        if class_ in _DUP_CLASSES or class_ == "supersedes":
            keys = [r[0] for r in conn.execute(
                "SELECT member_key FROM dup_member WHERE group_id = ?",
                (group_id,))]
            docs = _member_doc_ids(conn, keys)
            if year is None or any(doc_years.get(d) == year for d in docs):
                open_groups.append(group_id)
        elif class_ == "corroboration":
            roles = [r[0] for r in conn.execute(
                "SELECT role FROM dup_member WHERE group_id = ?",
                (group_id,))]
            if not any(r in _DISAGREE_ROLES for r in roles):
                continue  # all agree: not unresolved
            keys = [r[0] for r in conn.execute(
                "SELECT member_key FROM dup_member WHERE group_id = ?",
                (group_id,))]
            docs = _member_doc_ids(conn, keys)
            if year is None or any(doc_years.get(d) == year for d in docs):
                open_groups.append(group_id)
    open_conflicts: list[str] = []
    for (conflict_id,) in conn.execute(
            "SELECT conflict_id FROM conflict WHERE status = 'open' "
            "ORDER BY conflict_id"):
        if year is None:
            open_conflicts.append(conflict_id)
            continue
        docs, scope_ok = _conflict_docs_touching_year(conn, conflict_id,
                                                      doc_years, year)
        if not scope_ok or docs:
            # Unresolvable scope is fail-closed: blocks every year.
            open_conflicts.append(conflict_id)
    ok = not open_groups and not open_conflicts
    return {
        "status": "pass" if ok else "fail",
        "n_open_groups": len(open_groups),
        "open_group_ids": open_groups,
        "n_open_conflicts": len(open_conflicts),
        "open_conflict_ids": open_conflicts,
    }


def blind_audit(store: Any, year: int | None = None) -> dict[str, Any]:
    """The workstation's blind-audit invariants, metadata only.

    With year=None every invariant runs store-wide. With a year,
    lot_sums_reconciled, gold_inputs_validated, and
    zero_unresolved_before_gold scope to that year; bronze_accounted
    and files_accounted are store-wide by nature (bronze objects are
    not year-attributed). Each invariant returns
    {"status": "pass"|"fail"|"not_evaluated", counts...} with ids
    (bronze hashes, doc_ids, group/conflict ids) -- never values.
    """
    if not _has_medallion(store):
        raise TypeError("blind_audit requires a medallion store")
    conn = _connection(store)
    return {
        "bronze_accounted": _audit_bronze_accounted(conn, year),
        "files_accounted": _audit_files_accounted(conn),
        "lot_sums_reconciled": _audit_lot_sums(conn, year),
        "gold_inputs_validated": _audit_gold_inputs_validated(conn, year),
        "zero_unresolved_before_gold": _audit_zero_unresolved(conn, year),
    }
