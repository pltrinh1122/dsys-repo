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

K1 repair acceptances (DR-CMD-039, spec §Acceptance + I-18/19/20):
  A1. A drive reaching done leaves exactly one commit containing all
      events since the last commit (I-18), content-hash named (I-19),
      append-only (I-20); the message names the flow-run id and verifying.
  A2. A drive aborting in driving/verifying reaches failed with no commit.
  A3. Crash simulation: the World wiped except the accretion repo — the
      committed payload alone replays byte-equal (the R1 premise made true).
  A4. Flow table: 9 states, 16 transitions; totality + determinism pass.
  A5. committing -> done requires commit_confirmed: an unconfirmed
      completion is a loud I-15 fault, never done; a skip still confirms.
  A6. accretion.commit_authority=operator -> run_aborted -> failed; refused,
      never silently skipped.
  D4a. Abort, not retry: a failed commit leaves nothing; the next drive's
      cumulative commit covers the orphaned events.
  D4b. Bounded residual: drive N's terminal edge rides drive N+1's commit.
  D5a. git absent -> run_aborted -> failed (hard dependency, fail-closed).

K1 Q3a acceptances (DR-CMD-047, spec §Acceptances + I-25):
  A1. Matching identity (fixture installation mints both sides
      consistently, D1) -> the drive commits; the payload is
      byte-identical (R1).
  A2. Wrong identity (dsys.repo-id != manifest) -> run_aborted ->
      failed; refused, never silently skipped.
  A3. Missing key on either side (no dsys.repo-id; manifest records
      no identity) -> run_aborted -> failed.
  A4. Not-a-repo -> run_aborted -> failed (the D5a case, unchanged).
  R3. I-25 fires on mismatch, on each missing key, and on the D5a
      conjunct; clean on the bound triple.

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

import json

from .schema import AutomatonRelease, FlowRun, FlowTransitionEvent, SystemState
from .updater import (
    FLOW_ID,
    TOOLS,
    World,
    _RunAborted,
    _tool_commit_accretion,
    compile_flow,
    drive,
    i18_commit_completeness,
    i19_payload_canonicity,
    i20_append_only,
    i25_identity_binding,
    mint_repo_identity,
    path_hash,
    replay,
)
from .validators import validate

IDLE, DONE, FAILED = "urm-idle", "urm-done", "urm-failed"
FULL_PATH = ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
             "urm-driving", "urm-verifying", "urm-committing", "urm-done"]


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


def _event_dicts(s: SystemState):
    """The flow log in the dict form the writer embeds in commit payloads."""
    return [{
        "seq": e.seq,
        "from_state_id": e.from_state_id,
        "to_state_id": e.to_state_id,
        "trigger": e.trigger,
        "payload": json.loads(e.payload),
    } for e in sorted(s.flow_transition_events.values(),
                      key=lambda e: e.seq)]


