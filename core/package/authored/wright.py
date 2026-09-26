"""wright — agent-profile author (bootstrap, DR-CMD-083 J3).

Harness-side author-agent: ambient inference governed by this profile.
Authors agent profiles into staged proposals; stages build-requests for
the factory driver; never deploys (stage-only, staff S4). Bootstrap:
authored by the ambient directly (no prior profile existed); built and
verified by the factory like every profile; Peter's instruction is its
standing commission.

Archetypes: staff + office (author precedent, DR-CMD-069).
D2 principal_wins_ties: artifacts track the commission.
D7 0.75 fail_closed: a failed verification halts the loop — no artifact
leaves on a failed check (author precedent).
D5 0.0: build-requests are staged (J1-ii); the wright wields no tools.
"""

from __future__ import annotations

from core.package.agent_behavior import (
    AgentBehaviorProfile,
    D1Authority,
    D2Fidelity,
    D3Reproducibility,
    D4Observability,
    D5Scope,
    D6Initiative,
    D7Verification,
    TriggerSource,
)

ARCHETYPES = ("staff", "office")


def wright_profile() -> AgentBehaviorProfile:
    """mechanical-assist / wright: author agent profiles.

    Drafts profile modules (builder, archetypes, diagnostic_cases,
    rationale) into staged proposals under an operator commission; stages
    build-requests for the factory driver; records the authoring
    manifest. Never commits, never deploys, never disposes —
    proposer != disposer.
    """
    return AgentBehaviorProfile(
        agent="wright",
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
            write_scope=[]),  # J1-ii: build-requests are staged, not tooled
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR:
                    "authenticated-session; operator-attributed commission"},
            authorization={TriggerSource.OPERATOR: "stage-only"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


def diagnostic_cases():
    """The wright's self-diagnostic playbook (J2)."""
    def ctx_profile(ctx):
        return ctx["profile"]

    def w_d1_stage_only(ctx):
        p = ctx_profile(ctx)
        ok = p.d5_scope.write_scope == []
        return ok, f"write_scope={p.d5_scope.write_scope}"

    def w_d2_c4_shape(ctx):
        p = ctx_profile(ctx)
        d6 = p.d6_initiative
        missing = [s for s in d6.sources
                   if s not in d6.gating or s not in d6.authorization]
        non_stage = [s for s, a in d6.authorization.items()
                     if "stage-only" not in a]
        ok = not missing and not non_stage
        return ok, f"missing_gate_or_auth={missing} non_stage_only={non_stage}"

    def w_d3_diagnostics_exemplified(ctx):
        cases = diagnostic_cases()
        ok = len(cases) >= 3
        return ok, f"n_cases={len(cases)} (G6: profile must carry its own)"

    return [("W-D1", w_d1_stage_only),
            ("W-D2", w_d2_c4_shape),
            ("W-D3", w_d3_diagnostics_exemplified)]
