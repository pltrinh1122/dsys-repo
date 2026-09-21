"""Golden run: the adopted scenario simulation (DR-CMD-041, built under DR-CMD-044).

This file is not a Harness instance (AX2) — it is a unittest-style
assertion suite like updater_golden_run.py. It plays the strapped driver
(D3): the scenario interpreter is scenario_sim's; this file drives it and
asserts the acceptances A1..A6 from doc/scenario-simulation-spec.md section 5.

  A1. End-to-end hardening: brief → authored scenario → strapped-driver
      execution against a manifest-provisioned sandbox → I-23 PASS →
      operator disposition → spec placed, golden-run case added → full
      chain PASS, 0 violations.
  A2. Containment: the live install path (or any path outside the sandbox
      root) → I-21 violation → refused before execution, nothing
      constructed, nothing mutated.
  A3. Separation: kind=simulation presented to the accretion writer →
      refused (I-22); the disclosure funnel refuses; predicate checks.
  A4. Gate: I-23 PASS with no cited disposition → hardening refused
      (I-24); the suite is unchanged. Unknown standing classes refused.
  A5. Anti-flood: a brief rephrasing an existing suite case → I-23 fails on
      all; the brief's budget still bounds authorship (F-S1).
  A6. Refusal coverage: the K2 accretion refusal path hardens via the
      narrow refusal-path standing class; its case asserts the refusal.

Run from the workspace root:
  PYTHONPATH=core python3 -m package.scenario_sim_golden_run

Returns a dict with keys: violations (list[str]), refusals (list[str]),
ok (bool). Prints RESULT: PASS / FAIL.
"""
from __future__ import annotations

import hashlib
import json

from .scenario_sim import (
    STANDING_HARDENING_CLASSES,
    Brief,
    BudgetExhausted,
    ContainmentRefused,
    FlowPair,
    HardenedCase,
    HardeningRefused,
    ScenarioSpec,
    ScenarioSuite,
    ScenarioTurn,
    SeparationRefused,
    SimulationTranscript,
    adjudicate,
    author_scenario,
    coverage_report,
    covers_new_pair,
    disclose_from_transcript,
    event_pairs,
    execute_scenario,
    harden,
    i21_containment,
    i22_transcript_separation,
    make_scenario_world,
    provision_sandbox,
    retire_brief,
    run_scenario,
)
from .updater import FLOW_ID, ToolAborted, World, _tool_commit_accretion
from .validators import validate

LIVE = "/home/op/dsys-inst"  # the fixture's live installation path

# D9: the installation manifest's declared state (stipulated in the fixture;
# production cites an installer-issued manifest — G6 Q2).
MANIFEST = {
    "installed_version": "0.1.0",
    "release": "0.1.0",
    "config": {
        "updater_policy": "auto",
        "accretion_path": "/var/daccretion/dsys-inst",
    },
}

CANONICAL_MANIFEST = json.dumps(MANIFEST, sort_keys=True, separators=(",", ":"))
MANIFEST_HASH = hashlib.sha256(CANONICAL_MANIFEST.encode()).hexdigest()