def _add_run(s: SystemState, run_id: str) -> None:
    """A second drive sharing one SystemState (cumulative-commit cases)."""
    _add(s, "flow_runs", run_id,
         FlowRun(flow_id=FLOW_ID, current_state_id=IDLE, state="running"))


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # 0. R3 discharge: the compiled flow validates clean — mechanically.
    # K1-A4: 9 states, 16 transitions; totality + determinism over the table.
    s0 = build_updater_state()
    v0 = validate(s0)
    assert v0 == [], f"updater entities must validate clean: {v0}"
    states0 = [st for st in s0.flow_states.values()
               if st.flow_id == FLOW_ID]
    trans0 = [t for t in s0.flow_transitions.values()
              if t.flow_id == FLOW_ID]
    assert len(states0) == 9, f"9 states, got {len(states0)}"
    assert len(trans0) == 16, f"16 transitions, got {len(trans0)}"
    assert any(st.name == "committing" and st.kind == "task"
               for st in states0), "committing must be a task state"

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

    # K1-A1: the done drive leaves exactly one commit (I-18) containing all
    # events since the last commit, content-hash named (I-19), append-only
    # (I-20); the message names the flow-run id and the source state.
    assert len(w1.accretion_commits) == 1, "exactly one commit"
    c1 = w1.accretion_commits[0]
    assert i18_commit_completeness([], w1.accretion_commits,
                                   _event_dicts(s1)) == []
    assert i19_payload_canonicity(c1) == []
    assert i20_append_only(w1.accretion_commits) == []
    assert c1["message"].startswith("accretion: fr-a1 from verifying "), \
        f"message must name the run and source state: {c1['message']}"
    assert "events 1-6" in c1["message"], \
        f"commit covers the pre-terminal frontier: {c1['message']}"
    assert c1["first_seq"] == 1 and c1["last_seq"] == 6
    payload1 = json.loads(c1["payload"])
    assert payload1["schema"] == "accretion-commit/v1"
    assert payload1["verification"] == {"doctor_ok": True,
                                        "promotion_recorded": True}
    assert payload1["policy_decision"]["decision"] == "drive"
    assert len(payload1["promotions"]) == 1
    refusals.append("accretion commit written: " + c1["message"])

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
    # K1-A2: a drive aborting in driving reaches failed with no commit.
    assert w8.accretion_commits == [], "incomplete drive must not commit"
    refusals.append("installer failure refused the drive: "
                    f"path={path8[-2:]}")

    # K2 repair acceptances (DR-CMD-038).
    def _acc(argv):  # the --accretion-path value of an invocation
        return argv[argv.index("--accretion-path") + 1]

    # 9. (A1) unwritable accretion path -> refuse-the-drive: failed; the
    # attempt carried the explicit path + --accretion-required; no
    # promotion; version unconverged; never --overwrite.
    s9 = build_updater_state("fr-a9")
    w9 = World(feed_version="0.1.1", installed_version="0.1.0",
               updater_policy="auto", accretion_writable=False)
    path9 = drive(s9, w9, "fr-a9")
    assert path9 == ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
                     "urm-driving", "urm-failed"], \
        f"unwritable accretion must refuse the drive: {path9}"
    assert s9.flow_runs["fr-a9"].state == "aborted"
    assert len(w9.installer_argvs) == 1, "the attempt happened"
    assert "--accretion-required" in w9.installer_argvs[0]
    assert _acc(w9.installer_argvs[0]) == "/var/daccretion/dsys-inst"
    assert "--overwrite" not in w9.installer_argvs[0]
    assert w9.promotions == [], "no promotion on a refused drive"
    assert w9.installed_version == "0.1.0", "refused drive must not converge"
    refusals.append("unwritable accretion refused the drive: "
                    f"path={path9[-2:]}")

    # 10. (A2) previous home with config-overridden accretion.path -> the
    # drive pins THAT path, not the default rule.
    s10 = build_updater_state("fr-a10")
    w10 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto",
                prev_install_home="/home/op/old-inst",
                prev_accretion_path="/data/custom-accretion")
    path10 = drive(s10, w10, "fr-a10")
    assert path10 == FULL_PATH, f"unexpected path: {path10}"
    assert _acc(w10.installer_argvs[0]) == "/data/custom-accretion", \
        "must pin the previous install's effective path"
    assert "--overwrite" not in w10.installer_argvs[0]
    refusals.append("config-overridden accretion path pinned: "
                    + _acc(w10.installer_argvs[0]))

    # 11. (A3) first install (no previous home) -> fresh repo at the path
    # derived from our own home; the drive proceeds to done.
    s11 = build_updater_state("fr-a11")
    w11 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto", prev_install_home=None)
    path11 = drive(s11, w11, "fr-a11")
    assert path11 == FULL_PATH, f"unexpected path: {path11}"
    assert _acc(w11.installer_argvs[0]) == "/var/daccretion/dsys-inst"
    assert "--overwrite" not in w11.installer_argvs[0]
    assert w11.promotions and w11.promotions[0]["version"] == "0.1.1"
    refusals.append("first install derived a fresh accretion path: "
                    + _acc(w11.installer_argvs[0]))

    # 12. (A4) contract: no updater invocation ever carries --overwrite.
    for _w in (w1, w8, w9, w10, w11):
        for _argv in _w.installer_argvs:
            assert "--overwrite" not in _argv, "updater must never --overwrite"
    refusals.append("no invocation carried --overwrite (D5 contract)")

    # 13. (A5) replay of the refused drive (case 9) re-derives — R1 untouched.
    events9 = _events_of(s9, "fr-a9")
    trans9 = [t for t in s9.flow_transitions.values()
              if t.flow_id == FLOW_ID]
    path_r9 = replay(events9, trans9, IDLE)
    assert path_hash(path_r9) == path_hash(path9), "replay must re-derive"
    refusals.append("replay re-derived the refused drive: "
                    f"{path_hash(path_r9)[:12]} == {path_hash(path9)[:12]}")

    # 14. (K1-A2) drive aborting in verifying (doctor fails) -> failed at
    # verifying; no commit. Acceptance of the D1 narrowing: durability
    # attaches to completed drives; the incomplete drive's events surface
    # via the failed terminal state.
    s14 = build_updater_state("fr-a14")
    w14 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto", doctor_ok=False)
    path14 = drive(s14, w14, "fr-a14")
    assert path14 == ["urm-idle", "urm-checking", "urm-candidate", "urm-gate",
                      "urm-driving", "urm-verifying", "urm-failed"], \
        f"doctor failure must fail at verifying: {path14}"
    assert s14.flow_runs["fr-a14"].state == "aborted"
    assert w14.accretion_commits == [], "incomplete drive must not commit"
    assert w14.promotions == [], "no promotion without doctor_ok"
    refusals.append("verifying-abort left no commit (D1 narrowing)")

    # 15. (K1-A3) crash simulation: wipe the World except the accretion
    # repo. The committed payload alone — parsed from the repo, never from
    # the live state — replays byte-equal (the R1 premise made true).
    wiped = World()
    wiped.accretion_commits = w1.accretion_commits  # the repo survives
    assert i19_payload_canonicity(wiped.accretion_commits[0]) == []
    payload15 = json.loads(wiped.accretion_commits[0]["payload"])
    crash_events = [
        FlowTransitionEvent(
            id=f"crash-e{e['seq']}", flow_run_id="fr-crash", seq=e["seq"],
            from_state_id=e["from_state_id"], to_state_id=e["to_state_id"],
            trigger=e["trigger"], payload=json.dumps(e["payload"]))
        for e in payload15["events"]]
    trans1b = [t for t in s1.flow_transitions.values()
               if t.flow_id == FLOW_ID]
    path_crash = replay(crash_events, trans1b, IDLE)
    assert path_crash == path1[:-1], \
        f"repo payload must replay the pre-terminal path: {path_crash}"
    refusals.append("crash simulation: repo payload replayed byte-equal")

    # 16. (K1-A5) committing -> done requires commit_confirmed. A tool that
    # completes without confirming faults loudly on the guard — never done.
    real_tool = TOOLS["tool-commit-accretion"]
    TOOLS["tool-commit-accretion"] = lambda ctx, w: ctx.update(
        {"sabotaged": True})
    try:
        s16 = build_updater_state("fr-a16")
        w16 = World(feed_version="0.1.1", installed_version="0.1.0",
                    updater_policy="auto")
        try:
            drive(s16, w16, "fr-a16")
            raise AssertionError("sabotaged commit must not reach done")
        except Exception as e:  # noqa: BLE001 — the fault type is the point
            assert "commit_confirmed" in str(e), \
                f"must fault on the unconfirmed guard: {e!r}"
            refusals.append("unconfirmed commit faulted loudly on the guard, "
                            "never done")
    finally:
        TOOLS["tool-commit-accretion"] = real_tool

    # 17. (K1-A5, skip rule) the writer skipped with nothing new still
    # confirms — the step completed; the guard is confirmation, not bytes.
    # The driver's input channel is popped, never emitted.
    w17 = World()
    w17.accretion_commits.append({
        "payload": '{"schema":"accretion-commit/v1"}', "payload_hash": "x",
        "message": "seed", "first_seq": 1, "last_seq": 99,
        "promotions_through": 0})
    ctx17 = {"_commit_input": {"run_id": "fr-x", "source_state": "verifying",
                              "events": [{"seq": i} for i in range(1, 100)]}}
    _tool_commit_accretion(ctx17, w17)
    assert ctx17["commit_confirmed"] is True
    assert ctx17["commit_skipped"] is True
    assert len(w17.accretion_commits) == 1, "skip writes nothing"
    assert "_commit_input" not in ctx17, "input channel never emitted"
    refusals.append("skip-with-nothing-new confirmed without writing")

    # 18. (K1-A6) accretion.commit_authority=operator -> the commit step
    # refuses via run_aborted -> failed; no prompt, nothing silently skipped.
    s18 = build_updater_state("fr-a18")
    w18 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto", accretion_commit_authority="operator")
    path18 = drive(s18, w18, "fr-a18")
    assert path18[-2:] == ["urm-committing", "urm-failed"], \
        f"operator authority must refuse at committing: {path18}"
    assert s18.flow_runs["fr-a18"].state == "aborted"
    assert w18.accretion_commits == [], "refused commit writes nothing"
    refusals.append("operator commit authority refused loudly at committing")

    # 19. (K1-D5a) git absent -> run_aborted -> failed: the hard dependency
    # fails closed; nothing is committed, nothing silently skipped.
    s19 = build_updater_state("fr-a19")
    w19 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto", git_available=False)
    path19 = drive(s19, w19, "fr-a19")
    assert path19[-2:] == ["urm-committing", "urm-failed"], \
        f"absent git must fail the drive: {path19}"
    assert w19.accretion_commits == []
    refusals.append("absent git failed the drive closed (D5a)")

    # 20. (K1-D4a) abort, not retry: drive 1's commit fails (git down) and
    # leaves nothing; drive 2's cumulative commit covers the orphaned
    # events — the retry. Exactly one commit total.
    s20 = build_updater_state("fr-a20")
    w20 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto", git_available=False)
    path20a = drive(s20, w20, "fr-a20")
    assert path20a[-1] == FAILED
    assert w20.accretion_commits == [], "failed commit leaves nothing"
    w20.git_available = True
    w20.feed_version = "0.1.2"
    _add_run(s20, "fr-a20b")
    before20 = [dict(c) for c in w20.accretion_commits]
    path20b = drive(s20, w20, "fr-a20b")
    assert path20b == FULL_PATH, f"unexpected path: {path20b}"
    assert len(w20.accretion_commits) == 1, "exactly one commit total"
    c20 = w20.accretion_commits[0]
    assert c20["first_seq"] == 1, "cumulative from the first orphaned event"
    assert i18_commit_completeness(before20, w20.accretion_commits,
                                   _event_dicts(s20)) == []
    assert i19_payload_canonicity(c20) == []
    assert i20_append_only(w20.accretion_commits) == []
    payload20 = json.loads(c20["payload"])
    assert len(payload20["promotions"]) == 2, \
        "the orphaned promotion rides the cumulative commit"
    refusals.append("aborted commit retried cumulatively by the next drive: "
                    + c20["message"])

    # 21. (K1-D4b) bounded residual: drive 1's terminal edge rides drive 2's
    # commit — never the payload, at most the edge.
    s21 = build_updater_state("fr-a21")
    w21 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto")
    path21a = drive(s21, w21, "fr-a21")
    assert path21a == FULL_PATH
    assert w21.accretion_commits[0]["last_seq"] == 6, \
        "drive 1's commit stops before its terminal edge (event 7)"
    w21.feed_version = "0.1.2"
    _add_run(s21, "fr-a21b")
    before21 = [dict(c) for c in w21.accretion_commits]
    path21b = drive(s21, w21, "fr-a21b")
    assert path21b == FULL_PATH
    c21 = w21.accretion_commits[1]
    assert (c21["first_seq"], c21["last_seq"]) == (7, 13), \
        f"drive 2's commit picks up the residual edge: {c21['first_seq']}-" \
        f"{c21['last_seq']}"
    assert i18_commit_completeness(before21, w21.accretion_commits,
                                   _event_dicts(s21)) == []
    assert i19_payload_canonicity(c21) == []
    assert i20_append_only(w21.accretion_commits) == []
    refusals.append("bounded residual: terminal edge rode the next commit: "
                    + c21["message"])

    # 22. (K1-I-20 negative) a mutated committed payload breaks its
    # content-hash name — I-20 fires. Append-only is tamper-evident.
    tampered = [dict(c) for c in w1.accretion_commits]
    tampered[0] = dict(tampered[0])
    tampered[0]["payload"] = tampered[0]["payload"].replace(
        "0.1.1", "9.9.9", 1)
    bad22 = i20_append_only(tampered)
    assert any("I-20" in x for x in bad22), \
        f"I-20 must fire on the mutated payload: {bad22}"
    refusals.append("I-20 fired on the mutated committed payload")

    # 23. (K1-I-18 negative) a commit gapped from the watermark — I-18 fires.
    bad23 = i18_commit_completeness(
        w1.accretion_commits,
        w1.accretion_commits + [dict(w1.accretion_commits[0],
                                    first_seq=8, last_seq=10)],
        _event_dicts(s1))
    assert any("I-18" in x for x in bad23), \
        f"I-18 must fire on the gapped commit: {bad23}"
    refusals.append("I-18 fired on the gapped commit")

    # 24. (K1 Q3a-A1) matching identity -> the drive commits. The
    # fixture installation mints both sides consistently (D1); the
    # I-25 predicate is clean; the committing tool writes.
    s24 = build_updater_state("fr-a24")
    w24 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto")
    assert w24.manifest_repo_identity is not None
    assert w24.accretion_repo_id == w24.manifest_repo_identity, \
        "the fixture installation mints both sides consistently (D1)"
    assert i25_identity_binding(w24.manifest_repo_identity,
                                w24.accretion_repo_id,
                                w24.git_available) == []
    path24 = drive(s24, w24, "fr-a24")
    assert path24 == FULL_PATH, f"unexpected path: {path24}"
    assert len(w24.accretion_commits) == 1, "matching identity commits"
    assert i19_payload_canonicity(w24.accretion_commits[0]) == [], \
        "the identity check leaves the payload byte-identical (R1)"
    refusals.append("matching repo identity: the drive committed (D3)")

    # 25. (K1 Q3a-A2) wrong identity -> run_aborted -> failed: the
    # handle resolves to a repo that is not this installation's —
    # fail closed, nothing committed, nothing silently skipped.
    s25 = build_updater_state("fr-a25")
    w25 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto")
    w25.accretion_repo_id = "00000000-0000-0000-0000-000000000000"
    path25 = drive(s25, w25, "fr-a25")
    assert path25[-2:] == ["urm-committing", "urm-failed"], \
        f"wrong identity must fail the drive: {path25}"
    assert s25.flow_runs["fr-a25"].state == "aborted"
    assert w25.accretion_commits == [], "refused commit writes nothing"
    refusals.append("wrong repo identity failed the drive closed (D3)")

    # 26. (K1 Q3a-A3) missing dsys.repo-id -> run_aborted -> failed:
    # the missing key is a binding failure, not a default-allow.
    s26 = build_updater_state("fr-a26")
    w26 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto")
    w26.accretion_repo_id = None
    path26 = drive(s26, w26, "fr-a26")
    assert path26[-2:] == ["urm-committing", "urm-failed"], \
        f"missing repo key must fail the drive: {path26}"
    assert w26.accretion_commits == [], "refused commit writes nothing"
    refusals.append("missing dsys.repo-id failed the drive closed (D3)")

    # 27. (K1 Q3a-A3) manifest records no identity -> run_aborted ->
    # failed: the minter's record is absent, so there is nothing to
    # verify against — fail closed.
    s27 = build_updater_state("fr-a27")
    w27 = World(feed_version="0.1.1", installed_version="0.1.0",
                updater_policy="auto")
    w27.manifest_repo_identity = None
    path27 = drive(s27, w27, "fr-a27")
    assert path27[-2:] == ["urm-committing", "urm-failed"], \
        f"missing manifest identity must fail the drive: {path27}"
    assert w27.accretion_commits == [], "refused commit writes nothing"
    refusals.append("missing manifest identity failed the drive closed")

    # 28. (K1 Q3a-R3) I-25 fires on every violation shape and is clean
    # on the bound triple — the predicate, not the procedure.
    good_id = mint_repo_identity()
    assert i25_identity_binding(good_id, good_id, True) == []
    bad28a = i25_identity_binding(good_id, mint_repo_identity(), True)
    assert any("I-25" in x and "match" in x for x in bad28a), \
        f"I-25 must fire on mismatch: {bad28a}"
    bad28b = i25_identity_binding(good_id, None, True)
    assert any("I-25" in x and "dsys.repo-id" in x for x in bad28b), \
        f"I-25 must fire on the missing repo key: {bad28b}"
    bad28c = i25_identity_binding(None, good_id, True)
    assert any("I-25" in x and "manifest" in x for x in bad28c), \
        f"I-25 must fire on the missing manifest identity: {bad28c}"
    bad28d = i25_identity_binding(good_id, good_id, False)
    assert any("I-25" in x and "D5a" in x for x in bad28d), \
        f"I-25 must fire on the D5a conjunct: {bad28d}"
    refusals.append("I-25 fired on mismatch, missing keys, and the "
                    "D5a conjunct; clean on the bound triple")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
