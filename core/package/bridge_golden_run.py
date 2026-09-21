"""Golden run for the bridge (the adopted DR-CMD-037 build).

Acceptances (spec §7):
  1. The release-monitor source, compiled by the bridge, yields entities
     equal (by serialized hash, per collection) to updater.compile_flow()
     output — the bridge subsumes the one-off path, byte-for-byte.
  2. A second automaton (heartbeat), authored purely as an AutomatonSource,
     compiled by the bridge, executed, with replay-hash equality between
     the live run and the log re-derivation.
  3. Refusals: dangling runbook_id, unknown tool id, non-allowlisted guard,
     and schema-closure violations are compile-time refusals (loud).
  4. Determinism: compiling the same source bytes twice yields
     byte-identical entity sets.

Plus the R3 discharge: B-1/B-2/B-3 are enforced inside compile()
(BridgeRefused on violation), and the compiled output validates clean
under the standing validators I-14/I-15/I-16 — mechanically.

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from .bridge import (
    AutomatonSource,
    AutomatonState,
    AutomatonTransition,
    BridgeRefused,
    RunBookSource,
    RunBookStepSource,
    compile as bridge_compile,
    entities_hash,
    release_monitor_source,
    updater_tool_registry,
)
from .schema import (
    AutomatonRelease,
    AutomatonRun,
    FlowRun,
    FlowTransitionEvent,
    SystemState,
)
from .updater import compile_flow, eval_guard, path_hash, replay
from .validators import validate


class _StepAborted(Exception):
    pass


def _coll_hash(items) -> str:
    return hashlib.sha256(
        json.dumps([x.model_dump(mode="json") for x in items],
                   sort_keys=True).encode()).hexdigest()


def _add(s, coll, key, ent):
    getattr(s, coll)[key] = ent.model_copy(update={"id": key})


def _build_state(source: AutomatonSource, tools: dict,
                 run_id: str) -> SystemState:
    s = SystemState()
    aflow, states, transitions, runbooks, steps, tool_ents = bridge_compile(
        source, tools)
    flow_id = aflow.id
    _add(s, "releases", f"rel-{source.release_version}",
         AutomatonRelease(version=source.release_version))
    _add(s, "automaton_flows", flow_id, aflow)
    for st in states:
        _add(s, "flow_states", st.id, st)
    for t in transitions:
        _add(s, "flow_transitions", t.id, t)
    for rb in runbooks:
        _add(s, "runbooks", rb.id, rb)
    for step in steps:
        _add(s, "steps", step.id, step)
    for tool in tool_ents:
        _add(s, "tools", tool.id, tool)
    init = [st for st in states if st.name == source.initial_state][0]
    _add(s, "flow_runs", run_id,
         FlowRun(flow_id=flow_id, current_state_id=init.id,
                 state="running"))
    return s


def _select_loud(trans, from_id, trigger, payload, run_id):
    cands = [t for t in trans
             if t.from_state_id == from_id and t.trigger == trigger]
    winners = [t for t in cands if eval_guard(t.guard, payload)]
    if len(winners) != 1:
        raise _StepAborted(
            f"I-15 fault in {run_id}: {len(winners)} winners for "
            f"({from_id}, {trigger})")
    return winners[0].to_state_id


def _drive(s: SystemState, flow_id: str, run_id: str, tools: dict,
           world, max_steps: int = 50) -> list[str]:
    """Minimal deterministic walker over compiled entities (test
    scaffolding, mirroring updater.drive's semantics)."""
    try:
        run = s.flow_runs[run_id]
    except KeyError:
        raise ValueError(f"unknown flow run: {run_id}") from None
    trans = [t for t in s.flow_transitions.values()
             if t.flow_id == flow_id]
    path = [run.current_state_id]
    seq = 1
    accum: dict = {}
    ar_n = 0
    for _ in range(max_steps):
        st = s.flow_states[run.current_state_id]
        if st.kind == "end":
            run = run.model_copy(update={
                "state": "done" if st.outcome == "completed" else "aborted"})
            s.flow_runs[run_id] = run
            return path
        if st.kind == "wait":
            trigger, emitted = "timer", {"tick": 1}
        else:
            ar_n += 1
            steps = sorted(
                (x for x in s.steps.values()
                 if x.runbook_id == st.runbook_id),
                key=lambda x: x.seq)
            ctx = dict(accum)
            try:
                for step in steps:
                    if not eval_guard(step.expr, ctx):
                        continue
                    tool = tools.get(step.tool_id)
                    if tool is None:
                        raise _StepAborted(
                            f"unknown tool: {step.tool_id}")
                    tool(ctx, world)
            except _StepAborted as e:
                emitted, trigger = {"error": str(e)}, "run_aborted"
            else:
                emitted, trigger = ctx, "run_completed"
        accum.update(emitted)
        nxt = _select_loud(trans, run.current_state_id, trigger, accum,
                           run_id)
        evt_id = f"{run_id}-e{seq}"
        s.flow_transition_events[evt_id] = FlowTransitionEvent(
            id=evt_id, flow_run_id=run_id, seq=seq,
            from_state_id=run.current_state_id, to_state_id=nxt,
            trigger=trigger, payload=json.dumps(emitted, sort_keys=True))
        seq += 1
        run = run.model_copy(update={"current_state_id": nxt})
        s.flow_runs[run_id] = run
        path.append(nxt)
    raise RuntimeError("walker exceeded max steps")


@dataclass
class HeartbeatWorld:
    ticks: list[int] = field(default_factory=list)


def _tool_emit_tick(ctx: dict, w: HeartbeatWorld) -> None:
    w.ticks.append(1)
    ctx["ticks"] = len(w.ticks)


def heartbeat_source() -> AutomatonSource:
    return AutomatonSource(
        name="heartbeat",
        release_version="0.1.0",
        initial_state="idle",
        states=[
            AutomatonState(name="idle", kind="wait"),
            AutomatonState(name="beating", kind="task",
                           runbook_id="rb-heartbeat",
                           step_policy="abort"),
            AutomatonState(name="done", kind="end", outcome="completed"),
            AutomatonState(name="failed", kind="end", outcome="aborted"),
        ],
        transitions=[
            AutomatonTransition(from_state="idle", trigger="timer",
                                to_state="beating"),
            AutomatonTransition(from_state="beating",
                                trigger="run_completed",
                                guard=("payload.ticks == 1 or "
                                       "payload.ticks == 2"),
                                to_state="idle"),
            AutomatonTransition(from_state="beating",
                                trigger="run_completed",
                                guard="payload.ticks == 3",
                                to_state="done"),
            AutomatonTransition(from_state="beating",
                                trigger="run_aborted",
                                to_state="failed"),
        ],
        runbooks=[
            RunBookSource(id="rb-heartbeat", name="rb-heartbeat", steps=[
                RunBookStepSource(tool_id="tool-emit-tick")]),
        ],
    )


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    src = release_monitor_source()
    registry = updater_tool_registry()

    # 0. R3 discharge: bridge-compiled entities validate clean under the
    # standing validators — mechanically.
    s0 = _build_state(src, registry, "fr-b0")
    v0 = validate(s0)
    assert v0 == [], f"bridge output must validate clean: {v0}"

    # 1. §7.1: byte-for-byte equality with updater.compile_flow().
    be = bridge_compile(src, registry)
    le = compile_flow()
    names = ["flow", "states", "transitions", "runbooks", "steps", "tools"]
    for name, b, l in zip(names, be, le):
        b_items = b if isinstance(b, list) else [b]
        l_items = l if isinstance(l, list) else [l]
        hb, hl = _coll_hash(b_items), _coll_hash(l_items)
        assert hb == hl, f"§7.1: {name} differ: {hb[:12]} != {hl[:12]}"
    refusals.append("§7.1: bridge output == compile_flow() output, "
                    "all six collections, byte-for-byte")

    # 2. §7.4: compile twice -> byte-identical.
    h1 = entities_hash(bridge_compile(src, registry))
    h2 = entities_hash(bridge_compile(src, registry))
    assert h1 == h2, "recompile must be byte-identical"
    refusals.append(f"§7.4: recompile hash equality {h1[:12]} == {h2[:12]}")

    # 3. Refusals — all loud, all at compile time.
    def expect_refusal(label, mut):
        import copy
        bad = copy.deepcopy(src)
        bad = mut(bad)
        try:
            bridge_compile(bad, registry)
        except BridgeRefused as e:
            refusals.append(f"{label}: refused "
                            f"({str(e).splitlines()[0][:80]})")
        else:
            raise AssertionError(f"{label}: should have refused")

    def _with_states(s, states):
        return s.model_copy(update={"states": states})

    expect_refusal(
        "dangling runbook_id",
        lambda s: _with_states(s, [
            AutomatonState(name="idle", kind="wait"),
            AutomatonState(name="x", kind="task", runbook_id="rb-nope",
                           step_policy="abort"),
        ]))
    expect_refusal(
        "unknown tool id",
        lambda s: s.model_copy(update={"runbooks": [
            RunBookSource(id="rb-bad", name="rb-bad", steps=[
                RunBookStepSource(tool_id="tool-nope")])]}))
    expect_refusal(
        "non-allowlisted guard",
        lambda s: s.model_copy(update={"transitions": [
            AutomatonTransition(from_state="idle", trigger="timer",
                                guard="__import__('os').system('x')",
                                to_state="idle")]}))
    # B-3 at the bridge level: a smuggled kind via model_construct.
    smuggled = src.model_copy(update={
        "states": [s.model_construct(
            **{**s.model_dump(), "kind": "quantum"}) for s in src.states]})
    try:
        bridge_compile(smuggled, registry)
    except BridgeRefused as e:
        refusals.append("schema closure (B-3): refused "
                        f"({str(e).splitlines()[0][:80]})")
    else:
        raise AssertionError("B-3: smuggled kind should have refused")
    # Pydantic-level: empty runbooks refused before compile (model_copy
    # skips validation, so this goes through the validating constructor).
    try:
        AutomatonSource.model_validate(
            {**src.model_dump(), "runbooks": []})
    except ValidationError:
        refusals.append("pydantic: empty runbooks refused at the model")
    else:
        raise AssertionError("empty runbooks should have refused")

    # 4. §7.2: the heartbeat — authored purely as source, compiled,
    # executed, replay hash equality.
    hb_src = heartbeat_source()
    hb_tools = {"tool-emit-tick": _tool_emit_tick}
    sh = _build_state(hb_src, hb_tools, "fr-hb")
    assert validate(sh) == [], f"heartbeat must validate: {validate(sh)}"
    wh = HeartbeatWorld()
    hb_flow_id = "flow-heartbeat"
    path = _drive(sh, hb_flow_id, "fr-hb", hb_tools, wh)
    h_idle, h_beating, h_done = ("heartbeat-s-idle", "heartbeat-s-beating",
                                 "heartbeat-s-done")
    assert path == [h_idle, h_beating, h_idle, h_beating, h_idle,
                    h_beating, h_done], f"unexpected path: {path}"
    assert sh.flow_runs["fr-hb"].state == "done"
    assert wh.ticks == [1, 1, 1], "tool must fire exactly 3 times"
    events = sorted(
        (e for e in sh.flow_transition_events.values()
         if e.flow_run_id == "fr-hb"), key=lambda e: e.seq)
    trans = [t for t in sh.flow_transitions.values()
             if t.flow_id == hb_flow_id]
    path_r = replay(events, trans, h_idle)
    assert path_hash(path_r) == path_hash(path), "replay must re-derive"
    refusals.append("§7.2: heartbeat compiled, driven to done in 3 ticks, "
                    f"replay hash equality {path_hash(path)[:12]}")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
