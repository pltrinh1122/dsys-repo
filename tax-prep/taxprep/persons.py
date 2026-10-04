"""Per-person scoping (R21a).

A document set can span several household members: some in scope, some
out. The Operator assigns each document an owner; the system never
infers it silently.

Concepts:

* Person registry -- ``<data_dir>/persons.json`` maps opaque ids
  ``person-1..n`` to names. Ids are deterministic per store (first-seen
  order) and stable across runs. Names are PII: they live ONLY in this
  local file and NEVER cross the MCP boundary, the CLI ``--meta``
  output, or bus payloads. Every agent-facing surface carries the
  opaque id (plus counts) only.
* Suggestion -- a system-derived owner guess from recipient text in the
  document's fields. It is SHOWN to the Operator and never auto-applied
  (R16a rule: suggestion, never auto-apply). A suggestion is
  "un-disposed" exactly while ``Document.owner_person_id`` is None; the
  Operator's assignment consumes it (logged, with whether the
  suggestion was accepted).
* Scope filter -- documents whose assigned owner is outside the
  Operator's declared scope are routed to the R13 lifecycle
  ``excluded`` state with the machine reason ``"out-of-scope-person"``.
  That reason joins the EXISTING status_reason taxonomy
  (lifecycle.MACHINE_EXCLUDE_REASONS); the document is never deleted.
* Joint / multi-owner items -- raised to the Operator for allocation
  via the R16a conflict pattern (class ``"allocation"``, options are
  opaque person ids). NEVER mechanically split; per-artifact owners
  exist so the Operator can allocate a joint document piece by piece.
* Return assignment -- per document, an Operator decision recording
  which return the person's documents feed: ``joint`` (the joint
  return), ``own`` (the person's own return), or ``election``. Stored
  as a decision_log ``return_assignment`` row (the existing
  Operator-decision mechanism), opaque ids only.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import duplicates, lifecycle, silver

PERSONS_FILENAME = "persons.json"

# R21a: joint/multi-owner allocation conflict class (duplicates.py).
ALLOCATION_CLASS = "allocation"

# Return-assignment vocabulary (Operator decision).
RETURN_ASSIGNMENTS = frozenset({"joint", "own", "election"})

# Machine exclusion reason for the scope filter (lifecycle taxonomy).
OUT_OF_SCOPE_REASON = "out-of-scope-person"

# Field keys that may carry RECIPIENT identity (the document's owner
# candidate). Payer-side keys (payer/employer/broker names) are
# deliberately excluded: suggesting an owner from the PAYER would
# attribute the document to the wrong person. The current extractors do
# not emit recipient names (see duplicates._RECIPIENT_KEYS); the hooks
# below fire when they do.
_RECIPIENT_KEY_RES = (
    re.compile(r"recipient", re.I),
    re.compile(r"employee(?!_ein)", re.I),
    re.compile(r"taxpayer", re.I),
    re.compile(r"borrower", re.I),
    re.compile(r"\bpayee\b", re.I),
)
_PAYER_KEY_RES = (
    re.compile(r"payer", re.I),
    re.compile(r"employer", re.I),
    re.compile(r"broker", re.I),
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(data_dir) -> Path:
    return Path(data_dir) / PERSONS_FILENAME


def _load(data_dir) -> dict:
    """Read the registry; {} when no file exists.

    Raises ValueError (loud, fail closed) on corrupt JSON -- a damaged
    registry must never be mistaken for "no persons". Insertion order is
    first-seen order (person-1, person-2, ...).
    """
    path = _path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{PERSONS_FILENAME} is unreadable: {e}")
    if not isinstance(raw, dict):
        raise ValueError(f"{PERSONS_FILENAME} is corrupt: not a JSON object")
    return raw


def _save(data_dir, entries: dict) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def _next_person_id(entries: dict) -> str:
    taken = set()
    for pid in entries:
        m = re.fullmatch(r"person-(\d+)", pid)
        if m:
            taken.add(int(m.group(1)))
    n = (max(taken) + 1) if taken else 1
    while f"person-{n}" in entries:
        n += 1
    return f"person-{n}"


def register_person(data_dir, name: str) -> str:
    """Register a person by name; returns the opaque person id.

    Ids are deterministic per store: first-seen order, ``person-1``,
    ``person-2``, ... -- stable across runs. Registering the same name
    twice is idempotent (returns the existing id). Names are PII and
    stay in this local file only.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name is required: cannot register an unnamed person")
    name = " ".join(name.split())
    entries = _load(data_dir)
    for pid, rec in entries.items():
        if rec.get("name") == name:
            return pid
    pid = _next_person_id(entries)
    entries[pid] = {"name": name, "first_seen": _utcnow()}
    _save(data_dir, entries)
    return pid


def person_ids(data_dir) -> list[str]:
    """Opaque person ids in first-seen order (names never included)."""
    return list(_load(data_dir))


