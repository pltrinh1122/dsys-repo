"""D1-D7 agent factory golden run (step 5, DR-CMD-061; ensemble DR-CMD-072).

Exercises the compiler (cases A1-A8) and the verifier (cases B1-B10)
against the legacy fixture profiles (dsys self-profile, thermostat-like
minimal agent, high-autonomy agent, fail-open agent), and — the step-6
verification ensemble (Peter, 2026-09-26, DR-CMD-072) — all six exemplar
actors (analyst, advisor, author, executor, monitor, coordinator) through
the full pipeline in cases C-*. Cases M-* (DR-CMD-073) close the
multi-agent flows gap: the coordinator arbitrating live staged proposals
from other actors mid-flight, via a deterministic reference sweep driver
(zero inference; the factory builds agents, it does not operate them).
Cases A-* (DR-CMD-078) exercise the D6 `agent` source: the coordinator
waking on other agents' staging state changes through the staging-event
feed (admit on attested events; refuse spoofed authors and broken chains;
arbitration citing the agent wake; may-act still refused at [staff/S4]).
Cases O-* (DR-CMD-081) exercise the structural orphan-triage policy: orphans
born on the real 5b path, coordinator disclosure (count + oldest age), the
three triage dispositions with reasons, the closure bar, determinism.

Result shape: {"ok", "violations", "refusals"}.
  - violations: expectations that did not hold (must be empty for ok=true).
  - refusals: expected-refusal cases, recorded separately — a refusal that
    fires as specified is a PASS, not a violation. An expected refusal that
    does NOT fire is a violation.

Deterministic: no clocks, no UUIDs, no network. Staging roots are fresh
temp dirs per case; no hashes depend on the paths.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

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
    dsys_profile,
    reference_binding,
    ReferenceBindingError,
)
from .factory_compiler import (
    AGENT_TOOL_IDS,
    FACTORY_RELEASE,
    PROBE_SUITE_VERSION,
    CompileRefused,
    compile_factory_flow,
    compile_profile,
)
from .factory_archetypes import check_profile
from .factory_profile_set_001 import PROFILE_ARCHETYPES, PROFILE_SET_001
from .factory_substrate import (AccretionWriter, OrphanQueue, OrphanTriageError,
                                StagingArea, StagingEventListener,
                                TriggerWiring, canonical_json)
from .factory_verifier import (
    PROBE_IDS,
    PlanInterpreter,
    ProbeFixture,
    compile_verifier_flow,
    run_probes,
    verify,
)

# ---------------------------------------------------------------------------
# Fixture profiles
# ---------------------------------------------------------------------------

def _bound(profile: AgentBehaviorProfile) -> AgentBehaviorProfile:
    """DR-CMD-070: the personalization stage. Fixture profiles are generic;
    binding the golden-run test principal (empty bindings — role defaults
    stand) exercises the lifecycle stage mechanically before compile."""
    return bind_personalization(
        profile, principal_id="golden-test-principal", bindings={},
        disposition_ref="golden-fixture")


def minimal_profile() -> AgentBehaviorProfile:
    """Thermostat-like: per-event disposition, one source, no writes, no D7."""
    return AgentBehaviorProfile(
        agent="minimal-agent",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[], self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(principal_precedence=["operator"],
                               conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True, replay_supported=True),
        d4_observability=D4Observability(
            position=1 / 3, records_events=True, records_intents=False,
            records_verifications=False, inspectors=["operator"],
            retention="30d"),
        d5_scope=D5Scope(position=0.0, read_scope=[], write_scope=[]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR: "stage-only"}),
        d7_verification=D7Verification(position=0.0),
    )


def high_autonomy_profile() -> AgentBehaviorProfile:
    """Full autonomy, minimal audit trail: must verify WITH an S5 advisory."""
    return AgentBehaviorProfile(
        agent="high-autonomy-agent",
        d1_authority=D1Authority(
            position=1.0, per_event_disposition=False,
            standing_dispositions=["nightly-rollup"],
            self_correction=True, self_planning=True),
        d2_fidelity=D2Fidelity(principal_precedence=["operator"],
                               conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False, replay_supported=True),
        d4_observability=D4Observability(
            position=0.0, records_events=False, records_intents=False,
            records_verifications=False, inspectors=[], retention=None),
        d5_scope=D5Scope(position=0.15, read_scope=[],
                          write_scope=["contracted-tools-only"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.WORLD},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.WORLD: "allowlist + signature"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.WORLD: "stage-only"}),
        d7_verification=D7Verification(
            position=0.25, intent_target=True, on_failure="escalate"),
    )


def fail_open_profile() -> AgentBehaviorProfile:
    """fail_open policy at D7=0.25 (C7-legal): the only profile exercising
    the fail_open branch of P-D7."""
    return AgentBehaviorProfile(
        agent="fail-open-agent",
        d1_authority=D1Authority(
            position=0.25, per_event_disposition=False,
            standing_dispositions=[], self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(principal_precedence=["operator"],
                               conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True, replay_supported=True),
        d4_observability=D4Observability(
            position=1 / 3, records_events=False, records_intents=False,
            records_verifications=True, inspectors=["operator"],
            retention="30d"),
        d5_scope=D5Scope(position=0.0, read_scope=["config"], write_scope=[]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR: "stage-only"}),
        d7_verification=D7Verification(
            position=0.25, intent_target=True, event_target=False,
            world_target=False, trigger_target=False, on_failure="fail_open"),
    )


# ---------------------------------------------------------------------------
# Case harness
# ---------------------------------------------------------------------------

class Golden:
    def __init__(self) -> None:
        self.violations: list[str] = []
        self.refusals: list[str] = []
        self.passed: list[str] = []

    def check(self, case_id: str, cond: bool, detail: str = "") -> None:
        if cond:
            self.passed.append(case_id)
        else:
            self.violations.append(f"{case_id}: {detail}")

    def expect_refusal(self, case_id: str, fn, detail: str) -> None:
        """fn must raise CompileRefused or ValidationError; records the refusal."""
        try:
            fn()
        except (CompileRefused, ValidationError) as e:
            self.refusals.append(f"{case_id}: refused as specified ({detail}; "
                                 f"{type(e).__name__})")
            return
        self.violations.append(f"{case_id}: expected refusal did NOT fire ({detail})")

    def result(self) -> dict[str, Any]:
        """Public contract: exactly {ok, violations, refusals}."""
        return {"ok": not self.violations,
                "violations": self.violations,
                "refusals": self.refusals}

    @property
    def n_passed(self) -> int:
        return len(self.passed)


def _fresh_root(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


# ---------------------------------------------------------------------------
# Compiler cases A1-A8
# ---------------------------------------------------------------------------

def compiler_cases(g: Golden) -> None:
    dsys = _bound(dsys_profile())
    a1 = compile_profile(dsys)

    # A1: dsys compiles; structure matches the profile.
    g.check("A1", len(a1.plan.tool_bindings.write_allowlist) == len(AGENT_TOOL_IDS),
            f"write allowlist {a1.plan.tool_bindings.write_allowlist}")
    g.check("A1", {w.source for w in a1.plan.trigger_wiring}
            == {"operator", "world", "self"}, "trigger wiring sources")
    g.check("A1", {v.target for v in a1.plan.verifiers}
            == {"intent", "event", "world", "trigger"}, "verifier targets")
    g.check("A1", all([a1.manifest.profile_hash, a1.manifest.plan_hash,
                       a1.manifest.artifact_hash]), "hashes non-empty")
    g.check("A1", a1.plan.actuation.staging.durability == "accretion-backed",
            "staging durability")

    # A2: expected refusals (recorded separately, not violations).
    # NOTE: model_copy(update=) skips validation (AGENTS.md lesson) — rebuild
    # via model_validate on a mutated dict so validators actually run.
    def unknown_channel2() -> None:
        data = dsys.model_dump(mode="json")
        data["d5_scope"]["write_scope"].append("channel-does-not-exist")
        compile_profile(_bound(AgentBehaviorProfile.model_validate(data)))
    g.expect_refusal("A2a", unknown_channel2, "unknown write channel")
    def d2_enum_enforced() -> None:
        data = dsys.model_dump(mode="json")
        data["d2_fidelity"]["conflict_rule"] = "coin_flip"  # not in the enum
        AgentBehaviorProfile.model_validate(data)
    g.expect_refusal("A2b", d2_enum_enforced, "D2 conflict_rule outside the binary enum")
    def empty_sources() -> None:
        data = minimal_profile().model_dump(mode="json")
        data["d6_initiative"]["sources"] = []
        AgentBehaviorProfile.model_validate(data)
    g.expect_refusal("A2c", empty_sources, "empty trigger sources (C5)")
    def c1_violated() -> None:
        data = minimal_profile().model_dump(mode="json")
        data["d4_observability"]["records_events"] = False  # per-event needs events
        AgentBehaviorProfile.model_validate(data)
    g.expect_refusal("A2d", c1_violated, "per-event disposition without event trace (C1)")

    # A3: minimal agent compiles.
    m = compile_profile(_bound(minimal_profile()))
    g.check("A3", m.plan.tool_bindings.write_allowlist == [], "no write tools")
    g.check("A3", m.plan.actuation.routing == [], "no routing entries")

    # A4: determinism — two compiles, identical hashes.
    a2 = compile_profile(_bound(dsys_profile()))
    g.check("A4", a1.manifest.artifact_hash == a2.manifest.artifact_hash,
            "artifact hash deterministic")
    g.check("A4", a1.plan.plan_hash == a2.plan.plan_hash, "plan hash deterministic")

    # A5: manifest binds profile and plan.
    g.check("A5", a1.manifest.profile_hash == hashlib.sha256(
        dsys.canonical()).hexdigest(), "manifest binds profile")
    g.check("A5", a1.manifest.plan_hash == a1.plan.plan_hash,
            "manifest binds plan")

    # A6: routing classification.
    routes = {r.action_class: r for r in a1.plan.actuation.routing}
    chan = routes.get("contracted-tools-only")
    g.check("A6", chan is not None and chan.route == "workflow"
            and len(chan.bound_tools) == len(AGENT_TOOL_IDS),
            f"channel entry: {chan}")
    standing = routes.get("restart-webhook-handler")
    g.check("A6", standing is not None and standing.route == "workflow"
            and standing.note != "", f"standing entry fail-safe: {standing}")

    # A7: compiler flow bridges; every run-book tool resolves.
    _src, states, transitions, runbooks, steps, tools = compile_factory_flow()
    g.check("A7", len(states) == 9 and len(transitions) == 14,
            f"states={len(states)} transitions={len(transitions)}")

    # A8: factory version pin recorded.
    fv = a1.manifest.factory_version
    g.check("A8", fv.factory_release == FACTORY_RELEASE
            and fv.tool_registry_pin and fv.probe_suite_version == PROBE_SUITE_VERSION,
            f"factory version: {fv}")


# ---------------------------------------------------------------------------
# Verifier cases B1-B8
# ---------------------------------------------------------------------------

def verifier_cases(g: Golden) -> None:
    dsys = _bound(dsys_profile())
    dart = compile_profile(dsys)

    # B1: dsys verifies: verified, operable, full matrix green.
    v = verify(dart, dsys, _fresh_root("b1-"))
    g.check("B1", v.verdict == "verified" and v.operable,
            f"verdict={v.verdict} operable={v.operable} reason={v.failure_reason}")
    g.check("B1", all(r["passed"] for r in v.static_results),
            "all static pass")
    g.check("B1", all(r["passed"] for r in v.probe_results)
            and len(v.probe_results) == len(PROBE_IDS), "all probes pass")
    g.check("B1", v.staging_durability == "accretion-backed", "durability")

    # B2: tamper-evidence — refused, never failed, never verified.
    def tampered_plan():
        from .factory_compiler import AgentArtifact
        data = dart.model_dump(mode="json")
        data["plan"]["actuation"]["routing"].append(
            {"action_class": "smuggled", "route": "direct",
             "bound_tools": ["tool-rogue"], "note": ""})
        return AgentArtifact.model_validate(data)
    v2 = verify(tampered_plan(), dsys, _fresh_root("b2a-"))
    g.check("B2a", v2.verdict == "refused" and not v2.operable,
            f"tampered plan -> {v2.verdict}")
    v2b = verify(dart, _bound(minimal_profile()), _fresh_root("b2b-"))
    g.check("B2b", v2b.verdict == "refused" and not v2b.operable,
            f"wrong profile -> {v2b.verdict}")
    def tampered_manifest():
        from .factory_compiler import AgentArtifact
        data = dart.model_dump(mode="json")
        data["manifest"]["artifact_hash"] = "0" * 64
        return AgentArtifact.model_validate(data)
    v2c = verify(tampered_manifest(), dsys, _fresh_root("b2c-"))
    g.check("B2c", v2c.verdict == "refused" and not v2c.operable,
            f"tampered manifest -> {v2c.verdict}")

    # B3: each probe runs individually and passes on dsys.
    for pid in PROBE_IDS:
        results, _ = run_probes(dart.plan, dsys, _fresh_root("b3-"), [pid])
        g.check(f"B3-{pid}", len(results) == 1 and results[0]["passed"],
                f"{results[0]['evidence'][-1] if results and results[0]['evidence'] else ''}")

    # B4: minimal agent verifies.
    mprof = _bound(minimal_profile())
    mart = compile_profile(mprof)
    vm = verify(mart, mprof, _fresh_root("b4-"))
    g.check("B4", vm.verdict == "verified" and vm.operable,
            f"minimal -> {vm.verdict} {vm.failure_reason} "
            f"{[r['probe_id'] for r in vm.probe_results if not r['passed']]}")

    # B5: high-autonomy agent verifies WITH advisories.
    hprof = _bound(high_autonomy_profile())
    hart = compile_profile(hprof)
    vh = verify(hart, hprof, _fresh_root("b5-"))
    g.check("B5", vh.verdict == "verified" and vh.operable,
            f"high-autonomy -> {vh.verdict} {vh.failure_reason}")
    g.check("B5", any("audit trail" in a for a in vh.advisories),
            f"advisories: {vh.advisories}")

    # B6: full probe/check matrix on all three profiles.
    for label, prof, art in (("dsys", dsys, dart), ("minimal", mprof, mart),
                             ("high-autonomy", hprof, hart)):
        vv = verify(art, prof, _fresh_root(f"b6-{label}-"))
        g.check(f"B6-{label}", vv.verdict == "verified",
                f"{vv.verdict} static_fails="
                f"{[r['check_id'] for r in vv.static_results if not r['passed']]} "
                f"probe_fails="
                f"{[r['probe_id'] for r in vv.probe_results if not r['passed']]}")

    # B10: fail_open agent verifies (exercises the fail_open branch of P-D7).
    fprof = _bound(fail_open_profile())
    fart = compile_profile(fprof)
    vf10 = verify(fart, fprof, _fresh_root("b10-"))
    g.check("B10", vf10.verdict == "verified" and vf10.operable,
            f"fail-open -> {vf10.verdict} {vf10.failure_reason} "
            f"{[r['probe_id'] for r in vf10.probe_results if not r['passed']]}")
    p7 = next(r for r in vf10.probe_results if r["probe_id"] == "P-D7-boundary")
    g.check("B10", any("fail_open" in e for e in p7["evidence"]),
            f"P-D7 evidence: {p7['evidence'][:2]}")

    # B7: accretion-backed staging survives restarts (DR-CMD-065).
    root = _fresh_root("b7-")
    verify(dart, dsys, root)
    w = AccretionWriter(root)
    g.check("B7", w.verify(), "staging chain verifies after run")
    payloads = w.read_all()
    g.check("B7", any(p.get("kind") == "proposal" for p in payloads),
            "staged proposals persisted")
    w2 = AccretionWriter(root)  # a "restart": new writer continues the chain
    seq_before = w2.append({"kind": "probe-marker"})
    g.check("B7", w2.verify() and seq_before > 0, "chain continues across restarts")

    # B8: verifier malfunction -> failed (only failed verdict in the suite).
    blocker = _fresh_root("b8-") / "blocker"
    blocker.write_text("not a directory")
    vf = verify(dart, dsys, blocker)
    g.check("B8", vf.verdict == "failed" and not vf.operable
            and vf.failure_reason != "",
            f"malfunction -> {vf.verdict} ({vf.failure_reason[:80]})")

    # Verifier flow bridges.
    _src, states, transitions, runbooks, steps, tools = compile_verifier_flow()
    g.check("B9", len(states) == 8 and len(transitions) == 11,
            f"states={len(states)} transitions={len(transitions)}")


# ---------------------------------------------------------------------------
# Actor cases C-* (DR-CMD-072): the six exemplar actors as the step-6
# verification ensemble.
#
# Each actor runs the full pipeline — declare archetype -> author profile ->
# archetype gate (generic profile, per declared archetype) ->
# bind_personalization -> compile -> verify — plus deterministic repeat,
# disclosed re-binding, actuation-shape checks, the staff-boundary negative
# control, and actor-specific adversarial cases built from each profile's
# actual facets (no facet values invented, no profile facets changed).
#
# The legacy A/B cases are kept: they exercise dsys-adjacent behavior
# (the dsys self-profile, thermostat corner, high-autonomy interior,
# fail-open branch) that the six actors don't.
# ---------------------------------------------------------------------------

def _bind_actor(name: str,
                principal: str = "golden-actor-principal"
                ) -> AgentBehaviorProfile:
    """DR-CMD-070: the personalization stage, exercised per actor."""
    return bind_personalization(
        PROFILE_SET_001[name](), principal_id=principal, bindings={},
        disposition_ref="golden-actor-fixture")


def _synthetic(name: str, mutate) -> AgentBehaviorProfile:
    """Rebuild a profile variant through model_validate so validators run.

    NOTE: model_copy(update=) skips pydantic validation (AGENTS.md lesson) —
    mutate the dumped dict instead so the schema's own validators fire.
    """
    data = PROFILE_SET_001[name]().model_dump(mode="json")
    mutate(data)
    return AgentBehaviorProfile.model_validate(data)


def _actor_shared(g: Golden, name: str) -> None:
    """Shared battery: gate, pipeline, determinism, re-binding."""
    generic = PROFILE_SET_001[name]()
    for arch in PROFILE_ARCHETYPES[name]:
        vs = check_profile(generic, (arch,))
        g.check(f"C-{name}-gate-{arch}", vs == [],
                f"violations: {[str(v) for v in vs]}")
    bound = _bind_actor(name)
    art = compile_profile(bound)
    v = verify(art, bound, _fresh_root(f"c-{name}-"))
    g.check(f"C-{name}-verified", v.verdict == "verified" and v.operable,
            f"verdict={v.verdict} reason={v.failure_reason}")
    g.check(f"C-{name}-matrix",
            all(r["passed"] for r in v.static_results)
            and all(r["passed"] for r in v.probe_results),
            "static + probe matrix green")
    art2 = compile_profile(_bind_actor(name))
    g.check(f"C-{name}-deterministic",
            art.manifest.artifact_hash == art2.manifest.artifact_hash,
            "repeat bind+compile byte-identical")
    rebound = _bind_actor(name, principal="golden-other-principal")
    art_r = compile_profile(rebound)
    v_r = verify(art_r, rebound, _fresh_root(f"c-{name}-rebind-"))
    g.check(f"C-{name}-rebind-principal",
            art_r.manifest.personalization.principal_id
            == "golden-other-principal",
            "manifest records the new principal")
    g.check(f"C-{name}-rebind-newhash",
            art_r.manifest.artifact_hash != art.manifest.artifact_hash,
            "disclosed re-binding mints a new build")
    g.check(f"C-{name}-rebind-verified",
            v_r.verdict == "verified" and v_r.operable,
            f"re-bound build verifies: {v_r.verdict}")


def _actor_actuation(g: Golden) -> None:
    """Actuation shape per archetype membership (J-A, J-C)."""
    for name in ("analyst", "advisor", "author", "monitor", "coordinator"):
        art = compile_profile(_bind_actor(name))
        g.check(f"C-{name}-no-write-tools",
                art.plan.tool_bindings.write_allowlist == [],
                "staff actor: empty write_scope -> no write tools")
    art = compile_profile(_bind_actor("executor"))
    routing = art.plan.actuation.routing
    g.check("C-executor-all-direct",
            len(routing) == 6
            and all(r.route == "direct" for r in routing),
            f"4 write channels + 2 standing dispositions, all direct "
            f"(got {len(routing)})")
    g.check("C-executor-bound-tools",
            all(r.bound_tools == [r.action_class] for r in routing),
            "every entry binds exactly its named registered tool (J-C)")


def _actor_adversarial(g: Golden) -> None:
    """Negative controls and actor-specific adversarial cases."""
    # Staff boundary: a write_scope grant refuses at [staff/S2] for every
    # actor. For the five staff members this is their own archetype
    # refusing; for the executor it is the boundary proof — the executor
    # is not staff, and the gate says so.
    def add_writes(data):
        data["d5_scope"]["write_scope"] = ["tool-run-doctor"]
        data["d5_scope"]["position"] = 0.15  # derived: 1-3 channels
    for name in PROFILE_SET_001:
        vs = check_profile(_synthetic(name, add_writes), ("staff",))
        g.check(f"C-{name}-staff-boundary",
                any(v.archetype == "staff" and v.invariant == "S2"
                    for v in vs),
                f"write_scope grant refuses at [staff/S2]: "
                f"{[str(v) for v in vs]}")

    # analyst: the tie-break rule is declared, not bounded (DR-CMD-077) —
    # flipping world_wins_ties to principal_wins_ties validates; the enum
    # carries the decision outright, with no scalar to move.
    def flip_rule(data):
        data["d2_fidelity"]["conflict_rule"] = "principal_wins_ties"
    flipped = _synthetic("analyst", flip_rule)
    g.check("C-analyst-rule-declared",
            flipped.d2_fidelity.conflict_rule == "principal_wins_ties",
            "D2 rule flip validates: the enum is declared, not bounded")
    # analyst: world trigger gate authenticates (field W2).
    gate = _bind_actor("analyst").d6_initiative.gating[TriggerSource.WORLD]
    g.check("C-analyst-world-gate",
            gate.strip().lower() not in {"", "none", "unauthenticated"},
            f"world gate authenticates: {gate!r}")

    # advisor: the self source (scheduled rollups, J-D) is stage-only.
    auth = _bind_actor("advisor").d6_initiative.authorization[TriggerSource.SELF]
    g.check("C-advisor-self-stage-only", "may-act" not in auth.lower(),
            f"self authorization: {auth!r}")

    # author: claiming world corroboration refuses at [office/H1].
    def add_world_target(data):
        data["d7_verification"]["world_target"] = True
        data["d7_verification"]["position"] = 1.0  # derived: 4/4
    vs = check_profile(_synthetic("author", add_world_target), ("office",))
    g.check("C-author-office-boundary",
            any(v.invariant == "H1" for v in vs),
            f"world_target=True refuses at [office/H1]: "
            f"{[str(v) for v in vs]}")

    # monitor: field membership is load-bearing — dropping world_target
    # breaks W1.
    def drop_world_target(data):
        data["d7_verification"]["world_target"] = False
        data["d7_verification"]["position"] = 0.75  # derived: 3/4
    vs = check_profile(_synthetic("monitor", drop_world_target), ("field",))
    g.check("C-monitor-field-boundary",
            any(v.invariant == "W1" for v in vs),
            f"world_target=False refuses at [field/W1]: "
            f"{[str(v) for v in vs]}")
    # monitor: watch evaluation is deterministic (D3 0.0).
    m = _bind_actor("monitor").d3_reproducibility
    g.check("C-monitor-deterministic",
            m.deterministic_execution and m.replay_supported
            and m.position == 0.0,
            "D3 0.0: deterministic, replayable")

    # coordinator: a may-act authorization refuses at [staff/S4].
    def add_may_act(data):
        data["d6_initiative"]["authorization"]["self"] = "may-act on routing"
    vs = check_profile(_synthetic("coordinator", add_may_act), ("staff",))
    g.check("C-coordinator-staff-s4",
            any(v.invariant == "S4" for v in vs),
            f"may-act authorization refuses at [staff/S4]: "
            f"{[str(v) for v in vs]}")
    # coordinator: F1 resolved by DR-CMD-078 — the coordinator binds the
    # agent source (staging-event feed) alongside operator and self.
    srcs = _bind_actor("coordinator").d6_initiative.sources
    g.check("C-coordinator-f1",
            srcs == {TriggerSource.OPERATOR, TriggerSource.SELF,
                     TriggerSource.AGENT},
            f"sources={sorted(s.value for s in srcs)}: agent source bound "
            f"(F1 resolved, DR-CMD-078)")


def actor_cases(g: Golden) -> None:
    for name in PROFILE_SET_001:
        _actor_shared(g, name)
    _actor_actuation(g)
    _actor_adversarial(g)


# ---------------------------------------------------------------------------
# Multi-agent flow cases M-* (DR-CMD-073): the coordinator arbitrating live
# staged proposals from other actors mid-flight.
#
# Reference machinery, NOT shipped factory components: the factory builds
# agents; it does not operate them (DR-CMD-061). CoordinatorSweepDriver is
# the golden run's deterministic stand-in for the coordinator's runtime
# drive: sweep (self source: staging-area read) -> route/sequence
# (operator source: commissioned routing rules) -> arbitrate -> stage.
#
# Design choice (documented): a deterministic driver, not an AutomatonFlow.
# DR-CMD-064's discriminator routes *governed workflows* (intermediate
# observation, inter-step guards, unit replay) through flows. This pipeline
# is a total function over the sweep — no branching on observations, no
# guards, no replay — so a driver suffices. If arbitration ever needs to
# branch on untrusted proposal content, it graduates to an AutomatonFlow.
#
# ZERO inference: fixtures are authored; arbitration is sorting, grouping,
# and canonical serialization. DR-CMD-078 resolved the F1 gap: D6 now has an
# "agent" source and the coordinator binds it (staging-event feed, M6/A-*).
# The sweep path (self + operator) remains the reconciliation backstop.
# Proposer!=disposer holds by construction (the driver has no disposition
# code path) and is asserted empirically in every case.
# ---------------------------------------------------------------------------

# Operator-commissioned routing rules (AP-A3 commission afferent, fixture).
# Deterministic; authored, not inferred.
COMMISSIONED_ROUTING: dict[str, Any] = {
    "finding": {"rank": 0, "route_to": ["corroboration", "draft-verdict"]},
    "corroboration": {"rank": 1, "route_to": ["draft-verdict"]},
    "draft-verdict": {"rank": 2, "route_to": ["operator"]},
    "arbitration": {"rank": 3, "route_to": ["operator"]},
    "on_conflict": "stage-proposed-resolution",
}


def _content_hash(payload: dict) -> str:
    """Order-independent identity of a staged payload: sha256 over the
    canonical form. Payloads carry no seq, so the hash is identical
    regardless of staging order (M2)."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class CoordinatorSweepDriver:
    """Deterministic reference drive for coordinator arbitration.

    Not a shipped component: golden-run reference machinery demonstrating
    how a verified coordinator build is driven at runtime. No inference,
    no disposition, no tool effects — sweep, route, sequence, arbitrate,
    stage.
    """

    def __init__(self, writer: AccretionWriter, routing: dict) -> None:
        self.writer = writer
        self.routing = routing
        self._prior_arbitrations: list[str] = []

    def sweep(self) -> list[dict]:
        """Read the staging file; return pending proposals, oldest seq first.

        self source: the staging area IS the medium — the coordinator reads
        other actors' staged proposals here. Disposed proposals (kind ==
        "disposition" records) are excluded, never re-arbitrated. The
        coordinator's own prior arbitrations are history (referenced via
        supersedes), not re-arbitrated as inputs.
        """
        records: list[dict] = []
        if self.writer.file.exists():
            for line in self.writer.file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        disposed = {r["payload"]["proposal_id"] for r in records
                    if r["payload"].get("kind") == "disposition"}
        out = []
        for r in records:
            p = r["payload"]
            if p.get("kind") != "proposal":
                continue
            if p.get("agent") == "coordinator" and p.get("action_class") == "arbitration":
                continue  # own history, not an input
            pid = f"sp-{r['seq']:06d}"
            if pid in disposed:
                continue
            out.append({"seq": r["seq"], "proposal_id": pid, "payload": p})
        return out

    def arbitrate(self, trigger_ref: str = "self:staging-sweep"):
        """Sweep -> route/sequence -> detect conflicts -> stage arbitration.

        Total function over the sweep: sort by (routing rank, content hash),
        group by claim_id, stage proposed resolutions for conflicts with the
        caveat disclosed (J-F: escalate stages WITH the caveat, never
        suppresses, never disposes). trigger_ref records what woke the
        coordinator: "self:staging-sweep" (cadence backstop) or
        "agent:staging-event" (staging-event feed, DR-CMD-078).
        """
        pending = self.sweep()
        ranked = []
        for p in pending:
            ac = p["payload"]["action_class"]
            rank = self.routing.get(ac, {}).get("rank", 99)
            ranked.append((rank, _content_hash(p["payload"]), p))
        ranked.sort(key=lambda t: (t[0], t[1]))

        by_claim: dict[str, list] = {}
        for _, h, p in ranked:
            by_claim.setdefault(p["payload"]["args"].get("claim_id"), []).append((h, p))
        conflicts = []
        for claim_id in sorted(by_claim, key=lambda c: "" if c is None else c):
            verdicts: dict[str, list] = {}
            for h, p in by_claim[claim_id]:
                verdicts.setdefault(p["payload"]["args"].get("verdict"), []).append(h)
            if len(verdicts) > 1:
                conflicts.append({
                    "claim_id": claim_id,
                    "parties": sorted({h for hs in verdicts.values() for h in hs}),
                    "verdicts": {v: sorted(hs) for v, hs in sorted(verdicts.items())},
                    "proposed_resolution": {
                        "kind": "proposed-resolution",
                        "resolution": "escalate-to-operator-with-caveats",
                        "caveat": (f"conflicting staged verdicts on {claim_id}; "
                                   "coordinator proposes, operator disposes (J-F)"),
                    },
                })

        sources = ["self:staging-sweep", "operator:commissioned-routing"]
        if trigger_ref == "agent:staging-event":
            # The wake rode the agent source; the sweep still did the reading.
            sources = ["agent:staging-event"] + sources
        # DR-CMD-081: the orphan-triage duty — surface untriaged orphans
        # (count + oldest age) as standing disclosure. Orphans stay excluded
        # from arbitration *inputs* (sweep() skips disposed proposals):
        # surfaced, never re-arbitrated.
        orphans = OrphanQueue(self.writer).scan()
        body = {
            "kind": "arbitration",
            "agent": "coordinator",
            "inputs": [h for _, h, _ in ranked],
            "sequence": [
                {"rank": rank, "action_class": p["payload"]["action_class"],
                 "agent": p["payload"]["agent"], "content_hash": h}
                for rank, h, p in ranked
            ],
            "routing": {
                ac: self.routing[ac]["route_to"]
                for ac in sorted({p["payload"]["action_class"] for _, _, p in ranked})
                if ac in self.routing
            },
            "conflicts": conflicts,
            "supersedes": list(self._prior_arbitrations),
            "sources": sources,
            "trigger_ref": trigger_ref,
            "orphans": {
                "untriaged_count": len(orphans),
                "oldest_seq": orphans[0]["staged_seq"] if orphans else None,
            },
        }
        staging = StagingArea(self.writer, "coordinator")
        proposal = staging.stage(
            action_class="arbitration",
            effects=[],
            args=body,
            verification_evidence=[f"sweep:{len(pending)}-proposals",
                                   "routing:commissioned"],
            trigger_ref=trigger_ref,
        )
        self._prior_arbitrations.append(_content_hash(body))
        return proposal, body


