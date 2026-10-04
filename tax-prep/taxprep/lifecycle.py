"""R13: explicit document-lifecycle state machine (Arc C, W1).

A small, standalone transition table -- deliberately NOT coupled to the
dsys FSM machinery (Operator disposition on DR-CMD-115: tax-prep keeps a
local table; the bus message's suggestion (a) was refused).

The table declares every legal (from-state, event, actor) triple with a
typed, deterministic guard and its candidate targets. ``transition()``
is the ONLY way to change a Document's lifecycle status: a build test
greps the package for direct ``.status =`` writes outside this module
and fails if any exist.

Actor classes: ``"system"`` (ingest, sync, MCP/agent tools) vs
``"operator"`` (localhost review UI, CLI operator commands).
Operator-only events (validate, exclude, fix_form_year, select,
unselect) are refused for actor="system" by the table itself, and
``mcp_server.py`` never imports this module (test-pinned) -- this
extends the "no validate_document MCP tool" rule into the model.

Every fired transition appends one ``kind="lifecycle"`` row to the
medallion decision log (trigger-enforced append-only, Arc B):
``{ts, actor, kind, doc_id, payload={event, from, to, reason_code}}`` --
metadata only, never values. ``replay_lifecycle()`` rebuilds a doc's
current state from its event chain; the log is the source of truth.

Relevance stays an orthogonal dimension: it is never a lifecycle
state and never a transition target; guards may read it as input but
no row in this table changes it.

Mermaid view: ``mermaid()`` generates a stateDiagram-v2 verbatim from
TRANSITION_TABLE; the checked-in rendering is docs/lifecycle.mmd
(regenerate with ``write_mermaid("docs/lifecycle.mmd")`` whenever the
table changes -- a test pins that the file matches the generator).

State vocabulary note: the R1 legacy spellings BLOCKED / ORPHANED /
MULTI_FORM are retained verbatim (existing stores, readers, and tests
depend on them). All new R13 states are lowercase.

Declared table (from | event(actor) | guard | to):

    (none)       scan(system)            always            discovered
    discovered   select(operator)        always            selected
    discovered   select(system)         auto_select       selected
    discovered   unselect(operator)      always            unselected
    unselected   select(operator)        always            selected
    selected     ingest(system)          ingest_route      transcribed |
                                                          needs_review |
                                                          BLOCKED |
                                                          errored |
                                                          MULTI_FORM
    transcribed  ingest(system)          ingest_route      transcribed |
                                                          needs_review |
                                                          BLOCKED | errored
    needs_review ingest(system)          ingest_route      transcribed |
                                                          needs_review |
                                                          BLOCKED | errored
    BLOCKED      ingest(system)          ingest_route      transcribed |
                                                          needs_review |
                                                          BLOCKED | errored
    errored      ingest(system)          ingest_route      transcribed |
                                                          needs_review |
                                                          BLOCKED | errored
    MULTI_FORM   ingest(system)          multiform_still   MULTI_FORM
    validated    re_extract(system)      reextract_agree   validated | rereview
    rereview     re_extract(system)      reextract_agree   validated | rereview
    BLOCKED      fix_form_year(operator) fix_identity      needs_review
    needs_review validate(operator)      validate_guards   validated
    transcribed  validate(operator)      validate_guards   validated
    rereview     validate(operator)      validate_guards   validated
    <non-terminal> exclude(operator)     exclude_reason    excluded
    <any>        source_missing(system)  always            ORPHANED

Terminal states (no outgoing rows except source_missing): excluded,
ORPHANED.

Deviations from the bus sketch (documented, Operator-visible):
  * The sketch's select/unselect rows are operator-only, but batch
    ingest (CLI ``ingest``/``sync``, MCP ``ingest_directory``) has no
    separate selection step. The declared row
    ``discovered --select(system)--> selected`` with the
    ``auto_select`` guard is the standing auto-select policy: every
    scanned source is selected unless the Operator unselects it in the
    console. The operator-only guarantee is unchanged for validate /
    exclude / fix_form_year / explicit select / unselect.
  * The sketch's validate guard ("every field confirmed or edited")
    is narrowed to the ratified review semantics pinned by
    tests/test_review.py: at least one field confirmed, or any edit
    (form/year correction counts as an edit). Whole-doc attestation
    was never the shipped behavior.
  * ``rereview`` is a real state (not just the ``re_review`` flag):
    re-extraction that disagrees with validated values keeps the
    validated values and moves validated -> rereview. The ``re_review``
    flag is still set alongside for readers that key on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .models import Document

# -- vocabulary ---------------------------------------------------------

SYSTEM = "system"
OPERATOR = "operator"
ACTORS = (SYSTEM, OPERATOR)

# States. R1 legacy spellings (BLOCKED/ORPHANED/MULTI_FORM) retained
# verbatim; every new R13 state is lowercase.
DISCOVERED = "discovered"
SELECTED = "selected"
UNSELECTED = "unselected"
TRANSCRIBED = "transcribed"
NEEDS_REVIEW = "needs_review"
VALIDATED = "validated"
REREVIEW = "rereview"
ERRORED = "errored"
EXCLUDED = "excluded"
BLOCKED = "BLOCKED"
ORPHANED = "ORPHANED"
MULTI_FORM = "MULTI_FORM"

STATES = (
    DISCOVERED, SELECTED, UNSELECTED,
    TRANSCRIBED, NEEDS_REVIEW,
    BLOCKED, ERRORED,
    VALIDATED, REREVIEW,
    EXCLUDED, ORPHANED, MULTI_FORM,
)

TERMINAL_STATES = frozenset({EXCLUDED, ORPHANED})

# States whose docs are extracted but not yet validated -- the pre-R13
# ("transcribed", "needs_review") population plus R13 "errored".
# Review-queue / extractable readers use this so errored docs stay
# operator-visible exactly as they were as needs_review.
UNVALIDATED_EXTRACTED = frozenset({TRANSCRIBED, NEEDS_REVIEW, ERRORED})

# Events.
SCAN = "scan"
SELECT = "select"
UNSELECT = "unselect"
INGEST = "ingest"
RE_EXTRACT = "re_extract"
FIX_FORM_YEAR = "fix_form_year"
VALIDATE = "validate"
EXCLUDE = "exclude"
SOURCE_MISSING = "source_missing"

EVENTS = (SCAN, SELECT, UNSELECT, INGEST, RE_EXTRACT, FIX_FORM_YEAR,
          VALIDATE, EXCLUDE, SOURCE_MISSING)

# Operator-only events: refused for actor="system" by construction --
# there is simply no (from, event, "system") row for them (except the
# auto-select policy row for select, which is guarded separately).
OPERATOR_ONLY_EVENTS = frozenset(
    {VALIDATE, EXCLUDE, FIX_FORM_YEAR, SELECT, UNSELECT})

# -- typed event inputs -------------------------------------------------

@dataclass(frozen=True)
class ScanInput:
    """No inputs; the scan event just registers the source."""


@dataclass(frozen=True)
class SelectInput:
    auto: bool = False  # True: standing auto-select policy (system row)


@dataclass(frozen=True)
class IngestInput:
    route: str  # "ok" | "blocked" | "error" | "multiform"
    route_reason: str | None = None  # required for blocked/error
    clean: bool = True  # every KEY box extracted -> transcribed


@dataclass(frozen=True)
class ReextractInput:
    values_differ: bool  # new extraction disagrees w/ validated values
    reason: str = "extraction-disagrees"  # status_reason when disagreeing


@dataclass(frozen=True)
class FixInput:
    form_type: str | None
    tax_year: int | None


@dataclass(frozen=True)
class ValidateInput:
    n_fields: int
    form_known: bool
    year_known: bool
    form_confirmed_or_corrected: bool
    year_confirmed_or_corrected: bool
    field_confirmed_or_edited: bool


@dataclass(frozen=True)
class ExcludeInput:
    reason: str  # required, non-empty; kept in exclusions record, not the log


# -- guards (typed, deterministic, pure) --------------------------------

@dataclass(frozen=True)
class GuardResult:
    ok: bool
    target: str | None = None
    reason_code: str | None = None


def _refuse(code: str) -> GuardResult:
    return GuardResult(ok=False, reason_code=code)


def g_always(doc: Document, inp: Any) -> GuardResult:  # pragma: no cover
    # Unconditional rows are resolved by transition() directly from the
    # row's single target; this is only here so GUARDS covers every key.
    raise AssertionError("g_always must not be called")


def g_auto_select(doc: Document, inp: Any) -> GuardResult:
    if isinstance(inp, SelectInput) and inp.auto:
        return GuardResult(ok=True, target=SELECTED)
    return _refuse("auto_select_disabled")


def g_ingest_route(doc: Document, inp: Any) -> GuardResult:
    if not isinstance(inp, IngestInput):
        return _refuse("bad_ingest_input")
    if inp.route == "ok":
        return GuardResult(
            ok=True, target=TRANSCRIBED if inp.clean else NEEDS_REVIEW)
    if inp.route == "blocked":
        if not inp.route_reason:
            return _refuse("route_missing_reason")
        return GuardResult(ok=True, target=BLOCKED)
    if inp.route == "error":
        if not inp.route_reason:
            return _refuse("route_missing_reason")
        return GuardResult(ok=True, target=ERRORED)
    if inp.route == "multiform":
        return GuardResult(ok=True, target=MULTI_FORM)
    return _refuse("unknown_route")


def g_multiform(doc: Document, inp: Any) -> GuardResult:
    # A MULTI_FORM doc re-ingested while still unsplittable: idempotent
    # no-op. A file whose split topology changed produces NEW child
    # doc_ids; the stale MULTI_FORM parent is disposed via re_extract
    # (see ingest._mark_stale_children), never re-derived in place.
    if isinstance(inp, IngestInput) and inp.route == "multiform":
        return GuardResult(ok=True, target=MULTI_FORM)
    return _refuse("multiform_topology_changed")


def g_reextract(doc: Document, inp: Any) -> GuardResult:
    if not isinstance(inp, ReextractInput):
        return _refuse("bad_reextract_input")
    if inp.values_differ:
        return GuardResult(ok=True, target=REREVIEW)
    return GuardResult(ok=True, target=VALIDATED)


def g_fix_identity(doc: Document, inp: Any) -> GuardResult:
    if not isinstance(inp, FixInput):
        return _refuse("bad_fix_input")
    if not inp.form_type or inp.form_type == "UNKNOWN":
        return _refuse("identity_still_unknown_form")
    if inp.tax_year is None:
        return _refuse("identity_still_missing_year")
    return GuardResult(ok=True, target=NEEDS_REVIEW)


def g_validate(doc: Document, inp: Any) -> GuardResult:
    # Model-layer backstop mirroring review.apply_validation's ratified
    # gates (tests/test_review.py pins the exact reason codes).
    if not isinstance(inp, ValidateInput):
        return _refuse("bad_validate_input")
    if inp.n_fields < 1:
        return _refuse("empty_fields")
    if not inp.form_known:
        return _refuse("unknown_form")
    if not inp.year_known:
        return _refuse("missing_year")
    if not inp.form_confirmed_or_corrected:
        return _refuse("unconfirmed_form")
    if not inp.year_confirmed_or_corrected:
        return _refuse("unconfirmed_year")
    if not inp.field_confirmed_or_edited:
        return _refuse("nothing_confirmed")
    return GuardResult(ok=True, target=VALIDATED)


def g_exclude(doc: Document, inp: Any) -> GuardResult:
    if not isinstance(inp, ExcludeInput):
        return _refuse("bad_exclude_input")
    if not inp.reason or not inp.reason.strip():
        return _refuse("exclude_reason_required")
    return GuardResult(ok=True, target=EXCLUDED)


GUARDS: dict[str, Callable[[Document, Any], GuardResult]] = {
    "always": g_always,
    "auto_select": g_auto_select,
    "ingest_route": g_ingest_route,
    "multiform_still": g_multiform,
    "reextract_agree": g_reextract,
    "fix_identity": g_fix_identity,
    "validate_guards": g_validate,
    "exclude_reason": g_exclude,
}


# -- the declared table --------------------------------------------------

@dataclass(frozen=True)
class Transition:
    from_state: str | None  # None = pre-scan: no lifecycle state yet
    event: str
    actor: str
    guard: str  # key into GUARDS
    targets: tuple[str, ...]  # candidates; the guard selects exactly one


def _expand_table() -> tuple[Transition, ...]:
    rows = [
        Transition(None, SCAN, SYSTEM, "always", (DISCOVERED,)),
        Transition(DISCOVERED, SELECT, OPERATOR, "always", (SELECTED,)),
        Transition(DISCOVERED, SELECT, SYSTEM, "auto_select", (SELECTED,)),
        Transition(DISCOVERED, UNSELECT, OPERATOR, "always", (UNSELECTED,)),
        Transition(UNSELECTED, SELECT, OPERATOR, "always", (SELECTED,)),
        Transition(SELECTED, INGEST, SYSTEM, "ingest_route",
                   (TRANSCRIBED, NEEDS_REVIEW, BLOCKED, ERRORED,
                    MULTI_FORM)),
        Transition(TRANSCRIBED, INGEST, SYSTEM, "ingest_route",
                   (TRANSCRIBED, NEEDS_REVIEW, BLOCKED, ERRORED)),
        Transition(NEEDS_REVIEW, INGEST, SYSTEM, "ingest_route",
                   (TRANSCRIBED, NEEDS_REVIEW, BLOCKED, ERRORED)),
        Transition(BLOCKED, INGEST, SYSTEM, "ingest_route",
                   (TRANSCRIBED, NEEDS_REVIEW, BLOCKED, ERRORED)),
        Transition(ERRORED, INGEST, SYSTEM, "ingest_route",
                   (TRANSCRIBED, NEEDS_REVIEW, BLOCKED, ERRORED)),
        Transition(MULTI_FORM, INGEST, SYSTEM, "multiform_still",
                   (MULTI_FORM,)),
        Transition(VALIDATED, RE_EXTRACT, SYSTEM, "reextract_agree",
                   (VALIDATED, REREVIEW)),
        Transition(REREVIEW, RE_EXTRACT, SYSTEM, "reextract_agree",
                   (VALIDATED, REREVIEW)),
        Transition(BLOCKED, FIX_FORM_YEAR, OPERATOR, "fix_identity",
                   (NEEDS_REVIEW,)),
        Transition(NEEDS_REVIEW, VALIDATE, OPERATOR, "validate_guards",
                   (VALIDATED,)),
        Transition(TRANSCRIBED, VALIDATE, OPERATOR, "validate_guards",
                   (VALIDATED,)),
        Transition(REREVIEW, VALIDATE, OPERATOR, "validate_guards",
                   (VALIDATED,)),
        # Re-attestation: validating an already-validated doc is legal
        # (same guards); it keeps validated and refreshes validated_at.
        Transition(VALIDATED, VALIDATE, OPERATOR, "validate_guards",
                   (VALIDATED,)),
    ]
    # exclude: every non-terminal state, operator only.
    for s in STATES:
        if s not in TERMINAL_STATES:
            rows.append(
                Transition(s, EXCLUDE, OPERATOR, "exclude_reason",
                           (EXCLUDED,)))
    # source_missing: every state (a terminal doc's source can still
    # vanish), system only.
    for s in STATES:
        rows.append(
            Transition(s, SOURCE_MISSING, SYSTEM, "always", (ORPHANED,)))
    return tuple(rows)


TRANSITION_TABLE: tuple[Transition, ...] = _expand_table()

# (from_state, event, actor) -> row. The table declares each triple at
# most once, so lookup is deterministic.
_TABLE_INDEX: dict[tuple[str | None, str, str], Transition] = {
    (r.from_state, r.event, r.actor): r for r in TRANSITION_TABLE
}
assert len(_TABLE_INDEX) == len(TRANSITION_TABLE), \
    "transition table has duplicate (from, event, actor) rows"
for _r in TRANSITION_TABLE:
    if _r.guard == "always":
        assert len(_r.targets) == 1, \
            f"unconditional row {_r} must declare exactly one target"
    for _t in _r.targets:
        assert _t in STATES, f"row {_r} targets unknown state {_t!r}"
    assert _r.event in EVENTS and _r.actor in ACTORS
del _r, _t


# -- transition function (the only status writer) ------------------------

@dataclass
class TransitionResult:
    ok: bool
    event: str
    actor: str
    from_state: str | None
    to_state: str | None
    reason_code: str | None = None
    noop: bool = False  # target == from_state: state unchanged, not logged


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh(doc: Document) -> bool:
    """A doc built by new_document() has no lifecycle state yet."""
    return bool(getattr(doc, "_lifecycle_fresh", False))


def is_fresh(doc: Document) -> bool:
    """True when ``doc`` was built by :func:`new_document` and has not
    fired its ``scan`` transition yet."""
    return _fresh(doc)


def new_document(**kwargs: Any) -> Document:
    """Build a Document with no lifecycle state yet (pre-scan).

    The first fired event must be ``scan`` (actor="system"), which moves
    it to ``discovered``. The constructor-visible status is "discovered"
    so the model validator stays happy; ``transition()`` treats a fresh
    doc as from_state None.
    """
    kwargs.setdefault("status", DISCOVERED)
    doc = Document(**kwargs)
    object.__setattr__(doc, "_lifecycle_fresh", True)
    return doc


def _resolve_from(doc: Document) -> str | None:
    if _fresh(doc):
        return None
    status = doc.status
    return status if status in STATES else None


def _apply_effects(doc: Document, event: str, to_state: str,
                   inp: Any, now: str) -> None:
    """Lifecycle field effects owned by this module (status and friends).

    The ONLY place in the package that assigns ``doc.status``.
    """
    doc.status = to_state
    if to_state in (BLOCKED, ERRORED) and isinstance(inp, IngestInput):
        doc.status_reason = inp.route_reason
    elif to_state == EXCLUDED:
        # The operator's free-text reason lives in the exclusions
        # record (local data dir); the doc carries the stable code.
        doc.status_reason = "operator-excluded"
    elif to_state == ORPHANED:
        doc.status_reason = "source-missing"
    elif to_state == REREVIEW and isinstance(inp, ReextractInput):
        doc.re_review = True
        doc.status_reason = inp.reason
    elif to_state == VALIDATED:
        doc.validated_at = now
        doc.re_review = False
        doc.status_reason = None
    elif to_state == NEEDS_REVIEW and event == FIX_FORM_YEAR \
            and isinstance(inp, FixInput):
        doc.form_type = inp.form_type or doc.form_type
        doc.tax_year = inp.tax_year if inp.tax_year is not None \
            else doc.tax_year
        doc.status_reason = None


def _metadata_changed(doc: Document, target: str, inp: Any) -> bool:
    """A same-state re-fire still counts as a change when lifecycle
    metadata (the block/error reason) differs -- e.g. a re-ingest that
    finds a new reason for an already-BLOCKED doc."""
    if target in (BLOCKED, ERRORED) and isinstance(inp, IngestInput):
        return (doc.status_reason or None) != (inp.route_reason or None)
    return False


def _log_event(store: Any, doc: Document, result: TransitionResult) -> None:
    """Append one lifecycle row to the medallion decision log."""
    log = getattr(store, "log_decision", None)
    if not callable(log):
        return
    log(actor=result.actor, kind="lifecycle", doc_id=doc.doc_id,
        payload={"event": result.event,
                 "from": result.from_state,
                 "to": result.to_state,
                 "reason_code": result.reason_code})


def transition(doc: Document, event: str, *, actor: str,
               event_input: Any = None, store: Any = None,
               now: str | None = None) -> TransitionResult:
    """Fire one lifecycle event on ``doc``.

    Returns a TransitionResult. On refusal (``ok=False``) the doc is
    untouched and ``reason_code`` names the refusal (metadata only).
    On success the doc's lifecycle fields are updated in place; when
    ``store`` is given, one ``kind="lifecycle"`` decision is appended
    (callers persist the doc itself inside their own transaction --
    ``log_decision`` nests as a savepoint, so event + state stay
    atomic). A target equal to the current state is a no-op success:
    nothing changes and nothing is logged (keeps ingest-twice
    idempotent at the event-log level).
    """
    if event not in EVENTS:
        raise ValueError(f"unknown lifecycle event {event!r}")
    if actor not in ACTORS:
        raise ValueError(f"unknown lifecycle actor {actor!r}")
    from_state = _resolve_from(doc)
    row = _TABLE_INDEX.get((from_state, event, actor))
    if row is None:
        return TransitionResult(
            ok=False, event=event, actor=actor,
            from_state=from_state, to_state=None,
            reason_code="illegal_transition")
    if row.guard == "always":
        # Unconditional row: exactly one declared target.
        gres = GuardResult(ok=True, target=row.targets[0])
    else:
        gres = GUARDS[row.guard](doc, event_input)
    if not gres.ok:
        return TransitionResult(
            ok=False, event=event, actor=actor,
            from_state=from_state, to_state=None,
            reason_code=gres.reason_code or "guard_refused")
    target = gres.target
    if target not in row.targets:
        return TransitionResult(
            ok=False, event=event, actor=actor,
            from_state=from_state, to_state=None,
            reason_code="guard_target_not_declared")
    if target == from_state and not _metadata_changed(doc, target,
                                                        event_input):
        return TransitionResult(
            ok=True, event=event, actor=actor,
            from_state=from_state, to_state=target, noop=True)
    if _fresh(doc):
        object.__setattr__(doc, "_lifecycle_fresh", False)
    _apply_effects(doc, event, target, event_input, now or _utcnow_iso())
    result = TransitionResult(
        ok=True, event=event, actor=actor,
        from_state=from_state, to_state=target)
    if store is not None:
        _log_event(store, doc, result)
    return result


# -- replay ---------------------------------------------------------------

@dataclass
class ReplayResult:
    doc_id: str
    final_state: str | None
    n_events: int
    ok: bool  # the chain is gapless: each from == previous to
    breaks: list[int] = field(default_factory=list)  # event indexes


def replay_lifecycle(store: Any, doc_id: str) -> ReplayResult:
    """Rebuild a doc's lifecycle state from its append-only event chain.

    ``final_state`` is None when the doc has no lifecycle events
    (pre-R13 / migrated records). ``ok`` is False when the chain has a
    gap (each event's ``from`` must equal the previous event's ``to``).
    Metadata only -- never touches values.
    """
    decisions = store.decisions_for(doc_id=doc_id, kind="lifecycle") or []
    breaks: list[int] = []
    prev_to: str | None = None
    first = True
    for i, d in enumerate(decisions):
        p = d.get("payload") or {}
        if not first and p.get("from") != prev_to:
            breaks.append(i)
        prev_to = p.get("to")
        first = False
    final_state = prev_to
    return ReplayResult(doc_id=doc_id, final_state=final_state,
                        n_events=len(decisions), ok=not breaks,
                        breaks=breaks)


# -- sibling-workstream entry points (R11/R12 contract) -------------------
#
# sources.py (scan/select console flow) drives file-level lifecycle
# events that are NOT document transitions (e.g. recording an
# operator's select of a scanned file before any Document exists).
# These helpers append/read the same append-only decision-log home
# (kind="lifecycle") without firing the transition table. Document
# state changes must ALWAYS go through transition(); record_event is
# the file-level escape hatch only.

def record_event(store: Any, *, doc_id: str, event: str, actor: str,
                 from_state: str | None, to_state: str | None,
                 reason_code: str | None) -> bool:
    """Append one raw lifecycle event row. Returns True on success.

    No transition is fired and no guard runs -- the caller owns the
    vocabulary (file-level ids and states are allowed here). Payload
    is metadata only ({event, from, to, reason_code}).
    """
    log = getattr(store, "log_decision", None)
    if not callable(log):
        return False
    log(actor=actor, kind="lifecycle", doc_id=doc_id,
        payload={"event": event, "from": from_state, "to": to_state,
                 "reason_code": reason_code})
    return True


def events_for(store: Any, *, doc_id: str | None = None,
               limit: int = 200) -> list[dict]:
    """Lifecycle events, oldest first, normalized to the contract shape
    {ts, doc_id, event, actor, from, to, reason_code}. Metadata only."""
    decisions_for = getattr(store, "decisions_for", None)
    if not callable(decisions_for):
        return []
    rows = decisions_for(doc_id=doc_id, kind="lifecycle") or []
    out = []
    for d in rows[:limit]:
        p = d.get("payload") or {}
        out.append({
            "ts": d.get("ts"),
            "doc_id": d.get("doc_id", doc_id),
            "event": p.get("event"),
            "actor": d.get("actor"),
            "from": p.get("from"),
            "to": p.get("to"),
            "reason_code": p.get("reason_code"),
        })
    return out


def state_of(store: Any, doc_id: str) -> str | None:
    """Current lifecycle state of a doc, or None when unknown.

    Replays the doc's lifecycle event chain when it has one (the log
    is the source of truth); falls back to the stored status for
    pre-R13 records with no events.
    """
    replay = replay_lifecycle(store, doc_id)
    if replay.n_events:
        return replay.final_state
    get = getattr(store, "get", None)
    doc = get(doc_id) if callable(get) else None
    status = getattr(doc, "status", None)
    return status if status in STATES else None


# -- mermaid view (generated from the table) --------------------------------

def mermaid() -> str:
    """stateDiagram-v2 generated from TRANSITION_TABLE (R13 req. 5)."""
    lines = ["stateDiagram-v2"]
    seen: set[tuple] = set()
    for r in TRANSITION_TABLE:
        src = "[*]" if r.from_state is None else r.from_state
        label = f"{r.event} ({r.actor})"
        for t in r.targets:
            key = (src, label, t)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"    {src} --> {t} : {label}")
    for t in sorted(TERMINAL_STATES):
        lines.append(f"    {t} --> [*]")
    return "\n".join(lines) + "\n"


def write_mermaid(path: str) -> str:
    """Write the generated diagram to ``path``; returns the path."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(mermaid())
    return path
