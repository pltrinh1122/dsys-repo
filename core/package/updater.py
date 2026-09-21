"""Release-monitor automaton — the adopted updater expansion (DR-CMD-035).

Contents:
  - Pydantic v2 source models (DR-CMD-028): MonitorState, MonitorTransition,
    ReleaseMonitorFlow, and the authoritative RELEASE_MONITOR instance
    (spec §1: 8 states, 14 transitions).
  - compile_flow(): the updater's compilation path from source models to
    AutomatonFlow / FlowState / FlowTransition entities, executed by FlowRun
    (DR-CMD-030). The generic bridge remains a future governed matter; this
    function is deliberately shaped so the bridge can generalize it.
  - The five run-books' tool implementations (zero inference throughout).
  - A minimal deterministic driver + an AST-allowlisted guard evaluator
    (the v1 expression-language decision, scoped to the guards used here).
  - replay(): re-derivation of the state path from the FlowTransitionEvent
    log with tools and network disabled (R1).

All behavior here is mechanical: poll, compare, verify, invoke, record.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schema import (
    AutomatonFlow,
    AutomatonRun,
    FlowState,
    FlowTransition,
    FlowTransitionEvent,
    RunBook,
    Step,
    SystemState,
    Tool,
)

FLOW_ID = "flow-release-monitor"
RELEASE_VERSION = "0.1.0"

Trigger = Literal["timer", "run_completed", "run_aborted", "external"]
StateKind = Literal["task", "wait", "end"]
EndOutcome = Literal["completed", "aborted"]


# ---------------------------------------------------------------------------
# Source models (pydantic v2 — the DR-CMD-028 pin)
# ---------------------------------------------------------------------------

class MonitorState(BaseModel):
    """One FSM state — compiles to FlowState."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: StateKind
    runbook_id: str | None = None  # required iff kind == 'task'
    step_policy: str | None = None  # iff kind == 'task': abort | skip | retry:<n>
    outcome: EndOutcome | None = None  # iff kind == 'end'


class MonitorTransition(BaseModel):
    """One guarded edge — compiles to FlowTransition."""

    model_config = ConfigDict(frozen=True)

    from_state: str
    trigger: Trigger
    guard: str | None = None  # AST-allowlisted expr over payload.*
    to_state: str


class ReleaseMonitorFlow(BaseModel):
    """The release-monitor automaton — compiles to AutomatonFlow + entities."""

    model_config = ConfigDict(frozen=True)

    name: Literal["release-monitor"] = "release-monitor"
    release_version: str
    initial_state: str = "idle"
    states: list[MonitorState] = Field(min_length=1)
    transitions: list[MonitorTransition] = Field(min_length=1)


RELEASE_MONITOR = ReleaseMonitorFlow(
    release_version=RELEASE_VERSION,
    states=[
        MonitorState(name="idle", kind="wait"),
        MonitorState(name="checking", kind="task",
                     runbook_id="rb-release-check", step_policy="retry:3"),
        MonitorState(name="candidate", kind="task",
                     runbook_id="rb-release-verify", step_policy="abort"),
        MonitorState(name="gate", kind="task",
                     runbook_id="rb-policy-gate", step_policy="abort"),
        MonitorState(name="driving", kind="task",
                     runbook_id="rb-release-drive", step_policy="abort"),
        MonitorState(name="verifying", kind="task",
                     runbook_id="rb-release-verify-installed",
                     step_policy="abort"),
        MonitorState(name="done", kind="end", outcome="completed"),
        MonitorState(name="failed", kind="end", outcome="aborted"),
    ],
    transitions=[
        MonitorTransition(from_state="idle", trigger="timer",
                          to_state="checking"),
        MonitorTransition(from_state="checking", trigger="run_completed",
                          guard="payload.remote_version != payload.installed_version",
                          to_state="candidate"),
        MonitorTransition(from_state="checking", trigger="run_completed",
                          guard="payload.remote_version == payload.installed_version",
                          to_state="idle"),
        MonitorTransition(from_state="checking", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="candidate", trigger="run_completed",
                          to_state="gate"),
        MonitorTransition(from_state="candidate", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="gate", trigger="run_completed",
                          guard="payload.decision == 'drive'",
                          to_state="driving"),
        MonitorTransition(from_state="gate", trigger="run_completed",
                          guard="payload.decision == 'defer'",
                          to_state="idle"),
        MonitorTransition(from_state="gate", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="driving", trigger="run_completed",
                          to_state="verifying"),
        MonitorTransition(from_state="driving", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="verifying", trigger="run_completed",
                          guard="payload.doctor_ok and payload.promotion_recorded",
                          to_state="done"),
        MonitorTransition(from_state="verifying", trigger="run_completed",
                          guard="not (payload.doctor_ok and payload.promotion_recorded)",
                          to_state="failed"),
        MonitorTransition(from_state="verifying", trigger="run_aborted",
                          to_state="failed"),
    ],
)


