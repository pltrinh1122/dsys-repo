#!/usr/bin/env python3
"""Synthetic flow-driver tests: paths the production updater flow cannot
reach (its transitions are deterministic by I-15 design). Exercises
executor.advance_flow directly with hand-built flow specs.

Covers: multi-winner abort+disclosure, child completion routing via
run_completed/run.status, missing payload fields (None semantics),
wait-state payload guards, end-state closure, FlowDefinitionError on
unknown run-book.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib" / "dsys"))
import executor as X

PASS, FAIL = 0, 0


def ok(name):
    global PASS
    PASS += 1
    print(f"ok   {name}")


def bad(name, info=""):
    global FAIL
    FAIL += 1
    print(f"FAIL {name} {info}")


def fresh_home():
    h = Path(tempfile.mkdtemp())
    (h / "var" / "runs").mkdir(parents=True)
    return h


def flow_run(home, current="s0", state="open"):
    frun = {"run_id": "fr-test", "kind": "flow", "flow_id": "fx-flow",
            "state": state, "current_state_id": current, "events": []}
    return frun


RB_FIX = {"runbook_id": "fx-pass", "release_version": "1.0.0",
          "steps": [{"seq": 0, "tool": "noop", "expr": "True"}]}
TOOLS = {"noop": lambda ctx: {"ok": True, "result": {}, "ctx_delta": {}}}


def resolver(rb):
    return lambda rid: RB_FIX if rid == "fx-pass" else None


BASE_FLOW = {
    "flow_id": "fx-flow",
    "initial_state_id": "s0",
    "states": {
        "s0": {"kind": "wait"},
        "s1": {"kind": "task", "runbook_id": "fx-pass",
               "step_policy": "abort"},
        "s2": {"kind": "end", "outcome": "completed"},
        "s3": {"kind": "end", "outcome": "aborted"},
    },
    "transitions": [
        {"id": "t1", "from_state_id": "s0", "trigger": "timer",
         "guard": "payload.go", "to_state_id": "s1"},
        {"id": "t2", "from_state_id": "s1", "trigger": "run_completed",
         "guard": "run.status == 'completed'", "to_state_id": "s2"},
        {"id": "t3", "from_state_id": "s1", "trigger": "run_aborted",
         "guard": "True", "to_state_id": "s3"},
    ],
}

# 1. wait-state payload guard routes timer -> s1 (one step at a time)
home = fresh_home()
frun = flow_run(home)
res = X.advance_flow(frun, BASE_FLOW, resolver("fx-pass"), TOOLS, home,
                     trigger="timer", payload={"go": True}, max_steps=1)
if frun["current_state_id"] == "s1" and res["transitions_taken"] == 1:
    ok("wait payload guard routes")
else:
    bad("wait payload guard routes", res)

# 2. child completion: the task state's child runs to completion, the
# run_completed trigger routes s1 -> s2, end state closes the flow done
res = X.advance_flow(frun, BASE_FLOW, resolver("fx-pass"), TOOLS, home)
if frun["state"] == "done" and frun["current_state_id"] == "s2":
    ok("child completion routes to end state")
else:
    bad("child completion routes", {"state": frun["state"],
                                    "at": frun["current_state_id"]})
kinds = [(e["from_state_id"], e["to_state_id"], e["trigger"])
         for e in frun["events"]]
if kinds == [("s0", "s1", "timer"), ("s1", "s2", "run_completed")]:
    ok("flow events recorded in order")
else:
    bad("flow events", kinds)
child_files = [p for p in (home / "var" / "runs").glob("*.json")
               if json.load(open(p)).get("kind") == "run"]
if len(child_files) == 1:
    child = json.load(open(child_files[0]))
    if child["state"] == "completed" and child["policy"] == "abort":
        ok("child spawned once, task step_policy governs")
    else:
        bad("child record", child["state"])
else:
    bad("child spawned once", len(child_files))

# 3. missing payload field: guard over absent keys is falsy (None), so
# the transition does not win -> unhandled trigger -> abort+disclosure
home = fresh_home()
frun = flow_run(home)
flow2 = json.loads(json.dumps(BASE_FLOW))
flow2["transitions"][0]["guard"] = \
    "payload.remote_version != payload.installed_version"
res = X.advance_flow(frun, flow2, resolver("fx-pass"), TOOLS, home,
                     trigger="timer", payload={})
dls = list((home / "var" / "disclosures").glob("dl-*.json"))
if frun["state"] == "aborted" and len(dls) == 1:
    d = json.load(open(dls[0]))
    if d["kind"] == "automaton-exception" and d["trigger"] == "timer":
        ok("missing payload field -> abort + disclosure")
    else:
        bad("disclosure content", d)
else:
    bad("missing payload field", {"state": frun["state"], "dls": len(dls)})

# 4. multiple winners: two true guards on the same trigger -> the
# determinism invariant fires -> abort + disclosure (I-15 enforced)
home = fresh_home()
frun = flow_run(home)
flow3 = json.loads(json.dumps(BASE_FLOW))
flow3["transitions"].append(
    {"id": "t4", "from_state_id": "s0", "trigger": "timer",
     "guard": "payload.go", "to_state_id": "s3"})
res = X.advance_flow(frun, flow3, resolver("fx-pass"), TOOLS, home,
                     trigger="timer", payload={"go": True})
dls = list((home / "var" / "disclosures").glob("dl-*.json"))
if frun["state"] == "aborted" and len(dls) == 1 \
        and frun["current_state_id"] == "s0":
    ok("multi-winner -> abort + disclosure, state unchanged")
else:
    bad("multi-winner", {"state": frun["state"],
                         "at": frun["current_state_id"],
                         "dls": len(dls)})

# 5. quiescence: wait state with no trigger is a no-op (no events)
home = fresh_home()
frun = flow_run(home)
res = X.advance_flow(frun, BASE_FLOW, resolver("fx-pass"), TOOLS, home)
if res["transitions_taken"] == 0 and res["events_appended"] == 0 \
        and frun["state"] == "open":
    ok("wait with no trigger is quiescent")
else:
    bad("quiescence", res)

# 6. unknown run-book in a task state: definition error, loud
home = fresh_home()
frun = flow_run(home, current="s1")
flow4 = json.loads(json.dumps(BASE_FLOW))
try:
    X.advance_flow(frun, flow4, lambda rid: None, TOOLS, home)
    bad("unknown run-book", "no error raised")
except X.FlowDefinitionError as e:
    if "unknown run-book" in str(e):
        ok("unknown run-book raises FlowDefinitionError")
    else:
        bad("unknown run-book", str(e))

# 7. bad trigger / payload shapes are usage errors
home = fresh_home()
for kwargs, want in [({"trigger": "bogus"}, "bad trigger"),
                     ({"trigger": "timer", "payload": [1]}, "JSON object"),
                     ({"payload": {"a": 1}}, "without --trigger")]:
    try:
        X.advance_flow(flow_run(home), BASE_FLOW, resolver("fx-pass"),
                       TOOLS, home, **kwargs)
        bad(f"usage {kwargs}", "no error")
    except ValueError as e:
        if want in str(e):
            ok(f"usage error: {want}")
        else:
            bad(f"usage {kwargs}", str(e))

# 8. child idempotency: repeated advances reuse the spawned child
home = fresh_home()
frun = flow_run(home)
for _ in range(3):
    X.advance_flow(frun, BASE_FLOW, resolver("fx-pass"), TOOLS, home,
                   trigger="timer", payload={"go": True}, max_steps=1)
n = len([p for p in (home / "var" / "runs").glob("*.json")
         if json.load(open(p)).get("kind") == "run"])
if n == 1:
    ok("child spawn idempotent across advances")
else:
    bad("child idempotency", n)

# 9. child ctx becomes the run_completed trigger payload (§7)
TOOLS2 = dict(TOOLS)
TOOLS2["emit"] = lambda ctx: {"ok": True, "result": {},
                              "ctx_delta": {"v": 2}}
RB_EMIT = {"runbook_id": "fx-emit", "release_version": "1.0.0",
           "steps": [{"seq": 0, "tool": "emit", "expr": "True"}]}
FLOW_P = {
    "flow_id": "fx-flow-p",
    "initial_state_id": "s0",
    "states": {
        "s0": {"kind": "wait"},
        "s1": {"kind": "task", "runbook_id": "fx-emit",
               "step_policy": "abort"},
        "s2": {"kind": "end", "outcome": "completed"},
        "s3": {"kind": "end", "outcome": "aborted"},
    },
    "transitions": [
        {"id": "t1", "from_state_id": "s0", "trigger": "timer",
         "to_state_id": "s1"},
        {"id": "t2", "from_state_id": "s1", "trigger": "run_completed",
         "guard": "payload.v == 2", "to_state_id": "s2"},
        {"id": "t3", "from_state_id": "s1", "trigger": "run_aborted",
         "to_state_id": "s3"},
    ],
}
home = fresh_home()
frun = flow_run(home)
res = X.advance_flow(frun, FLOW_P, lambda rid: RB_EMIT, TOOLS2, home,
                     trigger="timer", payload={})
ev = [e for e in frun["events"]
      if e["from_state_id"] == "s1"][0]
if frun["state"] == "done" and frun["current_state_id"] == "s2" \
        and ev["trigger"] == "run_completed" and ev["payload"] == {"v": 2}:
    ok("child ctx minted as run_completed payload")
else:
    bad("payload propagation", {"state": frun["state"],
                                "at": frun["current_state_id"],
                                "ev": ev})

print(f"--- {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
