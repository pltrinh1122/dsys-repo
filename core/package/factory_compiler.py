"""D1-D7 agent compiler — step 5 build (NEW machinery).

Compiles a validated AgentBehaviorProfile into a harness-native agent
artifact {plan, manifest}: profile -> build plan -> agent. Deterministic,
total, closed per doc/d1-d7-compiler-spec.md (ratified DR-CMD-066).

Decisions implemented:
  - DR-CMD-062: positions derived from facets (the compiler calls the
    derivation functions in agent_behavior.py; it never reimplements them).
  - DR-CMD-063: harness-native agents — the seven substrate components.
  - DR-CMD-064: Q2 hybrid actuation. The discriminator (edge wording
    finalized by the ratified spec §5): a tool action is exactly one
    contracted-tool call with all arguments bound at disposition time
    (bound from the disposition record, or from the standing rule plus
    the activating trigger event — no dependence on any prior tool
    result, no inter-step guard) -> direct; anything else -> governed
    workflow -> automaton flow. Standing dispositions never pre-authorize
    an unseen flow source.
  - DR-CMD-065: Q3 accretion-backed staging — staging.durability is
    pinned to "accretion-backed".
  - DR-CMD-070: the validating stage requires the profile to be
    personalization-bound (bind_personalization() before compile); the
    manifest carries the declared personalization section, hash-covered.
    Compiler contract unchanged: validated profile bytes -> artifact.
  - DR-CMD-064 D2: the factory's own pipeline runs as an automaton flow.
    The pipeline is authored here as pydantic sources (DR-CMD-058) and
    bridged to AutomatonFlow entities via bridge.compile().

Step-5 judgment calls (beyond transcription, documented):
  J1. write_scope channels resolve against the closed contracted-tool
      registry (B-3 analog): a channel naming a registered tool id, or a
      registered alias, compiles; anything else is a loud refusal at the
      routing stage. One alias is registered: "contracted-tools-only"
      (the dsys profile's channel) -> all nine contracted tools.
  J2. A standing-disposition class resolves to bound tools iff its name
      is a registered tool id or alias (exactly one tool -> direct).
      An unresolvable class name is NOT a refusal (that would refuse the
      dsys profile): it routes `workflow` with an explanatory note, and
      the runtime predicate classifies per proposed action. Fail-safe
      direction: toward more governance.
  J3. Non-deterministic backends get the factory's stipulated defaults:
      temperature 1.0, model_pin "unpinned". Deterministic backends get
      temperature 0.0, a seed derived from the profile hash, and the
      pinned model reference "factory-pinned-model-v1" (Q1: the concrete
      facility resolves the reference; the binding is stubbed).
  J4. The compiler emits structure only (bridge F2: naming is not
      defining). Tool implementations live in the factory flow registry;
      the built agent's behavior definitions live in registered code.

Closedness: compile_source() reads {profile bytes, factory_version} and
module constants only. No network, no inference, no wall-clock, no
ambient state. Determinism: same inputs -> byte-identical artifact.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from .agent_behavior import (
    AgentBehaviorProfile,
    derive_d1_position,
    derive_d3_position,
    derive_d4_position,
    derive_d5_position,
    derive_d7_position,
)
from .bridge import AutomatonSource, AutomatonState, AutomatonTransition, RunBookSource, RunBookStepSource, compile as bridge_compile

# ---------------------------------------------------------------------------
# Factory version — the determinism scope (spec §6: all of it, exactly)
# ---------------------------------------------------------------------------

FACTORY_RELEASE = "0.1.0"
SCHEMA_VERSION = "1.2"            # agent_behavior module revision
                                # 1.2 (2026-09-26, DR-CMD-078): D6 source
                                # enum gains AGENT (activation by another
                                # built agent's staging state change,
                                # stigmergic trigger); coordinator binds it.
                                # 1.1 (2026-09-26, DR-CMD-077): D2 scalar
                                # position retired; D2 is the binary enum
                                # {principal_wins_ties, world_wins_ties}.
# Schema versioning rule (adopted by Peter 2026-09-26, DR-CMD-082):
# bump the MINOR version on any schema-enum or schema-field change and
# record the bump in the implementing decision record. The two historical
# bumps (1.0->1.1 for the D2 enum, 1.1->1.2 for the D6 AGENT source) were
# both enum changes — consistent with this rule, no retroactive conflict.
SEMANTICS_TABLE_VERSION = "1.0"  # construction-semantics table revision
PROBE_SUITE_VERSION = "1.0"      # verifier's probe suite (static here)


class FactoryVersion(BaseModel):
    """The five-part determinism scope. Any change is a new factory version."""

    model_config = ConfigDict(frozen=True)

    factory_release: str
    schema_version: str
    semantics_table_version: str
    tool_registry_pin: str
    probe_suite_version: str


# ---------------------------------------------------------------------------
# Closed contracted-tool registry (J1). Pinned inside FactoryVersion.
# ---------------------------------------------------------------------------

AGENT_TOOL_IDS: tuple[str, ...] = (
    "tool-fetch-feed",
    "tool-compare-versions",
    "tool-verify-checksum",
    "tool-read-policy",
    "tool-invoke-installer",
    "tool-run-doctor",
    "tool-record-promotion",
    "tool-commit-accretion",
    # DR-CMD-102 tranche 1: the contracted write channel for the
    # content-addressed append-only artifact registry (spec
    # doc/tool-register-artifact-spec.md). Addition under the standing
    # J1 discipline — the registry stays closed; it now has nine members.
    "tool-register-artifact",
)

# Registry aliases: channel names that expand to tool sets. Part of the
# pinned registry (J1). Two aliases: the dsys profile's channel, and
# "artifact-registry" (the registrar_clerk's write channel, DR-CMD-096).
CHANNEL_ALIASES: dict[str, list[str]] = {
    "contracted-tools-only": list(AGENT_TOOL_IDS),
    "artifact-registry": ["tool-register-artifact"],
}

_TOOL_PIN_DIGEST = hashlib.sha256(
    ",".join(sorted(AGENT_TOOL_IDS)).encode("utf-8")).hexdigest()[:16]
TOOL_REGISTRY_PIN = f"contracted-tools-v1:{_TOOL_PIN_DIGEST}"


def default_factory_version() -> FactoryVersion:
    return FactoryVersion(
        factory_release=FACTORY_RELEASE,
        schema_version=SCHEMA_VERSION,
        semantics_table_version=SEMANTICS_TABLE_VERSION,
        tool_registry_pin=TOOL_REGISTRY_PIN,
        probe_suite_version=PROBE_SUITE_VERSION,
    )


class CompileRefused(Exception):
    """Compile-time refusal: the profile cannot become an agent. Loud.

    Attributes: stage (ingesting|validating|deriving|planning|routing|
    materializing|attesting), reason. A refusal is never downgraded.
    """

    def __init__(self, stage: str, reason: str):
        super().__init__(f"compile refused at {stage}: {reason}")
        self.stage = stage
        self.reason = reason


# ---------------------------------------------------------------------------
# Build-plan schema (defined ONCE here; the verifier consumes it)
# ---------------------------------------------------------------------------

class BackendBindingPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    temperature: float
    seed: int | None
    model_pin: str
    wall_clock_dependent: bool


class ToolBindingsPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    read_grants: list[str]
    write_allowlist: list[str]


class TriggerWiringPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: str
    listener: str
    activation_gate: str
    authorization: str


class InstrumentationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    streams: list[str]
    inspectors: list[str]
    retention: str | None


class VerifierPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    target: str
    placement: str
    on_failure: str


class RoutingEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_class: str
    route: str  # direct | workflow
    bound_tools: list[str]
    note: str = ""  # set for workflow entries with undeclared bindings (J2)


class StagingPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    durability: str  # accretion-backed, fixed (DR-CMD-065)


class ActuationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    loop: str
    per_event_disposition: bool
    standing_table: list[str]
    feedback_loop: bool
    planner: bool
    routing: list[RoutingEntry]
    staging: StagingPlan


class AgentBuildPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    agent: str
    profile_version: str
    profile_hash: str
    factory_version: FactoryVersion
    derived_positions: dict[str, float | str | None]  # D2 is the enum string
    backend_binding: BackendBindingPlan
    tool_bindings: ToolBindingsPlan
    trigger_wiring: list[TriggerWiringPlan]
    instrumentation: InstrumentationPlan
    verifiers: list[VerifierPlan]
    precedence_table: list[str]
    tie_break: str
    actuation: ActuationPlan
    plan_hash: str


class PersonalizationManifest(BaseModel):
    """The manifest's declared personalization section (DR-CMD-070)."""

    model_config = ConfigDict(frozen=True)
    principal_id: str
    bindings_hash: str
    disposition_ref: str


class AgentArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    profile_hash: str
    plan_hash: str
    artifact_hash: str
    factory_version: FactoryVersion
    personalization: PersonalizationManifest | None = None
    """Declared personalization section (DR-CMD-070): who this build is
    bound to, the hash of the effective PERSONAL/BUILD field values, and
    the disposition authorizing the binding. Hash-covered like every other
    manifest field: an undisclosed mutation breaks artifact_hash and the
    verifier refuses at ingest; a disclosed re-binding is a new build."""


class AgentArtifact(BaseModel):
    """The compiler's final output; the verifier's input. Structure only."""

    model_config = ConfigDict(frozen=True)
    plan: AgentBuildPlan
    manifest: AgentArtifactManifest


# ---------------------------------------------------------------------------
# Q2 discriminator — the runtime predicate (spec §5, edge wording finalized)
# ---------------------------------------------------------------------------

def classify_effect_sequence(effects: list[dict]) -> str:
    """Classify one proposed action's effect sequence: direct | workflow.

    Each effect: {"tool_id", "args_bound", "depends_on_prior",
    "interstep_guard"}. "Bound" means bound from the disposition record
    or from the standing rule plus the activating trigger event. A tool
    action is exactly one effect with bound args, no prior-result
    dependence, no inter-step guard. Read-only tool uses are not effects
    and never reach this predicate.
    """
    if (len(effects) == 1 and effects[0].get("args_bound")
            and not effects[0].get("depends_on_prior")
            and not effects[0].get("interstep_guard")):
        return "direct"
    return "workflow"