def _stage_fixture(writer: AccretionWriter, agent: str, action_class: str,
                   claim_id: str, verdict: str, note: str,
                   trigger_ref: str):
    """Stage one authored fixture proposal through the real StagingArea."""
    return StagingArea(writer, agent).stage(
        action_class=action_class,
        effects=[],
        args={"claim_id": claim_id, "verdict": verdict, "note": note},
        verification_evidence=[f"{agent}:{action_class}-evidence"],
        trigger_ref=trigger_ref,
    )


def _m1_run():
    """One full M1 pass on a fresh root: verified builds, fixtures, sweep,
    arbitrate. Returns (writer, driver, proposal, body, builds)."""
    root = _fresh_root("m1-")
    writer = AccretionWriter(root)
    builds = {}
    for name in ("analyst", "monitor", "advisor", "coordinator"):
        bound = _bind_actor(name)
        art = compile_profile(bound)
        v = verify(art, bound, _fresh_root(f"m1-{name}-"))
        builds[name] = (bound, art, v)
    _stage_fixture(writer, "analyst", "finding", "claim-a", "supported",
                   "evidence supports claim-a", "world:reading-001")
    _stage_fixture(writer, "monitor", "corroboration", "claim-a", "supported",
                   "watch confirms claim-a", "world:watch-014")
    _stage_fixture(writer, "advisor", "draft-verdict", "claim-b", "approved",
                   "draft verdict on claim-b", "operator:commission-007")
    driver = CoordinatorSweepDriver(writer, COMMISSIONED_ROUTING)
    proposal, body = driver.arbitrate()
    return writer, driver, proposal, body, builds