# ---------------------------------------------------------------------------
# Compilation: source models -> AutomatonFlow / FlowState / FlowTransition
# ---------------------------------------------------------------------------

def _state_id(name: str) -> str:
    return f"urm-{name}"


def compile_flow(flow: ReleaseMonitorFlow = RELEASE_MONITOR):
    """Compile the source model into entities. Returns
    (AutomatonFlow, [FlowState], [FlowTransition], [RunBook], [Step], [Tool])."""
    aflow = AutomatonFlow(
        id=FLOW_ID, name=flow.name, release_version=flow.release_version,
        initial_state_id=_state_id(flow.initial_state))
    states = [
        FlowState(
            id=_state_id(s.name), flow_id=FLOW_ID, name=s.name, kind=s.kind,
            runbook_id=s.runbook_id, outcome=s.outcome,
            step_policy=s.step_policy)
        for s in flow.states
    ]
    transitions = [
        FlowTransition(
            id=f"urmt-{i + 1:02d}", flow_id=FLOW_ID,
            from_state_id=_state_id(t.from_state), trigger=t.trigger,
            guard=t.guard, to_state_id=_state_id(t.to_state))
        for i, t in enumerate(flow.transitions)
    ]
    runbooks, steps, tools = _runbook_entities()
    return aflow, states, transitions, runbooks, steps, tools


def _runbook_entities():
    """The five run-books as RunBook/Step/Tool entities. Steps are strictly
    sequential; each step is an (allowlisted expr, tool) pair."""
    specs = [
        ("rb-release-check", [("True", "tool-fetch-feed"),
                              ("True", "tool-compare-versions")]),
        ("rb-release-verify", [("True", "tool-verify-checksum")]),
        ("rb-policy-gate", [("True", "tool-read-policy")]),
        ("rb-release-drive", [("True", "tool-invoke-installer")]),
        ("rb-release-verify-installed", [("True", "tool-run-doctor"),
                                        ("True", "tool-record-promotion")]),
    ]
    runbooks, steps, tools = [], [], []
    seen_tools: set[str] = set()
    for rb_id, step_specs in specs:
        runbooks.append(RunBook(id=rb_id, release_version=RELEASE_VERSION,
                                name=rb_id))
        for seq, (expr, tool_id) in enumerate(step_specs, start=1):
            steps.append(Step(id=f"{rb_id}-s{seq}", runbook_id=rb_id, seq=seq,
                              expr=expr, tool_id=tool_id))
            if tool_id not in seen_tools:
                seen_tools.add(tool_id)
                tools.append(Tool(id=tool_id, name=tool_id))
    return runbooks, steps, tools


# ---------------------------------------------------------------------------
# World (fixture) + tools — zero inference
# ---------------------------------------------------------------------------

class ToolAborted(Exception):
    """A tool refused its work: the run-book run aborts (run_aborted)."""


class NetworkDisabled(Exception):
    """The feed poll attempted a network touch while disabled (replay)."""


@dataclass
class World:
    """Everything outside the machine the golden run scripts."""
    feed_version: str = "0.1.1"
    feed_sha256: str = "sha256:feed-bytes-fixture"
    feed_checksum_ok: bool = True
    installed_version: str = "0.1.0"
    updater_policy: str = "auto"  # auto | notify | off
    auto_max_bump: str = "patch"  # patch | minor | major
    poll_interval_s: int = 3600
    network_enabled: bool = True
    doctor_ok: bool = True
    installer_exit_code: int = 0  # nonzero -> the drive fails, loudly
    installer_invocations: list[str] = field(default_factory=list)
    installer_argvs: list[list[str]] = field(default_factory=list)  # K2 repair
    # K2 repair: the install-home concept. The drive's installer invocation
    # explicitly resumes the previous installation's accretion repo (D1).
    install_home: str = "/home/op/dsys-inst"  # own home (first install)
    prev_install_home: str | None = None      # previous install's home
    prev_accretion_path: str | None = None    # its config accretion.path
    accretion_writable: bool = True           # fixture: can the path be written
    promotions: list[dict] = field(default_factory=list)
    surfaced: list[dict] = field(default_factory=list)  # notify/off observations


