"""Golden run for the D1-D7 Agent Behavior Profile schema (derived scalars).

Acceptances:
  1. dsys_profile() validates clean: zero warnings, expected position vector
     (positions derived from facets).
  2. C1 refused: per-event disposition with no audit trail.
  3. C2 refused: self-correction with zero verification; the repaired
     variant (minimal verification) validates.
  4. C3 refused: event-target verification with no trace.
  5. C4 refused: a trigger source with no explicit gate.
  6. C5 refused: a profile with no activation source (vacuous).
  7. Warnings are advisory, never refusals: (a) world-triggered +
     write scope + unauthenticated trigger; (b) high autonomy +
     minimal audit trail.
  8. Canonical determinism: two constructions differing only in source
     insertion order canonicalize byte-identically; JSON round-trip
     yields an equal profile.
  9. Span: a verifier-pattern LLM agent (adaptable, stochastic, highly
     verified) and a thermostat (world-aligned, deterministic,
     world-triggered, minimally observed) both validate.
 10. Schema-level: a position outside [0, 1] is refused.
 11. Derivation enforced: a declared position contradicting the facets is
     refused, and the error names the derived value.
 12. D2 is the binary enum {principal_wins_ties, world_wins_ties}
     (DR-CMD-077): both values validate; an unknown rule is refused at the
     schema boundary; C6 retired with the scalar.
 13. C7: fail_open with derived verification position > 0.5 refused;
     fail_open at <= 0.5 validates with no warning.
 14. C4 extended: a trigger source with a gate but no authorization refused.
 15. D2 enum: the binary value is carried through position_vector() and the
     canonical form; winner mapping is principal/world only.

Positions in constructed cases are auto-derived from facets via _derive();
cases that must declare a contradicting position bypass it (derive=False).

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

import copy
import hashlib

from pydantic import ValidationError

from .agent_behavior import (
    AgentBehaviorProfile,
    derive_d1_position,
    derive_d3_position,
    derive_d4_position,
    derive_d5_position,
    derive_d7_position,
    dsys_profile,
)


def _base_kwargs() -> dict:
    return {
        "agent": "test-agent",
        "d1_authority": {"position": 0.0, "per_event_disposition": True,
                         "standing_dispositions": [], "self_correction": False,
                         "self_planning": False},
        "d2_fidelity": {"principal_precedence": ["operator"],
                        "conflict_rule": "principal_wins_ties"},
        "d3_reproducibility": {"position": 0.0, "deterministic_execution": True,
                               "replay_supported": True},
        "d4_observability": {"position": 1.0, "records_events": True,
                             "records_intents": True, "records_verifications": True,
                             "inspectors": ["operator"], "retention": "forever"},
        "d5_scope": {"position": 0.15, "read_scope": ["event-log"],
                     "write_scope": ["contracted-tools-only"]},
        "d6_initiative": {"sources": {"operator"},
                          "gating": {"operator": "authenticated-session"},
                          "authorization": {"operator": "may-act on disposition"}},
        "d7_verification": {"position": 1.0, "intent_target": True,
                            "event_target": True, "world_target": True,
                            "trigger_target": True, "on_failure": "fail_closed"},
    }


def _derive(kw: dict) -> dict:
    """Recompute every derived position from the facets.

    D2 is categorical since DR-CMD-077 (binary enum, no scalar) and is
    left untouched by derivation."""
    d1 = kw["d1_authority"]
    d1["position"] = derive_d1_position(
        d1["per_event_disposition"], d1["standing_dispositions"],
        d1["self_correction"], d1["self_planning"])
    d3 = kw["d3_reproducibility"]
    d3["position"] = derive_d3_position(
        d3["deterministic_execution"], d3["replay_supported"])
    d4 = kw["d4_observability"]
    d4["position"] = derive_d4_position(
        d4["records_events"], d4["records_intents"],
        d4["records_verifications"])
    d5 = kw["d5_scope"]
    d5["position"] = derive_d5_position(d5["write_scope"])
    d7 = kw["d7_verification"]
    d7["position"] = derive_d7_position(
        d7["intent_target"], d7["event_target"],
        d7["world_target"], d7["trigger_target"])
    return kw


def _build(mutate, derive: bool = True) -> dict:
    kw = copy.deepcopy(_base_kwargs())
    mutate(kw)
    return _derive(kw) if derive else kw


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    def expect_refused(label: str, kw: dict, match: str | None = None) -> None:
        try:
            AgentBehaviorProfile(**kw)
            violations.append(f"{label} validated but should have been refused")
        except ValidationError as e:
            if match is not None and match not in str(e).lower():
                violations.append(
                    f"{label} refused, but not for the expected reason "
                    f"(wanted {match!r}): {e}")
            else:
                refusals.append(label)

    # 1. dsys locates cleanly in the set; positions are derived from facets.
    dsys = dsys_profile()
    assert dsys.warnings() == [], dsys.warnings()
    assert dsys.position_vector() == {
        "D1": 0.25, "D2": "principal_wins_ties", "D3": 0.0, "D4": 1.0,
        "D5": 0.15, "D6": None, "D7": 1.0,
    }, dsys.position_vector()

    # 2. C1: per-event disposition with no audit trail -> refused.
    # (event_target cleared so the refusal is C1's alone.)
    expect_refused(
        "C1 refused per-event disposition without an audit trail",
        _build(lambda kw: (kw["d4_observability"].update(records_events=False),
                           kw["d7_verification"].update(event_target=False))),
        match="requires d4.records_events",
    )

    # 3. C2: self-correction with zero verification -> refused; repaired passes.
    expect_refused(
        "C2 refused self-correction with zero verification",
        _build(lambda kw: (
            kw["d1_authority"].update(per_event_disposition=False,
                                      self_correction=True),
            kw["d7_verification"].update(intent_target=False,
                                         event_target=False, world_target=False,
                                         trigger_target=False))),
        match="requires d7.position",
    )
    repaired = AgentBehaviorProfile(**_build(lambda kw: (
        kw["d1_authority"].update(per_event_disposition=False,
                                  self_correction=True),
        kw["d7_verification"].update(intent_target=False,
                                     event_target=False, world_target=True,
                                     trigger_target=False),
    )))
    assert repaired.warnings() == [], repaired.warnings()

    # 4. C3: event-target verification with no trace -> refused.
    # (per_event_disposition cleared so the refusal is C3's alone.)
    expect_refused(
        "C3 refused event-target verification without a trace",
        _build(lambda kw: (kw["d1_authority"].update(per_event_disposition=False),
                           kw["d4_observability"].update(records_events=False))),
        match="event_target requires",
    )

    # 5. C4: trigger source with no explicit gate -> refused.
    expect_refused(
        "C4 refused a world trigger source with no gate entry",
        _build(lambda kw: kw["d6_initiative"].update(
            sources={"operator", "world"})),
        match="missing gating",
    )

    # 6. C5: no activation source -> refused (vacuous profile).
    expect_refused(
        "C5 refused a profile with no activation source",
        _build(lambda kw: kw["d6_initiative"].update(
            sources=set(), gating={}, authorization={})),
        match="non-empty",
    )

    # 7a. World trigger + write scope + no authentication: warns, not refused.
    w7a = AgentBehaviorProfile(**_build(lambda kw: (
        kw["d6_initiative"].update(
            sources={"operator", "world"},
            gating={"operator": "authenticated-session", "world": "none"},
            authorization={"operator": "may-act on disposition",
                           "world": "stage-only"}),
        kw["d5_scope"].update(write_scope=["deploy-prod"]),
    )))
    assert any("no trigger authentication" in w for w in w7a.warnings()), \
        w7a.warnings()

    # 7b. High autonomy + minimal audit trail: warns, not refused.
    # (event_target cleared: no trace is kept, so C3 must not fire.)
    w7b = AgentBehaviorProfile(**_build(lambda kw: (
        kw["d1_authority"].update(per_event_disposition=False,
                                  self_correction=True, self_planning=True),
        kw["d4_observability"].update(records_events=False,
                                      records_intents=False,
                                      records_verifications=False),
        kw["d7_verification"].update(event_target=False),
    )))
    assert any("minimal audit trail" in w for w in w7b.warnings()), \
        w7b.warnings()

    # 8. Canonical determinism across source insertion orders; round-trip.
    kw_a = _build(lambda kw: kw["d6_initiative"].update(
        sources={"operator", "world", "self"},
        gating={"operator": "authenticated-session",
                "world": "allowlist + signature",
                "self": "ambient-staging-only; no self-commit"},
        authorization={"operator": "may-act on disposition",
                       "world": "stage-only; no self-commit",
                       "self": "stage-only; no self-commit"}))
    kw_b = _build(lambda kw: kw["d6_initiative"].update(
        sources={"self", "world", "operator"},
        gating={"self": "ambient-staging-only; no self-commit",
                "world": "allowlist + signature",
                "operator": "authenticated-session"},
        authorization={"self": "stage-only; no self-commit",
                       "world": "stage-only; no self-commit",
                       "operator": "may-act on disposition"}))
    pa, pb = AgentBehaviorProfile(**kw_a), AgentBehaviorProfile(**kw_b)
    assert pa.canonical() == pb.canonical(), "canonical form must be order-free"
    digest = hashlib.sha256(pa.canonical()).hexdigest()
    assert len(digest) == 64
    assert AgentBehaviorProfile.model_validate_json(pa.canonical()) == pa, \
        "canonical JSON must round-trip"

    # 9a. Verifier-pattern LLM agent: adaptable, stochastic, highly verified.
    verifier_agent = AgentBehaviorProfile(**_build(lambda kw: (
        kw.update(agent="verifier-llm-agent"),
        kw["d1_authority"].update(per_event_disposition=False,
                                  self_correction=True, self_planning=True),
        kw["d2_fidelity"].update(conflict_rule="principal_wins_ties"),
        kw["d3_reproducibility"].update(deterministic_execution=False,
                                        replay_supported=False),
        kw["d5_scope"].update(read_scope=["inbox", "calendar"],
                              write_scope=["draft-email", "schedule-event"]),
        kw["d6_initiative"].update(
            sources={"operator", "world"},
            gating={"operator": "authenticated-session",
                    "world": "allowlist"},
            authorization={"operator": "may-act on disposition",
                           "world": "stage-only"}),
        kw["d7_verification"].update(on_failure="escalate"),
    )))
    assert verifier_agent.warnings() == [], verifier_agent.warnings()

    # 9b. Thermostat: world-aligned, deterministic, world-triggered, dimly seen.
    thermostat = AgentBehaviorProfile(**_build(lambda kw: (
        kw.update(agent="thermostat"),
        kw["d1_authority"].update(per_event_disposition=False,
                                  standing_dispositions=["regulate-temperature"],
                                  self_correction=True, self_planning=False),
        kw["d2_fidelity"].update(principal_precedence=[],
                                  conflict_rule="world_wins_ties"),
        kw["d4_observability"].update(records_events=False,
                                      records_intents=False,
                                      records_verifications=False,
                                      inspectors=[], retention=None),
        kw["d5_scope"].update(read_scope=["temperature-sensor"],
                              write_scope=["heater-relay"]),
        kw["d6_initiative"].update(sources={"world"},
                                   gating={"world": "hardwired-sensor"},
                                   authorization={"world": "may-act"}),
        kw["d7_verification"].update(intent_target=False,
                                     event_target=False, world_target=True,
                                     trigger_target=False,
                                     on_failure="fail_closed"),
    )))
    # Coherent, but the framework flags autonomy without an audit trail:
    # warnings are advisory, never refusals.
    assert any("minimal audit trail" in w for w in thermostat.warnings()), \
        thermostat.warnings()

    # 10. Schema-level: position outside [0, 1] is refused.
    expect_refused(
        "position 1.5 refused at the schema boundary",
        _build(lambda kw: kw["d1_authority"].update(position=1.5),
               derive=False),
        match="less than or equal to 1",
    )

    # 11. Derivation enforced: declared 0.0 contradicts enabled streams.
    try:
        AgentBehaviorProfile(**_build(
            lambda kw: kw["d4_observability"].update(position=0.0),
            derive=False))
        violations.append("D4 derivation mismatch validated but should "
                          "have been refused")
    except ValidationError as e:
        assert "1.0" in str(e), str(e)  # the error names the derived value
        refusals.append("derivation mismatch refused (D4 declared 0.0, "
                        "derived 1.0)")

    # 12. D2 binary enum (DR-CMD-077): both values validate; an unknown
    # rule is refused at the schema boundary. C6 retired with the scalar —
    # incoherent posture declarations are unrepresentable by construction.
    expect_refused(
        "D2 refused an unknown conflict_rule",
        _build(lambda kw: kw["d2_fidelity"].update(
            conflict_rule="coin_flip"), derive=False),
        match="literal",
    )
    world_leaning = AgentBehaviorProfile(**_build(lambda kw: kw["d2_fidelity"].update(
        conflict_rule="world_wins_ties")))
    refusals.append("D2 world_wins_ties validates")

    # 13. C7: fail_open with derived verification position > 0.5 refused;
    # fail_open at 0.5 validates silently.
    expect_refused(
        "C7 refused fail_open with all four targets verified",
        _build(lambda kw: kw["d7_verification"].update(on_failure="fail_open")),
        match="fail_open",
    )
    quiet = AgentBehaviorProfile(**_build(lambda kw: (
        kw["d7_verification"].update(intent_target=True, world_target=True,
                                     event_target=False, trigger_target=False,
                                     on_failure="fail_open"),
    )))
    assert quiet.warnings() == [], quiet.warnings()

    # 14. C4 extended: gate present but authorization missing -> refused.
    expect_refused(
        "C4 refused a world trigger source with no authorization entry",
        _build(lambda kw: kw["d6_initiative"].update(
            sources={"operator", "world"},
            gating={"operator": "authenticated-session",
                    "world": "allowlist + signature"})),
        match="missing authorization",
    )

    # 15. D2 enum carried through position_vector() and the canonical form.
    enum_carrier = AgentBehaviorProfile(**_build(lambda kw: (
        kw["d2_fidelity"].update(conflict_rule="world_wins_ties"),
    )))
    assert enum_carrier.d2_fidelity.conflict_rule == "world_wins_ties"
    assert enum_carrier.position_vector()["D2"] == "world_wins_ties"
    assert "world_wins_ties" in enum_carrier.canonical().decode()

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
