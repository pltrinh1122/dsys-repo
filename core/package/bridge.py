"""The generic pydantic->core compile path (adopted DR-CMD-037).

Contents:
  - Pydantic v2 source models (DR-CMD-028): AutomatonState,
    AutomatonTransition, RunBookStepSource, RunBookSource, AutomatonSource.
  - compile(): pure function from source bytes + tool registry to the
    entity set the FlowRun scheduler executes (AutomatonFlow, FlowState[],
    FlowTransition[], RunBook[], Step[], Tool[]). Enforces B-1 (totality),
    B-2 (id determinism), B-3 (schema closure) as validators; anything
    unmappable is refused loudly (BridgeRefused), never warned past.
  - release_monitor_source(): the updater's automaton re-expressed as a
    generic source. updater.py is deliberately NOT touched (frozen,
    reviewed); the bridge reproduces compile_flow()'s output byte-for-byte
    (spec §7.1). The run-book specs are re-declared here as data — the
    golden run's hash equality is the mechanical guard against drift.

Anti-smuggling line (§5): the source declares structure (states, edges,
step order, guards, tool names). Tool implementations live in the
registry, outside the source; the bridge reads only the registry's keys.
"""
from __future__ import annotations

import ast
import hashlib
import json
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from .schema import (
    AutomatonFlow,
    FlowState,
    FlowTransition,
    RunBook,
    Step,
    Tool,
)
from .updater import RELEASE_MONITOR, RELEASE_VERSION

Trigger = "timer | run_completed | run_aborted | external"
StateKind = "task | wait | end"

_FLOW_TRIGGERS = ("timer", "run_completed", "run_aborted", "external")
_STATE_KINDS = ("task", "wait", "end")
_END_OUTCOMES = ("completed", "aborted")

# The AST-allowlisted expression subset — the v1 decision, same set as
# updater.eval_guard's. Re-declared (not imported) because updater.py is
# frozen; the two sets must stay identical by review, not by import.
_ALLOWED_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Attribute,
    ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq, ast.And, ast.Or,
    ast.Not,
)


class BridgeRefused(Exception):
    """Compile-time refusal: the source cannot become entities. Loud."""


# ---------------------------------------------------------------------------
# Source models (pydantic v2 — the DR-CMD-028 pin)
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name).strip("-")


class AutomatonState(BaseModel):
    """One FSM state — compiles to FlowState."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str  # task | wait | end (B-3: nothing else)
    runbook_id: str | None = None  # required iff kind == 'task'
    step_policy: str | None = None  # iff kind == 'task': abort|skip|retry:<n>
    outcome: str | None = None  # iff kind == 'end': completed | aborted


class AutomatonTransition(BaseModel):
    """One guarded edge — compiles to FlowTransition."""

    model_config = ConfigDict(frozen=True)

    from_state: str
    trigger: str  # B-3: one of the four flow triggers
    guard: str | None = None  # AST-allowlisted expr over payload.*
    to_state: str


class RunBookStepSource(BaseModel):
    """One run-book step — compiles to Step."""

    model_config = ConfigDict(frozen=True)

    expr: str = "True"  # AST-allowlisted step guard
    tool_id: str  # must resolve in the tool registry (B-3)


class RunBookSource(BaseModel):
    """One run-book's structure — compiles to RunBook + Steps."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    steps: list[RunBookStepSource] = Field(min_length=1)


class AutomatonSource(BaseModel):
    """One automaton — compiles to AutomatonFlow + states + transitions
    + run-books. Id prefixes manage the id space when several flows share
    a SystemState (the I-14 cross-flow checks); they default to the
    slug-derived form and are explicit whenever legacy ids must be
    reproduced byte-for-byte (spec §7.1)."""

    model_config = ConfigDict(frozen=True)

    name: str
    release_version: str
    initial_state: str
    state_id_prefix: str | None = None  # default: {slug}-s-
    transition_id_prefix: str | None = None  # default: {slug}-t-
    states: list[AutomatonState] = Field(min_length=1)
    transitions: list[AutomatonTransition] = Field(min_length=1)
    runbooks: list[RunBookSource] = Field(min_length=1)

    def resolved_prefixes(self) -> tuple[str, str]:
        s = _slug(self.name)
        return (self.state_id_prefix if self.state_id_prefix is not None
                else f"{s}-s-",
                self.transition_id_prefix
                if self.transition_id_prefix is not None else f"{s}-t-")


