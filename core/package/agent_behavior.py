"""Seven Dimensions of Agent Behavior (D1-D7) — pydantic source.

Status: set composition (D1-D7) ratified 2026-09-26 — D7 membership explicitly
ratified (Peter). Name "Seven Dimensions of Agent Behavior" ratified 2026-09-26
(Peter). Reference architecture adopted 2026-09-26 (Peter), DR-CMD-060; dsys one
instantiation. Derived scalars adopted 2026-09-26 (Peter), DR-CMD-062.

Seven design dimensions for agentic execution architecture. Scalar positions are
DERIVED from each dimension's facet configuration by a documented, deterministic
function — calibration by construction: two profilers configuring the same
facets get the same numbers. D2 is the honest exception: declared-but-bounded
by its conflict rule, hence auditable. D6 is structural: no scalar.

  D1 Authority:       who commits to action (human disposition <-> adaptability)
  D2 Fidelity:        what execution is faithful to (intent-sovereignty <-> world-alignment)
  D3 Reproducibility: whether execution replays identically (deterministic <-> stochastic)
  D4 Observability:   who can witness what happened (black box <-> fully inspectable)
  D5 Scope:           what the agent may affect, read x write (narrow <-> broad)
  D6 Initiative:      what may activate the agent
                      (source {operator,world,self,agent} x gating x authorization)
                      agent = another built agent's staging state change,
                      observed through the staging medium (DR-CMD-078)
  D7 Verification:    how rigorously claims are checked at trust boundaries
                      (unverified <-> every boundary verified; second-order over
                      ground truths established by D1/D2/D4)

Derivation functions (stipulated but uniform; documented here, enforced below):
  D1: 0.25 * (standing_nonempty + self_correction + self_planning
              + (not per_event_disposition))
      i.e. the share of the action repertoire executable without per-event
      disposition.
  D2: the binary enum {principal_wins_ties, world_wins_ties} (DR-CMD-077).
      No scalar: whose claims prevail at ties is declared outright, and
      incoherent posture declarations are unrepresentable by construction.
  D3: 0.5 * ((not deterministic_execution) + (not replay_supported))
      i.e. the entropy budget.
  D4: (records_events + records_intents + records_verifications) / 3.
  D5: write-scope breadth bands — empty: 0.0; 1-3 channels: 0.15; 4-10: 0.4;
      more: 0.7; any of {unbounded, open-ended, *}: 1.0.
      List one channel per capability (granularity discipline).
  D6: no scalar.
  D7: (intent_target + event_target + world_target + trigger_target) / 4.

Cross-dimension couplings found by falsification are enforced as validators:
  C1 (D1-D4 boundary): per-event disposition entails a minimum audit trail.
  C2 (D1-D7 boundary): self-correction entails minimal verification.
  C3 (D7-D4 target):   event-target verification needs the trace.
  C4 (D6 completeness): every trigger source must carry an explicit gate AND an
                       explicit authorization rule, even if "none"/"stage-only".
                       Activation (may the trigger fire?) is distinct from
                       authorization (may the agent act on it?).
  C5 (stated modeling rule): a profile with no activation source is vacuous.
  C6 (D2 coherence):   RETIRED — superseded by DR-CMD-077. D2's schema value
                       is the binary enum {principal_wins_ties,
                       world_wins_ties}; with no scalar position there is
                       nothing to bound, and incoherent posture declarations
                       are unrepresentable by construction.
  C7 (D7 coherence):   fail_open with derived verification position > 0.5 is
                       refused (promoted from advisory W3: claiming high
                       assurance while configured to continue past verification
                       failure is incoherent).

CONSTRUCTION SEMANTICS (factory step 1) — what each facet compiles to:  D1 per_event_disposition -> stage -> await-disposition -> execute actuation loop
  D1 standing_dispositions -> pre-authorized action-class rule table
  D1 self_correction       -> bounded observe/compare/adjust feedback loop
  D1 self_planning         -> planner component (plans staged per D1 position)
  D2 principal_precedence  -> conflict precedence table
  D2 conflict_rule         -> tie-breaking rule on intent/world conflict
  D3 deterministic_execution -> temperature 0, seeded RNG, pinned model,
                             no wall-clock dependence
  D3 replay_supported      -> event log + re-execution driver
  D4 records_*             -> instrumentation streams (event/intent/verification logs)
  D4 inspectors, retention -> read grants + storage policy
  D5 read_scope            -> data-source grants
  D5 write_scope           -> effect channels (tool allowlist; contracted tools)
  D6 sources               -> trigger wiring per source
  D6 gating                -> activation gate per source: may the trigger fire?
  D6 authorization          -> authorization rule per source: may the agent act?
                             ("stage-only" vs "may-act")
  D7 *_target              -> verifier component at the corresponding trust boundary
                             (intent: principal authenticity; event: log
                             integrity/attribution; world: independent
                             corroboration; trigger: trigger authentication)
  D7 on_failure            -> fail_closed: halt and stage; fail_open: log and
                             continue; escalate: stage for principal disposition

Risky-but-coherent combinations are advisory only, via warnings().

PLANES (DR-CMD-070, ratified 2026-09-26) — every configurable facet field
carries a plane tag in PLANE_TAGS: who disposes it, and when it binds.

  FACTORY_CONFIG    machine governor; pre-factory; shared across principals.
                    Audit instrumentation, storage policy, gate vocabulary.
  PROFILE_CUSTOM    profile author; binds at authoring; closes at the factory
                    gate (immutable post-build by hash coverage). Role-shaping.
  PRINCIPAL_PERSONAL the principal served; binds at the personalization stage
                    (bind_personalization) or accretes at standing. Never
                    touched by archetype invariants (definition-time check in
                    factory_archetypes.py).

  PRINCIPAL_PERSONAL fields carry a bind time:
  BUILD      affects the position vector / behavior guarantees; bound in the
             manifest's personalization section pre-verify; re-verified per
             binding (standing_dispositions, principal_precedence).
  REFERENCE  accreted as var/ material at standing; validated at reference
             time via reference_binding(), never in the build hash
             (interaction_preferences).

Lifecycle: generic profile (PERSONAL/BUILD unbound) -> bind_personalization
(principal-bound, disposed, archetype re-gated) -> compile -> verify ->
standing (PERSONAL/REFERENCE accretes) -> active -> closed -> superseded.
DR-CMD-062 untouched: positions remain derived, never hand-set — the binder
recomputes them. DR-CMD-066 untouched: the compiler still takes a validated
profile; "validated" now includes personalization-bound (enforced in the
compiler's validating stage).
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Annotated, Callable, Literal, Mapping

from pydantic import (BaseModel, ConfigDict, Field, TypeAdapter,
                      ValidationError, model_validator)

UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]

_POSITION_TOLERANCE = 1e-9


def derive_d1_position(per_event_disposition: bool,
                       standing_dispositions: list[str],
                       self_correction: bool,
                       self_planning: bool) -> float:
    """D1 position: share of the action repertoire executable without
    per-event disposition. Stipulated weights, uniform application."""
    return 0.25 * ((1 if standing_dispositions else 0)
                   + (1 if self_correction else 0)
                   + (1 if self_planning else 0)
                   + (0 if per_event_disposition else 1))


def derive_d3_position(deterministic_execution: bool,
                       replay_supported: bool) -> float:
    """D3 position: entropy budget. 0.0 = fully determined; 1.0 = unseeded."""
    return 0.5 * ((0 if deterministic_execution else 1)
                  + (0 if replay_supported else 1))


def derive_d4_position(records_events: bool, records_intents: bool,
                       records_verifications: bool) -> float:
    """D4 position: fraction of instrumentation streams enabled."""
    return (int(records_events) + int(records_intents)
            + int(records_verifications)) / 3


def derive_d5_position(write_scope: list[str]) -> float:
    """D5 position: write-scope breadth bands. List one channel per capability."""
    if not write_scope:
        return 0.0
    if any(s in {"unbounded", "open-ended", "*"} for s in write_scope):
        return 1.0
    n = len(write_scope)
    if n <= 3:
        return 0.15
    if n <= 10:
        return 0.4
    return 0.7


def derive_d7_position(intent_target: bool, event_target: bool,
                       world_target: bool, trigger_target: bool) -> float:
    """D7 position: fraction of trust-boundary targets verified."""
    return (int(intent_target) + int(event_target)
            + int(world_target) + int(trigger_target)) / 4


def _check_derived(dim: str, declared: float, derived: float) -> None:
    if abs(declared - derived) > _POSITION_TOLERANCE:
        raise ValueError(
            f"{dim} position {declared} != value derived from its facets "
            f"({derived}); positions are derived, not declared (DR-CMD-062)")


class TriggerSource(str, Enum):
    OPERATOR = "operator"
    WORLD = "world"
    SELF = "self"
    AGENT = "agent"  # DR-CMD-078: activation by another agent's staging
                     # state change, observed through the staging medium
                     # (stigmergic trigger — through staging, never around).


class Plane(str, Enum):
    """Disposition plane of a configurable facet field (DR-CMD-070).

    FACTORY_CONFIG: the machine governor disposes; pre-factory; shared
        across principals (audit instrumentation, storage policy).
    PROFILE_CUSTOM: the profile author disposes; binds at authoring; closes
        at the factory gate (role-shaping: scopes, conflict rules, gates).
    PRINCIPAL_PERSONAL: the principal served disposes; binds at the
        personalization stage or accretes at standing. Archetype invariants
        may never touch these fields (checked at archetype definition).
    """
    FACTORY_CONFIG = "factory-config"
    PROFILE_CUSTOM = "profile-custom"
    PRINCIPAL_PERSONAL = "principal-personal"


class BindTime(str, Enum):
    """When a PRINCIPAL_PERSONAL field binds (DR-CMD-070).

    BUILD: bound pre-verify in the manifest's personalization section;
        affects the position vector / behavior guarantees; re-verified
        per binding.
    REFERENCE: accreted as var/ material at standing; validated at
        reference time; never part of the build hash.
    """
    BUILD = "build"
    REFERENCE = "reference"


class D1Authority(BaseModel):
    """D1 — Authority: who commits to action.
    Position derived: share of the repertoire executable without per-event
    disposition."""

    position: UnitFloat = 0.0
    per_event_disposition: bool = False
    standing_dispositions: list[str] = Field(default_factory=list)
    self_correction: bool = False
    self_planning: bool = False

    @model_validator(mode="after")
    def _check_derived(self):
        _check_derived("D1", self.position, derive_d1_position(
            self.per_event_disposition, self.standing_dispositions,
            self.self_correction, self.self_planning))
        return self


class D2Fidelity(BaseModel):
    """D2 — Fidelity: whose claims prevail when principal and world conflict.

    DR-CMD-077 reconciliation: D2's schema value IS the binary enum
    {principal_wins_ties, world_wins_ties} — "principal" over "intent"
    because the question is jurisdictional (whose claims prevail), not
    hermeneutic (what was meant). The -ties qualifier is load-bearing: the
    enum governs the conflict limit case, not ordinary operation.
    The scalar position retired with C6: posture gradations were a redundant
    encoding of what role prose already says; the human-facing posture
    content lives in the profile's role description, not the schema.
    """

    principal_precedence: list[str] = Field(default_factory=list)
    conflict_rule: Literal["principal_wins_ties",
                           "world_wins_ties"] = "principal_wins_ties"
    interaction_preferences: dict[str, str] = Field(
        default_factory=dict,
        description=("PRINCIPAL_PERSONAL/REFERENCE: the principal's interaction "
                     "posture (e.g. challenge-style, clarification-style). "
                     "Declared slots, filled by the principal; accreted as var/ "
                     "at standing and validated at reference time — never a "
                     "build input, never in the build hash."))


class D3Reproducibility(BaseModel):
    """D3 — Reproducibility: whether execution replays identically.
    Position derived: entropy budget."""

    position: UnitFloat = 0.0
    deterministic_execution: bool = False
    replay_supported: bool = False

    @model_validator(mode="after")
    def _check_derived(self):
        _check_derived("D3", self.position, derive_d3_position(
            self.deterministic_execution, self.replay_supported))
        return self


class D4Observability(BaseModel):
    """D4 — Observability: who can witness what happened.
    Position derived: fraction of instrumentation streams enabled."""

    position: UnitFloat = 0.0
    records_events: bool = False
    records_intents: bool = False
    records_verifications: bool = False
    inspectors: list[str] = Field(default_factory=list)
    retention: str | None = None

    @model_validator(mode="after")
    def _check_derived(self):
        _check_derived("D4", self.position, derive_d4_position(
            self.records_events, self.records_intents,
            self.records_verifications))
        return self


class D5Scope(BaseModel):
    """D5 — Scope: what the agent may affect.
    Position derived: write-scope breadth bands. List one channel per
    capability (granularity discipline); the factory builds from the list,
    not the number."""

    position: UnitFloat = 0.0
    read_scope: list[str] = Field(default_factory=list)
    write_scope: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_derived(self):
        _check_derived("D5", self.position,
                       derive_d5_position(self.write_scope))
        return self


class D6Initiative(BaseModel):
    """D6 — Initiative: what may activate the agent.
    Structural: no scalar. Activation (gating: may the trigger fire?) is
    distinct from authorization (may the agent act on it?). The rule
    (sources/policy) is separated from the checking of the rule (D7).
    Sources: operator (the principal), world (authenticated external
    events), self (the agent's own cadence/sweeps), agent (another built
    agent's staging state change, observed through the staging medium —
    stigmergic trigger, DR-CMD-078)."""

    sources: set[TriggerSource] = Field(default_factory=set)
    gating: dict[TriggerSource, str] = Field(default_factory=dict)
    authorization: dict[TriggerSource, str] = Field(default_factory=dict)


class D7Verification(BaseModel):
    """D7 — Verification: how rigorously claims are checked at trust boundaries.
    Position derived: fraction of targets verified. Second-order: targets
    are ground truths established by D1 (principal), D2 (world), D4 (trace)."""

    position: UnitFloat = 0.0
    intent_target: bool = False
    event_target: bool = False
    world_target: bool = False
    trigger_target: bool = False
    on_failure: Literal["fail_closed", "fail_open", "escalate"] = "escalate"

    @model_validator(mode="after")
    def _check_derived_and_c7(self):
        derived = derive_d7_position(self.intent_target, self.event_target,
                                     self.world_target, self.trigger_target)
        _check_derived("D7", self.position, derived)
        if self.on_failure == "fail_open" and derived > 0.5:  # C7
            raise ValueError(
                "D7 fail_open with derived verification position > 0.5 "
                "refused: high assurance claimed while configured to continue "
                "past verification failure is incoherent")
        return self


class PersonalizationState(BaseModel):
    """Record of the personalization stage (DR-CMD-070).

    Set exactly once by bind_personalization(): the generic profile becomes
    principal-bound. The compiler's validating stage refuses profiles whose
    state is None ("validated" now includes personalization-bound; the
    compiler contract itself — validated profile bytes -> artifact — is
    unchanged, DR-CMD-066). No timestamps, no wall-clock: binding is pure.
    """
    model_config = ConfigDict(frozen=True)

    principal_id: str
    disposition_ref: str  # the principal's disposition that authorized this
    # binding (recorded, never invented: author drafts, principal disposes)
    bindings_hash: str     # hash of the effective PERSONAL/BUILD field values


class AgentBehaviorProfile(BaseModel):
    """A positioned profile of one agent across D1-D7."""

    agent: str
    version: str = "1.0"
    d1_authority: D1Authority
    d2_fidelity: D2Fidelity
    d3_reproducibility: D3Reproducibility
    d4_observability: D4Observability
    d5_scope: D5Scope
    d6_initiative: D6Initiative
    d7_verification: D7Verification
    personalization: PersonalizationState | None = None
    """None = generic profile (PERSONAL/BUILD fields at role defaults,
    unbound to any principal). Set = principal-bound via
    bind_personalization(). Required before compile."""

    @model_validator(mode="after")
    def _check_couplings(self):
        a, o, v, i = (self.d1_authority, self.d4_observability,
                      self.d7_verification, self.d6_initiative)
        # C1: per-event disposition entails a minimum audit trail (D1-D4).
        if a.per_event_disposition and not o.records_events:
            raise ValueError("per_event_disposition requires d4.records_events")
        # C2: self-correction entails minimal verification (D1-D7).
        if a.self_correction and v.position == 0.0:
            raise ValueError("self_correction requires d7.position > 0")
        # C3: event-target verification needs the trace (D7-D4).
        if v.event_target and not o.records_events:
            raise ValueError("d7.event_target requires d4.records_events")
        # C4: every trigger source must carry an explicit gate AND an explicit
        # authorization rule (D6 completeness).
        missing_gate = [s.value for s in i.sources if s not in i.gating]
        if missing_gate:
            raise ValueError(f"d6 sources missing gating: {missing_gate}")
        missing_auth = [s.value for s in i.sources if s not in i.authorization]
        if missing_auth:
            raise ValueError(f"d6 sources missing authorization: {missing_auth}")
        # C5 (stated modeling rule): no activation source is vacuous.
        if not i.sources:
            raise ValueError("d6.sources must be non-empty")
        return self

    def warnings(self) -> list[str]:
        """Coherent but dangerous combinations. Advisory, never a refusal."""
        w: list[str] = []
        gate_w = self.d6_initiative.gating.get(TriggerSource.WORLD, "")
        if (TriggerSource.WORLD in self.d6_initiative.sources
                and self.d5_scope.write_scope
                and gate_w.strip().lower() in {"none", "unauthenticated"}):
            w.append("world-triggered activation with write scope "
                     "and no trigger authentication")
        if self.d1_authority.position >= 0.7 and self.d4_observability.position <= 0.3:
            w.append("high autonomy with minimal audit trail")
        return w

    def position_vector(self) -> dict[str, float | str | None]:
        """Scalar summary. Positions are calibrated: derived from facets.
        D2 is categorical since DR-CMD-077 (binary enum
        {principal_wins_ties, world_wins_ties}, no scalar); D6 is
        structural and carries no scalar."""
        return {
            "D1": self.d1_authority.position,
            "D2": self.d2_fidelity.conflict_rule,
            "D3": self.d3_reproducibility.position,
            "D4": self.d4_observability.position,
            "D5": self.d5_scope.position,
            "D6": None,
            "D7": self.d7_verification.position,
        }

    def canonical(self) -> bytes:
        """Canonical byte form: sorted keys, compact separators, sorted sources.

        Set ordering is unstable across runs (hash randomization), so sources
        are sorted here; two profiles differing only in source insertion order
        canonicalize byte-identically.
        """
        data = self.model_dump(mode="json")
        data["d6_initiative"]["sources"] = sorted(data["d6_initiative"]["sources"])
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def require_personalized(self) -> None:
        """Schema-owned bound check: the profile must have passed through
        bind_personalization() before compile. Called by the compiler's
        validating stage (DR-CMD-070; DR-CMD-066 contract unchanged)."""
        if self.personalization is None:
            raise ValueError(
                "profile has no personalization binding: run "
                "bind_personalization() before compile")


# ---------------------------------------------------------------------------
# Plane registry (DR-CMD-070). (facet, field) -> Plane for every
# configurable field. Facet keys are the profile attribute names;
# "profile" covers the profile's own leaf fields. Derived positions are
# not configurable: they live in DERIVED_FIELDS. An untagged field is an
# implementation bug (asserted at import).
# ---------------------------------------------------------------------------

_FC, _CU, _PE = Plane.FACTORY_CONFIG, Plane.PROFILE_CUSTOM, Plane.PRINCIPAL_PERSONAL

PLANE_TAGS: dict[tuple[str, str], Plane] = {
    # D1 Authority
    ("d1_authority", "per_event_disposition"): _CU,   # role shape (S1)
    ("d1_authority", "standing_dispositions"): _PE,    # the principal's
    # pre-authorizations; BUILD: moves D1, hence behavior guarantees
    ("d1_authority", "self_correction"): _CU,
    ("d1_authority", "self_planning"): _CU,
    # D2 Fidelity — DR-CMD-077: the schema value IS the binary enum
    # {principal_wins_ties, world_wins_ties}; no scalar position to tag.
    ("d2_fidelity", "principal_precedence"): _PE,     # who the principal is;
    # BUILD: feeds conflict resolution guarantees
    ("d2_fidelity", "conflict_rule"): _CU,           # the D2 value itself:
    # whose claims prevail at ties (J-B/J-E)
    ("d2_fidelity", "interaction_preferences"): _PE,  # principal's
    # interaction posture; REFERENCE: accreted, never built
    # D3 Reproducibility
    ("d3_reproducibility", "deterministic_execution"): _CU,
    ("d3_reproducibility", "replay_supported"): _CU,
    # D4 Observability — audit instrumentation is a machine-governor
    # guarantee (factory agents are fully instrumented by policy, not by
    # role choice); the role declares only its oversight surface.
    ("d4_observability", "records_events"): _FC,
    ("d4_observability", "records_intents"): _FC,
    ("d4_observability", "records_verifications"): _FC,
    ("d4_observability", "inspectors"): _CU,   # which *roles* may inspect
    # ("operator" = the principal role, principal-agnostic)
    ("d4_observability", "retention"): _FC,    # storage policy
    # D5 Scope
    ("d5_scope", "read_scope"): _CU,                  # role-shaping (S2)
    ("d5_scope", "write_scope"): _CU,
    # D6 Initiative — per-source gate/authorization *choices* are
    # role-shaping; the gate vocabulary itself is pinned in the factory
    # version (semantics table).
    ("d6_initiative", "sources"): _CU,
    ("d6_initiative", "gating"): _CU,
    ("d6_initiative", "authorization"): _CU,  # rule text is role-level;
    # its *exercise* references the principal at runtime
    # D7 Verification
    ("d7_verification", "intent_target"): _CU,
    ("d7_verification", "event_target"): _CU,
    ("d7_verification", "world_target"): _CU,
    ("d7_verification", "trigger_target"): _CU,
    ("d7_verification", "on_failure"): _CU,
    # Profile identity
    ("profile", "agent"): _CU,                        # authoring label
    ("profile", "version"): _CU,
    ("profile", "personalization"): _PE,             # the binding record
    # itself; BUILD (hash-covered in the manifest)
}

DERIVED_FIELDS: set[tuple[str, str]] = {
    ("d1_authority", "position"),
    ("d3_reproducibility", "position"),
    ("d4_observability", "position"),
    ("d5_scope", "position"),
    ("d7_verification", "position"),
}

BIND_TIMES: dict[tuple[str, str], BindTime] = {
    ("d1_authority", "standing_dispositions"): BindTime.BUILD,
    ("d2_fidelity", "principal_precedence"): BindTime.BUILD,
    ("d2_fidelity", "interaction_preferences"): BindTime.REFERENCE,
    ("profile", "personalization"): BindTime.BUILD,
}


FACET_MODELS: dict[str, type[BaseModel]] = {
    "d1_authority": D1Authority,
    "d2_fidelity": D2Fidelity,
    "d3_reproducibility": D3Reproducibility,
    "d4_observability": D4Observability,
    "d5_scope": D5Scope,
    "d6_initiative": D6Initiative,
    "d7_verification": D7Verification,
}
"""Facet name -> schema model. Shared by the plane-coverage check and the
reference-time reader (both must agree on the field schemas)."""


def _assert_plane_coverage() -> None:
    """Every configurable field is tagged; untagged = implementation bug."""
    for facet, model in FACET_MODELS.items():
        for field in model.model_fields:
            if (facet, field) in DERIVED_FIELDS or (facet, field) in PLANE_TAGS:
                continue
            raise AssertionError(
                f"plane registry incomplete: untagged configurable field "
                f"{(facet, field)}")
    for field in ("agent", "version", "personalization"):
        if ("profile", field) not in PLANE_TAGS:
            raise AssertionError(
                f"plane registry incomplete: untagged profile field {field!r}")


_assert_plane_coverage()


def plane_of(facet: str, field: str) -> Plane | None:
    """The disposition plane of a configurable field, or None if the field
    is derived (see DERIVED_FIELDS) rather than configured."""
    return PLANE_TAGS.get((facet, field))


def personalization_bindings_hash(profile: AgentBehaviorProfile) -> str:
    """Hash of the effective PRINCIPAL_PERSONAL/BUILD field values.

    Single source of truth: bind_personalization() writes it into the
    binding record; the verifier's S6 recomputes it. Covers values, not
    the input bindings dict (role defaults + bindings merged)."""
    data: dict[str, object] = {}
    for (facet, field), plane in sorted(PLANE_TAGS.items()):
        if plane is not Plane.PRINCIPAL_PERSONAL:
            continue
        if BIND_TIMES.get((facet, field)) is not BindTime.BUILD:
            continue
        if (facet, field) == ("profile", "personalization"):
            continue  # the record holds the hash; hashing it is circular
        holder = profile if facet == "profile" else getattr(profile, facet)
        data[f"{facet}.{field}"] = getattr(holder, field)
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def bind_personalization(
    profile: AgentBehaviorProfile,
    principal_id: str,
    bindings: dict[tuple[str, str], object],
    disposition_ref: str,
    gate: Callable[[AgentBehaviorProfile], list[str]] | None = None,
) -> AgentBehaviorProfile:
    """The personalization stage: generic profile -> principal-bound profile.

    bindings maps (facet, field) -> value, restricted to
    PRINCIPAL_PERSONAL/BUILD fields (standing_dispositions,
    principal_precedence). Role defaults stand where no binding is given.
    Returns a NEW validated profile; the input is untouched.

    The author-agent flow: the author agent *drafts* the bindings and stages
    them; the principal *disposes* — disposition_ref records that
    disposition (never invented). gate, when given, re-checks archetype
    conformance on the bound profile (a binding that moves a position off
    its archetype's invariant — e.g. granting a staging agent a standing
    disposition moves D1 off 0.0 — refuses the binding, not the profile).

    Positions are recomputed from the bound facets (DR-CMD-062: derived,
    never hand-set), then the full schema validation (C1-C5, C7 — C6 retired, DR-CMD-077) runs. Pure:
    no timestamps, no randomness — the same inputs bind byte-identically.
    """
    if not principal_id:
        raise ValueError("bind_personalization: principal_id must be non-empty")
    if not disposition_ref:
        raise ValueError(
            "bind_personalization: disposition_ref must be non-empty "
            "(the principal's disposition authorizing this binding)")
    for key in bindings:
        if key not in PLANE_TAGS:
            raise ValueError(
                f"bind_personalization: unknown field {key}")
        if (PLANE_TAGS[key] is not Plane.PRINCIPAL_PERSONAL
                or BIND_TIMES.get(key) is not BindTime.BUILD
                or key == ("profile", "personalization")):
            raise ValueError(
                f"bind_personalization: {key} is not a bindable "
                f"PRINCIPAL_PERSONAL/BUILD field")

    data = profile.model_dump(mode="json")
    for (facet, field), value in bindings.items():
        data[facet][field] = value
    # Recompute derived positions from the bound facets (DR-CMD-062).
    d1 = data["d1_authority"]
    d1["position"] = derive_d1_position(
        d1["per_event_disposition"], d1["standing_dispositions"],
        d1["self_correction"], d1["self_planning"])
    d3 = data["d3_reproducibility"]
    d3["position"] = derive_d3_position(
        d3["deterministic_execution"], d3["replay_supported"])
    d4 = data["d4_observability"]
    d4["position"] = derive_d4_position(
        d4["records_events"], d4["records_intents"],
        d4["records_verifications"])
    d5 = data["d5_scope"]
    d5["position"] = derive_d5_position(d5["write_scope"])
    d7 = data["d7_verification"]
    d7["position"] = derive_d7_position(
        d7["intent_target"], d7["event_target"],
        d7["world_target"], d7["trigger_target"])
    # D2's position is declared-but-bounded (CUSTOM): untouched by binding.
    bound = AgentBehaviorProfile.model_validate(data)

    if gate is not None:
        reasons = gate(bound)
        if reasons:
            raise ValueError(
                "bind_personalization: binding refused by archetype gate: "
                + "; ".join(reasons))

    state = PersonalizationState(
        principal_id=principal_id,
        disposition_ref=disposition_ref,
        bindings_hash=personalization_bindings_hash(bound),
    )
    return AgentBehaviorProfile.model_validate(
        {**bound.model_dump(mode="json"),
         "personalization": state.model_dump(mode="json")})


class ReferenceBindingError(ValueError):
    """A REFERENCE read that cannot be honored, with explicit reasons.

    Refuse with reasons, never silent: a dangling reference (the slot was
    never filled at standing) or an invalid one (the accreted value fails
    the field's schema) raises here; the caller stages or escalates.
    """

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("reference_binding refused: " + "; ".join(reasons))


def reference_binding(
    facet: str,
    field: str,
    accreted: Mapping[tuple[str, str], object],
) -> object:
    """Reference-time read of a PRINCIPAL_PERSONAL/REFERENCE binding.

    REFERENCE fields (today: ``d2_fidelity.interaction_preferences``) are
    accreted as var/ material at standing — never part of the build hash —
    and validated HERE, at reference time. This function is the read path
    the schema's declaration promises; there is no other.

    ``accreted`` is the standing-time var/ material keyed by
    ``(facet, field)``, mirroring ``bind_personalization``'s ``bindings``.

    Rules — every refusal carries reasons, nothing passes silently:

    - ``(facet, field)`` must be tagged PRINCIPAL_PERSONAL with
      ``BindTime.REFERENCE``. Reading a BUILD field through this path
      would bypass the build hash -> refused. Reading a CUSTOM, CONFIG,
      or derived field -> refused (not principal material).
    - The slot must be present in ``accreted``. A dangling reference (the
      principal never filled the slot at standing) -> refused. There is
      no silent fallback to the role default; a caller that wants the
      default reads the profile facet directly.
    - The accreted value must validate against the field's declared
      schema (TypeAdapter over the facet model's field annotation) ->
      invalid values refused with the validation reasons.

    Pure and deterministic: no I/O, no timestamps, no randomness.
    """
    key = (facet, field)
    if key not in PLANE_TAGS:
        raise ReferenceBindingError([f"unknown field {key}"])
    bind_time = BIND_TIMES.get(key)
    if (PLANE_TAGS[key] is not Plane.PRINCIPAL_PERSONAL
            or bind_time is not BindTime.REFERENCE):
        raise ReferenceBindingError([
            f"{key} is not a PRINCIPAL_PERSONAL/REFERENCE field "
            f"(plane={PLANE_TAGS[key].value}, "
            f"bind_time={bind_time.value if bind_time else None}); "
            f"REFERENCE reads are the only post-factory personalization path"])
    if key not in accreted:
        raise ReferenceBindingError([
            f"dangling reference {key}: no accreted var/ binding for this "
            f"slot; the principal has not filled it at standing"])
    value = accreted[key]
    adapter = TypeAdapter(FACET_MODELS[facet].model_fields[field].annotation)
    try:
        return adapter.validate_python(value)
    except ValidationError as e:
        raise ReferenceBindingError(
            [f"invalid accreted value for {key}: {err['msg']} "
             f"(at {'.'.join(str(p) for p in err['loc']) or '<root>'})"
             for err in e.errors()]) from e


def dsys_profile() -> AgentBehaviorProfile:
    """dsys located in the set. Positions are derived from the facets."""
    return AgentBehaviorProfile(
        agent="dsys",
        d1_authority=D1Authority(
            position=0.25, per_event_disposition=True,
            standing_dispositions=["restart-webhook-handler", "accretion-commit"],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(principal_precedence=["operator"],
                               conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True, replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True, inspectors=["operator", "auditor"],
            retention="forever"),
        d5_scope=D5Scope(position=0.15, read_scope=["accretion-repo", "event-log"],
                          write_scope=["contracted-tools-only"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.WORLD, TriggerSource.SELF},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.WORLD: "allowlist + signature",
                    TriggerSource.SELF: "ambient-staging-only; no self-commit"},
            authorization={TriggerSource.OPERATOR: "may-act on disposition",
                           TriggerSource.WORLD: "stage-only; no self-commit",
                           TriggerSource.SELF: "stage-only; no self-commit"}),
        d7_verification=D7Verification(
            position=1.0, intent_target=True, event_target=True,
            world_target=True, trigger_target=True, on_failure="fail_closed"),
    )


__all__ = [
    "AgentBehaviorProfile",
    "BIND_TIMES",
    "BindTime",
    "D1Authority",
    "D2Fidelity",
    "D3Reproducibility",
    "D4Observability",
    "D5Scope",
    "D6Initiative",
    "D7Verification",
    "DERIVED_FIELDS",
    "PLANE_TAGS",
    "PersonalizationState",
    "Plane",
    "TriggerSource",
    "ValidationError",
    "bind_personalization",
    "derive_d1_position",
    "derive_d3_position",
    "derive_d4_position",
    "derive_d5_position",
    "derive_d7_position",
    "dsys_profile",
    "personalization_bindings_hash",
    "plane_of",
]