def _disposition_payloads(writer: AccretionWriter) -> list[dict]:
    return [p for p in writer.read_all() if p.get("kind") == "disposition"]


def multi_agent_cases(g: Golden) -> None:
    # M1: fixtures from verified builds -> sweep -> arbitrate -> stage.
    writer, driver, proposal, body, builds = _m1_run()
    for name, (bound, art, v) in builds.items():
        g.check(f"M1-{name}-verified", v.verdict == "verified" and v.operable,
                f"{name}: {v.verdict} {v.failure_reason}")
    g.check("M1-inputs", len(body["inputs"]) == 3,
            f"3 staged proposals ingested: {len(body['inputs'])}")
    g.check("M1-sequence",
            [s["action_class"] for s in body["sequence"]]
            == ["finding", "corroboration", "draft-verdict"]
            and [s["rank"] for s in body["sequence"]] == [0, 1, 2],
            "commissioned routing order: finding -> corroboration -> draft-verdict")
    g.check("M1-routing",
            body["routing"]["finding"] == ["corroboration", "draft-verdict"]
            and body["routing"]["draft-verdict"] == ["operator"],
            f"routing table applied: {body['routing']}")
    g.check("M1-no-conflicts", body["conflicts"] == [],
            "no conflicting verdicts in M1 fixtures")
    g.check("M1-arbitration-pending", proposal.disposition == "pending",
            "arbitration output is staged, never disposed (proposer!=disposer)")
    g.check("M1-inputs-still-pending", len(driver.sweep()) == 3
            and _disposition_payloads(writer) == [],
            "inputs untouched: still pending, zero disposition records")
    g.check("M1-no-effects",
            all(p.get("effects", None) == [] for p in writer.read_all()
                if p.get("kind") == "proposal"),
            "no tool effects anywhere: the coordinator never touches the world")
    g.check("M1-chain", writer.verify(), "staging chain intact")
    g.check("M1-coordinator-no-write",
            builds["coordinator"][1].plan.tool_bindings.write_allowlist == [],
            "staff coordinator: empty write allowlist")
    _w2, _d2, _p2, body2, _b2 = _m1_run()
    g.check("M1-deterministic", canonical_json(body) == canonical_json(body2),
            "repeat run byte-identical arbitration")

    # M2: arrival-order independence — all 6 staging orders, one arbitration.
    staged = {
        "analyst": ("finding", "claim-a", "supported", "world:reading-001"),
        "monitor": ("corroboration", "claim-a", "supported", "world:watch-014"),
        "advisor": ("draft-verdict", "claim-b", "approved",
                    "operator:commission-007"),
    }
    bodies = []
    for perm in itertools.permutations(staged):
        root = _fresh_root("m2-")
        w = AccretionWriter(root)
        for agent in perm:
            ac, claim, verdict, trig = staged[agent]
            _stage_fixture(w, agent, ac, claim, verdict, f"{agent} note", trig)
        _, b = CoordinatorSweepDriver(w, COMMISSIONED_ROUTING).arbitrate()
        bodies.append(canonical_json(b))
    g.check("M2-order-independent",
            len(bodies) == 6 and all(b == bodies[0] for b in bodies),
            "6 arrival orders -> identical arbitration (content-hash ordering)")

    # M3: a late proposal arrives mid-flow -> deterministic re-sequence;
    # the earlier arbitration is superseded by staging, never rewritten.
    root = _fresh_root("m3-")
    w3 = AccretionWriter(root)
    _stage_fixture(w3, "analyst", "finding", "claim-a", "supported",
                   "n1", "world:reading-001")
    _stage_fixture(w3, "monitor", "corroboration", "claim-a", "supported",
                   "n2", "world:watch-014")
    d3 = CoordinatorSweepDriver(w3, COMMISSIONED_ROUTING)
    p_a1, b_a1 = d3.arbitrate()
    file_before = w3.file.read_text(encoding="utf-8")
    _stage_fixture(w3, "analyst", "finding", "claim-c", "supported",
                   "late finding", "world:reading-002")
    p_a2, b_a2 = d3.arbitrate()
    g.check("M3-superset",
            set(b_a1["inputs"]) < set(b_a2["inputs"])
            and len(b_a2["inputs"]) == 3,
            "re-arbitration ingests the late proposal")
    g.check("M3-supersedes", b_a2["supersedes"] == [_content_hash(b_a1)],
            "new arbitration declares supersession of the old")
    g.check("M3-history-preserved",
            w3.file.read_text(encoding="utf-8").startswith(file_before)
            and w3.verify(),
            "earlier arbitration record byte-unchanged; chain intact")
    g.check("M3-nothing-disposed",
            p_a1.disposition == "pending" and p_a2.disposition == "pending"
            and _disposition_payloads(w3) == [],
            "superseded by staging, never rewritten, never disposed")

    # M4: conflicting staged verdicts -> proposed resolution WITH caveat.
    root = _fresh_root("m4-")
    w4 = AccretionWriter(root)
    _stage_fixture(w4, "analyst", "finding", "claim-x", "supported",
                   "evidence for x", "world:reading-003")
    _stage_fixture(w4, "monitor", "corroboration", "claim-x", "supported",
                   "watch confirms x", "world:watch-015")
    _stage_fixture(w4, "advisor", "draft-verdict", "claim-x", "rejected",
                   "draft rejects x", "operator:commission-008")
    p4, b4 = CoordinatorSweepDriver(w4, COMMISSIONED_ROUTING).arbitrate()
    g.check("M4-conflict-detected",
            len(b4["conflicts"]) == 1
            and b4["conflicts"][0]["claim_id"] == "claim-x",
            f"conflicts: {b4['conflicts']}")
    c4 = b4["conflicts"][0]
    g.check("M4-parties", len(c4["parties"]) == 3
            and len(c4["verdicts"]) == 2,
            "all three proposals party to the conflict; verdicts split 2-1 "
            "(analyst+monitor vs advisor)")
    g.check("M4-caveat-disclosed",
            "operator disposes" in c4["proposed_resolution"]["caveat"],
            f"caveat: {c4['proposed_resolution']['caveat']}")
    g.check("M4-staged-not-disposed",
            p4.disposition == "pending" and _disposition_payloads(w4) == [],
            "proposed resolution staged; conflict never disposed by coordinator")

    # M5: the disposition-shaped temptation — a routing rule that decides.
    # It cannot be authored: the gate refuses at [staff/S4] before compile.
    def may_act_coord(data):
        data["d6_initiative"]["authorization"]["self"] = "may-act on routing"
    vs = check_profile(_synthetic("coordinator", may_act_coord), ("staff",))
    g.check("M5-may-act-refused",
            any(v.archetype == "staff" and v.invariant == "S4" for v in vs),
            f"may-act routing rule refuses at [staff/S4]: "
            f"{[str(v) for v in vs]}")

    # M6: DR-CMD-078 — the coordinator binds the agent source (F1 resolved).
    # The inter-agent afferent now rides agent (staging-event feed, wake on
    # other agents' staging state changes) + self (cadence sweep, the
    # reconciliation backstop, J-G) + operator (commissioned routing rules).
    coord = _bind_actor("coordinator")
    g.check("M6-agent-source-bound",
            coord.d6_initiative.sources
            == {TriggerSource.OPERATOR, TriggerSource.SELF,
                TriggerSource.AGENT},
            "coordinator binds operator+self+agent (DR-CMD-078)")
    g.check("M6-agent-gate-authenticated",
            "authenticated"
            in coord.d6_initiative.gating[TriggerSource.AGENT].lower()
            and coord.d6_initiative.authorization[TriggerSource.AGENT]
            == "stage-only",
            "agent gate is authenticated-agent; authorization stage-only "
            "(staff S4)")
    g.check("M6-afferent-path",
            body["sources"]
            == ["self:staging-sweep", "operator:commissioned-routing"],
            f"sweep arbitration cites its afferent path: {body['sources']}")