def person_name(data_dir, person_id: str) -> str | None:
    """Local-only name lookup (Operator surfaces; never agent-facing)."""
    rec = _load(data_dir).get(person_id)
    return rec.get("name") if isinstance(rec, dict) else None


def _norm(s: object) -> str:
    return " ".join(str(s).split()).casefold()


def _is_recipient_key(code: str) -> bool:
    if any(rx.search(code) for rx in _PAYER_KEY_RES):
        return False
    return any(rx.search(code) for rx in _RECIPIENT_KEY_RES)


def suggest_owner(fields: dict, persons: dict[str, str]
                  ) -> tuple[str, str] | None:
    """Derive an owner suggestion from recipient text (pure, no I/O).

    ``persons`` maps opaque person id -> name. Returns
    ``(person_id, basis)`` for the first-registered person whose name
    appears (whole-word, case-insensitive) in a recipient-identity
    field value, else None. Payer-side fields never participate. This
    is a SUGGESTION only -- callers must show it to the Operator, never
    apply it.
    """
    ordered = sorted(persons, key=lambda p: (
        int(re.fullmatch(r"person-(\d+)", p).group(1))
        if re.fullmatch(r"person-(\d+)", p) else 10**9, p))
    for code, f in (fields or {}).items():
        if not _is_recipient_key(str(code)):
            continue
        val = f.get("value") if isinstance(f, dict) else f
        if val is None or val == "":
            continue
        text = _norm(val)
        for pid in ordered:
            name = _norm(persons[pid])
            if not name:
                continue
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text):
                return pid, f"field_value_match:{code}"
    return None


def suggest_owner_for_doc(store, doc_id: str) -> dict | None:
    """Derive and store an owner suggestion for one document.

    The suggestion is written to the doc's ``owner_suggestion`` fields
    (marked un-disposed: ``owner_person_id`` stays None) for the
    Operator to dispose. Refuses loudly when the doc already has an
    assigned owner (the Operator's decision stands) or when no
    recipient text matches a registered person (returns None, writes
    nothing -- an absent suggestion is honest, not an error).
    """
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    if doc.owner_person_id is not None:
        raise ValueError(
            f"doc {doc_id} already owned by {doc.owner_person_id}: "
            "the Operator's assignment stands; not overwritten by a suggestion")
    persons = {pid: rec["name"] for pid, rec in _load(store.data_dir).items()
               if isinstance(rec, dict) and rec.get("name")}
    hit = suggest_owner(doc.fields, persons)
    if hit is None:
        return None
    pid, basis = hit
    store.set_doc_owner(doc_id, owner_person_id=None,
                        owner_suggestion=pid, owner_suggestion_basis=basis)
    return {"doc_id": doc_id, "owner_suggestion": pid, "basis": basis,
            "disposed": False}


def assign_owner(store, doc_id: str, person_id: str, *,
                 actor: str = "operator") -> dict:
    """Operator assigns a document's owner (the R21a disposition).

    The person must be registered. Any pending suggestion is consumed;
    the decision is logged (kind ``owner_assignment``) with whether the
    suggestion was accepted. Re-assignment is allowed -- the Operator's
    later word wins, and the log keeps the history.
    """
    if actor != "operator":
        raise ValueError(
            f"owner assignment is operator-only, got actor={actor!r}")
    if person_id not in _load(store.data_dir):
        raise ValueError(f"unknown person {person_id!r}: register first")
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    previous = doc.owner_person_id
    accepted = doc.owner_suggestion == person_id
    store.set_doc_owner(doc_id, owner_person_id=person_id,
                        owner_suggestion=None, owner_suggestion_basis=None)
    seq = store.log_decision(
        actor="operator", kind="owner_assignment", doc_id=doc_id,
        payload={"person_id": person_id, "previous": previous,
                 "accepted_suggestion": accepted, "ts": _utcnow()})
    return {"doc_id": doc_id, "owner_person_id": person_id,
            "previous": previous, "accepted_suggestion": accepted,
            "decision_seq": seq}


def assign_artifact_owner(store, artifact_id: str, person_id: str, *,
                          actor: str = "operator") -> dict:
    """Operator allocates one artifact of a joint document to a person.

    Per-artifact owners are how a joint/multi-owner document is
    allocated without ever being mechanically split. Logged as
    ``owner_assignment`` with the artifact_id.
    """
    if actor != "operator":
        raise ValueError(
            f"owner assignment is operator-only, got actor={actor!r}")
    if person_id not in _load(store.data_dir):
        raise ValueError(f"unknown person {person_id!r}: register first")
    store.set_artifact_owner(artifact_id, owner_person_id=person_id,
                             owner_suggestion=None)
    seq = store.log_decision(
        actor="operator", kind="owner_assignment", artifact_id=artifact_id,
        payload={"person_id": person_id, "ts": _utcnow()})
    return {"artifact_id": artifact_id, "owner_person_id": person_id,
            "decision_seq": seq}


