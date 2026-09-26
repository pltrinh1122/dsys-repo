"""PVB creation-and-ratification workflow — a dsys Architecture application.

A Product Vision Board (PVB) is the industry artifact (Roman Pichler) that
captures, on one page, a product's vision, target group, needs, product
properties, and business goals. This module implements the *workflow* that
carries one PVB document from draft to ratified publication — authored as
Pydantic v2 source models (DR-CMD-058) and compiled to AutomatonFlow
entities by the generic bridge (DR-CMD-037).

Glossary
--------
PVB ................ Product Vision Board: the one-page product-vision
                     artifact (vision, target group, needs, product,
                     business goals).
Harness ............ The deliberation plane: bounded, attributable
                     inference (chat turns) aimed at definition-of-done
                     conditions. Drafting and reviewing happen here.
Automaton .......... The execution plane: zero inference, declared steps,
                     deterministic replay. State transitions happen here.
Operator ........... The human principal. Only the operator disposes:
                     ratify, withdraw, publish.
ambient ............ The AI agent. It proposes, stages, and revises; it
                     never disposes.
disposition ........ An operator's explicit decision utterance (ratify,
                     withdraw, publish). A chat response is not authority;
                     only an explicit disposition is injected as an
                     operator event.
ratification ....... The operator's recorded disposition to adopt the
                     document. Written as a canonical JSON record;
                     the workflow's analogue of a DecisionRecord.
run-book ........... A declared sequence of tool steps executed by a task
                     state. Zero inference inside.
tool ............... A contracted, deterministic, network-free function
                     named in the tool registry. Tools here only read
                     files, hash bytes, and write canonical records.
injected event ..... The sole channel by which the outside (Harness)
                     reaches a running flow: a discrete, attributed
                     {verb, actor, ...} record consumed at a wait state
                     or by a task state's run-book.
refusal ............ A loud, attributed halt (DriveRefused / ToolAborted).
                     The workflow never silently advances past a violated
                     guard.
replay ............. Re-derivation of the state path from the
                     FlowTransitionEvent log with tools disabled. The log
                     alone determines the path.

The flow
--------
States:
  draft      (wait)  The document exists as a draft artifact, referenced
                     by path + sha256. Initial state.
  in_review  (task)  One review round: present the document, collect the
                     reviewer's injected event, record the outcome.
                     Run-book rb-review-round.
  revising   (task)  Apply a revision addressing open findings.
                     Run-book rb-apply-revision.
  ratified   (wait)  The operator's ratification is recorded. Awaits the
                     publish disposition.
  published  (end, completed)  Terminal: the ratified document is
                     published — the operator's act, executed through
                     the ambient's hands.
  withdrawn  (end, aborted)    Terminal: the operator deliberately
                     refused the document (distinct from failure).
  failed     (end, aborted)    Terminal: a mechanical fault (tool abort,
                     guard violation). Loud, never silent.

Transitions (trigger — guard — target):
  draft --external-- payload.event == 'begin_review' and
                     payload.document_ok --> in_review
  draft --external-- payload.event == 'withdraw' --> withdrawn
  in_review --run_completed-- payload.outcome == 'ratified' --> ratified
  in_review --run_completed-- payload.outcome == 'findings' --> revising
  in_review --run_completed-- payload.outcome == 'withdrawn' --> withdrawn
  in_review --run_aborted--> failed
  revising --run_completed-- payload.revised --> in_review
  revising --run_aborted--> failed
  ratified --external-- payload.event == 'publish' and
                     payload.actor == 'operator' --> published
  ratified --external-- payload.event == 'withdraw' --> withdrawn

Authority rules (enforced by tools, not by convention)
-----------------------------------------------------
- begin_review: ambient or operator. submit_revision: ambient or operator.
- report_findings: any reviewer; recorded with reported_by.
- ratify / withdraw / publish: actor MUST be 'operator'. Anything else
  is a loud ToolAborted — the ambient never disposes.
- ratify requires zero open findings.
- A revision must change the document bytes (new sha256 != presented
  sha256); a byte-identical "revision" aborts loudly.

Deliberation boundary
---------------------
Drafting, reviewing, and revising the document's *prose* happen in the
Harness (outside this module). The automaton sees only: the document's
path + hash, findings text, and disposition verbs. The docx artifact
itself is never parsed or rewritten here.

Limitations (v1)
----------------
- Single review round at a time; findings are addressed wholesale by
  each revision (all open findings marked addressed by the new hash).
- One reviewer role: the operator. Co-founder / investor / customer
  review rounds are future work.
- Records carry the event sequence as logical time; no wall-clock, so
  replay stays byte-clean.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from .bridge import (
    AutomatonSource,
    AutomatonState,
    AutomatonTransition,
    RunBookSource,
    RunBookStepSource,
    compile,
)
from .schema import FlowTransitionEvent
from .updater import eval_guard, path_hash  # noqa: F401  (path_hash re-exported)

FLOW_NAME = "pvb-ratification"
RELEASE_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Case model — the workflow's working memory (pydantic v2)
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """One reported defect or misalignment."""

    model_config = ConfigDict(frozen=True)

    seq: int
    text: str
    reported_by: str
    status: str = "open"  # open | addressed
    addressed_by: str | None = None  # document sha256 of the addressing revision


class PVBCase(BaseModel):
    """One PVB document's journey through the flow."""

    case_id: str
    document_path: str
    document_hash: str  # sha256 of the current document bytes
    findings: list[Finding] = Field(default_factory=list)
    revisions: int = 0
    ratification: dict | None = None

    def open_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "open"]