def _bump(old: str, new: str) -> str:
    """Classify the bump old->new. Defensive: real-world versions carry
    suffixes ('1.2.3-rc1') and uneven segment counts; parse leading
    digits per segment, pad short, compare major/minor/rest."""

    def nums(v: str) -> list[int]:
        out = []
        for seg in v.split("."):
            digits = ""
            for ch in seg:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            out.append(int(digits) if digits else 0)
        return out

    o, n = nums(old), nums(new)
    width = max(len(o), len(n))
    o += [0] * (width - len(o))
    n += [0] * (width - len(n))
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"


_BUMP_ORDER = {"patch": 0, "minor": 1, "major": 2}


def _tool_fetch_feed(ctx: dict, w: World) -> None:
    if not w.network_enabled:
        raise NetworkDisabled("feed poll attempted with network disabled")
    # The sole network touch: one GET of the pinned feed. Nothing leaves.
    ctx["feed_sha256"] = w.feed_sha256
    ctx["remote_version"] = w.feed_version
    ctx["feed_checksum"] = w.feed_sha256 if w.feed_checksum_ok else "sha256:tampered"


def _tool_compare_versions(ctx: dict, w: World) -> None:
    ctx["installed_version"] = w.installed_version
    # Guards compare payload.remote_version != payload.installed_version.


def _tool_verify_checksum(ctx: dict, w: World) -> None:
    if ctx.get("feed_checksum") != w.feed_sha256:
        raise ToolAborted("checksum mismatch: no candidacy")


def _tool_read_policy(ctx: dict, w: World) -> None:
    policy = w.updater_policy
    if policy == "auto":
        bump = _bump(ctx["installed_version"], ctx["remote_version"])
        if _BUMP_ORDER[bump] <= _BUMP_ORDER[w.auto_max_bump]:
            ctx["decision"] = "drive"
            ctx["reason"] = f"policy=auto, bump={bump} within {w.auto_max_bump}"
        else:
            ctx["decision"] = "defer"
            ctx["reason"] = f"policy=auto but bump={bump} exceeds {w.auto_max_bump}"
            w.surfaced.append({"version": ctx["remote_version"],
                               "reason": ctx["reason"]})
    elif policy == "notify":
        ctx["decision"] = "defer"
        ctx["reason"] = "policy=notify: surfaced, not driven"
        w.surfaced.append({"version": ctx["remote_version"],
                           "reason": ctx["reason"]})
    elif policy == "off":
        ctx["decision"] = "defer"
        ctx["reason"] = "policy=off: recorded only"
    else:
        # Unknown policy is a config error: abort loudly. Silently
        # degrading to 'off' would hide a typo'd policy ('autoo').
        raise ToolAborted(f"unknown updater policy: {policy!r}")


def _accretion_path(w: World) -> str:
    # K2 repair D1: the previous install's effective accretion path —
    # its config override when known, else the default rule over the
    # previous home's basename. First install (no previous home): derive
    # from our own home. Always explicit — never ambient defaults.
    if w.prev_accretion_path:
        return w.prev_accretion_path
    home = w.prev_install_home or w.install_home
    return "/var/daccretion/" + home.strip("/").split("/")[-1]


def _tool_invoke_installer(ctx: dict, w: World) -> None:
    # The composed perform step: install.sh --release <version>
    # --accretion-path <explicit> --accretion-required (K2 repair).
    # The drive always passes the explicit path (never --overwrite: D5)
    # and always fail-closed (D2): an unwritable path refuses the drive
    # rather than warn-and-continue under autonomous operation (D3).
    version = ctx["remote_version"]
    acc_path = _accretion_path(w)
    argv = ["install.sh", "--release", version,
            "--accretion-path", acc_path, "--accretion-required"]
    w.installer_argvs.append(argv)
    w.installer_invocations.append(version)
    if not w.accretion_writable:
        # The world models the installer faithfully: fail-closed accretion
        # fails the install before converge — nothing is written, nothing
        # is adopted, the drive refuses loudly.
        raise ToolAborted(
            f"accretion path not writable: {acc_path} (--accretion-required)")
    if w.installer_exit_code != 0:
        # The drive fails; the version does NOT converge (world models the
        # installer faithfully: a failed install changes nothing).
        raise ToolAborted(
            f"installer exited {w.installer_exit_code} for {version}")
    w.installed_version = version  # the world converges, like the installer
    ctx["exit_code"] = 0