# ---------------------------------------------------------------------------
# Compile stages (the flow's run-book tools call these; compile_source
# orchestrates them directly — the flow is the pipeline's form, not its
# executor, in this build)
# ---------------------------------------------------------------------------

def _canonical_bytes(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def tool_parse_profile(payload: dict) -> dict:
    """rb-compiler-ingest: bytes -> profile object + hash."""
    try:
        profile = AgentBehaviorProfile.model_validate_json(
            payload["profile_bytes"])
    except (ValidationError, KeyError, TypeError, ValueError) as e:
        raise CompileRefused("ingesting", f"profile does not parse: {e}")
    profile_hash = hashlib.sha256(profile.canonical()).hexdigest()
    return {"profile": profile, "profile_hash": profile_hash,
            "profile_parsed": True}


def tool_run_validators(payload: dict) -> dict:
    """rb-compiler-validate: C1-C5, C7 (C6 retired, DR-CMD-077) + derivations + personalization-bound, loudly.

    DR-CMD-070 extends what "validated" means (the profile must have passed
    through bind_personalization()); the compiler contract — validated
    profile bytes -> artifact, same stages — is unchanged (DR-CMD-066)."""
    profile = payload["profile"]
    try:
        profile.require_personalized()
        AgentBehaviorProfile.model_validate(profile.model_dump(mode="json"))
    except (ValidationError, ValueError) as e:
        raise CompileRefused("validating", str(e))
    return {"violation_count": 0}


def tool_derive_positions(payload: dict) -> dict:
    """rb-compiler-derive: record the derived position vector."""
    profile: AgentBehaviorProfile = payload["profile"]
    derived = profile.position_vector()
    # The schema already enforces derived == declared (DR-CMD-062); the
    # stage re-asserts against the derivation functions (single source).
    d1, d3, d4, d5, d7 = (profile.d1_authority, profile.d3_reproducibility,
                          profile.d4_observability, profile.d5_scope,
                          profile.d7_verification)
    checks = {
        "D1": (d1.position, derive_d1_position(
            d1.per_event_disposition, d1.standing_dispositions,
            d1.self_correction, d1.self_planning)),
        "D3": (d3.position, derive_d3_position(
            d3.deterministic_execution, d3.replay_supported)),
        "D4": (d4.position, derive_d4_position(
            d4.records_events, d4.records_intents, d4.records_verifications)),
        "D5": (d5.position, derive_d5_position(d5.write_scope)),
        "D7": (d7.position, derive_d7_position(
            d7.intent_target, d7.event_target, d7.world_target,
            d7.trigger_target)),
    }
    for dim, (declared, recomputed) in checks.items():
        if abs(declared - recomputed) > 1e-9:
            raise CompileRefused(
                "deriving",
                f"{dim} declared {declared} != recomputed {recomputed}")
    return {"derived_positions": derived, "derived_ok": True}


def _resolve_channel(channel: str) -> list[str]:
    """A write-scope channel -> contracted tool ids (J1)."""
    if channel in AGENT_TOOL_IDS:
        return [channel]
    if channel in CHANNEL_ALIASES:
        return list(CHANNEL_ALIASES[channel])
    raise CompileRefused(
        "routing",
        f"write-scope channel {channel!r} names no registered contracted "
        f"tool or alias (B-3 analog)")


_LISTENERS = {"operator": "session-listener",
              "world": "webhook-allowlist", "self": "scheduler",
              "agent": "staging-event-feed"}

_PLACEMENTS = {
    "intent": "principal->agent: intent authenticity check",
    "event": "agent->log: trace integrity/attribution",
    "world": "world->agent: independent corroboration",
    "trigger": "trigger->agent: activation-gate authentication",
}


def tool_emit_plan(payload: dict) -> dict:
    """rb-compiler-plan: facet-by-facet compilation (spec §4) + the
    mechanical totality guard: every profile facet mapped, asserted."""
    profile: AgentBehaviorProfile = payload["profile"]
    d1, d2 = profile.d1_authority, profile.d2_fidelity
    d3, d4 = profile.d3_reproducibility, profile.d4_observability
    d5, d6 = profile.d5_scope, profile.d6_initiative
    d7 = profile.d7_verification
    profile_hash: str = payload["profile_hash"]
    fv: FactoryVersion = payload["factory_version"]

    backend = BackendBindingPlan(
        temperature=0.0 if d3.deterministic_execution else 1.0,  # J3
        seed=(int(hashlib.sha256(
            (profile_hash + "|d3-seed").encode()).hexdigest()[:16], 16)
              if d3.deterministic_execution else None),
        model_pin=("factory-pinned-model-v1"  # J3; Q1 resolves the reference
                   if d3.deterministic_execution else "unpinned"),
        wall_clock_dependent=not d3.deterministic_execution,
    )
    allowlist: list[str] = []
    for channel in d5.write_scope:
        for tool_id in _resolve_channel(channel):
            if tool_id not in allowlist:
                allowlist.append(tool_id)
    tools = ToolBindingsPlan(read_grants=list(d5.read_scope),
                             write_allowlist=allowlist)
    wiring = [TriggerWiringPlan(
        source=s.value, listener=_LISTENERS[s.value],
        activation_gate=d6.gating[s], authorization=d6.authorization[s])
        for s in sorted(d6.sources, key=lambda x: x.value)]
    streams = [name for name, flag in
               (("event", d4.records_events), ("intent", d4.records_intents),
                ("verification", d4.records_verifications)) if flag]
    instrumentation = InstrumentationPlan(
        streams=streams, inspectors=list(d4.inspectors),
        retention=d4.retention)
    targets = [("intent", d7.intent_target), ("event", d7.event_target),
               ("world", d7.world_target), ("trigger", d7.trigger_target)]
    verifiers = [VerifierPlan(target=t, placement=_PLACEMENTS[t],
                              on_failure=d7.on_failure)
                 for t, flag in targets if flag]
    actuation = ActuationPlan(
        loop="stage -> disposition -> execute",
        per_event_disposition=d1.per_event_disposition,
        standing_table=list(d1.standing_dispositions),
        feedback_loop=d1.self_correction,
        planner=d1.self_planning,
        routing=[],  # filled by the routing stage
        staging=StagingPlan(durability="accretion-backed"),  # DR-CMD-065
    )
    plan = AgentBuildPlan(
        agent=profile.agent, profile_version=profile.version,
        profile_hash=profile_hash, factory_version=fv,
        derived_positions=payload["derived_positions"],
        backend_binding=backend, tool_bindings=tools,
        trigger_wiring=wiring, instrumentation=instrumentation,
        verifiers=verifiers, precedence_table=list(d2.principal_precedence),
        tie_break=d2.conflict_rule, actuation=actuation, plan_hash="")

    # Mechanical totality guard: every profile facet appears in the plan.
    coverage = [
        ("d1.per_event_disposition",
         plan.actuation.per_event_disposition == d1.per_event_disposition),
        ("d1.standing_dispositions",
         plan.actuation.standing_table == d1.standing_dispositions),
        ("d1.self_correction",
         plan.actuation.feedback_loop == d1.self_correction),
        ("d1.self_planning", plan.actuation.planner == d1.self_planning),
        ("d2.principal_precedence",
         plan.precedence_table == d2.principal_precedence),
        ("d2.conflict_rule", plan.tie_break == d2.conflict_rule),
        ("d3.deterministic_execution",
         (plan.backend_binding.temperature == 0.0)
         == d3.deterministic_execution),
        ("d4.streams", plan.instrumentation.streams == streams),
        ("d4.inspectors",
         plan.instrumentation.inspectors == d4.inspectors),
        ("d4.retention", plan.instrumentation.retention == d4.retention),
        ("d5.read_scope", plan.tool_bindings.read_grants == d5.read_scope),
        ("d6.sources",
         sorted(w.source for w in plan.trigger_wiring)
         == sorted(s.value for s in d6.sources)),
        ("d6.gating+authorization",
         all(w.activation_gate and w.authorization
             for w in plan.trigger_wiring)),
        ("d7.targets",
         sorted(v.target for v in plan.verifiers)
         == sorted(t for t, flag in targets if flag)),
        ("d7.on_failure",
         all(v.on_failure == d7.on_failure for v in plan.verifiers)),
        ("staging.durability",
         plan.actuation.staging.durability == "accretion-backed"),
    ]
    unmapped = [name for name, ok in coverage if not ok]
    if unmapped:
        raise CompileRefused(
            "planning", f"facet coverage failed (totality): {unmapped}")
    return {"plan": plan, "plan_complete": True}


def _classify_class(action_class: str) -> RoutingEntry:
    """Compile-time classification of one standing-disposition class (J2)."""
    if action_class in AGENT_TOOL_IDS:
        return RoutingEntry(action_class=action_class, route="direct",
                            bound_tools=[action_class])
    if action_class in CHANNEL_ALIASES:
        tools = CHANNEL_ALIASES[action_class]
        route = "direct" if len(tools) == 1 else "workflow"
        return RoutingEntry(action_class=action_class, route=route,
                            bound_tools=list(tools))
    # Unresolvable class name: NOT a refusal (J2). Routes workflow with an
    # explanatory note; the runtime predicate classifies per proposed
    # action, and an unseen flow source is never pre-authorized (spec §5).
    return RoutingEntry(
        action_class=action_class, route="workflow", bound_tools=[],
        note=("class tools undeclared in profile: runtime classification "
              "per proposed action; flow source drafted and staged per "
              "event, never pre-authorized"))


def tool_resolve_tools(payload: dict) -> dict:
    """rb-compiler-route (1/2): every write-scope channel resolves (J1)."""
    profile: AgentBehaviorProfile = payload["profile"]
    resolved: dict[str, list[str]] = {}
    for channel in profile.d5_scope.write_scope:
        resolved[channel] = _resolve_channel(channel)  # raises on unknown
    return {"resolved_channels": resolved}


def tool_classify_actions(payload: dict) -> dict:
    """rb-compiler-route (2/2): the Q2 routing table, total over standing
    classes and write channels."""
    profile: AgentBehaviorProfile = payload["profile"]
    plan: AgentBuildPlan = payload["plan"]
    resolved: dict[str, list[str]] = payload["resolved_channels"]
    routing: list[RoutingEntry] = []
    for channel, tool_ids in resolved.items():
        route = "direct" if len(tool_ids) == 1 else "workflow"
        routing.append(RoutingEntry(
            action_class=channel, route=route, bound_tools=list(tool_ids),
            note="" if route == "direct" else
            f"channel alias expands to {len(tool_ids)} tools"))
    for cls in profile.d1_authority.standing_dispositions:
        routing.append(_classify_class(cls))
    plan = AgentBuildPlan.model_validate(
        {**plan.model_dump(mode="json"),
         "actuation": {**plan.actuation.model_dump(mode="json"),
                       "routing": [r.model_dump(mode="json")
                                   for r in routing]}})
    return {"plan": plan, "routing_ok": True}


def _plan_canonical(plan: AgentBuildPlan) -> bytes:
    dump = plan.model_dump(mode="json")
    dump.pop("plan_hash", None)
    return _canonical_bytes(dump)


def tool_canonicalize_artifact(payload: dict) -> dict:
    """rb-compiler-materialize: canonical bytes + plan_hash."""
    plan: AgentBuildPlan = payload["plan"]
    plan_bytes = _plan_canonical(plan)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    plan = AgentBuildPlan.model_validate(
        {**plan.model_dump(mode="json"), "plan_hash": plan_hash})
    return {"plan": plan, "plan_bytes": plan_bytes,
            "materialized": True}


def tool_mint_manifest(payload: dict) -> dict:
    """rb-compiler-attest: the manifest; artifact_hash binds plan+manifest."""
    plan: AgentBuildPlan = payload["plan"]
    plan_bytes: bytes = payload["plan_bytes"]
    p13n = payload["profile"].personalization
    manifest = AgentArtifactManifest(
        profile_hash=plan.profile_hash, plan_hash=plan.plan_hash,
        artifact_hash="",
        factory_version=plan.factory_version,
        personalization=(PersonalizationManifest(
            principal_id=p13n.principal_id,
            bindings_hash=p13n.bindings_hash,
            disposition_ref=p13n.disposition_ref)
            if p13n is not None else None))
    core = manifest.model_dump(mode="json")
    core.pop("artifact_hash", None)
    artifact_hash = hashlib.sha256(
        _canonical_bytes(core) + plan_bytes).hexdigest()
    manifest = AgentArtifactManifest.model_validate(
        {**manifest.model_dump(mode="json"), "artifact_hash": artifact_hash})
    for field in ("profile_hash", "plan_hash", "artifact_hash"):
        if not getattr(manifest, field):
            raise CompileRefused("attesting",
                                 f"manifest incomplete: {field} empty")
    return {"manifest": manifest, "manifest_ok": True}


def mint_artifact(plan: AgentBuildPlan,
                 personalization: PersonalizationManifest | None = None
                 ) -> AgentArtifact:
    """Re-mint an artifact from a plan (used by tests to re-mint after a
    white-box mutation — the verifier must still catch the tamper)."""
    out = tool_canonicalize_artifact({"plan": plan})
    # mint_artifact has no source profile: the personalization section is
    # supplied explicitly (tamper tests) or left None.
    from types import SimpleNamespace
    out.update(tool_mint_manifest(
        {"plan": out["plan"], "plan_bytes": out["plan_bytes"],
         "profile_hash": out["plan"].profile_hash,
         "profile": SimpleNamespace(personalization=personalization)}))
    return AgentArtifact(plan=out["plan"], manifest=out["manifest"])


def compile_source(profile_bytes: bytes,
                   factory_version: FactoryVersion | None = None
                   ) -> AgentArtifact:
    """Compile profile bytes -> agent artifact. Pure: {profile bytes,
    factory_version} -> artifact. Any refusal is a CompileRefused."""
    fv = factory_version or default_factory_version()
    payload: dict = {"profile_bytes": profile_bytes, "factory_version": fv}
    payload.update(tool_parse_profile(payload))
    payload.update(tool_run_validators(payload))
    payload.update(tool_derive_positions(payload))
    payload.update(tool_emit_plan(payload))
    payload.update(tool_resolve_tools(payload))
    payload.update(tool_classify_actions(payload))
    payload.update(tool_canonicalize_artifact(payload))
    payload.update(tool_mint_manifest(payload))
    return AgentArtifact(plan=payload["plan"], manifest=payload["manifest"])


def compile_profile(profile: AgentBehaviorProfile,
                    factory_version: FactoryVersion | None = None
                    ) -> AgentArtifact:
    """Compile an in-memory profile (already validated by construction)."""
    return compile_source(profile.canonical(), factory_version)


# ---------------------------------------------------------------------------
# The factory's own pipeline as an automaton flow (DR-CMD-064 D2):
# pydantic source (DR-CMD-058) bridged to entities.
# ---------------------------------------------------------------------------

def _task(name: str, runbook_id: str) -> AutomatonState:
    return AutomatonState(name=name, kind="task", runbook_id=runbook_id,
                          step_policy="abort")


AGENT_COMPILER_FLOW = AutomatonSource(
    name="agent-compiler-flow",
    release_version=FACTORY_RELEASE,
    initial_state="ingesting",
    states=[
        _task("ingesting", "rb-compiler-ingest"),
        _task("validating", "rb-compiler-validate"),
        _task("deriving", "rb-compiler-derive"),
        _task("planning", "rb-compiler-plan"),
        _task("routing", "rb-compiler-route"),
        _task("materializing", "rb-compiler-materialize"),
        _task("attesting", "rb-compiler-attest"),
        AutomatonState(name="done", kind="end", outcome="completed"),
        AutomatonState(name="failed", kind="end", outcome="aborted"),
    ],
    transitions=[
        AutomatonTransition(from_state="ingesting", trigger="external",
                            guard="payload.profile_parsed == True",
                            to_state="validating"),
        AutomatonTransition(from_state="ingesting", trigger="run_aborted",
                            to_state="failed"),
        AutomatonTransition(from_state="validating", trigger="run_completed",
                            guard="payload.violation_count == 0",
                            to_state="deriving"),
        AutomatonTransition(from_state="validating", trigger="run_aborted",
                            to_state="failed"),
        AutomatonTransition(from_state="deriving", trigger="run_completed",
                            guard="payload.derived_ok == True",
                            to_state="planning"),
        AutomatonTransition(from_state="deriving", trigger="run_aborted",
                            to_state="failed"),
        AutomatonTransition(from_state="planning", trigger="run_completed",
                            guard="payload.plan_complete == True",
                            to_state="routing"),
        AutomatonTransition(from_state="planning", trigger="run_aborted",
                            to_state="failed"),
        AutomatonTransition(from_state="routing", trigger="run_completed",
                            guard="payload.routing_ok == True",
                            to_state="materializing"),
        AutomatonTransition(from_state="routing", trigger="run_aborted",
                            to_state="failed"),
        AutomatonTransition(from_state="materializing",
                            trigger="run_completed",
                            guard="payload.materialized == True",
                            to_state="attesting"),
        AutomatonTransition(from_state="materializing",
                            trigger="run_aborted", to_state="failed"),
        AutomatonTransition(from_state="attesting", trigger="run_completed",
                            guard="payload.manifest_ok == True",
                            to_state="done"),
        AutomatonTransition(from_state="attesting", trigger="run_aborted",
                            to_state="failed"),
    ],
    runbooks=[
        RunBookSource(id="rb-compiler-ingest", name="rb-compiler-ingest",
                      steps=[RunBookStepSource(tool_id="tool-parse-profile")]),
        RunBookSource(id="rb-compiler-validate", name="rb-compiler-validate",
                      steps=[RunBookStepSource(tool_id="tool-run-validators")]),
        RunBookSource(id="rb-compiler-derive", name="rb-compiler-derive",
                      steps=[RunBookStepSource(
                          tool_id="tool-derive-positions")]),
        RunBookSource(id="rb-compiler-plan", name="rb-compiler-plan",
                      steps=[RunBookStepSource(tool_id="tool-emit-plan")]),
        RunBookSource(id="rb-compiler-route", name="rb-compiler-route",
                      steps=[RunBookStepSource(tool_id="tool-resolve-tools"),
                             RunBookStepSource(
                                 tool_id="tool-classify-actions")]),
        RunBookSource(id="rb-compiler-materialize",
                      name="rb-compiler-materialize",
                      steps=[RunBookStepSource(
                          tool_id="tool-canonicalize-artifact")]),
        RunBookSource(id="rb-compiler-attest", name="rb-compiler-attest",
                      steps=[RunBookStepSource(tool_id="tool-mint-manifest")]),
    ],
)

# The factory flow's tool registry: names the pipeline tools (bridge §5:
# naming is not defining). Implementations are the stage functions above.
FACTORY_FLOW_TOOL_REGISTRY: dict[str, Callable] = {
    "tool-parse-profile": tool_parse_profile,
    "tool-run-validators": tool_run_validators,
    "tool-derive-positions": tool_derive_positions,
    "tool-emit-plan": tool_emit_plan,
    "tool-resolve-tools": tool_resolve_tools,
    "tool-classify-actions": tool_classify_actions,
    "tool-canonicalize-artifact": tool_canonicalize_artifact,
    "tool-mint-manifest": tool_mint_manifest,
}


# Public aliases used by the conformance verifier's recompute checks (S3, S4).
resolve_channel = _resolve_channel
classify_standing_class = _classify_class


def compile_factory_flow():
    """Bridge the compiler pipeline source to AutomatonFlow entities."""
    return bridge_compile(AGENT_COMPILER_FLOW, FACTORY_FLOW_TOOL_REGISTRY)


__all__ = [
    "AGENT_TOOL_IDS",
    "CHANNEL_ALIASES",
    "TOOL_REGISTRY_PIN",
    "FACTORY_RELEASE",
    "SCHEMA_VERSION",
    "SEMANTICS_TABLE_VERSION",
    "PROBE_SUITE_VERSION",
    "AgentArtifact",
    "AgentArtifactManifest",
    "AgentBuildPlan",
    "ActuationPlan",
    "BackendBindingPlan",
    "CompileRefused",
    "FactoryVersion",
    "InstrumentationPlan",
    "PersonalizationManifest",
    "RoutingEntry",
    "StagingPlan",
    "ToolBindingsPlan",
    "TriggerWiringPlan",
    "VerifierPlan",
    "AGENT_COMPILER_FLOW",
    "FACTORY_FLOW_TOOL_REGISTRY",
    "classify_effect_sequence",
    "classify_standing_class",
    "compile_factory_flow",
    "compile_profile",
    "compile_source",
    "default_factory_version",
    "mint_artifact",
    "resolve_channel",
]
