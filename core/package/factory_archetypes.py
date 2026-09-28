"""Agent archetypes — authoring-reliability constraints (Peter, 2026-09-26).

An archetype is a CONSTRAINT on authoring, not a generative pipeline stage.
There is deliberately no archetype+parameters -> profile instantiation
machinery: the factory compiler's input contract is unchanged (it takes a
validated profile; DR-CMD-066 is not amended by this module). The archetype
check runs at authoring time, before compile.

An archetype = a named set of facet invariants + declared parameter points +
a conformance predicate ``conforms(profile, archetype) -> [violations]``.
A new profile declares its archetype(s); the authoring gate refuses
violations with explicit reasons. The exemplar set is the registered
built population (DR-CMD-098): every profile present in a
PROFILE_SET_00X + PROFILE_ARCHETYPES_00X registry with a green set run
must conform, and a non-conformance is a finding about the archetype
definition, never a license to alter a profile facet.

Archetype set — the Tetrad (DR-CMD-094, 2026-09-27; "Triad" deprecated):
staff/field/office derived from the seven profiles' shared invariants
(DR-CMD-069); clerk admitted by operator disposition (DR-CMD-094),
which supersedes DR-CMD-093's deferral and the DR-CMD-069 evidentiary
bar for this instance. The bar stands for future admissions.
  staff   (analyst, advisor, author, monitor, coordinator, customizer)
  field   (analyst, monitor, executor)
  office  (advisor, author, coordinator, customizer)
  clerk   () — no built profiles yet; populating it (e.g. inbox-organizer,
            news-synthesizer-poster) is outstanding work

Declined: a single-member "acting-agent" archetype for the executor's
field may-act D1/D5 shape. The data does not earn it (one member); C7
plus the field archetype already cover the critical core (no unverified
world contact, no fail-open at high assurance). The may-act x office
cell is a different matter: clerk fills it (DR-CMD-094).

Deterministic: every predicate is a pure function of the profile.

DR-CMD-070: every invariant declares the (facet, field) pairs it reads
(``touches``); a definition-time check rejects invariants touching
PRINCIPAL_PERSONAL fields — archetypes constrain principal-agnostic
planes only. S1 was amended accordingly: the direct
standing_dispositions-emptiness check is removed (PERSONAL/BUILD); the
derived D1 position == 0.0 check keeps its teeth, and
bind_personalization() re-runs the gate on the bound profile, so a
principal binding that grants autonomy refuses the binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .agent_behavior import AgentBehaviorProfile, TriggerSource

# Predicate: None = invariant holds; otherwise a human-readable reason.
Check = Callable[[AgentBehaviorProfile], "str | None"]


@dataclass(frozen=True)
class Invariant:
    """One checkable facet invariant of an archetype."""
    id: str          # stable id, e.g. "S1"
    statement: str   # human-readable statement of the invariant
    check: Check     # predicate over a profile
    touches: tuple[tuple[str, str], ...] = ()
    # (facet, field) pairs the predicate reads, e.g.
    # ("d5_scope", "write_scope"). Definition-time rule (DR-CMD-070): every
    # touched field must be tagged FACTORY_CONFIG or PROFILE_CUSTOM in
    # PLANE_TAGS, or be a derived field — archetypes never touch
    # PRINCIPAL_PERSONAL fields (the line from DR-CMD-069, now mechanical).


@dataclass(frozen=True)
class Violation:
    """One failed invariant, with an explicit reason for the refusal."""
    archetype: str
    invariant: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.archetype}/{self.invariant}] {self.detail}"


@dataclass(frozen=True)
class Archetype:
    """A named authoring constraint: invariants + parameter points."""
    name: str
    description: str
    members: tuple[str, ...]      # exemplar member labels (documentation)
    invariants: tuple[Invariant, ...]
    parameters: tuple[str, ...]   # declared parameter points (documentation;
                                  # author-decided within schema bounds)


# ---------------------------------------------------------------------------
# staff — mechanizes J-A (analyst, advisor, author, monitor, coordinator)
# ---------------------------------------------------------------------------

def _s1_d1_no_autonomy(profile: AgentBehaviorProfile) -> str | None:
    # DR-CMD-070 amendment: the direct standing_dispositions-emptiness check
    # is removed — standing_dispositions is PRINCIPAL_PERSONAL/BUILD, which
    # archetypes may not touch. The derived-position check below keeps S1's
    # teeth: any binding granting a standing disposition moves D1 off 0.0
    # (positions are derived), and bind_personalization() re-runs this gate
    # on the bound profile, refusing the binding.
    a = profile.d1_authority
    problems = []
    if not a.per_event_disposition:
        problems.append("per_event_disposition must be True")
    if a.self_correction:
        problems.append("self_correction must be False")
    if a.self_planning:
        problems.append("self_planning must be False")
    if a.position != 0.0:
        problems.append(f"D1 position must be 0.0, got {a.position}")
    return "; ".join(problems) or None


def _s2_no_write_scope(profile: AgentBehaviorProfile) -> str | None:
    s = profile.d5_scope
    if s.write_scope:
        return ("write_scope must be empty: a staff agent's work product "
                "IS its staged proposals, realized by the accretion-backed "
                "staging area (J-A), not by tool effects; got "
                f"{s.write_scope}")
    if s.position != 0.0:
        return f"D5 position must be 0.0, got {s.position}"
    return None


def _s3_full_instrumentation(profile: AgentBehaviorProfile) -> str | None:
    o = profile.d4_observability
    problems = []
    for stream in ("records_events", "records_intents", "records_verifications"):
        if not getattr(o, stream):
            problems.append(f"d4.{stream} must be True")
    for inspector in ("operator", "auditor"):
        if inspector not in o.inspectors:
            problems.append(f"d4.inspectors must include {inspector!r}")
    if o.retention != "forever":
        problems.append(f"d4.retention must be 'forever', got {o.retention!r}")
    if o.position != 1.0:
        problems.append(f"D4 position must be 1.0, got {o.position}")
    return "; ".join(problems) or None


def _s4_stage_only_authorizations(profile: AgentBehaviorProfile) -> str | None:
    bad = {s.value: auth
           for s, auth in profile.d6_initiative.authorization.items()
           if "may-act" in auth.lower()}
    if bad:
        return ("every D6 authorization must be stage-only (no 'may-act'): "
                + "; ".join(f"{src}={auth!r}" for src, auth in bad.items()))
    return None


STAFF = Archetype(
    name="staff",
    description=("Agents whose entire work product is staged proposals for "
                 "operator disposition (proposer != disposer). Mechanizes "
                 "judgment call J-A."),
    members=("analyst", "advisor", "author", "monitor", "coordinator",
             "customizer"),
    invariants=(
        Invariant("S1", "D1 0.0: per-event disposition, no self-correction, "
                        "no self-planning (standing dispositions excluded "
                        "via the derived position: any grant moves D1 off "
                        "0.0; DR-CMD-070)",
                  _s1_d1_no_autonomy,
                  touches=(("d1_authority", "per_event_disposition"),
                           ("d1_authority", "self_correction"),
                           ("d1_authority", "self_planning"),
                           ("d1_authority", "position"))),
        Invariant("S2", "D5 0.0: empty write_scope — output is staged "
                        "proposals, not tool effects",
                  _s2_no_write_scope,
                  touches=(("d5_scope", "write_scope"),
                           ("d5_scope", "position"))),
        Invariant("S3", "D4 1.0: full event/intent/verification streams; "
                        "inspectors operator+auditor; retention forever",
                  _s3_full_instrumentation,
                  touches=(("d4_observability", "records_events"),
                           ("d4_observability", "records_intents"),
                           ("d4_observability", "records_verifications"),
                           ("d4_observability", "inspectors"),
                           ("d4_observability", "retention"),
                           ("d4_observability", "position"))),
        Invariant("S4", "every D6 authorization is stage-only (no may-act)",
                  _s4_stage_only_authorizations,
                  touches=(("d6_initiative", "authorization"),)),
    ),
    parameters=(
        "D2 conflict_rule + position (bounded by C6)",
        "D3 facets (deterministic_execution, replay_supported)",
        "D6 source set (non-empty per C5; every source stage-only per S4)",
        "D7 targets + on_failure (bounded by C7)",
        "D5 read_scope contents",
        "agent label",
    ),
)


# ---------------------------------------------------------------------------
# field — agents that touch raw world claims (analyst, monitor, executor)
# ---------------------------------------------------------------------------

def _w1_all_boundaries_verified(profile: AgentBehaviorProfile) -> str | None:
    v = profile.d7_verification
    missing = [t for t, on in
               (("intent_target", v.intent_target),
                ("event_target", v.event_target),
                ("world_target", v.world_target),
                ("trigger_target", v.trigger_target)) if not on]
    problems = []
    if missing:
        problems.append(
            "field agents must verify all four trust boundaries; "
            f"missing: {missing}")
    if v.position != 1.0:
        problems.append(f"D7 position must be 1.0, got {v.position}")
    return "; ".join(problems) or None


def _w2_world_gate_authenticated(profile: AgentBehaviorProfile) -> str | None:
    i = profile.d6_initiative
    if TriggerSource.WORLD in i.sources:
        gate = i.gating.get(TriggerSource.WORLD, "").strip().lower()
        if gate in {"", "none", "unauthenticated"}:
            return ("world trigger gate must authenticate the trigger "
                    f"(e.g. allowlist + signature), got {gate!r}")
    return None


FIELD = Archetype(
    name="field",
    description=("Agents that read raw world claims or act on the world: "
                 "every trust boundary verified, world triggers "
                 "authenticated."),
    members=("analyst", "monitor", "executor"),
    invariants=(
        Invariant("W1", "D7 1.0: intent, event, world, and trigger targets "
                        "all verified",
                  _w1_all_boundaries_verified,
                  touches=(("d7_verification", "intent_target"),
                           ("d7_verification", "event_target"),
                           ("d7_verification", "world_target"),
                           ("d7_verification", "trigger_target"),
                           ("d7_verification", "position"))),
        Invariant("W2", "world trigger gate authenticates the trigger",
                  _w2_world_gate_authenticated,
                  touches=(("d6_initiative", "sources"),
                           ("d6_initiative", "gating"))),
    ),
    parameters=(
        "D7 on_failure: escalate | fail_closed (fail_open refused by C7)",
        "D1/D2/D5 positions and facets",
        "D6 source sets and authorization rules",
    ),
)


# ---------------------------------------------------------------------------
# office — agents that read staged material only
# (advisor, author, coordinator)
# ---------------------------------------------------------------------------

def _h1_no_world_target(profile: AgentBehaviorProfile) -> str | None:
    v = profile.d7_verification
    problems = []
    if v.world_target:
        problems.append(
            "world_target must be False: this agent reads harness-internal "
            "staged material, not raw world claims — claiming world "
            "corroboration it cannot perform is incoherent")
    for target, on in (("intent_target", v.intent_target),
                       ("event_target", v.event_target),
                       ("trigger_target", v.trigger_target)):
        if not on:
            problems.append(f"{target} must be True")
    if v.position != 0.75:
        problems.append(f"D7 position must be 0.75, got {v.position}")
    return "; ".join(problems) or None


OFFICE = Archetype(
    name="office",
    description=("Agents that read harness-internal staged material only: "
                 "no world-target verification claimed."),
    members=("advisor", "author", "coordinator", "customizer"),
    invariants=(
        Invariant("H1", "D7 0.75: intent, event, trigger verified; "
                        "world_target False",
                  _h1_no_world_target,
                  touches=(("d7_verification", "intent_target"),
                           ("d7_verification", "event_target"),
                           ("d7_verification", "world_target"),
                           ("d7_verification", "trigger_target"),
                           ("d7_verification", "position"))),
    ),
    parameters=(
        "D7 on_failure: escalate | fail_closed",
        "D2 conflict_rule + position (bounded by C6)",
        "D3 facets",
        "D6 source sets (stage-only per staff S4)",
        "D5 read_scope contents",
    ),
)


# ---------------------------------------------------------------------------
# clerk — may-act x office (DR-CMD-094; label confirmed DR-CMD-095).
# Agents that act on the world on standing operator
# disposition while reading staged material only. Fills the unnamed cell of
# the two-axis model (DR-CMD-092 §3.4). First member: registrar_clerk
# (registered DR-CMD-104).
# ---------------------------------------------------------------------------

def _cl1_d1_may_act(profile: AgentBehaviorProfile) -> str | None:
    # Flipped S1 polarity; DR-CMD-070 applies symmetrically: the derived D1
    # position carries the standing-disposition grant — archetypes may not
    # touch standing_dispositions (PRINCIPAL_PERSONAL/BUILD). A clerk
    # commits to action on standing operator disposition: no per-event
    # disposition gate, derived position above 0.0.
    a = profile.d1_authority
    problems = []
    if a.per_event_disposition:
        problems.append("per_event_disposition must be False: a clerk acts "
                        "on standing operator disposition, not per-event "
                        "disposition")
    if a.position <= 0.0:
        problems.append(f"D1 position must be > 0.0, got {a.position}")
    return "; ".join(problems) or None


def _cl2_d4_full_instrumentation(profile: AgentBehaviorProfile) -> str | None:
    o = profile.d4_observability
    if o.position != 1.0:
        return (f"D4 position must be 1.0, got {o.position}: a clerk's world "
                f"actions are fully observed (mirrors staff S3's position "
                f"requirement)")
    return None


def _cl3_d5_bounded_write_scope(profile: AgentBehaviorProfile) -> str | None:
    s = profile.d5_scope
    problems = []
    if not s.write_scope:
        problems.append("write_scope must be non-empty: a clerk acts, and "
                        "its effect channels are declared")
    if any(w in {"unbounded", "open-ended", "*"} for w in s.write_scope):
        problems.append("write_scope must be bounded: 'unbounded', "
                        "'open-ended' and '*' are refused — declare the "
                        "effect channels (cf. derive_d5_position bands)")
    if s.position <= 0.0:
        problems.append(f"D5 position must be > 0.0, got {s.position}")
    return "; ".join(problems) or None


def _cl4_d6_operator_only(profile: AgentBehaviorProfile) -> str | None:
    sources = profile.d6_initiative.sources
    bad = sorted(s.value for s in sources if s is not TriggerSource.OPERATOR)
    if bad:
        return ("D6 sources must be OPERATOR only: acting without external "
                "corroboration is operator-initiated or it does not happen; "
                f"got {bad}")
    if not sources:
        return ("D6 sources must be non-empty (C5): a clerk is activated "
                "by the operator")
    return None


def _cl6_d2_principal_wins(profile: AgentBehaviorProfile) -> str | None:
    # DR-CMD-077: D2 is the binary enum {principal_wins_ties,
    # world_wins_ties}. DR-CMD-093's derivation said "commission_wins_ties";
    # corrected here (DR-CMD-094): the principal's commission binds — the
    # commission IS the principal's standing disposition. Presented bytes
    # never win ties; world_wins_ties is incoherent for office reading
    # (there is no world_target to win).
    rule = profile.d2_fidelity.conflict_rule
    if rule != "principal_wins_ties":
        return (f"D2 conflict_rule must be 'principal_wins_ties', got "
                f"{rule!r}: the principal's commission binds action "
                f"parameters; presented bytes never win ties — "
                f"'world_wins_ties' is incoherent with office reading "
                f"(no world_target)")
    return None


CLERK = Archetype(
    name="clerk",
    description=("Agents that act on the world on standing operator "
                 "disposition while reading staged material only: "
                 "may-act x office. Label confirmed DR-CMD-095."),
    members=("registrar_clerk",),
    invariants=(
        Invariant("CL1", "D1 > 0.0: standing operator disposition, no "
                         "per-event disposition gate (flipped S1 polarity; "
                         "standing_dispositions excluded via the derived "
                         "position per DR-CMD-070)",
                  _cl1_d1_may_act,
                  touches=(("d1_authority", "per_event_disposition"),
                           ("d1_authority", "position"))),
        Invariant("CL2", "D4 1.0: full instrumentation — a clerk's world "
                         "actions are fully observed (mirrors staff S3's "
                         "position requirement)",
                  _cl2_d4_full_instrumentation,
                  touches=(("d4_observability", "position"),)),
        Invariant("CL3", "D5 > 0.0: non-empty, bounded write_scope — effect "
                         "channels declared, never unbounded",
                  _cl3_d5_bounded_write_scope,
                  touches=(("d5_scope", "write_scope"),
                           ("d5_scope", "position"))),
        Invariant("CL4", "D6 OPERATOR only: no WORLD, AGENT, or SELF triggers "
                         "(non-empty per C5)",
                  _cl4_d6_operator_only,
                  touches=(("d6_initiative", "sources"),)),
        Invariant("CL5", "D7 office reading: reuses H1 (0.75; intent, event, "
                         "trigger verified; world_target False)",
                  _h1_no_world_target,
                  touches=(("d7_verification", "intent_target"),
                           ("d7_verification", "event_target"),
                           ("d7_verification", "world_target"),
                           ("d7_verification", "trigger_target"),
                           ("d7_verification", "position"))),
        Invariant("CL6", "D2 principal_wins_ties: the principal's commission "
                         "binds action parameters; presented bytes never win "
                         "ties (world_wins_ties incoherent with office "
                         "reading; DR-CMD-077)",
                  _cl6_d2_principal_wins,
                  touches=(("d2_fidelity", "conflict_rule"),)),
    ),
    parameters=(
        "D1 standing disposition classes (the pre-authorized action classes)",
        "D5 write_scope bounds (effect channels, declared)",
        "D6 authorization rule text (operator authorization for may-act)",
        "D2 fixed: principal_wins_ties",
        "D7 on_failure: escalate | fail_closed",
        "agent label",
    ),
)


ARCHETYPES: dict[str, Archetype] = {
    a.name: a for a in (STAFF, FIELD, OFFICE, CLERK)
}


def _validate_invariant_planes() -> None:
    """Definition-time check (DR-CMD-070): archetype invariants may only
    touch FACTORY_CONFIG / PROFILE_CUSTOM fields, or derived fields.
    PRINCIPAL_PERSONAL fields are never constrainable by an archetype —
    the line from DR-CMD-069, now mechanical. An invariant with an
    undeclared or mistagged touch fails at import, loudly."""
    from .agent_behavior import DERIVED_FIELDS, PLANE_TAGS, Plane
    for arch in ARCHETYPES.values():
        for inv in arch.invariants:
            if not inv.touches:
                raise ValueError(
                    f"archetype {arch.name!r} invariant {inv.id}: touches "
                    f"undeclared — every invariant must declare the "
                    f"(facet, field) pairs it reads")
            for facet, field in inv.touches:
                if (facet, field) in DERIVED_FIELDS:
                    continue
                plane = PLANE_TAGS.get((facet, field))
                if plane is None:
                    raise ValueError(
                        f"archetype {arch.name!r} invariant {inv.id}: "
                        f"{(facet, field)} is not a tagged configurable "
                        f"field")
                if plane is Plane.PRINCIPAL_PERSONAL:
                    raise ValueError(
                        f"archetype {arch.name!r} invariant {inv.id}: "
                        f"{(facet, field)} is PRINCIPAL_PERSONAL — "
                        f"archetypes may not constrain principal-bound fields")


_validate_invariant_planes()


def conforms(profile: AgentBehaviorProfile,
             archetype: Archetype) -> list[Violation]:
    """Check one profile against one archetype. Empty = conforms."""
    violations = []
    for inv in archetype.invariants:
        reason = inv.check(profile)
        if reason is not None:
            violations.append(Violation(archetype.name, inv.id, reason))
    return violations


def check_profile(profile: AgentBehaviorProfile,
                  archetype_names: tuple[str, ...] | list[str]
                  ) -> list[Violation]:
    """Authoring gate: check a profile against its declared archetypes.

    Returns violations (refuse with explicit reasons). Empty = gate green.
    """
    violations: list[Violation] = []
    for name in archetype_names:
        if name not in ARCHETYPES:
            raise ValueError(
                f"unknown archetype {name!r}; known: {sorted(ARCHETYPES)}")
        violations.extend(conforms(profile, ARCHETYPES[name]))
    return violations


__all__ = [
    "ARCHETYPES",
    "STAFF",
    "FIELD",
    "OFFICE",
    "CLERK",
    "Archetype",
    "Invariant",
    "Violation",
    "check_profile",
    "conforms",
]


if __name__ == "__main__":
    # Gate self-test: the exemplar set IS the registered built population
    # (DR-CMD-098) — "registered" = present in a PROFILE_SET_00X +
    # PROFILE_ARCHETYPES_00X registry with its set run green. New profiles in
    # existing sets join automatically; a new set joins with one line in
    # PROFILE_SET_PAIRS below. triager and dr_registrar are not
    # registered (compile-refused, DR-CMD-097/100) and correctly do not join
    # yet; they join on registration with green set runs, no disposition.
    # registrar_clerk joined on registration (DR-CMD-104).
    from .agent_behavior import D5Scope
    from .factory_profile_set_001 import PROFILE_ARCHETYPES, PROFILE_SET_001
    from .factory_profile_set_002 import (
        PROFILE_ARCHETYPES_002, PROFILE_SET_002)

    PROFILE_SET_PAIRS = (
        (PROFILE_SET_001, PROFILE_ARCHETYPES),
        (PROFILE_SET_002, PROFILE_ARCHETYPES_002),
    )

    total = 0
    for profile_set, archetypes in PROFILE_SET_PAIRS:
        for label, builder in profile_set.items():
            vs = check_profile(builder(), archetypes[label])
            print(f"{label}: {len(vs)} violations")
            total += len(vs)
            for v in vs:
                print(f"    {v}")
    assert total == 0, f"exemplars must conform, got {total} violations"

    # Validating rebuild: model_copy(update=) skips pydantic validation
    # (AGENTS.md lesson), which would make this negative control vacuous.
    base = PROFILE_SET_001["analyst"]()
    bad = AgentBehaviorProfile.model_validate({
        **base.model_dump(),
        "d5_scope": D5Scope(position=0.15, read_scope=["web-search"],
                            write_scope=["tool-run-doctor"]),
    })
    neg = check_profile(bad, PROFILE_ARCHETYPES["analyst"])
    assert neg, "synthetic write_scope violation must refuse"
    print("negative case refused as expected:")
    for v in neg:
        print(f"    {v}")

    try:
        check_profile(bad, ("no-such-archetype",))
    except ValueError as e:
        print(f"unknown archetype rejected as expected: {e}")
    else:
        raise AssertionError("unknown archetype name must raise ValueError")

    # Clerk non-vacuousness (DR-CMD-094): no built clerk profile exists, so
    # discrimination is shown with existing exemplars as negative controls.
    # A staff profile (D1 0.0, D5 0.0) must refuse clerk (CL1, CL3); the
    # executor (D7 1.0, world_target) must refuse clerk (CL5).
    staff_vs_clerk = check_profile(PROFILE_SET_001["analyst"](), ("clerk",))
    assert staff_vs_clerk, "staff profile must refuse clerk"
    assert any(v.invariant == "CL1" for v in staff_vs_clerk), \
        "expected a CL1 (D1 may-act) refusal"
    print("staff profile refused clerk as expected:")
    for v in staff_vs_clerk:
        print(f"    {v}")

    executor_vs_clerk = check_profile(PROFILE_SET_001["executor"](),
                                       ("clerk",))
    assert executor_vs_clerk, "executor must refuse clerk"
    assert any(v.invariant == "CL5" for v in executor_vs_clerk), \
        "expected a CL5 (office reading) refusal"
    print("executor refused clerk as expected:")
    for v in executor_vs_clerk:
        print(f"    {v}")

    print("archetype gate self-test: ok")