def _tool_run_doctor(ctx: dict, w: World) -> None:
    ctx["doctor_ok"] = w.doctor_ok


def _tool_record_promotion(ctx: dict, w: World) -> None:
    # The promotion bridge records the step-change. The accretion commit is
    # the installer's own discipline — mirrored here as a world fact.
    # (K1, updater-spec §9: that assignment covers install-time state only;
    # the updater's inter-install event log has no writer in this build.)
    if ctx.get("doctor_ok"):
        w.promotions.append({"version": w.installed_version,
                             "feed_sha256": w.feed_sha256})
        ctx["promotion_recorded"] = True
    else:
        ctx["promotion_recorded"] = False


TOOLS: dict[str, Callable[[dict, World], None]] = {
    "tool-fetch-feed": _tool_fetch_feed,
    "tool-compare-versions": _tool_compare_versions,
    "tool-verify-checksum": _tool_verify_checksum,
    "tool-read-policy": _tool_read_policy,
    "tool-invoke-installer": _tool_invoke_installer,
    "tool-run-doctor": _tool_run_doctor,
    "tool-record-promotion": _tool_record_promotion,
}


# ---------------------------------------------------------------------------
# Guard evaluator — AST allowlist over payload.* (v1 expression language)
# ---------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Attribute,
    ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq, ast.And, ast.Or,
    ast.Not,
)


class _Payload:
    def __init__(self, d: dict):
        self.__dict__["_d"] = d

    def __getattr__(self, name: str):
        try:
            return self.__dict__["_d"][name]
        except KeyError:
            raise AttributeError(f"payload has no attribute {name!r}")


def eval_guard(guard: str | None, payload: dict) -> bool:
    """Evaluate an allowlisted guard. None (guardless) counts as true."""
    if guard is None:
        return True
    tree = ast.parse(guard, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"guard uses non-allowlisted syntax: "
                             f"{type(node).__name__}")
        if isinstance(node, ast.Name) and node.id != "payload":
            raise ValueError(f"guard may only reference payload, "
                             f"got '{node.id}'")
    code = compile(tree, "<guard>", "eval")
    return bool(eval(code, {"__builtins__": {}}, {"payload": _Payload(payload)}))


# ---------------------------------------------------------------------------
# Driver — advances a FlowRun through the compiled entities
# ---------------------------------------------------------------------------

def _payload_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def drive(s: SystemState, world: World, run_id: str = "fr-updater",
          max_steps: int = 50, until: str | None = None) -> list[str]:
    """Advance the release-monitor FlowRun.

    Runs to an end state by default. `until` stops early when the run
    returns to the named state after at least one transition — for the
    monitor's non-terminating regime (notify/off, or a deferred bump):
    under those policies the correct steady-state behavior is the
    watch cycle itself, so the golden run observes one cycle.
    """
    flow_id = FLOW_ID
    try:
        run = s.flow_runs[run_id]
    except KeyError:
        raise ValueError(f"unknown flow run: {run_id}") from None
    trans = [t for t in s.flow_transitions.values() if t.flow_id == flow_id]
    path = [run.current_state_id]
    seq = len(s.flow_transition_events) + 1
    ar_n = 0
    # The accumulator: payload data flows between states by merging each
    # state's emitted context snapshot (the full ctx at that state, stored
    # as the event payload). Replay re-derives the same accumulator by
    # merging the logged snapshots in seq order.
    accum: dict = {}

    for _ in range(max_steps):
        st = s.flow_states[run.current_state_id]
        if st.kind == "end":
            run = run.model_copy(update={
                "state": "done" if st.outcome == "completed" else "aborted"})
            s.flow_runs[run_id] = run
            return path
        if st.kind == "wait":
            trigger, emitted = "timer", {"tick": world.poll_interval_s}
        else:
            ar_n += 1
            ar_id = f"{run_id}-ar{ar_n}"
            s.automaton_runs[ar_id] = AutomatonRun(
                id=ar_id, runbook_id=st.runbook_id, state="running",
                idempotency_key=f"{run_id}:{st.id}:{ar_n}",
                parent_flow_run_id=run_id, flow_state_id=st.id)
            try:
                emitted = _run_runbook(s, st.runbook_id, world, dict(accum))
                trigger = "run_completed"
                new_ar_state = "completed"
            except _RunAborted as e:
                emitted = {"error": str(e)}
                trigger = "run_aborted"
                new_ar_state = "aborted"
            s.automaton_runs[ar_id] = s.automaton_runs[ar_id].model_copy(
                update={"state": new_ar_state})
        accum.update(emitted)
        # I-15 faults (ambiguity or no route) propagate loudly: a broken
        # flow definition must never masquerade as a normal run_aborted.
        nxt = _select(trans, run.current_state_id, trigger, accum, run_id)
        evt_id = f"{run_id}-e{seq}"
        s.flow_transition_events[evt_id] = FlowTransitionEvent(
            id=evt_id, flow_run_id=run_id, seq=seq,
            from_state_id=run.current_state_id, to_state_id=nxt,
            trigger=trigger, payload=_payload_json(emitted))
        seq += 1
        run = run.model_copy(update={"current_state_id": nxt})
        s.flow_runs[run_id] = run
        path.append(nxt)
        if until is not None and nxt == until:
            # One observed cycle of the non-terminating regime.
            return path
    raise RuntimeError("driver exceeded max steps without reaching an end state")