@dataclass
class PVBWorld:
    """The driver's world: no network, ever. The pending injected event is
    set by the driver before a task state's run-book runs and cleared after."""

    records_dir: str
    pending_event: dict | None = None


# ---------------------------------------------------------------------------
# Tools — contracted, deterministic, network-free
# ---------------------------------------------------------------------------

class ToolAborted(Exception):
    """Loud tool failure. The driver turns this into a run_aborted edge."""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _case(ctx: dict) -> PVBCase:
    return ctx["case"]


def _tool_present(ctx: dict, w: PVBWorld) -> None:
    """Present the current document for review: the file must exist and its
    bytes must match the case's recorded hash (draft integrity)."""
    case = _case(ctx)
    if not os.path.isfile(case.document_path):
        raise ToolAborted(
            f"pvb.present: document missing at {case.document_path}")
    h = _sha256_file(case.document_path)
    if h != case.document_hash:
        raise ToolAborted(
            f"pvb.present: hash mismatch — case records {case.document_hash}, "
            f"file is {h}")
    ctx["presented_hash"] = h
    ctx["presented"] = True


def _tool_collect(ctx: dict, w: PVBWorld) -> None:
    """Classify the injected review event. Disposition verbs require the
    operator; anything else aborts loudly."""
    ev = w.pending_event
    if ev is None:
        raise ToolAborted("pvb.collect: no injected event to collect")
    verb = ev.get("verb")
    actor = ev.get("actor")
    if verb == "report_findings":
        texts = ev.get("findings") or []
        if not texts or any(not t or not t.strip() for t in texts):
            raise ToolAborted(
                "pvb.collect: report_findings with empty finding text refused")
        ctx["outcome"] = "findings"
        ctx["findings"] = [{"text": t, "reported_by": actor} for t in texts]
    elif verb == "ratify":
        if actor != "operator":
            raise ToolAborted(
                f"pvb.collect: ratify by '{actor}' refused — only the "
                f"operator disposes")
        if _case(ctx).open_findings():
            raise ToolAborted(
                "pvb.collect: ratify with open findings refused — address "
                "or withdraw first")
        ctx["outcome"] = "ratified"
        ctx["disposition"] = "ratify"
    elif verb == "withdraw":
        if actor != "operator":
            raise ToolAborted(
                f"pvb.collect: withdraw by '{actor}' refused — only the "
                f"operator disposes")
        ctx["outcome"] = "withdrawn"
    else:
        raise ToolAborted(f"pvb.collect: unknown verb {verb!r} refused")


