"""registrar — registry of verified built agents (DR-CMD-083 J4 demo).

Authored END-TO-END through the author-agent loop: commission-001 ->
governed authoring session -> staged bytes -> factory driver ->
self-diagnostic. These bytes are what the driver built; nothing was
hand-placed past the driver.

Role: watch for new factory verdict records; when a build verifies,
stage a registry-update proposal (agent, artifact hash, verdict ref).
The registry is what DR-CMD-078's authenticated-agent gating attests
against ("author is a verified built agent"). Registry integrity is
fail_closed: an unverified agent or a broken chain is never staged —
refused with reasons instead (monitor J-E precedent).

Archetypes: staff + office. D6 {OPERATOR, SELF}: commissioned registry
policy + scheduler-cadence sweeps of the verdict staging area. AGENT is
deliberately NOT bound (J-H discipline): no built agent currently stages
verified-build notices, so there is nothing truthful for it to name;
SELF sweeps discover verdicts. Cf. spec §8 as-built deviation, DR-CMD-083.

D2 principal_wins_ties: the registry is the principal's instrument — on
a tie between a substrate claim and the principal's record, the record
wins (author/advisor precedent, J-B).
"""

from __future__ import annotations

import hashlib

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


def registrar_profile() -> AgentBehaviorProfile:
    """mediation-assist / registrar: verified-build registry.

    Stages registry-update proposals for verified builds; refuses
    unverified or unattested notices with reasons. Never writes the
    registry directly (J-A: updates are staged proposals); never
    disposes (proposer != disposer).
    """
    return AgentBehaviorProfile(
        agent="registrar",
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
                        "disposition-records"],
            write_scope=[]),  # J-A: registry updates are staged proposals
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.SELF},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.SELF:
                        "scheduler-cadence; verdict-area sweeps"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.SELF: "stage-only; no self-commit"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


def registry_update_decision(notice: dict) -> tuple[str, dict]:
    """Pure decision rule for registry updates (the registrar's behavior).

    notice: {"agent": str, "artifact_hash": str,
             "verified": bool, "chain_ok": bool}
    Returns ("stage", proposal) or ("refuse", {"reasons": [...]}).
    Total: every notice maps to stage|refuse, never silent.
    """
    reasons: list[str] = []
    agent = notice.get("agent") or ""
    if not agent:
        reasons.append("notice names no agent")
    if not notice.get("verified"):
        reasons.append(
            f"agent {agent!r} is not verified; "
            "the registry admits verified builds only")
    if not notice.get("chain_ok"):
        reasons.append("staging chain does not verify; attestation failed")
    if not notice.get("artifact_hash"):
        reasons.append("notice carries no artifact hash")
    if reasons:
        return "refuse", {"reasons": reasons}
    return "stage", {"kind": "registry-update", "agent": agent,
                     "artifact_hash": notice["artifact_hash"]}


def diagnostic_cases():
    """The registrar's self-diagnostic playbook (J2) — the success criterion."""

    def r_d1_stage_only(ctx):
        p = ctx["profile"]
        ok = p.d5_scope.write_scope == []
        return ok, f"write_scope={p.d5_scope.write_scope}"

    def r_d2_sources_honest(ctx):
        p = ctx["profile"]
        d6 = p.d6_initiative
        want = {TriggerSource.OPERATOR, TriggerSource.SELF}
        missing = [s for s in d6.sources
                   if s not in d6.gating or s not in d6.authorization]
        non_stage = [s for s, a in d6.authorization.items()
                     if "stage-only" not in a]
        ok = set(d6.sources) == want and not missing and not non_stage
        return ok, (f"sources={sorted(s.name for s in d6.sources)} "
                    f"missing={missing} non_stage_only={non_stage}")

    def r_d3_fail_closed(ctx):
        p = ctx["profile"]
        ok = p.d7_verification.on_failure == "fail_closed"
        return ok, f"on_failure={p.d7_verification.on_failure}"

    def r_d4_refuse_unverified(ctx):
        mod = ctx["module"]
        outcome, detail = mod.registry_update_decision(
            {"agent": "ghost", "artifact_hash": "abc",
             "verified": False, "chain_ok": True})
        ok = outcome == "refuse" and detail.get("reasons")
        return ok, f"outcome={outcome} reasons={detail.get('reasons')}"

    def r_d5_stage_verified(ctx):
        mod = ctx["module"]
        outcome, detail = mod.registry_update_decision(
            {"agent": "wright", "artifact_hash": "def",
             "verified": True, "chain_ok": True})
        ok = (outcome == "stage"
              and detail.get("kind") == "registry-update"
              and detail.get("agent") == "wright")
        return ok, f"outcome={outcome} kind={detail.get('kind')}"

    def r_d6_artifact_fidelity(ctx):
        p, a = ctx["profile"], ctx["artifact"]
        expect = hashlib.sha256(p.canonical()).hexdigest()
        ok = a.manifest.profile_hash == expect
        return ok, f"profile_hash_match={ok}"

    return [("R-D1", r_d1_stage_only),
            ("R-D2", r_d2_sources_honest),
            ("R-D3", r_d3_fail_closed),
            ("R-D4", r_d4_refuse_unverified),
            ("R-D5", r_d5_stage_verified),
            ("R-D6", r_d6_artifact_fidelity)]
