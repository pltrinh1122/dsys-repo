"""Golden run for the production-drive contract (DR-CMD-050).

Acceptances (spec §Acceptances):
  1. An operator-initiated drive via the flow-drive surface runs to
     completion bearing the D3-verified handle; the transcript
     records the initiator and principal; the drive-resolved
     manifest identity is what the tool verified (D5).
  2. An ambient-originated initiation (no operator instruction) is
     refused — the drive does not start (the K3 tripwire, D4).
  3. Identity mismatch mid-drive -> D3 aborts -> the drive ends
     failed; no retry within the drive, no re-initiation (D7); the
     failure is recorded and surfaced.
  4. Base-profile invocation -> refused, naming the component (D6;
     the CLI maps the refusal to exit 1).
  5. Replay: the drive transcript re-validates; initiation metadata
     does not break the replay-identity (R1).

Plus the R3 discharge: I-26 fires on every broken conjunct and is
clean on the authorized tuple — the predicate, not the procedure.

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
Refusals are the expected-loud cases behaving correctly; violations
are unexpected failures (any assertion firing fails the run).
"""
from __future__ import annotations

import json

from .updater import (
    FLOW_ID,
    DriveInitiation,
    DriveRefused,
    World,
    drive,
    i25_identity_binding,
    i26_authorized_initiation,
    mint_repo_identity,
    path_hash,
    production_drive,
    replay,
)
from .updater_golden_run import _events_of, build_updater_state

IDLE, DONE, FAILED = "urm-idle", "urm-done", "urm-failed"
FULL_PATH = ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
             "urm-driving", "urm-verifying", "urm-committing", "urm-done"]