# ---------------------------------------------------------------------------
# Validators B-1 / B-2 / B-3 — predicates, not procedures
# ---------------------------------------------------------------------------

def _guard_ok(expr: str | None) -> str | None:
    """None if the expr is allowlisted; the violation otherwise."""
    if expr is None:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"guard is not parseable: {e}"
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return (f"guard uses non-allowlisted syntax: "
                    f"{type(node).__name__}")
        if isinstance(node, ast.Name) and node.id != "payload":
            return f"guard may only reference payload, got '{node.id}'"
    return None


def _step_policy_ok(policy: str | None) -> bool:
    if policy is None:
        return False  # task states: explicit — no silent default
    if policy in ("abort", "skip"):
        return True
    if policy.startswith("retry:"):
        try:
            return int(policy.split(":", 1)[1]) >= 1
        except ValueError:
            return False
    return False


def validate_schema_closure(source: AutomatonSource,
                            tool_ids: set[str]) -> list[str]:
    """B-3: everything in the source maps onto the existing entity schema.
    Anything else is a refusal, never an extension."""
    v: list[str] = []
    state_names = {s.name for s in source.states}
    rb_ids = {rb.id for rb in source.runbooks}
    if source.initial_state not in state_names:
        v.append(f"B-3: initial_state '{source.initial_state}' "
                 f"names no state")
    for s in source.states:
        if s.kind not in _STATE_KINDS:
            v.append(f"B-3: state '{s.name}': unknown kind '{s.kind}'")
            continue
        if s.kind == "task":
            if s.runbook_id is None:
                v.append(f"B-3: task state '{s.name}': runbook_id required")
            elif s.runbook_id not in rb_ids:
                v.append(f"B-3: task state '{s.name}': dangling runbook_id "
                         f"'{s.runbook_id}'")
            if not _step_policy_ok(s.step_policy):
                v.append(f"B-3: task state '{s.name}': bad step_policy "
                         f"'{s.step_policy}' (abort|skip|retry:<n>=1, explicit)")
        if s.kind == "end" and s.outcome not in _END_OUTCOMES:
            v.append(f"B-3: end state '{s.name}': outcome must be "
                     f"completed|aborted, got '{s.outcome}'")
    for t in source.transitions:
        if t.trigger not in _FLOW_TRIGGERS:
            v.append(f"B-3: transition {t.from_state}->{t.to_state}: "
                     f"unknown trigger '{t.trigger}'")
        if t.from_state not in state_names:
            v.append(f"B-3: transition from unknown state '{t.from_state}'")
        if t.to_state not in state_names:
            v.append(f"B-3: transition to unknown state '{t.to_state}'")
        bad = _guard_ok(t.guard)
        if bad is not None:
            v.append(f"B-3: transition {t.from_state}->{t.to_state}: {bad}")
    for rb in source.runbooks:
        for i, step in enumerate(rb.steps):
            bad = _guard_ok(step.expr)
            if bad is not None:
                v.append(f"B-3: run-book '{rb.id}' step {i + 1}: {bad}")
            if step.tool_id not in tool_ids:
                v.append(f"B-3: run-book '{rb.id}' step {i + 1}: "
                         f"unknown tool '{step.tool_id}' (naming is not "
                         f"defining — register it or refuse)")
    return v


Entities = tuple[AutomatonFlow, list[FlowState], list[FlowTransition],
                 list[RunBook], list[Step], list[Tool]]