def raise_allocation_conflict(store, doc_id: str,
                              candidate_person_ids: list[str]) -> str:
    """Raise a joint/multi-owner document to the Operator for allocation.

    The R16a raising pattern: class ``"allocation"``, field ``"owner"``,
    one option per candidate opaque person id. The doc is NEVER split
    here; the Operator disposes via choose_conflict (doc-level) or
    per-artifact assign_artifact_owner. Re-raising is idempotent.
    """
    if store.get(doc_id) is None:
        raise KeyError(doc_id)
    registered = set(_load(store.data_dir))
    unknown = [p for p in candidate_person_ids if p not in registered]
    if unknown:
        raise ValueError(f"unknown persons {unknown}: register first")
    if not candidate_person_ids:
        raise ValueError("allocation needs at least one candidate person")
    return duplicates.raise_conflict(
        store, cls=ALLOCATION_CLASS, field="owner",
        options=[{"option_key": pid, "value_json": pid,
                  "evidence_ref": doc_id}
                 for pid in sorted(set(candidate_person_ids))])


def apply_scope_filter(store, in_scope: set[str]) -> list[dict]:
    """Exclude out-of-scope-owned documents (Operator's scope decision).

    Every document with an assigned ``owner_person_id`` outside
    ``in_scope`` is routed through the R13 lifecycle ``exclude`` event
    (actor=operator) with the machine reason ``"out-of-scope-person"``
    -- the same exclusion taxonomy as every other exclusion, never a
    parallel mechanism, and the document is never deleted. Unassigned
    documents and already-terminal documents are untouched. Returns the
    applied list [{doc_id, owner_person_id}].
    """
    unknown = set(in_scope) - set(_load(store.data_dir))
    if unknown:
        raise ValueError(f"unknown persons {sorted(unknown)}: register first")
    applied = []
    for doc in store.list():
        pid = doc.owner_person_id
        if pid is None or pid in in_scope:
            continue
        if doc.status in lifecycle.TERMINAL_STATES:
            continue
        res = lifecycle.transition(
            doc, lifecycle.EXCLUDE, actor=lifecycle.OPERATOR,
            event_input=lifecycle.ExcludeInput(reason=OUT_OF_SCOPE_REASON),
            store=store)
        if not res.ok:
            raise RuntimeError(
                f"scope filter refused for {doc.doc_id}: {res.reason_code}")
        if res.noop:
            continue
        bronze_hash = silver.bronze_hash_for_doc(store, doc)
        silver.persist_silver_doc(
            store, doc, silver.derivation_for_doc(store, doc.doc_id),
            bronze_hash)
        applied.append({"doc_id": doc.doc_id, "owner_person_id": pid})
    return sorted(applied, key=lambda r: r["doc_id"])


def record_return_assignment(store, doc_id: str, person_id: str,
                             assignment: str) -> dict:
    """Operator decision: which return this person's documents feed.

    ``assignment`` is one of ``joint`` (the joint return), ``own``
    (the person's own return), ``election``. Recorded in the
    append-only decision log (kind ``return_assignment``) -- the
    existing Operator-decision mechanism, opaque ids only.
    """
    if assignment not in RETURN_ASSIGNMENTS:
        raise ValueError(
            f"assignment must be one of {sorted(RETURN_ASSIGNMENTS)}, "
            f"got {assignment!r}")
    if person_id not in _load(store.data_dir):
        raise ValueError(f"unknown person {person_id!r}: register first")
    if store.get(doc_id) is None:
        raise KeyError(doc_id)
    seq = store.log_decision(
        actor="operator", kind="return_assignment", doc_id=doc_id,
        payload={"person_id": person_id, "assignment": assignment,
                 "ts": _utcnow()})
    return {"doc_id": doc_id, "person_id": person_id,
            "assignment": assignment, "decision_seq": seq}


def return_assignments(store, doc_id: str | None = None) -> list[dict]:
    """Return-assignment decisions, oldest first (metadata only)."""
    return store.decisions_for(doc_id=doc_id, kind="return_assignment")


def scope_payload(store, in_scope: set[str]) -> dict:
    """Agent-safe scope shape: opaque ids + counts only, never names.

    Built for bus payloads / blind-orchestrator consumption; safe to
    serialize because the person registry names never enter it.
    """
    counts: dict[str, int] = {}
    unassigned = 0
    excluded_out = 0
    for doc in store.list():
        pid = doc.owner_person_id
        if pid is None:
            unassigned += 1
        else:
            counts[pid] = counts.get(pid, 0) + 1
            if (doc.status == lifecycle.EXCLUDED
                    and doc.status_reason == OUT_OF_SCOPE_REASON):
                excluded_out += 1
    return {
        "in_scope": sorted(in_scope),
        "doc_counts": {pid: counts.get(pid, 0) for pid in sorted(counts)},
        "unassigned_docs": unassigned,
        "out_of_scope_excluded": excluded_out,
    }