def _world() -> World:
    return World(feed_version="0.1.1", installed_version="0.1.0",
                 updater_policy="auto")


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # 1. (A1) operator-initiated drive -> done; the initiation record
    # is in the drive record; the drive-resolved manifest identity is
    # what the D3 check verified (D5: read once at initiation).
    s1 = build_updater_state("fr-d1")
    w1 = _world()
    init1 = DriveInitiation()  # the authorized tuple: operator /
    # operator-direct / dyad-or-human / strapped / full
    assert i26_authorized_initiation(init1) == [], \
        f"I-26 must be clean on the authorized tuple: " \
        f"{i26_authorized_initiation(init1)}"
    rec1 = production_drive(s1, w1, init1, "fr-d1")
    assert rec1["state"] == "done", f"the drive must complete: {rec1}"
    assert rec1["path"] == FULL_PATH, f"unexpected path: {rec1['path']}"
    assert rec1["initiation"]["initiator"] == "operator"
    assert rec1["initiation"]["principal"] == "dyad-or-human"
    assert rec1["initiation"]["harness_strapped"] is True
    assert rec1["initiation"]["manifest_identity"] == \
        w1.manifest_repo_identity, \
        "the drive runs under the initiation-resolved identity (D5)"
    assert i25_identity_binding(rec1["initiation"]["manifest_identity"],
                                w1.accretion_repo_id,
                                w1.git_available) == [], \
        "the D3 check verified the drive-resolved identity"
    assert len(w1.accretion_commits) == 1, "the drive committed"
    refusals.append("operator-initiated drive completed under the "
                    "D3-verified handle; initiation recorded")

    # 2. (A2) ambient-originated initiation -> refused: the drive does
    # not start (D4 — the K3 tripwire as a gate). Refusal is not
    # failure: no events, nothing surfaced, the run never started.
    s2 = build_updater_state("fr-d2")
    w2 = _world()
    init2 = DriveInitiation(initiator="ambient", origin="ambient")
    bad2 = i26_authorized_initiation(init2)
    assert any("K3" in x for x in bad2), \
        f"I-26 must fire the K3 tripwire: {bad2}"
    try:
        production_drive(s2, w2, init2, "fr-d2")
        raise AssertionError("ambient-originated initiation must refuse")
    except DriveRefused as e:
        refusals.append(f"ambient-originated initiation refused: {e}")
    assert len(s2.flow_transition_events) == 0, \
        "the refused drive started nothing"
    assert w2.surfaced == [], "refusal surfaces nothing (nothing failed)"
    assert w2.accretion_commits == [], "the refused drive wrote nothing"

    # 3. (A3) identity mismatch mid-drive -> D3 aborts -> failed; the
    # wrapper does not retry and does not re-initiate (D7); the failure
    # is recorded and surfaced.
    s3 = build_updater_state("fr-d3")
    w3 = _world()
    w3.accretion_repo_id = "00000000-0000-0000-0000-000000000000"
    rec3 = production_drive(s3, w3, DriveInitiation(), "fr-d3")
    assert rec3["state"] == "failed", f"the drive must fail: {rec3}"
    assert rec3["path"][-2:] == ["urm-committing", "urm-failed"], \
        f"the D3 check aborts the drive: {rec3['path']}"
    assert s3.flow_runs["fr-d3"].state == "aborted"
    assert len(s3.flow_runs) == 1, \
        "no re-initiation: one call starts exactly one drive"
    assert w3.accretion_commits == [], "fail-closed writes nothing"
    assert len(w3.surfaced) == 1, "the failure is surfaced once"
    surf3 = w3.surfaced[0]
    assert surf3["kind"] == "drive_failed" and surf3["run_id"] == "fr-d3"
    assert surf3["initiation"]["initiator"] == "operator", \
        "the surfaced failure carries the initiation record"
    assert rec3["surfaced"] is surf3
    refusals.append("identity mismatch failed the drive closed; the "
                    "failure was recorded and surfaced, no retry")

    # 4. (A4) base profile -> refused, naming the component (D6). The
    # fixture raises DriveRefused; the CLI surface maps it to exit 1
    # naming the component (cli-interface-spec §3.7).
    s4 = build_updater_state("fr-d4")
    w4 = _world()
    try:
        production_drive(s4, w4, DriveInitiation(profile="base"), "fr-d4")
        raise AssertionError("base profile must refuse")
    except DriveRefused as e:
        assert "production-drive contract" in str(e), \
            f"the refusal must name the component: {e}"
        refusals.append(f"base profile refused, naming the component: {e}")
    assert len(s4.flow_transition_events) == 0, \
        "the refused drive started nothing"

    # 5. (A5) R1: replay case 1's log with the network disabled -> the
    # same path. The initiation record lives in the drive record
    # (the transcript envelope), never in the event log: assert it is
    # absent from every event payload, so initiation metadata cannot
    # break the replay-identity.
    events1 = _events_of(s1, "fr-d1")
    trans1 = [t for t in s1.flow_transitions.values()
              if t.flow_id == FLOW_ID]
    for e in events1:
        payload = json.loads(e.payload)
        assert "initiator" not in payload and "manifest_identity" \
            not in payload, \
            f"initiation metadata must not enter the event log: {e.id}"
    path_r = replay(events1, trans1, IDLE)
    assert path_hash(path_r) == path_hash(rec1["path"]), \
        "replay must re-derive the drive's path"
    refusals.append("replay re-derived the drive's path; initiation "
                    "metadata absent from the event log (R1)")

    # 6. (R3) I-26 fires on every broken conjunct and is clean on the
    # authorized tuple — the predicate, not the procedure.
    good = DriveInitiation()
    assert i26_authorized_initiation(good) == []
    bad6a = i26_authorized_initiation(
        DriveInitiation(initiator="ambient", origin="ambient"))
    assert any("operator principal" in x for x in bad6a), \
        f"I-26 must fire on a non-operator initiator: {bad6a}"
    assert any("K3" in x for x in bad6a), \
        f"I-26 must fire the K3 tripwire: {bad6a}"
    bad6b = i26_authorized_initiation(DriveInitiation(origin="cron-job"))
    assert any("unknown initiation origin" in x for x in bad6b), \
        f"I-26 must fire on an unknown origin: {bad6b}"
    bad6c = i26_authorized_initiation(DriveInitiation(principal="agent"))
    assert any("agents excluded" in x for x in bad6c), \
        f"I-26 must fire on a non-dyad principal: {bad6c}"
    bad6d = i26_authorized_initiation(DriveInitiation(harness_strapped=False))
    assert any("Harness" in x for x in bad6d), \
        f"I-26 must fire on an unstrapped drive: {bad6d}"
    # The operator-instructed origin is authorized: the ambient acting
    # on the operator's explicit instruction is the operator's act.
    assert i26_authorized_initiation(
        DriveInitiation(origin="operator-instructed")) == [], \
        "operator-instructed initiation is authorized (D1)"
    refusals.append("I-26 fired on every broken conjunct; clean on the "
                    "authorized tuple incl. operator-instructed")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