# ---------------------------------------------------------------------------
# Agent-source trigger cases A-* (DR-CMD-078): the coordinator wakes on
# other agents' staging state changes through the staging-event feed.
# Reference machinery, not shipped components.
# ---------------------------------------------------------------------------

# The attestation registry: the six verified built agents (PROFILE_SET_001).
VERIFIED_SIX = {"analyst", "advisor", "author", "executor", "monitor",
                "coordinator"}


def _coordinator_agent_wiring() -> TriggerWiring:
    """The coordinator's compiled agent-source wiring, built from the plan
    exactly as the verifier builds it."""
    art = compile_profile(_bind_actor("coordinator"))
    w = next(x for x in art.plan.trigger_wiring if x.source == "agent")
    assert w.listener == "staging-event-feed", w.listener
    return TriggerWiring(w.source, w.activation_gate, w.authorization)


def agent_source_cases(g: Golden) -> None:
    wiring = _coordinator_agent_wiring()

    # A1: agent-source trigger admitted on an authenticated staging event.
    root = _fresh_root("a1-")
    w1 = AccretionWriter(root)
    feed1 = StagingEventListener(w1, VERIFIED_SIX, own_agent="coordinator")
    _stage_fixture(w1, "analyst", "finding", "claim-a", "supported",
                   "evidence supports claim-a", "world:reading-001")
    events = feed1.drain()
    g.check("A1-one-event", len(events) == 1,
            f"one event drained, got {len(events)}")
    ev = events[0]
    g.check("A1-attested",
            ev.source == "agent" and ev.source_id == "analyst"
            and ev.session_authenticated is True
            and ev.payload["author"] == "analyst",
            f"event attested: source={ev.source} author={ev.source_id} "
            f"authenticated={ev.session_authenticated}")
    out = wiring.process(ev)
    g.check("A1-admitted",
            out.admitted and out.authorization == "stage-only",
            f"agent trigger admitted stage-only: admitted={out.admitted} "
            f"authorization={out.authorization}")

    # A2: refused on a spoofed author id (not a verified built agent).
    root = _fresh_root("a2-")
    w2 = AccretionWriter(root)
    feed2 = StagingEventListener(w2, VERIFIED_SIX, own_agent="coordinator")
    StagingArea(w2, "mallory").stage(
        action_class="finding", effects=[], args={"claim_id": "claim-z"},
        verification_evidence=["mallory:note"], trigger_ref="world:fake")
    events = feed2.drain()
    g.check("A2-event-emitted", len(events) == 1,
            "spoofed record still emits an (unattested) event")
    g.check("A2-unattested", events[0].session_authenticated is False,
            "spoofed author is unattested")
    out = wiring.process(events[0])
    g.check("A2-denied",
            not out.admitted and out.authorization == "dropped",
            "spoofed-author trigger denied at the gate")
    g.check("A2-chain-intact", w2.verify(),
            "denial wrote nothing: staging chain intact")

    # A3: refused on a broken record chain (tampered staging file).
    root = _fresh_root("a3-")
    w3 = AccretionWriter(root)
    feed3 = StagingEventListener(w3, VERIFIED_SIX, own_agent="coordinator")
    _stage_fixture(w3, "analyst", "finding", "claim-a", "supported",
                   "evidence", "world:reading-001")
    lines = w3.file.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["args"]["note"] = "tampered"
    lines[0] = canonical_json(rec)
    w3.file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    g.check("A3-chain-broken", not w3.verify(), "tamper breaks the chain")
    events = feed3.drain()
    g.check("A3-event-emitted", len(events) == 1,
            "tampered record still emits an (unattested) event")
    g.check("A3-unattested", events[0].session_authenticated is False,
            "broken chain fails closed: event unattested")
    out = wiring.process(events[0])
    g.check("A3-denied",
            not out.admitted and out.authorization == "dropped",
            "broken-chain trigger denied at the gate")

    # A4: arbitration staged on an agent-source trigger; a may-act
    # authorization on the agent source still refuses at [staff/S4].
    root = _fresh_root("a4-")
    w4 = AccretionWriter(root)
    feed4 = StagingEventListener(w4, VERIFIED_SIX, own_agent="coordinator")
    _stage_fixture(w4, "analyst", "finding", "claim-x", "supported",
                   "evidence for x", "world:reading-003")
    _stage_fixture(w4, "monitor", "corroboration", "claim-x", "supported",
                   "watch confirms x", "world:watch-015")
    _stage_fixture(w4, "advisor", "draft-verdict", "claim-x", "rejected",
                   "draft rejects x", "operator:commission-008")
    events = feed4.drain()
    g.check("A4-three-events",
            len(events) == 3
            and all(e.session_authenticated for e in events),
            "one attested event per staged proposal")
    out = wiring.process(events[0])
    g.check("A4-wake-admitted",
            out.admitted and out.authorization == "stage-only",
            "coordinator wakes stage-only on the agent trigger")
    driver = CoordinatorSweepDriver(w4, COMMISSIONED_ROUTING)
    proposal, body = driver.arbitrate(trigger_ref="agent:staging-event")
    g.check("A4-arbitration-cites-wake",
            body["trigger_ref"] == "agent:staging-event"
            and body["sources"][0] == "agent:staging-event",
            f"arbitration cites the agent wake: {body['sources']}")
    g.check("A4-conflict-arbitrated", len(body["conflicts"]) == 1,
            "conflict arbitrated on the agent-triggered pass")
    g.check("A4-staged-not-disposed",
            proposal.disposition == "pending"
            and _disposition_payloads(w4) == [],
            "proposed resolution staged; nothing disposed")

    def may_act_agent(data):
        data["d6_initiative"]["authorization"]["agent"] = "may-act on routing"
    vs = check_profile(_synthetic("coordinator", may_act_agent), ("staff",))
    g.check("A4-may-act-agent-refused",
            any(v.archetype == "staff" and v.invariant == "S4" for v in vs),
            "may-act on the agent source refuses at [staff/S4]")


