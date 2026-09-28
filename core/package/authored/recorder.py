"""recorder — may-act recorder for the artifact registry (DR-CMD-107;
renamed from registrar_clerk, DR-CMD-096).

The minimal pair across the acting axis with the set-002 staff
registrar (DR-CMD-083): same office reading (D7 0.75 — validates
presented documents, never investigates the world), flipped acting
posture (D1 0.5 / D5 0.15 — records directly on standing operator
disposition instead of staging proposals).

Role: on the operator's schedule (standing disposition; arrivals never
trigger it — CL4), sweep the staged area for verified build notices and
adopted customization proposals; validate each against office criteria
(well-formed, attested, chain verifies — no world investigation);
record the survivors into the content-addressed append-only artifact
registry (the customization bridge's registry, DR-CMD-091); refuse the
rest with reasons. Registry integrity is fail_closed: an unverified
agent or a broken chain is never recorded.

Archetype: clerk (may-act x office). D6 {OPERATOR} only: no WORLD,
AGENT, or SELF triggers — acting without external corroboration is
operator-initiated or it does not happen.

D2 principal_wins_ties: the registry is the principal's instrument —
the commission binds action parameters; presented bytes never win ties.

NOTE (DR-CMD-107): the DR-CMD-096 as-built deviation is closed.
write_scope=["artifact-registry"] names the true effect channel and it
now resolves: the factory compiler's contracted-tool registry (J1,
DR-CMD-055/057) carries the channel alias "artifact-registry" ->
tool-register-artifact (DR-CMD-102 tranche 1, DR-CMD-103). The
profile's write channel is a registered contracted tool; compile no
longer refuses at the routing stage.
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

ARCHETYPES = ("clerk",)


def recorder_profile() -> AgentBehaviorProfile:
    """mediation-assist / recorder: may-act artifact registrar.

    Records verified, attested artifacts into the content-addressed
    append-only artifact registry on standing operator disposition;
    refuses unverified or unattested notices with reasons. Reads staged
    material only (office); never disposes (proposer != disposer — the
    standing disposition pre-authorizes the recording class, not
    per-event outcomes).
    """
    return AgentBehaviorProfile(
        agent="recorder",
        d1_authority=D1Authority(
            position=0.5, per_event_disposition=False,
            standing_dispositions=["register-artifact-standing"],
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
            position=0.15,
            read_scope=["staging-area", "accretion-repo",
                        "disposition-records", "artifact-registry"],
            # "artifact-registry" resolves via the compiler's channel
            # alias to tool-register-artifact (DR-CMD-103). Bounded
            # (single declared channel), never wildcard — CL3's
            # boundedness and J1's closed registry both hold.
            write_scope=["artifact-registry"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR:
                           "may-act: register presented artifacts on "
                           "standing disposition; pre-authorized-standing"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


def registry_record_decision(notice: dict) -> tuple[str, dict]:
    """Pure decision rule for artifact-registry recording (office criteria).

    notice: {"agent": str, "artifact_hash": str, "kind": str, "name": str,
             "artifact_bytes": bytes, "verified": bool, "chain_ok": bool}
    Returns ("record", record) or ("refuse", {"reasons": [...]}).
    Total: every notice maps to record|refuse, never silent. No world
    investigation: attestation is checked against presented bytes only.
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
    if not notice.get("artifact_bytes"):
        reasons.append("notice carries no artifact bytes to register")
    if reasons:
        return "refuse", {"reasons": reasons}
    return "record", {"kind": "artifact-registration", "agent": agent,
                      "artifact_kind": notice.get("kind"),
                      "artifact_name": notice.get("name"),
                      "artifact_hash": notice.get("artifact_hash")}


def diagnostic_cases():
    """The recorder's self-diagnostic playbook (J2)."""

    def rc_d1_may_act_shape(ctx):
        p = ctx["profile"]
        a = p.d1_authority
        ok = (not a.per_event_disposition and a.position == 0.5
              and bool(a.standing_dispositions)
              and not a.self_correction and not a.self_planning)
        return ok, (f"per_event={a.per_event_disposition} "
                    f"position={a.position} "
                    f"standing={a.standing_dispositions}")

    def rc_d2_operator_only(ctx):
        p = ctx["profile"]
        d6 = p.d6_initiative
        want = {TriggerSource.OPERATOR}
        missing = [s for s in d6.sources
                   if s not in d6.gating or s not in d6.authorization]
        ok = set(d6.sources) == want and not missing
        return ok, (f"sources={sorted(s.name for s in d6.sources)} "
                    f"missing={missing}")

    def rc_d3_office_reading(ctx):
        p = ctx["profile"]
        v = p.d7_verification
        ok = (v.position == 0.75 and not v.world_target
              and v.intent_target and v.event_target and v.trigger_target
              and v.on_failure == "fail_closed")
        return ok, (f"D7={v.position} world_target={v.world_target} "
                    f"on_failure={v.on_failure}")

    def rc_d4_bounded_write_scope(ctx):
        p = ctx["profile"]
        s = p.d5_scope
        ok = (s.write_scope == ["artifact-registry"]
              and s.position == 0.15
              and not any(w in {"unbounded", "open-ended", "*"}
                          for w in s.write_scope))
        return ok, f"write_scope={s.write_scope} position={s.position}"

    def rc_d5_principal_wins(ctx):
        p = ctx["profile"]
        ok = p.d2_fidelity.conflict_rule == "principal_wins_ties"
        return ok, f"conflict_rule={p.d2_fidelity.conflict_rule}"

    def rc_d6_refuse_unverified(ctx):
        mod = ctx["module"]
        outcome, detail = mod.registry_record_decision(
            {"agent": "ghost", "artifact_hash": "abc",
             "artifact_bytes": b"x", "verified": False, "chain_ok": True})
        ok = outcome == "refuse" and detail.get("reasons")
        return ok, f"outcome={outcome} reasons={detail.get('reasons')}"

    def rc_d7_record_verified(ctx):
        mod = ctx["module"]
        outcome, detail = mod.registry_record_decision(
            {"agent": "wright", "kind": "profile", "name": "wright",
             "artifact_hash": "def", "artifact_bytes": b"y",
             "verified": True, "chain_ok": True})
        ok = (outcome == "record"
              and detail.get("kind") == "artifact-registration"
              and detail.get("agent") == "wright")
        return ok, f"outcome={outcome} kind={detail.get('kind')}"

    def rc_d8_artifact_fidelity(ctx):
        p, a = ctx["profile"], ctx["artifact"]
        expect = hashlib.sha256(p.canonical()).hexdigest()
        ok = a.manifest.profile_hash == expect
        return ok, f"profile_hash_match={ok}"

    return [("RC-D1", rc_d1_may_act_shape),
            ("RC-D2", rc_d2_operator_only),
            ("RC-D3", rc_d3_office_reading),
            ("RC-D4", rc_d4_bounded_write_scope),
            ("RC-D5", rc_d5_principal_wins),
            ("RC-D6", rc_d6_refuse_unverified),
            ("RC-D7", rc_d7_record_verified),
            ("RC-D8", rc_d8_artifact_fidelity)]
