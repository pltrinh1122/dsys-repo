"""Factory profile set 001 — six D1-D7 agent profiles (Peter, 2026-09-26).

Org-function labels ratified by Peter, 2026-09-26 (DR-CMD-068):
  analyst   (was diverge)    — ideate, research, observe
  advisor   (was converge)   — decide, design, synthesize (as staged draft verdicts)
  author                     — spec, code, generate (artifacts staged for review)
  executor  (was execute)    — run, remedy, report, audit (disposed or standing actions only)
  monitor   (was sentinel)   — watch, alert (afferent-relay; never acts)
  coordinator                — inter-agent mediation: route, arbitrate, sequence

cognitive-assist:
  analyst  — ideate, research, observe
  advisor — decide, design, synthesize (as staged draft verdicts)
mechanical-assist:
  author   — spec, code, generate (artifacts staged for review)
  executor  — run, remedy, report, audit (disposed or standing actions only)
mediation-assist:
  monitor    — watch, alert (afferent-relay; never acts)
  coordinator — inter-agent mediation: route, arbitrate, sequence
                (ratified by Peter, DR-CMD-067)

Invariants (non-negotiable):
  - Proposer != disposer: NO agent disposes. advisor "deciding" = drafting
    proposed verdicts staged for operator disposition (D1 per-event ->
    stage). executor actuates only disposed or standing-disposition actions.
  - Every profile validates cleanly with ZERO warnings. Positions are
    derived from facets by agent_behavior.py (DR-CMD-062) — never hand-set.
    D2 is the binary enum {principal_wins_ties, world_wins_ties} (DR-CMD-077);
    D6 structural, no scalar.
  - D5 write_scope: contracted tools only (the compiler's closed registry,
    J1). D6: every enabled source carries an explicit gate AND an explicit
    authorization (C4). D7 targets sit at the trust boundaries. D4 fully on.

Judgment calls (documented, not hidden):
  J-A. analyst/advisor/author carry EMPTY write_scope (D5 = 0.0). The
      closed contracted-tool registry contains no artifact-writing tool,
      and inventing channel names would be refused at routing (J1); the
      "contracted-tools-only" alias would grant installer/promotion tools
      these agents must never touch. Their work product — research notes,
      draft verdicts, specs/code — IS their staged proposals: generation
      is realized by the accretion-backed staging area (DR-CMD-065), not
      by tool effects. Per proposer!=disposer they never commit.
  J-B. analyst is world-wins-ties: honest research lets evidence win
      ties against the principal's hypothesis. advisor/author/executor are
      principal-wins-ties: drafts, artifacts, and actuations track
      the principal's intent. (DR-CMD-077: the former D2 scalar gradations —
      0.7/0.2/0.1 — retired; the posture content lives in role prose.)
  J-C. executor's standing dispositions name registered tool ids
      ("tool-run-doctor", "tool-verify-checksum") so J2 resolves them
      direct; installer/promotion effects stay per-event (disposed) only.
  J-D. advisor carries a self source (scheduled rollups) alongside the
      operator source; both are stage-only, so ambient synthesis can never
      self-dispose.
  J-E. monitor's D2 is world_wins_ties on the *reading* (the analyst
      precedent): D2 adjudicates ties between principal and world on the
      *reading* — whether the watched target changed — and there the world
      wins, because an honest watch reports evidence, not wishes. *What*
      to watch is not a D2 tie at all: it is the AP-A3
      commission afferent, authenticated by D7 intent_target. D7 on_failure
      is fail_closed (not escalate): an uncorroborated change is never
      staged as an alert — no false alarms into the disposition queue;
      the verification failure is staged as a watch-health disclosure
      (a different kind from a change alert) and watching continues.
  J-F. coordinator's D7 on_failure is escalate (not fail_closed), the
      advisor precedent: the coordinator's entire output is a *proposed*
      resolution staged for operator disposition anyway, so the draft is
      staged WITH the verification caveat disclosed — the operator
      disposes with eyes open rather than receiving a silent suppression.
  F1-CONFIRMED. D6's source enum is exactly {operator, world, self} —
      there is no "agent" source. The coordinator's true afferent is other
      agents' staged proposals, read via the accretion-backed staging area;
      it is therefore carried on SELF (staging-area sweeps) + OPERATOR
      (commissioned routing rules), both stage-only. This mislabeling is
      mechanical evidence of the F1 inter-agent-afferent gap, documented
      as a finding, not a defect: the D6 "agent" source is a schema
      change requiring separate ratification, and is NOT added here.
      AMENDMENT 2026-09-26 (DR-CMD-078): Peter ratified OPEN NOW on the F1
      gap — the coordinator must operate autonomously upon state changes.
      The enum now carries AGENT (activation by another built agent's
      staging state change, observed through the staging medium —
      stigmergic trigger, through staging never around it); the coordinator
      binds it with authenticated-agent gating (chain verifies + author is
      a verified built agent) and stage-only authorization. The SELF cadence
      is retained as reconciliation backstop (J-G). The "finding, not a
      defect" status above is retired — F1 is implemented. Historical text
      preserved; see doc/d1-d7-d6-agent-source-spec.md for the design.

Deterministic: profile construction is pure; run() uses fresh temp staging
roots per agent (no hashes depend on the paths).

Archetype gate (Peter, 2026-09-26, DR-CMD-069): each profile declares its
archetype(s) in PROFILE_ARCHETYPES; run_agent() checks conformance via
core/package/factory_archetypes.py at authoring time, before compile.
Violations refuse with explicit reasons. See doc/d1-d7-archetypes.md.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .agent_behavior import (
    AgentBehaviorProfile,
    D1Authority,
    D2Fidelity,
    D3Reproducibility,
    D4Observability,
    D5Scope,
    D6Initiative,
    D7Verification,
    TriggerSource,
    bind_personalization,
)
from .factory_compiler import compile_profile
from .factory_verifier import verify
from .factory_archetypes import check_profile


# ---------------------------------------------------------------------------
# Archetype declarations (authoring gate — Peter, 2026-09-26, DR-CMD-069)
#
# Each profile declares its archetype(s). The gate runs at authoring time,
# before compile: violations refuse with explicit reasons. The six
# profiles are the exemplars — every one must conform; a non-conformance
# is a finding about the archetype definition, never a license to alter
# a profile facet.
# ---------------------------------------------------------------------------

PROFILE_ARCHETYPES: dict[str, tuple[str, ...]] = {
    "analyst": ("staff", "field"),
    "advisor": ("staff", "office"),
    "author": ("staff", "office"),
    "executor": ("field",),
    "monitor": ("staff", "field"),
    "coordinator": ("staff", "office"),
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def analyst_profile() -> AgentBehaviorProfile:
    """cognitive-assist / analyst: ideate, research, observe.

    Broad reads, no direct writes (notes are staged proposals). World- and
    operator-triggered. Evidence wins ties (world_wins_ties, J-B).
    """
    return AgentBehaviorProfile(
        agent="analyst",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="world_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["web-search", "arxiv", "docs-library",
                        "code-repos", "event-log", "accretion-repo"],
            write_scope=[]),  # J-A: research notes are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.WORLD},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.WORLD: "allowlist + signature"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.WORLD: "stage-only; no self-commit"}),
        d7_verification=D7Verification(
            position=1.0, intent_target=True, event_target=True,
            world_target=True, trigger_target=True,
            on_failure="escalate"),
    )


def advisor_profile() -> AgentBehaviorProfile:
    """cognitive-assist / advisor: decide, design, synthesize.

    "Deciding" = drafting proposed verdicts staged for operator disposition
    (proposer != disposer). Reads staged proposals; writes staged drafts
    only. Principal-wins-ties: drafts track the principal's intent (J-B).
    """
    return AgentBehaviorProfile(
        agent="advisor",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["staging-area", "accretion-repo", "event-log",
                        "disposition-records"],
            write_scope=[]),  # J-A: draft verdicts are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.SELF},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.SELF:
                        "scheduler-cadence; ambient-staging-only"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.SELF: "stage-only; no self-commit"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="escalate"),
    )


def author_profile() -> AgentBehaviorProfile:
    """mechanical-assist / author: spec, code, generate.

    Artifacts are generated into staged proposals for review; the author
    never commits (proposer != disposer). Principal-wins-ties: artifacts
    track the principal's intent (J-B).
    Failed verification halts: no artifact leaves on a failed intent check.
    """
    return AgentBehaviorProfile(
        agent="author",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["staging-area", "accretion-repo",
                        "disposition-records", "spec-library"],
            write_scope=[]),  # J-A: specs/code are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR: "stage-only"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


def executor_profile() -> AgentBehaviorProfile:
    """mechanical-assist / executor: run, remedy, report, audit.

    Actuates disposed actions (per-event) and pre-authorized routine checks
    (standing dispositions naming registered tools -> direct, J-C).
    Installer/promotion effects are per-event only. Deterministic (D3 = 0.0),
    fully verified (D7 = 1.0, fail_closed): strong D7 for the acting agent.
    """
    return AgentBehaviorProfile(
        agent="executor",
        d1_authority=D1Authority(
            position=0.25, per_event_disposition=True,
            standing_dispositions=["tool-run-doctor",
                                   "tool-verify-checksum"],  # J-C
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.4,
            read_scope=["disposition-records", "event-log",
                        "accretion-repo", "policy-config"],
            write_scope=["tool-invoke-installer", "tool-run-doctor",
                          "tool-record-promotion", "tool-commit-accretion"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.WORLD,
                     TriggerSource.SELF},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.WORLD: "allowlist + signature",
                    TriggerSource.SELF: "scheduler-cadence"},
            authorization={
                TriggerSource.OPERATOR: "may-act on disposition",
                TriggerSource.WORLD: ("may-act within standing dispositions; "
                                      "otherwise stage-only"),
                TriggerSource.SELF: ("may-act within standing dispositions; "
                                     "otherwise stage-only")}),
        d7_verification=D7Verification(
            position=1.0, intent_target=True, event_target=True,
            world_target=True, trigger_target=True,
            on_failure="fail_closed"),
    )


def monitor_profile() -> AgentBehaviorProfile:
    """mediation-assist / monitor: watch, alert (afferent-relay).

    Watches principal-commissioned targets in the world; on a corroborated
    change, stages an alert proposal for operator disposition. Never
    actuates, never disposes. Watch evaluation is a pure function of prior
    reading + new reading (D3 = 0.0). D2 is world_wins_ties on the *reading*
    (J-E): when the principal's belief conflicts with the evidence of
    change, evidence wins the tie — an honest watch. D7 = 1.0 fail_closed:
    an uncorroborated change is never staged as an alert.
    """
    return AgentBehaviorProfile(
        agent="monitor",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="world_wins_ties"),  # J-E: world wins on the reading
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["watch-targets", "event-log", "accretion-repo",
                        "disposition-records"],
            write_scope=[]),  # J-A: alerts are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.WORLD},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.WORLD: "allowlist + signature"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.WORLD: "stage-only; no self-commit"}),
        d7_verification=D7Verification(
            position=1.0, intent_target=True, event_target=True,
            world_target=True, trigger_target=True,
            on_failure="fail_closed"),  # J-E: suppress uncorroborated alerts
    )


def coordinator_profile() -> AgentBehaviorProfile:
    """mediation-assist / coordinator: inter-agent mediation.

    Routes staged findings to downstream consumers, arbitrates conflicting
    staged proposals from multiple agents, sequences multi-agent pipeline
    work. Its true afferent is other agents' staged proposals, read via the
    accretion-backed staging area on three sources: AGENT (staging-event
    feed — wakes on other agents' staging state changes, authenticated-agent
    gating: chain verifies + author is a verified built agent, DR-CMD-078),
    SELF (scheduler-cadence staging-area sweeps — the reconciliation
    backstop, J-G), and OPERATOR (commissioned routing rules). The trigger
    rides through staging, never around it: the state change IS a staging
    record, so proposer != disposer is untouched; the agent source changes
    WHEN the coordinator wakes, not WHAT it may do (still stage-only,
    staff S4). F1's old "no agent source" gap is resolved by DR-CMD-078.
    Arbitration outputs are *proposed* resolutions (draft-verdict kind)
    staged for operator disposition; the coordinator never disposes a
    conflict itself (proposer != disposer). Principal-wins-ties (advisor
    precedent, J-B): routing and arbitration follow the principal's
    commission and pipeline wiring.
    """
    return AgentBehaviorProfile(
        agent="coordinator",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),  # advisor precedent
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["staging-area", "accretion-repo",
                        "disposition-records", "pipeline-config",
                        "event-log"],
            write_scope=[]),  # J-A: routing + arbitration are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.SELF,
                     TriggerSource.AGENT},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.SELF:
                        "scheduler-cadence; staging-area sweeps",
                    TriggerSource.AGENT:
                        "authenticated-agent staging event; "
                        "chain+registry attested"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.SELF:
                               "stage-only; no self-commit",
                           TriggerSource.AGENT: "stage-only"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="escalate"),  # J-F: advisor precedent
    )


PROFILE_SET_001: dict[str, Any] = {
    "analyst": analyst_profile,
    "advisor": advisor_profile,
    "author": author_profile,
    "executor": executor_profile,
    "monitor": monitor_profile,
    "coordinator": coordinator_profile,
}


# ---------------------------------------------------------------------------
# Runner: validate -> compile -> verify each profile
# ---------------------------------------------------------------------------

def run_agent(name: str) -> dict[str, Any]:
    """Validate, compile, and verify one profile. Returns its report.

    DR-CMD-070: the personalization stage runs before compile. The profile
    builders produce *generic* profiles (PERSONAL/BUILD fields at role
    defaults, unbound); run_agent binds an explicit test principal via
    bind_personalization() — exercising the lifecycle stage mechanically —
    with the archetype gate re-run on the bound profile. Facet values are
    unchanged; only the binding record is added (manifest hashes change;
    determinism across repeat runs is what must hold).
    """
    builder = PROFILE_SET_001[name]
    generic = builder()
    try:
        profile = bind_personalization(
            generic,
            principal_id="test-principal",
            bindings={},  # role defaults stand; the stage, not the values
            disposition_ref="test-fixture",  # fixture, not a real disposition
            gate=lambda p: [str(v)
                            for v in check_profile(p, PROFILE_ARCHETYPES[name])],
        )
    except ValueError as e:
        raise AssertionError(f"{name}: personalization binding refused:\n  - {e}")
    warnings = profile.warnings()
    if warnings:
        raise AssertionError(
            f"{name}: profile must validate with zero warnings, got: "
            f"{warnings}")
    artifact = compile_profile(profile)
    root = Path(tempfile.mkdtemp(prefix=f"pset001-{name}-"))
    verdict = verify(artifact, profile, root)
    return {
        "agent": name,
        "position_vector": profile.position_vector(),
        "warnings": warnings,
        "personalization": {
            "principal_id": profile.personalization.principal_id,
            "bindings_hash": profile.personalization.bindings_hash,
            "disposition_ref": profile.personalization.disposition_ref,
        },
        "compile": {
            "profile_hash": artifact.manifest.profile_hash,
            "plan_hash": artifact.plan.plan_hash,
            "artifact_hash": artifact.manifest.artifact_hash,
        },
        "verify": {
            "verdict": verdict.verdict,
            "operable": verdict.operable,
            "failure_reason": verdict.failure_reason,
            "advisories": list(verdict.advisories),
            "static_failed": [r["check_id"] for r in verdict.static_results
                              if not r["passed"]],
            "probe_failed": [r["probe_id"] for r in verdict.probe_results
                             if not r["passed"]],
            "n_static": len(verdict.static_results),
            "n_probes": len(verdict.probe_results),
        },
    }


def run() -> dict[str, Any]:
    """Run all six profiles through validate -> compile -> verify."""
    reports = {name: run_agent(name) for name in PROFILE_SET_001}
    ok = all(r["verify"]["verdict"] == "verified" for r in reports.values())
    return {"ok": ok, "agents": reports}


if __name__ == "__main__":
    import json as _json
    _rep = run()
    for _name, _r in _rep["agents"].items():
        _v = _r["position_vector"]
        print(f"{_name}: D1={_v['D1']} D2={_v['D2']} D3={_v['D3']} "
              f"D4={_v['D4']} D5={_v['D5']} D6={_v['D6']} D7={_v['D7']} "
              f"-> { _r['verify']['verdict']}")
    print(_json.dumps({"ok": _rep["ok"]}, indent=2))
    raise SystemExit(0 if _rep["ok"] else 1)


__all__ = [
    "PROFILE_SET_001",
    "PROFILE_ARCHETYPES",
    "author_profile",
    "advisor_profile",
    "coordinator_profile",
    "analyst_profile",
    "executor_profile",
    "run",
    "run_agent",
    "monitor_profile",
]