def _expected_ids(source: AutomatonSource) -> dict[str, str]:
    """The deterministic id derivation (B-2's reference)."""
    sp, tp = source.resolved_prefixes()
    ids: dict[str, str] = {}
    for s in source.states:
        ids[f"state:{s.name}"] = f"{sp}{s.name}"
    for i, t in enumerate(source.transitions):
        ids[f"trans:{i}"] = f"{tp}{i + 1:02d}"
    for rb in source.runbooks:
        ids[f"runbook:{rb.id}"] = rb.id
        for seq, step in enumerate(rb.steps, start=1):
            ids[f"step:{rb.id}:{seq}"] = f"{rb.id}-s{seq}"
    return ids


def validate_totality(source: AutomatonSource, e: Entities) -> list[str]:
    """B-1: every source element maps to exactly one entity — nothing
    dropped, nothing invented."""
    v: list[str] = []
    _, states, transitions, runbooks, steps, tools = e
    exp = _expected_ids(source)
    for s in source.states:
        got = [x for x in states if x.id == exp[f"state:{s.name}"]]
        if len(got) != 1:
            v.append(f"B-1: state '{s.name}': {len(got)} entities")
    for i in range(len(source.transitions)):
        got = [x for x in transitions if x.id == exp[f"trans:{i}"]]
        if len(got) != 1:
            v.append(f"B-1: transition #{i + 1}: {len(got)} entities")
    for rb in source.runbooks:
        got = [x for x in runbooks if x.id == rb.id]
        if len(got) != 1:
            v.append(f"B-1: run-book '{rb.id}': {len(got)} entities")
        for seq in range(1, len(rb.steps) + 1):
            got_s = [x for x in steps
                     if x.id == exp[f"step:{rb.id}:{seq}"]]
            if len(got_s) != 1:
                v.append(f"B-1: step {rb.id}-s{seq}: {len(got_s)} entities")
    if len(states) != len(source.states):
        v.append(f"B-1: {len(states)} states for "
                 f"{len(source.states)} source states")
    if len(transitions) != len(source.transitions):
        v.append(f"B-1: {len(transitions)} transitions for "
                 f"{len(source.transitions)} source transitions")
    return v


def validate_id_determinism(source: AutomatonSource,
                            e: Entities) -> list[str]:
    """B-2: the same source bytes always yield the same entity ids."""
    v: list[str] = []
    _, states, transitions, runbooks, steps, _ = e
    exp = _expected_ids(source)
    by_id = {x.id: x for x in states + transitions + runbooks + steps}
    for key, want in exp.items():
        if want not in by_id:
            v.append(f"B-2: expected id '{want}' ({key}) not emitted")
    return v


# ---------------------------------------------------------------------------
# compile() — source bytes + tool registry -> entities. Pure.
# ---------------------------------------------------------------------------

def compile(source: AutomatonSource,
            tools: dict[str, Callable]) -> Entities:
    """Compile one automaton source to entities. The bridge reads only the
    registry's keys (naming); implementations are execution's business.
    Any unmappable source element -> BridgeRefused, loudly."""
    bad = validate_schema_closure(source, set(tools))
    if bad:
        raise BridgeRefused("B-3 schema closure:\n" + "\n".join(bad))

    flow_id = f"flow-{source.name}"
    sp, tp = source.resolved_prefixes()
    sid = lambda name: f"{sp}{name}"  # noqa: E731

    aflow = AutomatonFlow(
        id=flow_id, name=source.name,
        release_version=source.release_version,
        initial_state_id=sid(source.initial_state))
    states = [
        FlowState(
            id=sid(s.name), flow_id=flow_id, name=s.name, kind=s.kind,
            runbook_id=s.runbook_id, outcome=s.outcome,
            step_policy=s.step_policy)
        for s in source.states
    ]
    transitions = [
        FlowTransition(
            id=f"{tp}{i + 1:02d}", flow_id=flow_id,
            from_state_id=sid(t.from_state), trigger=t.trigger,
            guard=t.guard, to_state_id=sid(t.to_state))
        for i, t in enumerate(source.transitions)
    ]
    runbooks, steps, tool_ents = [], [], []
    seen: set[str] = set()
    for rb in source.runbooks:
        runbooks.append(RunBook(id=rb.id, release_version=source.release_version,
                                name=rb.name))
        for seq, step in enumerate(rb.steps, start=1):
            step_id = f"{rb.id}-s{seq}"
            steps.append(Step(id=step_id, runbook_id=rb.id, seq=seq,
                              expr=step.expr, tool_id=step.tool_id))
            if step.tool_id not in seen:
                seen.add(step.tool_id)
                tool_ents.append(Tool(id=step.tool_id, name=step.tool_id))

    entities: Entities = (aflow, states, transitions, runbooks, steps,
                          tool_ents)
    for name, fn in (("B-1 totality", validate_totality),
                     ("B-2 id determinism", validate_id_determinism)):
        viols = fn(source, entities)
        if viols:
            raise BridgeRefused(f"{name}:\n" + "\n".join(viols))
    return entities


