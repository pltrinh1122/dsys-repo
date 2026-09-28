"""triager — may-act triage of staged items (DR-CMD-097).

The monitor's clerk-shaped downstream (DR-CMD-094 addendum; populate-clerk
/pb-decide O2, adopted by Peter ~18:17 PDT 2026-09-27). The composition:
field monitor detects and stages (staff+field — corroborated change ->
staged alert proposal) -> triager reads the staged items and acts on
standing operator disposition. Detection is field work; triage is office
work. A clerk "monitor" watching the world fails CL4/CL5/CL6; the
coherent clerk-shaped watcher is this profile.

Role: on the operator's schedule (standing disposition; arrivals never
trigger it — CL4), sweep the staged area; assess each staged item
against the commissioned triage criteria (office criteria only —
well-formed, attested, chain verifies, kind/severity against the
commission's bands; never investigate the world); quarantine the
unverified, escalate the urgent, archive the routine, and defer the
ambiguous (defer = stage for operator disposition — the staff-like
residue: the standing disposition pre-authorizes the clear action
classes, not per-event outcomes; proposer != disposer holds for the
ambiguous middle).

Archetype: clerk (may-act x office). D6 {OPERATOR} only: no WORLD,
AGENT, or SELF triggers — acting without external corroboration is
operator-initiated or it does not happen. Triage runs on schedule; the
schedule is the operator's standing trigger.

D2 principal_wins_ties: the triage criteria are the principal's
commission — they bind the action parameters; presented bytes (e.g. a
self-asserted severity) never win ties.

All three effect channels are reversible by design: quarantine is
holding, escalation is routing to a queue, archive is filing. Nothing
here destroys.

AS-BUILT DEVIATION (DR-CMD-097): write_scope=["quarantine",
"escalation-queue", "archive"] names the true effect channels, but the
factory compiler's closed contracted-tool registry (J1, DR-CMD-055/057)
resolves write channels only against AGENT_TOOL_IDS / CHANNEL_ALIASES —
no contracted tool backs quarantine, escalation, or archival today.
Compile therefore refuses at the routing stage until contracted tools
exist for these channels or the channel question is disposed (Peter).
The profile is authored, validates, and passes the clerk gate; factory
registration (PROFILE_SET_002) is deferred pending the Operator's
disposition on the channel. No channel was silently substituted, no
tool was added to the pinned registry, and the closed-registry
discipline was not amended.
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


def triager_profile() -> AgentBehaviorProfile:
    """mediation-assist / triager: may-act staged-item triage.

    Assesses staged items against commissioned triage criteria on the
    operator's schedule; quarantines the unverified, escalates the
    urgent, archives the routine, defers the ambiguous for operator
    disposition. Reads staged material only (office); the standing
    disposition pre-authorizes the action classes, not per-event
    outcomes.
    """
    return AgentBehaviorProfile(
        agent="triager",
        d1_authority=D1Authority(
            position=0.5, per_event_disposition=False,
            standing_dispositions=["triage-staged-standing"],
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
                        "disposition-records", "triage-criteria"],
            # AS-BUILT DEVIATION: these are the true effect channels but
            # resolve against no contracted tool (see module docstring).
            # Bounded (three declared channels), never wildcard — CL3's
            # boundedness holds; J1 resolution does not.
            write_scope=["quarantine", "escalation-queue", "archive"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR:
                           "may-act: quarantine/escalate/archive staged "
                           "items on standing disposition; "
                           "pre-authorized-standing"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


DEFAULT_CRITERIA = {
    "escalate_kinds": ["security-alert", "pipeline-failure",
                       "operator-page"],
    "escalate_severity_at_least": 8,
    "archive_kinds": ["routine-notice", "heartbeat", "digest"],
    "quarantine_on_unverified": True,
}


def triage_decision(item: dict, criteria: dict | None = None) -> tuple[str, dict]:
    """Pure triage rule (office criteria; no world investigation).

    item: {"id": str, "kind": str, "severity": int (presented, never
          trusted over the commission), "source_agent": str,
          "verified": bool, "chain_ok": bool}
    criteria: the commission (DEFAULT_CRITERIA shape). Binds the action
          parameters; presented bytes never win ties (D2).
    Returns (action, detail) with action in {"quarantine", "escalate",
    "archive", "defer"}. Total: every item maps to exactly one action,
    never silent. The ambiguous middle defers to operator disposition.
    """
    criteria = criteria or DEFAULT_CRITERIA
    reasons: list[str] = []
    item_id = item.get("id") or ""
    kind = item.get("kind") or ""
    try:
        severity = int(item.get("severity") or 0)
    except (TypeError, ValueError):
        severity = 0
        reasons.append("severity not an integer; treated as 0")
    if criteria.get("quarantine_on_unverified", True):
        if not item.get("verified"):
            reasons.append(
                f"item {item_id!r} not verified; unverified items never "
                "escalate or archive")
        if not item.get("chain_ok"):
            reasons.append("staging chain does not verify")
    if reasons:
        return "quarantine", {"reasons": reasons, "item_id": item_id}
    if (kind in criteria.get("escalate_kinds", ())
            or severity >= criteria.get("escalate_severity_at_least", 10)):
        return "escalate", {"item_id": item_id, "kind": kind,
                            "severity": severity}
    if kind in criteria.get("archive_kinds", ()):
        return "archive", {"item_id": item_id, "kind": kind}
    return "defer", {"item_id": item_id, "kind": kind,
                     "reasons": ["matches no commissioned action class; "
                                 "staged for operator disposition"]}


def diagnostic_cases():
    """The triager's self-diagnostic playbook (J2)."""

    def t_d1_may_act_shape(ctx):
        p = ctx["profile"]
        a = p.d1_authority
        ok = (not a.per_event_disposition and a.position == 0.5
              and bool(a.standing_dispositions)
              and not a.self_correction and not a.self_planning)
        return ok, (f"per_event={a.per_event_disposition} "
                    f"position={a.position} "
                    f"standing={a.standing_dispositions}")

    def t_d2_operator_only(ctx):
        p = ctx["profile"]
        d6 = p.d6_initiative
        want = {TriggerSource.OPERATOR}
        missing = [s for s in d6.sources
                   if s not in d6.gating or s not in d6.authorization]
        ok = set(d6.sources) == want and not missing
        return ok, (f"sources={sorted(s.name for s in d6.sources)} "
                    f"missing={missing}")

    def t_d3_office_reading(ctx):
        p = ctx["profile"]
        v = p.d7_verification
        ok = (v.position == 0.75 and not v.world_target
              and v.intent_target and v.event_target and v.trigger_target
              and v.on_failure == "fail_closed")
        return ok, (f"D7={v.position} world_target={v.world_target} "
                    f"on_failure={v.on_failure}")

    def t_d4_bounded_write_scope(ctx):
        p = ctx["profile"]
        s = p.d5_scope
        ok = (s.write_scope == ["quarantine", "escalation-queue", "archive"]
              and s.position == 0.15
              and not any(w in {"unbounded", "open-ended", "*"}
                          for w in s.write_scope))
        return ok, f"write_scope={s.write_scope} position={s.position}"

    def t_d5_principal_wins(ctx):
        p = ctx["profile"]
        ok = p.d2_fidelity.conflict_rule == "principal_wins_ties"
        return ok, f"conflict_rule={p.d2_fidelity.conflict_rule}"

    def t_d6_quarantine_unverified(ctx):
        mod = ctx["module"]
        outcome, detail = mod.triage_decision(
            {"id": "i-1", "kind": "security-alert", "severity": 9,
             "source_agent": "monitor", "verified": False, "chain_ok": True})
        ok = outcome == "quarantine" and detail.get("reasons")
        return ok, f"outcome={outcome} reasons={detail.get('reasons')}"

    def t_d7_route_clear_cases(ctx):
        mod = ctx["module"]
        base = {"source_agent": "monitor", "verified": True, "chain_ok": True}
        o1, _ = mod.triage_decision({**base, "id": "i-2",
                                     "kind": "security-alert", "severity": 9})
        o2, _ = mod.triage_decision({**base, "id": "i-3",
                                     "kind": "heartbeat", "severity": 1})
        o3, d3 = mod.triage_decision({**base, "id": "i-4",
                                      "kind": "odd-notice", "severity": 3})
        ok = (o1 == "escalate" and o2 == "archive" and o3 == "defer"
              and d3.get("reasons"))
        return ok, f"escalate={o1} archive={o2} defer={o3}"

    def t_d8_artifact_fidelity(ctx):
        p, a = ctx["profile"], ctx["artifact"]
        expect = hashlib.sha256(p.canonical()).hexdigest()
        ok = a.manifest.profile_hash == expect
        return ok, f"profile_hash_match={ok}"

    return [("T-D1", t_d1_may_act_shape),
            ("T-D2", t_d2_operator_only),
            ("T-D3", t_d3_office_reading),
            ("T-D4", t_d4_bounded_write_scope),
            ("T-D5", t_d5_principal_wins),
            ("T-D6", t_d6_quarantine_unverified),
            ("T-D7", t_d7_route_clear_cases),
            ("T-D8", t_d8_artifact_fidelity)]
