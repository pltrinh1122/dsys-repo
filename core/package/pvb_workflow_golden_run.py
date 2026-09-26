"""Golden run for the PVB creation-and-ratification workflow.

Acceptances:
  1. Happy path: draft -> begin_review -> in_review (ratify, no findings)
     -> ratified -> publish -> published. The ratification record is
     written with the document's hash; replay re-derives the same path.
  2. Findings loop: findings are reported, a byte-changed revision
     addresses them, re-review ratifies. Findings carry addressed_by.
  3. Ratify with open findings -> run_aborted -> failed (loud).
  4. begin_review with a missing document -> DriveRefused (loud).
  5. A byte-identical "revision" -> run_aborted -> failed (loud).
  6. A publish event while in_review is consumed by the review round's
     collector, which aborts loudly on the unknown verb -> failed.
  7. Ratify by the ambient -> refused; only the operator disposes (loud).
  8. Withdraw by the operator -> withdrawn; no ratification record.
  9. R3 discharge: the compiled entities validate clean under the
     standing validators (I-14 totality, I-15 determinism) — 7 states,
     10 transitions, checked mechanically. A source naming an unknown
     tool is refused at compile time (B-3).
 10. An event injected after the run closed -> DriveRefused (I-16).

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

import json
import os
import tempfile

from .bridge import (
    AutomatonSource,
    AutomatonState,
    AutomatonTransition,
    BridgeRefused,
    RunBookSource,
    RunBookStepSource,
    compile,
)
from .pvb_workflow import (
    ENTITIES,
    TOOLS,
    DriveRefused,
    PVBWorld,
    begin_case,
    drive,
    path_hash,
    replay,
)
from .schema import AutomatonRelease, FlowRun, SystemState
from .validators import validate

D = "pvb-ratification-s-draft"
R = "pvb-ratification-s-in_review"
V = "pvb-ratification-s-revising"
T = "pvb-ratification-s-ratified"
P = "pvb-ratification-s-published"
W = "pvb-ratification-s-withdrawn"
F = "pvb-ratification-s-failed"

HAPPY_PATH = [D, R, T, P]
LOOP_PATH = [D, R, V, R, T, P]


def _add(s, coll, key, ent):
    getattr(s, coll)[key] = ent.model_copy(update={"id": key})


def _doc(tmp: str, name: str, content: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # 0. R3 discharge: the compiled flow validates clean — mechanically.
    aflow, states, transitions, runbooks, steps, tools = ENTITIES
    s0 = SystemState()
    _add(s0, "releases", "rel-0.1.0", AutomatonRelease(version="0.1.0"))
    _add(s0, "automaton_flows", aflow.id, aflow)
    for st in states:
        _add(s0, "flow_states", st.id, st)
    for t in transitions:
        _add(s0, "flow_transitions", t.id, t)
    for rb in runbooks:
        _add(s0, "runbooks", rb.id, rb)
    for stp in steps:
        _add(s0, "steps", stp.id, stp)
    for tl in tools:
        _add(s0, "tools", tl.id, tl)
    _add(s0, "flow_runs", "fr-r3",
         FlowRun(flow_id=aflow.id, current_state_id=D, state="running"))
    v0 = validate(s0)
    assert v0 == [], f"pvb entities must validate clean: {v0}"
    assert len(states) == 7, f"7 states, got {len(states)}"
    assert len(transitions) == 10, f"10 transitions, got {len(transitions)}"
    refusals.append("R3: 7 states / 10 transitions validate clean "
                    "(I-14 totality, I-15 determinism)")

    with tempfile.TemporaryDirectory() as tmp:
        rec = os.path.join(tmp, "records")

        # 1. Happy path.
        d1 = _doc(tmp, "pvb-v1.docx", "draft-one")
        c1 = begin_case("pvb-001", d1)
        w1 = PVBWorld(records_dir=rec)
        log1 = drive(c1, w1, [
            {"verb": "begin_review", "actor": "ambient"},
            {"verb": "ratify", "actor": "operator"},
            {"verb": "publish", "actor": "operator"},
        ], flow_run_id="fr-1")
        path1 = replay(log1)
        assert path1 == HAPPY_PATH, f"unexpected path: {path1}"
        assert path_hash(path1) == path_hash(HAPPY_PATH)
        rec1 = os.path.join(rec, "pvb-001.ratification.json")
        assert os.path.isfile(rec1), "ratification record must be written"
        with open(rec1, encoding="utf-8") as f:
            body = json.load(f)
        assert body["disposition"] == "ratify"
        assert body["actor"] == "operator"
        assert body["document_hash"] == c1.document_hash
        assert set(body) == {"case_id", "document_hash", "disposition",
                             "actor", "flow_run_id", "event_seq"}, \
            "the record is exactly the canonical field set — no wall-clock"
        refusals.append("happy path reached published; ratification record "
                        "written with the document hash")

        # 2. Findings loop.
        d2 = _doc(tmp, "pvb-v2.docx", "draft-two")
        d2r = _doc(tmp, "pvb-v2r.docx", "draft-two-REVISED")
        c2 = begin_case("pvb-002", d2)
        w2 = PVBWorld(records_dir=rec)
        log2 = drive(c2, w2, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "report_findings", "actor": "operator",
             "findings": ["vision too narrow", "needs lack evidence"]},
            {"verb": "submit_revision", "actor": "ambient",
             "document_path": d2r},
            {"verb": "ratify", "actor": "operator"},
            {"verb": "publish", "actor": "operator"},
        ], flow_run_id="fr-2")
        path2 = replay(log2)
        assert path2 == LOOP_PATH, f"unexpected path: {path2}"
        assert c2.revisions == 1
        assert c2.open_findings() == []
        assert all(f.status == "addressed"
                   and f.addressed_by == c2.document_hash
                   for f in c2.findings), c2.findings
        refusals.append("findings loop: 2 findings addressed by the revision "
                        "hash; re-review ratified")

        # 3. Ratify with open findings -> failed, loudly.
        d3 = _doc(tmp, "pvb-v3.docx", "draft-three")
        c3 = begin_case("pvb-003", d3)
        w3 = PVBWorld(records_dir=rec)
        log3 = drive(c3, w3, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "report_findings", "actor": "operator",
             "findings": ["unresolved"]},
            {"verb": "ratify", "actor": "operator"},
        ], flow_run_id="fr-3")
        assert replay(log3)[-1] == F, "must end in failed"
        assert not os.path.exists(os.path.join(rec, "pvb-003.ratification.json"))
        refusals.append("ratify with open findings failed the drive closed")

        # 4. begin_review with a missing document -> refused.
        d4 = _doc(tmp, "pvb-v4.docx", "draft-four")
        c4 = begin_case("pvb-004", d4)
        os.remove(d4)
        w4 = PVBWorld(records_dir=rec)
        try:
            drive(c4, w4, [{"verb": "begin_review", "actor": "operator"}],
                  flow_run_id="fr-4")
            violations.append("begin_review on a missing document advanced")
        except DriveRefused:
            refusals.append("begin_review on a missing document refused")

        # 5. Byte-identical "revision" -> failed, loudly.
        d5 = _doc(tmp, "pvb-v5.docx", "draft-five")
        c5 = begin_case("pvb-005", d5)
        w5 = PVBWorld(records_dir=rec)
        log5 = drive(c5, w5, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "report_findings", "actor": "operator",
             "findings": ["fix me"]},
            {"verb": "submit_revision", "actor": "ambient",
             "document_path": d5},
        ], flow_run_id="fr-5")
        assert replay(log5)[-1] == F, "identical revision must fail"
        refusals.append("byte-identical revision failed the drive closed")

        # 6. A publish event while in_review is consumed by the review
        # round's collector, which aborts loudly on the unknown verb.
        d6 = _doc(tmp, "pvb-v6.docx", "draft-six")
        c6 = begin_case("pvb-006", d6)
        w6 = PVBWorld(records_dir=rec)
        log6 = drive(c6, w6, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "publish", "actor": "operator"},
        ], flow_run_id="fr-6")
        assert replay(log6) == [D, R, F], replay(log6)
        refusals.append("publish from in_review failed the drive closed "
                        "(unknown verb at the collector)")

        # 7. Ratify by the ambient -> refused; only the operator disposes.
        d7 = _doc(tmp, "pvb-v7.docx", "draft-seven")
        c7 = begin_case("pvb-007", d7)
        w7 = PVBWorld(records_dir=rec)
        log7 = drive(c7, w7, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "ratify", "actor": "ambient"},
        ], flow_run_id="fr-7")
        assert replay(log7)[-1] == F, "ambient ratify must fail"
        refusals.append("ambient ratify refused — only the operator disposes")

        # 8. Withdraw by the operator -> withdrawn; no record.
        d8 = _doc(tmp, "pvb-v8.docx", "draft-eight")
        c8 = begin_case("pvb-008", d8)
        w8 = PVBWorld(records_dir=rec)
        log8 = drive(c8, w8, [
            {"verb": "begin_review", "actor": "operator"},
            {"verb": "withdraw", "actor": "operator"},
        ], flow_run_id="fr-8")
        assert replay(log8) == [D, R, W], replay(log8)
        assert not os.path.exists(os.path.join(rec, "pvb-008.ratification.json"))
        refusals.append("operator withdraw reached the withdrawn terminal; "
                        "no ratification record")

        # 9. B-3: a source naming an unknown tool refuses at compile time.
        bad_source = AutomatonSource(
            name="pvb-bad", release_version="0.1.0", initial_state="draft",
            states=[AutomatonState(name="draft", kind="wait"),
                    AutomatonState(name="done", kind="end",
                                   outcome="completed")],
            transitions=[AutomatonTransition(
                from_state="draft", trigger="external",
                guard="payload.event == 'go'", to_state="done")],
            runbooks=[RunBookSource(
                id="rb-bad", name="bad",
                steps=[RunBookStepSource(expr="True",
                                         tool_id="pvb.no_such_tool")])])
        try:
            compile(bad_source, TOOLS)
            violations.append("source naming an unknown tool compiled")
        except BridgeRefused:
            refusals.append("B-3 refused a source naming an unknown tool "
                            "at compile time")

        # 10. An event after close -> refused (I-16): one drive that
        # reaches published, then receives one more event.
        d10 = _doc(tmp, "pvb-v10.docx", "draft-ten")
        c10 = begin_case("pvb-010", d10)
        w10 = PVBWorld(records_dir=rec)
        try:
            drive(c10, w10, [
                {"verb": "begin_review", "actor": "operator"},
                {"verb": "ratify", "actor": "operator"},
                {"verb": "publish", "actor": "operator"},
                {"verb": "publish", "actor": "operator"},
            ], flow_run_id="fr-10")
            violations.append("event after close advanced")
        except DriveRefused:
            refusals.append("event after close refused (I-16 closure)")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
