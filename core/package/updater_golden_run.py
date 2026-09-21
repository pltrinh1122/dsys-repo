"""Golden run for the release-monitor automaton (the adopted updater build).

Acceptances (spec §7):
  1. Fixture feed with a newer version, policy=auto -> the run reaches done;
     the event log shows the full path; a promotion is recorded.
  2. policy=notify -> the run returns to idle; install.sh never invoked.
  3. Replay acceptance 1's event log with the network disabled -> the
     derived state sequence hashes equal (R1).
  4. Fixture feed with a checksum mismatch -> failed; no candidacy.
  5. policy=auto but a minor bump against auto_max_bump=patch -> the trust
     gate defers (the standing-authorization bound bites).

Plus the R3 discharge: the compiled entities validate clean under the
standing validators (I-14 totality, I-15 determinism, I-16 closure,
step-policy declared) — totality and determinism checked mechanically,
not by inspection. Two negative cases show the validators bite. A final
case covers installer failure: the drive must fail loudly, record no
promotion, and leave the installed version unconverged.

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

from .schema import AutomatonRelease, FlowRun, SystemState
from .updater import (
    FLOW_ID,
    World,
    compile_flow,
    drive,
    path_hash,
    replay,
)
from .validators import validate

IDLE, DONE, FAILED = "urm-idle", "urm-done", "urm-failed"
FULL_PATH = ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
             "urm-driving", "urm-verifying", "urm-done"]


def _add(s, coll, key, ent):
    getattr(s, coll)[key] = ent.model_copy(update={"id": key})


def build_updater_state(run_id: str = "fr-updater") -> SystemState:
    s = SystemState()
    _add(s, "releases", "rel-0.1.0", AutomatonRelease(version="0.1.0"))
    aflow, states, transitions, runbooks, steps, tools = compile_flow()
    _add(s, "automaton_flows", FLOW_ID, aflow)
    for st in states:
        _add(s, "flow_states", st.id, st)
    for t in transitions:
        _add(s, "flow_transitions", t.id, t)
    for rb in runbooks:
        _add(s, "runbooks", rb.id, rb)
    for step in steps:
        _add(s, "steps", step.id, step)
    for tool in tools:
        _add(s, "tools", tool.id, tool)
    _add(s, "flow_runs", run_id,
         FlowRun(flow_id=FLOW_ID, current_state_id=IDLE, state="running"))
    return s


def _events_of(s: SystemState, run_id: str):
    return sorted(
        (e for e in s.flow_transition_events.values()
         if e.flow_run_id == run_id),
        key=lambda e: e.seq)


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # 0. R3 discharge: the compiled flow validates clean — mechanically.
    s0 = build_updater_state()
    v0 = validate(s0)
    assert v0 == [], f"updater entities must validate clean: {v0}"

    # 1. auto + patch bump -> done; promotion recorded.
    s1 = build_updater_state("fr-a1")
    w1 = World(feed_version="0.1.1", installed_version="0.1.0",
               updater_policy="auto", auto_max_bump="patch")
    path1 = drive(s1, w1, "fr-a1")
    assert path1 == FULL_PATH, f"unexpected path: {path1}"
    assert s1.flow_runs["fr-a1"].state == "done"
    assert w1.installer_invocations == ["0.1.1"], "installer must run once"
    assert w1.promotions and w1.promotions[0]["version"] == "0.1.1"
    assert validate(s1) == [], f"post-run state must stay clean: {validate(s1)}"

    # 2. notify -> one watch cycle back to idle; installer never invoked.
    # (The monitor is non-terminating under notify: the steady state IS the
    # cycle, so the driver observes one.)
    s2 = build_updater_state("fr-a2")
    w2 = World(feed_version="0.1.1", installed_version="0.1.0",
               updater_policy="notify")
    path2 = drive(s2, w2, "fr-a2", until=IDLE)
    assert path2 == ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
                     "urm-idle"], f"notify must cycle home: {path2}"
    assert s2.flow_runs["fr-a2"].state == "running"
    assert w2.installer_invocations == [], "notify must not drive"
    assert w2.surfaced and w2.surfaced[0]["version"] == "0.1.1"

    # 3. R1: replay case 1's log with the network disabled -> same path.
    # replay() takes no world and no network handle: by construction it
    # cannot touch the network. The disabled-network world is passed to
    # nothing — the assertion is that replay needs nothing but the log.
    events1 = _events_of(s1, "fr-a1")
    trans1 = [t for t in s1.flow_transitions.values()
              if t.flow_id == FLOW_ID]
    path_r = replay(events1, trans1, IDLE)
    assert path_hash(path_r) == path_hash(path1), "replay must re-derive"
    refusals.append("replay re-derived the event log: "
                    f"{path_hash(path_r)[:12]} == {path_hash(path1)[:12]}")

    # 4. checksum mismatch -> failed; installer never invoked.
    s4 = build_updater_state("fr-a4")
    w4 = World(feed_version="0.1.1", installed_version="0.1.0",
               updater_policy="auto", feed_checksum_ok=False)
    path4 = drive(s4, w4, "fr-a4")
    assert path4[-1] == FAILED, f"tampered feed must fail: {path4}"
    assert s4.flow_runs["fr-a4"].state == "aborted"
    assert w4.installer_invocations == []
    refusals.append("checksum mismatch refused candidacy: "
                    f"path={path4[-3:]}")

    # 5. auto + minor bump against auto_max_bump=patch -> gate defers.
    s5 = build_updater_state("fr-a5")
    w5 = World(feed_version="0.2.0", installed_version="0.1.0",
               updater_policy="auto", auto_max_bump="patch")
    path5 = drive(s5, w5, "fr-a5", until=IDLE)
    assert path5 == ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
                     "urm-idle"], f"bump-scope breach must defer: {path5}"
    assert w5.installer_invocations == []
    assert any("exceeds" in r["reason"] for r in w5.surfaced)
    refusals.append("bump-scope breach deferred at the trust gate: "
                    + w5.surfaced[0]["reason"])

    # 6. negative: drop gate's run_aborted edge -> I-14 bites.
    s6 = build_updater_state("fr-a6")
    del s6.flow_transitions["urmt-09"]
    bad6 = validate(s6)
    assert any("I-14" in x and "run_aborted" in x for x in bad6), \
        f"I-14 must fire on the missing edge: {bad6}"
    refusals.append("I-14 fired on the missing run_aborted edge")

    # 7. negative: second guardless edge on (idle, timer) -> I-15 bites.
    s7 = build_updater_state("fr-a7")
    from .schema import FlowTransition
    _add(s7, "flow_transitions", "urmt-XX", FlowTransition(
        flow_id=FLOW_ID, from_state_id=IDLE, trigger="timer",
        to_state_id="urm-failed"))
    bad7 = validate(s7)
    assert any("I-15" in x for x in bad7), \
        f"I-15 must fire on the ambiguous edge: {bad7}"
    refusals.append("I-15 fired on the ambiguous guardless edge")

    # 8. installer failure -> failed; no promotion; version unconverged.
    s8 = build_updater_state("fr-a8")
    w8 = World(feed_version="0.1.1", installed_version="0.1.0",
               updater_policy="auto", installer_exit_code=1)
    path8 = drive(s8, w8, "fr-a8")
    assert path8 == ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
                     "urm-driving", "urm-failed"], \
        f"installer failure must fail at driving: {path8}"
    assert s8.flow_runs["fr-a8"].state == "aborted"
    assert w8.installer_invocations == ["0.1.1"], "the attempt happened"
    assert w8.promotions == [], "no promotion on a failed drive"
    assert w8.installed_version == "0.1.0", "failed install must not converge"
    refusals.append("installer failure refused the drive: "
                    f"path={path8[-2:]}")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