# ---------------------------------------------------------------------------
# REFERENCE bind-time cases R-* (DR-CMD-079): the declared reference-time
# validation of PERSONAL/REFERENCE bindings, now implemented.
#
# The schema promises: REFERENCE fields are accreted as var/ material at
# standing, validated at reference time, never part of the build hash.
# reference_binding() is that read path. Failure mode is refuse-with-reasons:
# a dangling or invalid reference raises ReferenceBindingError; nothing
# passes silently (no fallback to the role default, no unvalidated read).
# ---------------------------------------------------------------------------

_REF_KEY = ("d2_fidelity", "interaction_preferences")


def reference_cases(g: Golden) -> None:
    # R1: a valid accreted binding reads back validated and equal.
    prefs = {"challenge-style": "direct", "clarification-style": "socratic"}
    got = reference_binding("d2_fidelity", "interaction_preferences",
                            {_REF_KEY: prefs})
    g.check("R1-valid-passes", got == prefs,
            f"valid REFERENCE binding reads back: {got}")

    # R2: dangling reference (slot never filled at standing) refused.
    try:
        reference_binding("d2_fidelity", "interaction_preferences", {})
        g.check("R2-dangling-refused", False, "dangling reference passed")
    except ReferenceBindingError as e:
        g.check("R2-dangling-refused",
                any("dangling" in r for r in e.reasons),
                f"refused with reasons: {e.reasons}")

    # R3: invalid accreted values refused (wrong value type; not a dict).
    for label, bad in (("R3a", {"challenge-style": 5}),
                       ("R3b", "just-a-string"),
                       ("R3c", {"challenge-style": None})):
        try:
            reference_binding("d2_fidelity", "interaction_preferences",
                              {_REF_KEY: bad})
            g.check(f"{label}-invalid-refused", False,
                    f"invalid binding passed: {bad!r}")
        except ReferenceBindingError as e:
            g.check(f"{label}-invalid-refused", len(e.reasons) > 0,
                    f"refused with reasons: {e.reasons}")

    # R4: a BUILD field read through the REFERENCE path is refused —
    # it would bypass the build hash.
    try:
        reference_binding("d2_fidelity", "principal_precedence",
                          {("d2_fidelity", "principal_precedence"): ["operator"]})
        g.check("R4-build-bypass-refused", False, "BUILD field read passed")
    except ReferenceBindingError as e:
        g.check("R4-build-bypass-refused",
                any("not a PRINCIPAL_PERSONAL/REFERENCE" in r
                    for r in e.reasons),
                f"refused with reasons: {e.reasons}")

    # R5: a non-personal plane field is refused (not principal material).
    try:
        reference_binding("d5_scope", "write_scope",
                          {("d5_scope", "write_scope"): []})
        g.check("R5-custom-refused", False, "CUSTOM field read passed")
    except ReferenceBindingError as e:
        g.check("R5-custom-refused", True,
                f"refused with reasons: {e.reasons}")

    # R6: unknown field refused.
    try:
        reference_binding("d9_nonsense", "foo", {})
        g.check("R6-unknown-refused", False, "unknown field read passed")
    except ReferenceBindingError as e:
        g.check("R6-unknown-refused", True,
                f"refused with reasons: {e.reasons}")

    # R7: REFERENCE material never enters the build hash, and reads are
    # pure — the profile is untouched by reference_binding.
    bound = _bind_actor("advisor")
    before = bound.model_dump(mode="json")
    h1 = compile_profile(bound).manifest.artifact_hash
    _ = reference_binding("d2_fidelity", "interaction_preferences",
                          {_REF_KEY: prefs})
    _ = reference_binding("d2_fidelity", "interaction_preferences",
                          {_REF_KEY: {"other": "values"}})
    g.check("R7-profile-untouched",
            bound.model_dump(mode="json") == before,
            "reference reads do not mutate the profile")
    g.check("R7-hash-stable",
            compile_profile(bound).manifest.artifact_hash == h1,
            "REFERENCE reads cannot move the build hash")

    # R8: deterministic — same accreted material reads byte-identically.
    r1 = reference_binding("d2_fidelity", "interaction_preferences",
                           {_REF_KEY: prefs})
    r2 = reference_binding("d2_fidelity", "interaction_preferences",
                           {_REF_KEY: dict(prefs)})
    g.check("R8-deterministic", r1 == r2 == prefs, "repeat reads identical")