def _tool_record_ratification(ctx: dict, w: PVBWorld) -> None:
    """Write the canonical ratification record. Deterministic content: no
    wall-clock — the event sequence is the logical time."""
    case = _case(ctx)
    if ctx.get("outcome") != "ratified":
        raise ToolAborted(
            "pvb.record_ratification: outcome is not 'ratified'")
    record = {
        "case_id": case.case_id,
        "document_hash": case.document_hash,
        "disposition": "ratify",
        "actor": "operator",
        "flow_run_id": ctx["flow_run_id"],
        "event_seq": ctx["event_seq"],
    }
    os.makedirs(w.records_dir, exist_ok=True)
    path = os.path.join(w.records_dir, f"{case.case_id}.ratification.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, sort_keys=True, indent=2)
        f.write("\n")
    case.ratification = record
    ctx["ratification_path"] = path


def _tool_record_findings(ctx: dict, w: PVBWorld) -> None:
    """Persist reported findings as open findings on the case."""
    case = _case(ctx)
    if ctx.get("outcome") != "findings":
        raise ToolAborted(
            "pvb.record_findings: outcome is not 'findings'")
    base = len(case.findings)
    for i, item in enumerate(ctx["findings"], start=1):
        case.findings.append(Finding(seq=base + i, text=item["text"],
                                     reported_by=item["reported_by"]))
    ctx["findings_recorded"] = True


def _tool_apply_revision(ctx: dict, w: PVBWorld) -> None:
    """Apply a revision: the new document must exist and must differ
    byte-wise from the presented document; all open findings are marked
    addressed by the new hash."""
    case = _case(ctx)
    ev = w.pending_event
    if ev is None or ev.get("verb") != "submit_revision":
        raise ToolAborted(
            "pvb.apply_revision: no submit_revision event injected")
    actor = ev.get("actor")
    if actor not in ("ambient", "operator"):
        raise ToolAborted(
            f"pvb.apply_revision: actor '{actor}' refused")
    new_path = ev.get("document_path")
    if not new_path or not os.path.isfile(new_path):
        raise ToolAborted(
            f"pvb.apply_revision: revision document missing: {new_path}")
    new_hash = _sha256_file(new_path)
    if new_hash == case.document_hash:
        raise ToolAborted(
            "pvb.apply_revision: revision is byte-identical to the presented "
            "document — not a revision")
    if not case.open_findings():
        raise ToolAborted(
            "pvb.apply_revision: no open findings to address")
    addressed = []
    for f in case.findings:
        if f.status == "open":
            addressed.append(f.model_copy(
                update={"status": "addressed", "addressed_by": new_hash}))
        else:
            addressed.append(f)
    case.findings = addressed
    case.document_path = new_path
    case.document_hash = new_hash
    case.revisions += 1
    ctx["revised"] = True
    ctx["new_hash"] = new_hash
    ctx["revised_by"] = actor


TOOLS = {
    "pvb.present": _tool_present,
    "pvb.collect": _tool_collect,
    "pvb.record_ratification": _tool_record_ratification,
    "pvb.record_findings": _tool_record_findings,
    "pvb.apply_revision": _tool_apply_revision,
}


# ---------------------------------------------------------------------------
# Source model (pydantic v2 — the DR-CMD-058 pin) + compiled entities
# ---------------------------------------------------------------------------

PVB_SOURCE = AutomatonSource(
    name=FLOW_NAME,
    release_version=RELEASE_VERSION,
    initial_state="draft",
    states=[
        AutomatonState(name="draft", kind="wait"),
        AutomatonState(name="in_review", kind="task",
                       runbook_id="rb-review-round", step_policy="abort"),
        AutomatonState(name="revising", kind="task",
                       runbook_id="rb-apply-revision", step_policy="abort"),
        AutomatonState(name="ratified", kind="wait"),
        AutomatonState(name="published", kind="end", outcome="completed"),
        AutomatonState(name="withdrawn", kind="end", outcome="aborted"),
        AutomatonState(name="failed", kind="end", outcome="aborted"),
    ],
    transitions=[
        AutomatonTransition(
            from_state="draft", trigger="external",
            guard="payload.event == 'begin_review' and payload.document_ok",
            to_state="in_review"),
        AutomatonTransition(
            from_state="draft", trigger="external",
            guard="payload.event == 'withdraw'",
            to_state="withdrawn"),
        AutomatonTransition(
            from_state="in_review", trigger="run_completed",
            guard="payload.outcome == 'ratified'",
            to_state="ratified"),
        AutomatonTransition(
            from_state="in_review", trigger="run_completed",
            guard="payload.outcome == 'findings'",
            to_state="revising"),
        AutomatonTransition(
            from_state="in_review", trigger="run_completed",
            guard="payload.outcome == 'withdrawn'",
            to_state="withdrawn"),
        AutomatonTransition(
            from_state="in_review", trigger="run_aborted",
            to_state="failed"),
        AutomatonTransition(
            from_state="revising", trigger="run_completed",
            guard="payload.revised",
            to_state="in_review"),
        AutomatonTransition(
            from_state="revising", trigger="run_aborted",
            to_state="failed"),
        AutomatonTransition(
            from_state="ratified", trigger="external",
            guard="payload.event == 'publish' and "
                   "payload.actor == 'operator'",
            to_state="published"),
        AutomatonTransition(
            from_state="ratified", trigger="external",
            guard="payload.event == 'withdraw'",
            to_state="withdrawn"),
    ],
    runbooks=[
        RunBookSource(
            id="rb-review-round", name="Review round",
            steps=[
                RunBookStepSource(expr="True",
                                  tool_id="pvb.present"),
                RunBookStepSource(expr="True",
                                  tool_id="pvb.collect"),
                RunBookStepSource(expr="payload.outcome == 'ratified'",
                                  tool_id="pvb.record_ratification"),
                RunBookStepSource(expr="payload.outcome == 'findings'",
                                  tool_id="pvb.record_findings"),
            ]),
        RunBookSource(
            id="rb-apply-revision", name="Apply revision",
            steps=[
                RunBookStepSource(expr="True",
                                  tool_id="pvb.apply_revision"),
            ]),
    ],
)

# Compiled once, at import: any unmappable source element refuses here,
# loudly, before any run exists.
ENTITIES = compile(PVB_SOURCE, TOOLS)


# ---------------------------------------------------------------------------
# Driver — advances one case through the compiled entities on injected events
# ---------------------------------------------------------------------------

class DriveRefused(Exception):
    """Loud refusal: no transition fires, the run is closed, or the event
    log is ambiguous. The case state is left untouched."""


def _document_ok(case: PVBCase) -> bool:
    return (os.path.isfile(case.document_path)
            and _sha256_file(case.document_path) == case.document_hash)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def drive(case: PVBCase, world: PVBWorld, events: list[dict],
          flow_run_id: str | None = None) -> list[FlowTransitionEvent]:
    """Drive one case through the flow on a list of injected events.

    Each event is {"verb": ..., "actor": ..., ...}. Wait states consume the
    event directly; task states run their run-book against it, then route
    on run_completed / run_aborted. Every transition is appended to the
    returned event log. Any violation -> DriveRefused, state untouched.
    """
    aflow, states, transitions, runbooks, steps, _ = ENTITIES
    by_id = {s.id: s for s in states}
    rb_steps: dict[str, list] = {}
    for rb in runbooks:
        rb_steps[rb.id] = sorted(
            (st for st in steps if st.runbook_id == rb.id),
            key=lambda st: st.seq)
    run_id = flow_run_id or f"fr-{case.case_id}"
    cur = aflow.initial_state_id
    log: list[FlowTransitionEvent] = []
    seq = 0
    for ev in events:
        st = by_id[cur]
        if st.kind == "end":
            raise DriveRefused(
                f"run {run_id} is closed in '{st.name}': event {ev!r} refused")
        if st.kind == "wait":
            payload = {"event": ev.get("verb"), "actor": ev.get("actor"),
                       "document_ok": _document_ok(case)}
            trigger = "external"
        else:
            ctx: dict = {"case": case, "flow_run_id": run_id,
                         "event_seq": seq + 1}
            world.pending_event = ev
            aborted: Exception | None = None
            try:
                for step in rb_steps[st.runbook_id]:
                    if eval_guard(step.expr, ctx):
                        TOOLS[step.tool_id](ctx, world)
            except ToolAborted as e:
                aborted = e
            finally:
                world.pending_event = None
            if aborted is not None:
                trigger, payload = "run_aborted", {"aborted": str(aborted)}
            else:
                trigger, payload = "run_completed", ctx
        cands = [t for t in transitions
                 if t.from_state_id == cur and t.trigger == trigger]
        fired = [t for t in cands if eval_guard(t.guard, payload)]
        if not fired:
            raise DriveRefused(
                f"no transition from '{st.name}' on '{trigger}': "
                f"payload keys {sorted(payload)}")
        if len(fired) > 1:
            raise DriveRefused(
                f"I-15 runtime ambiguity from '{st.name}' on '{trigger}': "
                f"{[t.id for t in fired]}")
        t = fired[0]
        seq += 1
        log.append(FlowTransitionEvent(
            flow_run_id=run_id, seq=seq, from_state_id=cur,
            to_state_id=t.to_state_id, trigger=trigger,
            payload=_canonical(payload)))
        cur = t.to_state_id
    return log


def replay(events: list[FlowTransitionEvent]) -> list[str]:
    """Re-derive the state path from the event log alone. Tools stay
    disabled: the log is the source of truth, never reinvoked."""
    path: list[str] = []
    for e in events:
        if not path:
            path.append(e.from_state_id)
        elif path[-1] != e.from_state_id:
            raise ValueError(
                f"event log not contiguous at seq {e.seq}: "
                f"{path[-1]} != {e.from_state_id}")
        path.append(e.to_state_id)
    return path


# ---------------------------------------------------------------------------
# Case factory
# ---------------------------------------------------------------------------

def begin_case(case_id: str, document_path: str) -> PVBCase:
    """Open a case on a draft document. The file must exist; its sha256 is
    the identity the whole run is checked against."""
    if not os.path.isfile(document_path):
        raise DriveRefused(
            f"begin_case: no draft document at {document_path}")
    return PVBCase(case_id=case_id, document_path=document_path,
                   document_hash=_sha256_file(document_path))