def _run_runbook(s: SystemState, runbook_id: str, world: World,
                 ctx: dict) -> dict:
    """Execute a run-book's steps in seq order starting from ctx (the
    accumulated payload). Steps invoke tools, which mutate ctx. A tool
    raising ToolAborted/NetworkDisabled aborts the run: the driver reports
    run_aborted. Returns ctx (the state's emitted payload, merged by the
    driver into the accumulator)."""
    steps = sorted(
        (st for st in s.steps.values() if st.runbook_id == runbook_id),
        key=lambda st: st.seq)
    try:
        for step in steps:
            if not eval_guard(step.expr, ctx):
                continue  # expr gates the step; 'True' always runs
            tool = TOOLS.get(step.tool_id)
            if tool is None:
                # Unknown tool is a modeling error: abort the run loudly,
                # never crash the driver with a KeyError.
                raise ToolAborted(f"unknown tool: {step.tool_id}")
            tool(ctx, world)
    except (ToolAborted, NetworkDisabled) as e:
        # Mark the failure on the child run, then propagate as run_aborted.
        raise _RunAborted(str(e)) from e
    return ctx


class _RunAborted(Exception):
    pass


def _select(trans: list, from_id: str, trigger: str, payload: dict,
            run_id: str) -> str:
    cands = [t for t in trans
             if t.from_state_id == from_id and t.trigger == trigger]
    winners = [t for t in cands if eval_guard(t.guard, payload)]
    if len(winners) != 1:
        # I-15: ambiguity (or no route) is a fault, not an ordering problem.
        raise _RunAborted(
            f"I-15 fault in {run_id}: {len(winners)} winners for "
            f"({from_id}, {trigger})")
    return winners[0].to_state_id


# ---------------------------------------------------------------------------
# Replay (R1) — re-derive the state path from the event log; tools disabled
# ---------------------------------------------------------------------------

def replay(events: list[FlowTransitionEvent],
           transitions: list[FlowTransition],
           initial_state_id: str) -> list[str]:
    """Re-derive the state path from recorded events. Never invokes tools,
    never touches the network: guards are re-evaluated over recorded
    payloads and the recorded transition must be the unique winner."""
    by_from: dict[str, list[FlowTransition]] = {}
    for t in transitions:
        by_from.setdefault(t.from_state_id, []).append(t)
    path = [initial_state_id]
    current = initial_state_id
    merged: dict = {}  # the accumulator, re-derived by merging the log
    for e in sorted(events, key=lambda e: e.seq):
        if e.from_state_id != current:
            raise ValueError(f"replay: event {e.seq} starts at "
                             f"{e.from_state_id}, expected {current}")
        merged.update(json.loads(e.payload))
        cands = [t for t in by_from.get(current, [])
                 if t.trigger == e.trigger]
        winners = [t for t in cands if eval_guard(t.guard, merged)]
        if len(winners) != 1 or winners[0].to_state_id != e.to_state_id:
            raise ValueError(f"replay: event {e.seq} does not re-derive "
                             f"(winners={[w.id for w in winners]})")
        current = e.to_state_id
        path.append(current)
    return path


def path_hash(path: list[str]) -> str:
    return hashlib.sha256("\n".join(path).encode()).hexdigest()