# ---------------------------------------------------------------------------
# Orphan-triage cases O-* (DR-CMD-081): the structural orphan-triage policy.
#
# An orphan is born on the real 5b path: an admitted trigger whose proposed
# action matches no standing disposition, under the standing-only policy,
# stages a proposal and a disposition record with decision "staged" — parked,
# never silently dropped. The OrphanQueue derives the queue from the
# append-only file; the coordinator's arbitration discloses count + oldest
# age; triage() is the only exit, always with reasons (the closure bar).
# Shape-specific routing rules are the deferred G6: nothing here presumes
# orphan shapes.
# ---------------------------------------------------------------------------

def _birth_orphan(root, action_class="novel-action", event_id="op-orphan-001"):
    """Birth one orphan through the real 5b path (PlanInterpreter +
    standing-only policy) on a fresh root. Returns (writer, result)."""
    profile = minimal_profile()
    bound = bind_personalization(profile, principal_id="golden-orphan-principal",
                                 bindings={}, disposition_ref="o-orphan-fixture")
    plan = compile_profile(bound).plan
    interp = PlanInterpreter(plan, bound, root)
    fx = ProbeFixture(
        fixture_id="o-orphan",
        source="operator",
        event_id=event_id,
        source_id="golden-operator",
        session_authenticated=True,
        proposed_action={"action_class": action_class, "effects": []},
    )
    result = interp.handle_trigger(fx, "standing-only")
    return AccretionWriter(root), result