def _expect_fail(fn, exc, needle, note):
    try:
        fn()
    except exc as e:
        assert needle in str(e), f"{note}: expected {needle!r} in {e}"
        return str(e)
    raise AssertionError(f"{note}: expected refusal ({exc.__name__})")


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []
    suite = ScenarioSuite()

    # ---------------------------------------------------------------
    # A1. End-to-end hardening.
    # ---------------------------------------------------------------
    brief1 = Brief(
        id="brief-k2fb-1",
        source_falsification="K2 F-B: unwritable accretion path",
        survivor_under_test="K2 fail-closed drive (DR-CMD-038)",
        risk_question=(
            "does the survivor hold under permission-flapping mid-drive?"),
        budget=3,
    )
    spec1 = ScenarioSpec(
        id="sim-flap-gate-1", brief_id="brief-k2fb-1",
        target_flow_id=FLOW_ID,
        narrative=(
            "F-B flap, gate variant: the operator, remediating an accretion "
            "refusal, hand-edits the policy mid-cycle and typos it. The gate "
            "must abort loudly rather than degrade silently."),
        turns=[
            ScenarioTurn(actor="world", input={
                "feed_version": "0.1.1",
                "installed_version": "0.1.0",
                "updater_policy": "autoo",  # the typo
            }),
            ScenarioTurn(actor="driver", input={"run_id": "fr-sim-a1"}),
            ScenarioTurn(actor="referee", input={}, expect={
                "ends_at": "urm-failed",
                "covers": [["urmt-09", "unguarded"]],
            }),
        ],
    )
    brief1, spec1 = author_scenario(brief1, spec1)  # D1: budget consumed
    assert brief1.authored == 1 and not brief1.retired
    sandbox1 = provision_sandbox(MANIFEST, "/tmp/sim-sbx-a1")  # D9
    assert sandbox1.manifest_hash == MANIFEST_HASH, "sandbox derives from the manifest"
    assert sandbox1.id == provision_sandbox(MANIFEST, "/tmp/sim-sbx-a1").id, (
        "provisioning is deterministic")
    assert sandbox1.manifest_source == "stipulated-fixture", (
        "fidelity provenance is recorded (G6 Q2)")
    # D3: the strapped driver executes against the sandbox copy.
    state1, world1, path1, events1 = execute_scenario(
        spec1, sandbox1, LIVE, "fr-sim-a1")
    assert world1.install_home == "/tmp/sim-sbx-a1/dsys-inst", (
        "the scenario World is rooted under the sandbox root")
    assert validate(state1) == [], (
        f"simulated state must validate clean, got {validate(state1)}")
    tx1: SimulationTranscript = adjudicate(
        spec1, sandbox1, "fr-sim-a1", path1, events1)
    assert tx1.kind == "simulation", "kind set at construction (D7)"
    assert path1 == ["urm-idle", "urm-checking", "urm-candidate",
                     "urm-gate", "urm-failed"], f"path {path1}"
    assert tx1.terminal_pair == FlowPair(
        transition_id="urmt-09", guard_outcome="unguarded")
    # D4: the coverage verdict against the (seeded) suite.
    report1 = coverage_report(spec1.id, tx1, suite, "rep-a1")
    assert report1.passes and len(report1.new_pairs) == 4, (
        f"I-23 passes with 4 new pairs, got {len(report1.new_pairs)}")
    # D5: operator disposition (per-scenario DecisionRecord) → harden.
    case1: HardenedCase = harden(
        scenario=spec1, transcript=tx1, report=report1, suite=suite,
        disposition_ref="DR-SIM-001")
    assert len(suite.cases) == 1
    assert suite.cases[0].disposition_ref == "DR-SIM-001"
    assert suite.transcripts[tx1.id] is tx1
    refusals.append("A1: brief→scenario→sandbox execution→I-23 PASS→"
                    "DR-SIM-001→hardened; full chain 0 violations")

    # ---------------------------------------------------------------
    # A2. Containment: I-21 refusals before construction.
    # ---------------------------------------------------------------
    sandbox2 = provision_sandbox(MANIFEST, "/tmp/sim-sbx-a2")
    assert i21_containment("/tmp/sim-sbx-a2/dsys-inst",
                           "/tmp/sim-sbx-a2", LIVE) == [], (
        "a sandbox-rooted path is contained")
    bad_live = i21_containment(LIVE, "/tmp/sim-sbx-a2", LIVE)
    assert any("I-21" in x and "live" in x for x in bad_live), bad_live
    bad_out = i21_containment("/etc/evil", "/tmp/sim-sbx-a2", LIVE)
    assert any("I-21" in x and "outside" in x for x in bad_out), bad_out
    # A2's positive control: a World CAN be constructed against a sandbox.
    w2 = make_scenario_world(sandbox2, LIVE)
    assert w2.install_home == "/tmp/sim-sbx-a2/dsys-inst"
    for bad_home in (LIVE, "/etc/evil"):
        _expect_fail(
            lambda h=bad_home: make_scenario_world(
                sandbox2, LIVE, install_home=h),
            ContainmentRefused, "I-21",
            f"A2: naming {bad_home} refuses before construction")
    # And the refused turns (I-22's writer-side twin) share the rule:
    assert i22_transcript_separation([
        {"kind": "simulation", "destination": "accretion-writer"},
        {"kind": "simulation", "destination": "disclosure"},
        {"kind": "simulation", "destination": "replay-corpus"},
    ]) and all("I-22" in x for x in i22_transcript_separation([
        {"kind": "simulation", "destination": "accretion-writer"},
        {"kind": "simulation", "destination": "disclosure"},
        {"kind": "simulation", "destination": "replay-corpus"},
    ])), "simulation kind is barred from all production destinations"
    assert i22_transcript_separation([
        {"kind": "production", "destination": "accretion-writer"},
    ]) == [], "production kind is not barred"
    refusals.append("A2: I-21 refused the live path and the outside path "
                    "before construction; nothing constructed, nothing mutated")

    # ---------------------------------------------------------------
    # A3. Separation: the accretion writer refuses simulation kind (I-22).
    # ---------------------------------------------------------------
    w3 = World()
    presented = tx1.as_commit_input()
    assert presented["kind"] == "simulation"
    _expect_fail(lambda: _tool_commit_accretion(
        {"_commit_input": presented}, w3), ToolAborted, "I-22",
        "A3: the accretion writer refuses kind=simulation")
    assert w3.accretion_commits == [], "the refused write commits nothing"
    # The single transcript→disclosure funnel refuses (DR-5: no other path
    # exists, so simulation transcripts are absent from disclosure views by
    # construction).
    _expect_fail(lambda: disclose_from_transcript(tx1, "the gate aborted"),
                 SeparationRefused, "I-22",
                 "A3: the disclosure funnel refuses simulation transcripts")
    refusals.append("A3: I-22 refused the simulation transcript at the "
                    "accretion writer and the disclosure funnel")

    # ---------------------------------------------------------------
    # A4. The gate: I-23 PASS without disposition → refused (I-24).
    # ---------------------------------------------------------------
    brief4 = Brief(
        id="brief-a4",
        source_falsification="A4 control: already-current feed",
        survivor_under_test="the monitor's no-delta cycle",
        risk_question="does a no-delta poll cycle home cleanly?",
        budget=2,
    )
    spec4 = ScenarioSpec(
        id="sim-nodelta-1", brief_id="brief-a4", target_flow_id=FLOW_ID,
        narrative=("Stale-feed flap: the candidate release was retracted; "
                   "this poll sees no delta."),
        turns=[
            ScenarioTurn(actor="world", input={
                "feed_version": "0.1.0", "installed_version": "0.1.0",
                "updater_policy": "auto"}),
            ScenarioTurn(actor="driver", input={
                "run_id": "fr-sim-a4", "until": "urm-idle"}),
            ScenarioTurn(actor="referee", input={}, expect={
                "ends_at": "urm-idle",
                "covers": [["urmt-03", "guard-true"]]}),
        ],
    )
    brief4, spec4 = author_scenario(brief4, spec4)
    sandbox4 = provision_sandbox(MANIFEST, "/tmp/sim-sbx-a4")
    tx4 = run_scenario(spec4, sandbox4, LIVE, "fr-sim-a4")
    report4 = coverage_report(spec4.id, tx4, suite, "rep-a4")
    assert report4.passes, "urmt-03/guard-true is new to the suite"
    assert FlowPair(transition_id="urmt-03",
                    guard_outcome="guard-true") in set(report4.new_pairs)
    before4 = list(suite.cases)
    _expect_fail(lambda: harden(scenario=spec4, transcript=tx4,
                                report=report4, suite=suite),
                 HardeningRefused, "I-24",
                 "A4: I-23 PASS without a disposition refuses")
    _expect_fail(lambda: harden(scenario=spec4, transcript=tx4,
                                report=report4, suite=suite,
                                disposition_ref=""),
                 HardeningRefused, "I-24",
                 "A4: an empty disposition is no disposition")
    assert suite.cases == before4, (
        "refused hardening leaves the suite unchanged")
    # A rubber-stamp standing class is refused (F-S2).
    _expect_fail(lambda: harden(scenario=spec4, transcript=tx4,
                                report=report4, suite=suite,
                                standing_class="harden-everything"),
                 HardeningRefused, "I-24",
                 "A4: an unenumerated standing class is a rubber stamp")
    # The refusal-path class admits only refusal terminals.
    _expect_fail(lambda: harden(scenario=spec4, transcript=tx4,
                                report=report4, suite=suite,
                                standing_class="refusal-path"),
                 HardeningRefused, "I-24",
                 "A4: refusal-path rejects a non-refusal terminal")
    refusals.append("A4: I-24 refused hardening without a cited "
                    "disposition; suite unchanged")

    # ---------------------------------------------------------------
    # A5. Anti-flood: rephrasing a hardened case covers nothing new.
    # ---------------------------------------------------------------
    brief5 = Brief(
        id="brief-b5",
        source_falsification="K2 F-B (rephrase control)",
        survivor_under_test="K2 fail-closed drive (DR-CMD-038)",
        risk_question="control: does a rephrased scenario harden?",
        budget=1,
    )
    spec5 = ScenarioSpec(
        id="sim-flap-gate-1b", brief_id="brief-b5",
        target_flow_id=FLOW_ID,
        narrative=("Rephrase of sim-flap-gate-1: the same gate-typo "
                   "mechanism, retold."),
        turns=[
            ScenarioTurn(actor="world", input={
                "feed_version": "0.1.1",
                "installed_version": "0.1.0",
                "updater_policy": "autoo"}),
            ScenarioTurn(actor="driver", input={"run_id": "fr-sim-a5"}),
            ScenarioTurn(actor="referee", input={}, expect={
                "ends_at": "urm-failed",
                "covers": [["urmt-09", "unguarded"]]}),
        ],
    )
    brief5, spec5 = author_scenario(brief5, spec5)
    sandbox5 = provision_sandbox(MANIFEST, "/tmp/sim-sbx-a5")
    tx5 = run_scenario(spec5, sandbox5, LIVE, "fr-sim-a5")
    report5 = coverage_report(spec5.id, tx5, suite, "rep-a5")
    assert not report5.passes and report5.new_pairs == [], (
        "the rephrase covers no pair outside the hardened case")
    before5 = list(suite.cases)
    _expect_fail(lambda: harden(scenario=spec5, transcript=tx5,
                                report=report5, suite=suite,
                                disposition_ref="DR-SIM-005"),
                 HardeningRefused, "I-23",
                 "A5: I-23 bars the rephrase even with a disposition")
    assert suite.cases == before5
    # F-S1: the budget still bounds authorship — the brief retires.
    _expect_fail(lambda: author_scenario(brief5, spec5), BudgetExhausted,
                 "retires", "A5: an exhausted brief refuses further authorship")
    retired5 = retire_brief(brief5)
    assert retired5.retired and retired5.authored == 1
    refusals.append("A5: the rephrase failed I-23 with only the coverage "
                    "report spent; the brief's budget enforced")

    # ---------------------------------------------------------------
    # A6. Refusal coverage: the K2 accretion refusal hardens via the
    # narrow refusal-path standing class (enumerated before first use).
    # ---------------------------------------------------------------
    assert "refusal-path" in STANDING_HARDENING_CLASSES, (
        "G6 Q1: standing classes enumerated before first use")
    brief6 = Brief(
        id="brief-k2fb-2",
        source_falsification="K2 F-B: unwritable accretion path",
        survivor_under_test="K2 fail-closed drive (DR-CMD-038)",
        risk_question="the refusal itself, as a regression case",
        budget=2,
    )
    spec6 = ScenarioSpec(
        id="sim-accretion-refusal-1", brief_id="brief-k2fb-2",
        target_flow_id=FLOW_ID,
        narrative=("K2's refusal path as a regression case: an unwritable "
                   "accretion refuses the drive loudly."),
        turns=[
            ScenarioTurn(actor="world", input={
                "feed_version": "0.1.1", "installed_version": "0.1.0",
                "updater_policy": "auto", "accretion_writable": False}),
            ScenarioTurn(actor="driver", input={"run_id": "fr-sim-a6"}),
            ScenarioTurn(actor="referee", input={}, expect={
                "ends_at": "urm-failed",
                "covers": [["urmt-11", "unguarded"]]}),
        ],
    )
    brief6, spec6 = author_scenario(brief6, spec6)
    sandbox6 = provision_sandbox(MANIFEST, "/tmp/sim-sbx-a6")
    tx6 = run_scenario(spec6, sandbox6, LIVE, "fr-sim-a6")
    report6 = coverage_report(spec6.id, tx6, suite, "rep-a6")
    assert report6.passes, "the refusal pair is new to the suite"
    assert report6.terminal_trigger == "run_aborted"
    case6: HardenedCase = harden(
        scenario=spec6, transcript=tx6, report=report6, suite=suite,
        standing_class="refusal-path")
    assert case6.disposition_ref == "standing:refusal-path"
    assert FlowPair(transition_id="urmt-11",
                    guard_outcome="unguarded") in set(case6.pairs), (
        "the hardened case asserts the K2 refusal pair")
    assert tx6.terminal_pair.transition_id == "urmt-11"
    assert len(suite.cases) == 2
    refusals.append("A6: the K2 refusal scenario hardened via the narrow "
                    "refusal-path standing class; its case asserts the refusal")

    # ---------------------------------------------------------------
    # A5's twin: I-23's bug-finding alternative — a real failure is
    # hardenable even when every pair is covered.
    # ---------------------------------------------------------------
    tx_bug = tx5.model_copy(update={"bug_found": True})
    report_bug = coverage_report(tx_bug.scenario_id, tx_bug, suite,
                                 "rep-bug")
    assert report_bug.passes and report_bug.bug_found, (
        "a real failure hardens with no new pair")
    refusals.append("I-23's bug-finding alternative: a failure is hardenable "
                    "with no new pair")

    ok = not violations
    return {"violations": violations, "refusals": refusals, "ok": ok}


if __name__ == "__main__":
    res = run()
    print(f"RESULT: {'PASS' if res['ok'] else 'FAIL'}")
    for r in res["refusals"]:
        print(f"  refused: {r}")
    for v in res["violations"]:
        print(f"  VIOLATION: {v}")