def entities_hash(e: Entities) -> str:
    """Canonical hash of the compiled entity set (spec §4, §7.4)."""
    parts = []
    for coll in e:
        items = coll if isinstance(coll, list) else [coll]
        parts.append(json.dumps([x.model_dump(mode="json") for x in items],
                                sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# The updater re-expressed as a generic source (spec §7.1)
# ---------------------------------------------------------------------------

# The five run-books' structure, re-declared as source data. Authority:
# updater._runbook_entities (updater.py frozen); this duplication is
# intentional, and the §7.1 hash equality is its drift guard.
_UPDATER_RUNBOOK_SPECS: list[tuple[str, list[tuple[str, str]]]] = [
    ("rb-release-check", [("True", "tool-fetch-feed"),
                          ("True", "tool-compare-versions")]),
    ("rb-release-verify", [("True", "tool-verify-checksum")]),
    ("rb-policy-gate", [("True", "tool-read-policy")]),
    ("rb-release-drive", [("True", "tool-invoke-installer")]),
    ("rb-release-verify-installed", [("True", "tool-run-doctor"),
                                     ("True", "tool-record-promotion")]),
]

_UPDATER_TOOL_IDS = [
    "tool-fetch-feed", "tool-compare-versions", "tool-verify-checksum",
    "tool-read-policy", "tool-invoke-installer", "tool-run-doctor",
    "tool-record-promotion",
]


def release_monitor_source() -> AutomatonSource:
    """The release-monitor automaton as a generic AutomatonSource —
    states/transitions mapped from RELEASE_MONITOR, run-books as source,
    legacy id prefixes declared for byte-equality (spec §7.1)."""
    return AutomatonSource(
        name=RELEASE_MONITOR.name,
        release_version=RELEASE_VERSION,
        initial_state=RELEASE_MONITOR.initial_state,
        state_id_prefix="urm-",
        transition_id_prefix="urmt-",
        states=[
            AutomatonState(name=s.name, kind=s.kind, runbook_id=s.runbook_id,
                           step_policy=s.step_policy, outcome=s.outcome)
            for s in RELEASE_MONITOR.states
        ],
        transitions=[
            AutomatonTransition(from_state=t.from_state, trigger=t.trigger,
                                guard=t.guard, to_state=t.to_state)
            for t in RELEASE_MONITOR.transitions
        ],
        runbooks=[
            RunBookSource(
                id=rb_id, name=rb_id,
                steps=[RunBookStepSource(expr=expr, tool_id=tool_id)
                       for expr, tool_id in step_specs])
            for rb_id, step_specs in _UPDATER_RUNBOOK_SPECS
        ],
    )


def updater_tool_registry() -> dict[str, Callable]:
    """The registry keys the updater's source resolves against. Values are
    placeholders here — compile() reads only the keys; execution wires the
    real implementations."""
    return {tid: (lambda ctx, w, tid=tid: None) for tid in _UPDATER_TOOL_IDS}