def orphan_cases(g: Golden) -> None:
    # O1: an unmatched trigger stages (not drops) -> the orphan appears in
    # the queue, untriaged, with its provenance.
    root = _fresh_root("o1-")
    writer, res = _birth_orphan(root)
    g.check("O1-staged-not-dropped",
            res["outcome"] == "staged-staged" and res["decision"] == "staged",
            f"5b path parks the trigger: outcome={res['outcome']} "
            f"decision={res['decision']}")
    orphans = OrphanQueue(writer).scan()
    g.check("O1-orphan-queued",
            len(orphans) == 1 and orphans[0]["action_class"] == "novel-action"
            and orphans[0]["agent"] == "minimal-agent"
            and orphans[0]["trigger_ref"] == "op-orphan-001",
            f"orphan queued with provenance: {orphans}")

    # O2: the coordinator's arbitration discloses orphans (count + oldest
    # age) as standing disclosure.
    root = _fresh_root("o2-")
    w2 = AccretionWriter(root)
    _birth_orphan(root, action_class="novel-a", event_id="op-o2-a")
    _birth_orphan(root, action_class="novel-b", event_id="op-o2-b")
    first = OrphanQueue(w2).scan()[0]
    driver = CoordinatorSweepDriver(w2, COMMISSIONED_ROUTING)
    _p2, body2 = driver.arbitrate()
    g.check("O2-disclosed",
            body2["orphans"]["untriaged_count"] == 2
            and body2["orphans"]["oldest_seq"] == first["staged_seq"],
            f"arbitration discloses orphans: {body2['orphans']}")

    # O3/O4/O5: each triage disposition exits the queue, always with reasons.
    root = _fresh_root("o345-")
    w345 = AccretionWriter(root)
    _birth_orphan(root, action_class="novel-a", event_id="op-o3")
    _birth_orphan(root, action_class="novel-b", event_id="op-o4")
    _birth_orphan(root, action_class="novel-c", event_id="op-o5")
    q345 = OrphanQueue(w345)
    ids = [o["proposal_id"] for o in q345.scan()]
    r_routed = q345.triage(ids[0], "routed", "belongs to analyst intake",
                           route_to="analyst")
    r_refused = q345.triage(ids[1], "refused", "duplicate of sp-000000")
    r_archived = q345.triage(ids[2], "archived", "superseded by policy change")
    g.check("O3-routed-with-reasons",
            r_routed["decision"] == "routed"
            and r_routed["reason"] == "belongs to analyst intake"
            and r_routed["route_to"] == "analyst",
            f"routed triage recorded: {r_routed}")
    g.check("O4-refused-with-reasons",
            r_refused["decision"] == "refused"
            and r_refused["reason"] == "duplicate of sp-000000",
            f"refused triage recorded: {r_refused}")
    g.check("O5-archived-with-reasons",
            r_archived["decision"] == "archived"
            and r_archived["reason"] == "superseded by policy change",
            f"archived triage recorded: {r_archived}")
    g.check("O5-queue-drained", q345.scan() == [],
            "all three triaged: queue empty")

    # O6: the closure bar — invalid triage attempts refuse with reasons;
    # the orphan cannot silently exit.
    root = _fresh_root("o6-")
    w6 = AccretionWriter(root)
    _birth_orphan(root, action_class="novel-x", event_id="op-o6")
    q6 = OrphanQueue(w6)
    oid = q6.scan()[0]["proposal_id"]
    for label, fn in (
            ("O6a-empty-reason",
             lambda: q6.triage(oid, "refused", "   ")),
            ("O6b-unknown-disposition",
             lambda: q6.triage(oid, "escalated", "not a triage disposition")),
            ("O6c-unknown-id",
             lambda: q6.triage("sp-999999", "refused", "no such orphan"))):
        try:
            fn()
            g.check(label, False, "invalid triage passed")
        except OrphanTriageError as e:
            g.check(label, True, f"refused with reasons: {e}")
    q6.triage(oid, "archived", "valid triage")
    try:
        q6.triage(oid, "refused", "second triage attempt")
        g.check("O6d-double-triage-refused", False, "double triage passed")
    except OrphanTriageError as e:
        g.check("O6d-double-triage-refused", True, f"refused: {e}")
    g.check("O6e-queue-empty-after-valid-triage", q6.scan() == [],
            "only a valid triage exits the queue")

    # O7: surfaced, never re-arbitrated, never silently dropped — the orphan
    # persists across subsequent activity and stays out of arbitration inputs.
    root = _fresh_root("o7-")
    w7 = AccretionWriter(root)
    _birth_orphan(root, action_class="novel-y", event_id="op-o7")
    q7 = OrphanQueue(w7)
    oid7 = q7.scan()[0]["proposal_id"]
    d7 = CoordinatorSweepDriver(w7, COMMISSIONED_ROUTING)
    _p7a, b7a = d7.arbitrate()
    _stage_fixture(w7, "analyst", "finding", "claim-o7", "supported",
                   "later finding", "world:reading-007")
    _p7b, b7b = d7.arbitrate()
    g.check("O7-persists",
            len(q7.scan()) == 1 and q7.scan()[0]["proposal_id"] == oid7
            and b7a["orphans"]["untriaged_count"] == 1
            and b7b["orphans"]["untriaged_count"] == 1
            and b7b["orphans"]["oldest_seq"] == q7.scan()[0]["staged_seq"],
            "untriaged orphan survives later staging + arbitrations, "
            "still disclosed")
    g.check("O7-not-rearbitrated",
            all(oid7 not in b["inputs"] for b in (b7a, b7b)),
            "orphan excluded from arbitration inputs: surfaced, not re-driven")

    # O8: determinism — identical runs, identical queue and disclosure.
    def _o8_run():
        r = _fresh_root("o8-")
        w = AccretionWriter(r)
        _birth_orphan(r, action_class="novel-a", event_id="op-o8-a")
        _birth_orphan(r, action_class="novel-b", event_id="op-o8-b")
        _p, b = CoordinatorSweepDriver(w, COMMISSIONED_ROUTING).arbitrate()
        return canonical_json(b), canonical_json(OrphanQueue(w).scan())
    g.check("O8-deterministic", _o8_run() == _o8_run(),
            "repeat orphan run byte-identical")


def run() -> dict[str, Any]:
    """Run the factory golden suite. Returns {ok, violations, refusals}."""
    g = Golden()
    compiler_cases(g)
    verifier_cases(g)
    actor_cases(g)
    multi_agent_cases(g)
    agent_source_cases(g)
    reference_cases(g)
    orphan_cases(g)
    return g.result()


if __name__ == "__main__":
    import json as _json
    _g = Golden()
    compiler_cases(_g)
    verifier_cases(_g)
    actor_cases(_g)
    multi_agent_cases(_g)
    agent_source_cases(_g)
    reference_cases(_g)
    orphan_cases(_g)
    print(_json.dumps(_g.result(), indent=2))
    print(f"passed cases: {_g.n_passed}")
    raise SystemExit(0 if _g.result()["ok"] else 1)
