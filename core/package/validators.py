"""Dyad System Architecture — invariants: referential integrity, lifecycle
constraints, and cross-plane authority rules. All checks are mechanical."""
from __future__ import annotations

from .schema import (
    AuthorityPolicy,
    AuthorityScope,
    BondState,
    ClaimState,
    DisclosureStatus,
    Disposition,
    DispositionMode,
    DispositionResponse,
    DispositionStatus,
    FalsificationOutcome,
    GateCheckVerdict,
    KnowledgeStage,
    MaterializationVerdict,
    MODE_SILENCE,
    NULL_OPTION,
    OnConflict,
    RatificationVerdict,
    RunState,
    SilenceMeaning,
    SystemState,
    TxnState,
    VetoStatus,
)
from .views import verification_view

# (collection, field, target_collection, is_list)
_FK = [
    ("dyads", "human_id", "humans", False),
    ("dyads", "agent_id", "agents", False),
    ("bonds", "dyad_id", "dyads", False),
    ("intents", "dyad_id", "dyads", False),
    ("claims", "dyad_id", "dyads", False),
    ("claims", "intent_id", "intents", False),
    ("falsifiers", "claim_id", "claims", False),
    ("falsification_records", "claim_id", "claims", False),
    ("falsification_records", "falsifier_id", "falsifiers", False),
    ("evidence", "record_id", "falsification_records", False),
    ("knowledge_units", "claim_id", "claims", False),
    ("knowledge_units", "ledger_id", "ledgers", False),
    ("knowledge_units", "evidence_ids", "evidence", True),
    ("materializations", "claim_id", "claims", False),
    ("playbooks", "dyad_id", "dyads", False),
    ("hats", "dyad_id", "dyads", False),
    ("dispositions", "dyad_id", "dyads", False),
    ("dispositions", "session_id", "sessions", False),
    ("dispositions", "hat_id", "hats", False),
    ("dispositions", "proposer_id", "agents", False),
    ("dispositions", "disposer_id", "humans", False),
    ("sessions", "dyad_id", "dyads", False),
    ("sessions", "owner_id", "humans", False),
    ("transactions", "session_id", "sessions", False),
    ("ledgers", "dyad_id", "dyads", False),
    ("ledger_entries", "ledger_id", "ledgers", False),
    ("ledger_entries", "session_id", "sessions", False),
    ("ledger_entries", "txn_id", "transactions", False),
    ("subagents", "dyad_id", "dyads", False),
    ("briefings", "dyad_id", "dyads", False),
    ("briefings", "session_id", "sessions", False),
    ("briefings", "artifact_ref", "artifacts", False),
    ("proposals", "dyad_id", "dyads", False),
    ("ratifications", "proposal_id", "proposals", False),
    ("harness_runs", "principal_id", "principals", False),
    ("harness_runs", "dyad_id", "dyads", False),
    ("harness_runs", "session_id", "sessions", False),
    ("conditions", "run_id", "harness_runs", False),
    ("threads", "run_id", "harness_runs", False),
    ("interaction_prefs", "run_id", "harness_runs", False),
    ("artifacts", "run_id", "harness_runs", False),
    ("strap_gates", "run_id", "harness_runs", False),
    ("strap_gates", "required_condition_ids", "conditions", True),
    ("local_vetoes", "principal_id", "principals", False),
    ("local_vetoes", "directive_id", "directives", False),
    ("directives", "source_run_id", "harness_runs", False),
    ("directives", "target_run_id", "harness_runs", False),
    ("directives", "supersedes_directive_id", "directives", False),
    ("directives", "disposition_id", "dispositions", False),
    ("gate_checks", "directive_id", "directives", False),
    ("gate_checks", "target_run_id", "harness_runs", False),
    ("applications", "directive_id", "directives", False),
    ("applications", "gate_check_id", "gate_checks", False),
    ("promotions", "artifact_id", "artifacts", False),
    ("promotions", "directive_id", "directives", False),
    ("promotions", "disposition_id", "dispositions", False),
    ("releases", "artifact_ids", "artifacts", True),
    ("runbooks", "release_version", "releases", False),
    ("steps", "runbook_id", "runbooks", False),
    ("steps", "tool_id", "tools", False),
    ("automaton_runs", "runbook_id", "runbooks", False),
    ("automaton_events", "run_id", "automaton_runs", False),
    ("automaton_flows", "release_version", "releases", False),
    ("flow_states", "flow_id", "automaton_flows", False),
    ("flow_states", "runbook_id", "runbooks", False),
    ("flow_transitions", "flow_id", "automaton_flows", False),
    ("flow_transitions", "from_state_id", "flow_states", False),
    ("flow_transitions", "to_state_id", "flow_states", False),
    ("flow_runs", "flow_id", "automaton_flows", False),
    ("flow_runs", "current_state_id", "flow_states", False),
    ("flow_transition_events", "flow_run_id", "flow_runs", False),
    ("automaton_runs", "parent_flow_run_id", "flow_runs", False),
    ("automaton_runs", "flow_state_id", "flow_states", False),
    ("dispositions", "disclosure_ref", "disclosures", False),
    ("dispositions", "supersedes_disposition_id", "dispositions", False),
    ("decision_records", "disposition_id", "dispositions", False),
    ("dispositions", "absorbed_into_directive_id", "directives", False),
]


def _referential_integrity(s: SystemState) -> list[str]:
    v: list[str] = []
    for coll, field, target, is_list in _FK:
        src = getattr(s, coll)
        tgt = getattr(s, target)
        for eid, ent in src.items():
            # releases are keyed by id but referenced by version
            val = getattr(ent, field)
            if val is None:
                continue
            vals = val if is_list else [val]
            for x in vals:
                if target == "releases":
                    ok = any(r.version == x for r in tgt.values())
                else:
                    ok = x in tgt
                if not ok:
                    v.append(f"RI: {coll}.{eid}.{field} -> {target} '{x}' missing")
    return v


def _claim_materialization(s: SystemState) -> list[str]:
    """IFF1/IFF2: materialize only via a surviving, externally-separated record."""
    v: list[str] = []
    for m in s.materializations.values():
        if m.verdict != MaterializationVerdict.MATERIALIZED:
            continue
        claim = s.claims.get(m.claim_id)
        if claim is None or claim.state != ClaimState.SURVIVED:
            v.append(f"I-1: materialization {m.id}: claim not in survived state")
        recs = [r for r in s.falsification_records.values()
                if r.claim_id == m.claim_id
                and r.outcome == FalsificationOutcome.SURVIVED
                and r.external_separator.strip()]
        if not recs:
            v.append(f"I-1: materialization {m.id}: no surviving record with external separator (IFF1/IFF2)")
        if not all(m.gate_results.values()):
            v.append(f"I-1: materialization {m.id}: covenant gate failed")
    return v


def _no_self_ratify(s: SystemState) -> list[str]:
    """proposer != disposer; the disposer is the dyad's human (terminal)."""
    v: list[str] = []
    for d in s.dispositions.values():
        if d.proposer_id == d.disposer_id:
            v.append(f"I-2: disposition {d.id}: proposer == disposer (no-self-ratify)")
        dyad = s.dyads.get(d.dyad_id)
        if dyad is not None and d.disposer_id != dyad.human_id:
            v.append(f"I-2: disposition {d.id}: disposer is not the dyad human (terminal authority)")
        if d.cta is not None and d.cta != "Y/N":
            v.append(f"I-2: disposition {d.id}: more than one CTA per turn (DFD)")
    return v


def _disposition_modes(s: SystemState) -> list[str]:
    """Mode-specific definitions of done [§8.2]: authorize names its action;
    set_standing names its domain; overrule cites an existing veto (which
    stays logged); triage cites its disclosure. A mode-DoD failure is a
    refused disposition."""
    v: list[str] = []
    for d in s.dispositions.values():
        if d.mode == DispositionMode.AUTHORIZE and not (d.action_ref or "").strip():
            v.append(f"I-2: disposition {d.id}: authorize mode without named action_ref "
                     f"(explicit authorization names its action)")
        if d.mode == DispositionMode.SET_STANDING and not (d.standing_domain or "").strip():
            v.append(f"I-2: disposition {d.id}: set_standing mode without standing_domain")
        if d.mode == DispositionMode.OVERRULE:
            if not (d.veto_id or "").strip():
                v.append(f"I-2: disposition {d.id}: overrule mode without veto_id")
            elif d.veto_id not in s.local_vetoes:
                v.append(f"I-2: disposition {d.id}: overrule cites unknown veto {d.veto_id}")
        if d.mode == DispositionMode.TRIAGE and not (d.disclosure_ref or "").strip():
            v.append(f"I-2: disposition {d.id}: triage mode without disclosure_ref")
        if (d.mode == DispositionMode.AUTHORIZE
                and d.status in (DispositionStatus.APPROVED, DispositionStatus.ACTED)
                and not (d.state_ref or "").strip()):
            v.append(f"I-2: disposition {d.id}: authorize without state binding (E2)")
        if d.response == DispositionResponse.COUNTER and not (d.counter_text or "").strip():
            v.append(f"I-2: disposition {d.id}: counter response without counter text (E3)")
        if (d.response == DispositionResponse.COUNTER
                and d.status in (DispositionStatus.APPROVED, DispositionStatus.ACTED)):
            v.append(f"I-2: disposition {d.id}: counter-proposed disposition cannot be approved (E3)")
        if d.response == DispositionResponse.YES and d.status == DispositionStatus.PROPOSED:
            v.append(f"I-2: disposition {d.id}: affirmed disposition left proposed (E3)")
        if d.absorbed_into_directive_id and d.mode != DispositionMode.OVERRULE:
            v.append(f"I-2: disposition {d.id}: absorption is an overrule pattern (E7)")
        if (d.absorbed_into_directive_id and d.mode == DispositionMode.OVERRULE
                and d.status not in (DispositionStatus.APPROVED, DispositionStatus.ACTED)):
            v.append(f"I-2: disposition {d.id}: absorption without approved overrule disposition (E7)")
    return v


def _disclosure_triage(s: SystemState) -> list[str]:
    """Silence is not triage: every non-open disclosure is cited by exactly
    one triage disposition, and no disclosure is cited by more than one."""
    v: list[str] = []
    for d in s.disclosures.values():
        citers = [x.id for x in s.dispositions.values()
                  if x.mode == DispositionMode.TRIAGE and x.disclosure_ref == d.id]
        if len(citers) > 1:
            v.append(f"I-2: disclosure {d.id}: cited by more than one triage "
                     f"disposition ({', '.join(citers)}) — exactly one outcome")
        elif d.status != DisclosureStatus.OPEN and len(citers) != 1:
            v.append(f"I-2: disclosure {d.id}: status {d.status.value} without its "
                     f"triage disposition")
    return v


def _standing_supersession(s: SystemState) -> list[str]:
    """Standing policy forms one supersession chain per domain: exactly one
    root, every other member citing a same-domain member, no cycles."""
    v: list[str] = []
    groups: dict[str, list] = {}
    for d in s.dispositions.values():
        if (d.mode == DispositionMode.SET_STANDING
                and d.status == DispositionStatus.APPROVED
                and (d.standing_domain or "").strip()):
            groups.setdefault(d.standing_domain, []).append(d)
    for domain, members in groups.items():
        ids = {m.id for m in members}
        roots = [m for m in members if not m.supersedes_disposition_id]
        for m in members:
            sup = m.supersedes_disposition_id
            if sup and sup not in ids:
                v.append(f"I-2: disposition {m.id}: set_standing supersedes outside "
                         f"its domain '{domain}'")
        if len(members) > 1 and len(roots) != 1:
            v.append(f"I-2: domain '{domain}': {len(roots)} supersession roots "
                     f"— standing policy must form one chain")
        # every non-root must resolve to the root without cycles
        root_id = roots[0].id if len(roots) == 1 else None
        by_id = {m.id: m for m in members}
        for m in members:
            seen = {m.id}
            cur = m.supersedes_disposition_id
            while cur:
                if cur in seen:
                    v.append(f"I-2: disposition {m.id}: supersession cycle at {cur}")
                    break
                seen.add(cur)
                nxt = by_id.get(cur)
                cur = nxt.supersedes_disposition_id if nxt else None
            else:
                if root_id and m.id != root_id and (root_id not in seen):
                    v.append(f"I-2: disposition {m.id}: supersession chain does not "
                             f"resolve to the domain root")
    return v


def _overrule_backing(s: SystemState) -> list[str]:
    """An overruled veto must be backed by an approved/ACTED overrule
    disposition that cites it. The veto stays logged."""
    v: list[str] = []
    for lv in s.local_vetoes.values():
        if lv.status == VetoStatus.OVERRULED:
            backers = [x.id for x in s.dispositions.values()
                       if x.mode == DispositionMode.OVERRULE and x.veto_id == lv.id
                       and x.status in (DispositionStatus.APPROVED, DispositionStatus.ACTED)]
            if not backers:
                v.append(f"I-2: veto {lv.id}: status overruled without a backing "
                         f"overrule disposition")
    return v


_UNDECIDED_VERDICTS = {"draft", "proposed", ""}


def _dialectic_separator(s: SystemState) -> list[str]:
    """E4: dialectic mode requires a designated separator. Self-separation
    is rehearsal by construction."""
    v: list[str] = []
    for r in s.decision_records.values():
        if not r.dialectic:
            continue
        if not (r.separator_id or "").strip():
            v.append(f"I-12: record {r.id}: dialectic without designated "
                     f"separator")
        elif r.separator_id == r.proposer_id and not r.rehearsal:
            v.append(f"I-12: record {r.id}: self-separation must be labeled "
                     f"rehearsal")
    return v


def _null_option_triage(s: SystemState) -> list[str]:
    """E5: a triage-mode record may not select the enumerated null option.
    Silence is not triage; smuggling the status quo past as 'decide
    nothing' is refused."""
    v: list[str] = []
    for r in s.decision_records.values():
        if r.selected != NULL_OPTION or NULL_OPTION not in r.options:
            continue
        d = s.dispositions.get(r.disposition_id or "")
        if d is not None and d.mode == DispositionMode.TRIAGE:
            v.append(f"I-2: record {r.id}: triage mode selected "
                     f"'{NULL_OPTION}' — silence is not an outcome (E5)")
    return v


def _citation_integrity(s: SystemState) -> list[str]:
    """E1: a non-rehearsal record's premises must resolve to real,
    decided, non-quarantined records. No simulated thing cited as
    decided."""
    v: list[str] = []
    for r in s.decision_records.values():
        if r.rehearsal:
            continue
        for pid in r.premises:
            if pid in s.decision_records:
                t = s.decision_records[pid]
                if t.rehearsal:
                    v.append(f"I-11: record {r.id}: premise cites quarantined "
                             f"rehearsal record {pid}")
                elif t.verdict in _UNDECIDED_VERDICTS:
                    v.append(f"I-11: record {r.id}: premise cites undecided "
                             f"record {pid}")
            elif pid in s.dispositions:
                d = s.dispositions[pid]
                if d.status not in (DispositionStatus.APPROVED,
                                    DispositionStatus.ACTED):
                    v.append(f"I-11: record {r.id}: premise cites undecided "
                             f"disposition {pid}")
            else:
                v.append(f"I-11: record {r.id}: premise cites missing record "
                         f"{pid}")
    return v


def _knowledge_lifecycle(s: SystemState) -> list[str]:
    """single-home uniqueness; kb graduation requires a survived claim."""
    v: list[str] = []
    homes: dict[str, str] = {}
    for ku in s.knowledge_units.values():
        if ku.canonical_home in homes:
            v.append(f"I-3: knowledge unit {ku.id}: canonical_home '{ku.canonical_home}' "
                     f"already held by {homes[ku.canonical_home]} (single-home)")
        else:
            homes[ku.canonical_home] = ku.id
        if ku.stage == KnowledgeStage.KB:
            claim = s.claims.get(ku.claim_id)
            if claim is None or claim.state != ClaimState.SURVIVED:
                v.append(f"I-3: knowledge unit {ku.id}: kb stage without survived claim (kb-graduation)")
    return v


def _playbook_triad(s: SystemState) -> list[str]:
    v: list[str] = []
    for p in s.playbooks.values():
        if not (p.play_start.strip() and p.play_stop.strip() and p.play_keep.strip()):
            v.append(f"I-4: playbook {p.id}: must hold exactly three plays (start/stop/keep)")
    return v


def _briefings_and_ratification(s: SystemState) -> list[str]:
    v: list[str] = []
    for b in s.briefings.values():
        if not b.artifact_ref.strip():
            v.append(f"I-5: briefing {b.id}: no checkable artifact (conversation, not work)")
    for r in s.ratifications.values():
        if r.verdict == RatificationVerdict.RETURNED_TO_DRAFT and not (r.failure or "").strip():
            v.append(f"I-5: ratification {r.id}: returned to draft without its failure attached")
    return v


def _session_transaction_ledger(s: SystemState) -> list[str]:
    """Commit/abort always lands a ledger entry; sessions carry owner,
    boundary, falsifiable claim."""
    v: list[str] = []
    for sess in s.sessions.values():
        if not sess.owner_id.strip():
            v.append(f"I-6: session {sess.id}: no owner (one session, one owner)")
        if not sess.falsifiable_claim.strip():
            v.append(f"I-6: session {sess.id}: no falsifiable claim")
    for t in s.transactions.values():
        entries = [e for e in s.ledger_entries.values() if e.txn_id == t.id]
        if t.state == TxnState.COMMITTED and not any(e.kind == "commit" for e in entries):
            v.append(f"I-6: transaction {t.id}: committed without an atomic ledger commit entry")
        if t.state == TxnState.ABORTED and not any(e.kind == "abort" for e in entries):
            v.append(f"I-6: transaction {t.id}: aborted without recording the attempt")
    return v


def _directive_application(s: SystemState) -> list[str]:
    """No bypass: application requires a passed gate check for that directive.
    close_completed requires all required target conditions satisfied."""
    v: list[str] = []
    for a in s.applications.values():
        gc = s.gate_checks.get(a.gate_check_id)
        if gc is None:
            v.append(f"I-7: application {a.id}: gate check missing")
            continue
        if gc.directive_id != a.directive_id:
            v.append(f"I-7: application {a.id}: gate check is for another directive")
        if gc.verdict != GateCheckVerdict.PASSED:
            v.append(f"I-7: application {a.id}: gate check not passed (no bypass)")
    for gc in s.gate_checks.values():
        d = s.directives.get(gc.directive_id)
        if d is None or gc.verdict != GateCheckVerdict.PASSED:
            continue
        if d.action == "close_completed":
            req = [c for c in s.conditions.values()
                   if c.run_id == gc.target_run_id and c.required]
            if any(not c.satisfied for c in req):
                v.append(f"I-7: gate check {gc.id}: close_completed passed with "
                         f"unsatisfied required conditions")
        if not all(gc.per_gate.values()):
            v.append(f"I-7: gate check {gc.id}: passed with a failing per-gate result")
    return v


def _promotion_release(s: SystemState) -> list[str]:
    """Unique versions; preconditions; Operator disposition for the
    irreversible publish; playbook-before-automation."""
    v: list[str] = []
    versions = [r.version for r in s.releases.values()]
    if len(set(versions)) != len(versions):
        v.append("I-8: duplicate AutomatonRelease version")
    for p in s.promotions.values():
        if not any(r.version == p.release_version for r in s.releases.values()):
            v.append(f"I-8: promotion {p.id}: release {p.release_version} missing")
        if not p.preconditions_ok:
            v.append(f"I-8: promotion {p.id}: preconditions not ok")
        d = s.dispositions.get(p.disposition_id)
        if d is None:
            v.append(f"I-8: promotion {p.id}: no Operator disposition (N6)")
        else:
            # the disposer must be the human of the dyad that owns the run
            dyad_human = None
            art = s.artifacts.get(p.artifact_id)
            run = s.harness_runs.get(art.run_id) if art else None
            dyad = s.dyads.get(run.dyad_id) if run and run.dyad_id else None
            if dyad:
                dyad_human = dyad.human_id
            if d.status != DispositionStatus.APPROVED:
                v.append(f"I-8: promotion {p.id}: disposition not approved")
            elif dyad_human and d.disposer_id != dyad_human:
                v.append(f"I-8: promotion {p.id}: disposition disposer is not the dyad human")
            if d.mode != DispositionMode.AUTHORIZE:
                v.append(f"I-8: promotion {p.id}: disposition is not AUTHORIZE mode (N6)")
            art_p = s.artifacts.get(p.artifact_id)
            if art_p is not None and d.state_ref != art_p.content_hash:
                v.append(f"I-8: promotion {p.id}: authorization stale or unbound (N6)")
        art = s.artifacts.get(p.artifact_id)
        if art is not None:
            if not any(pb.domain == art.domain for pb in s.playbooks.values()):
                v.append(f"I-8: promotion {p.id}: domain '{art.domain}' has no dyad "
                         f"playbook (playbook before automation)")
        if p.directive_id is not None:
            applied = any(a.directive_id == p.directive_id for a in s.applications.values())
            if not applied:
                v.append(f"I-8: promotion {p.id}: cited directive was never applied")
    return v


def _run_lifecycle(s: SystemState) -> list[str]:
    """At most one non-closed run per (principal, authority-scope). A
    governance (Chief-of-Staff) run coexists with the execution run it
    manages because their scopes are disjoint by construction."""
    v: list[str] = []
    open_by_scope: dict[tuple[str, AuthorityScope], str] = {}
    for r in s.harness_runs.values():
        if r.state != RunState.CLOSED:
            key = (r.principal_id, r.authority_scope)
            if key in open_by_scope:
                v.append(f"I-9: principal {r.principal_id}: more than one non-closed "
                         f"{r.authority_scope.value} run ({open_by_scope[key]}, {r.id})")
            else:
                open_by_scope[key] = r.id
    for lv in s.local_vetoes.values():
        if lv.status not in (VetoStatus.UPHELD, VetoStatus.OVERRULED):
            v.append(f"I-9: veto {lv.id}: unresolved status (dissent must be logged)")
    for ap in s.authority_policies.values():
        if ap.on_conflict not in (OnConflict.FLEET_WINS, OnConflict.LOCAL_WINS):
            v.append(f"I-9: authority policy {ap.id}: unknown on_conflict")
    return v


def _drain_closure_bar(s: SystemState) -> list[str]:
    """I-13 (DR-5/B3): a governance run may not close with undisposed backlog —
    OPEN disclosures older than the run's opening (seq < open_seq).
    Implemented in terms of verification_view: the bar reads ground truth,
    not any agent's account of the queue. Applies to every governance run
    (the duty attaches to the scope) and every closure reason (abandonment
    does not exempt; the orphan rule catches the aftermath)."""
    v: list[str] = []
    queue = verification_view(s)
    for r in s.harness_runs.values():
        if r.authority_scope != AuthorityScope.GOVERNANCE or r.state != RunState.CLOSED:
            continue
        for row in queue:
            if row.seq < r.open_seq:
                v.append(f"I-13: governance run {r.id} closed with undisposed "
                         f"backlog disclosure {row.id} (seq {row.seq} < "
                         f"open_seq {r.open_seq})")
    return v


def _orphan_queue(s: SystemState) -> list[str]:
    """I-13 (DR-5/B1): open disclosures with no non-closed governance run —
    the queue is orphaned. Procedural rule: disclosure write and drain-run
    opening are same-turn atomic, so the only legitimate transient is
    within a turn."""
    v: list[str] = []
    queue = verification_view(s)
    if not queue:
        return v
    draining = any(r.authority_scope == AuthorityScope.GOVERNANCE
                   and r.state != RunState.CLOSED
                   for r in s.harness_runs.values())
    if not draining:
        v.append(f"I-13: {len(queue)} open disclosure(s) with no non-closed "
                 f"governance run draining ({', '.join(r.id for r in queue)})")
    return v


def _automaton_ordering(s: SystemState) -> list[str]:
    """Unique step seq per run-book; unique event seq per run (append-only);
    unique transition-event seq per flow run."""
    v: list[str] = []
    seen_step: set[tuple[str, int]] = set()
    for st in s.steps.values():
        key = (st.runbook_id, st.seq)
        if key in seen_step:
            v.append(f"I-10: run-book {st.runbook_id}: duplicate step seq {st.seq}")
        seen_step.add(key)
    seen_ev: set[tuple[str, int]] = set()
    for e in s.automaton_events.values():
        key = (e.run_id, e.seq)
        if key in seen_ev:
            v.append(f"I-10: automaton run {e.run_id}: duplicate event seq {e.seq}")
        seen_ev.add(key)
    seen_te: set[tuple[str, int]] = set()
    for e in s.flow_transition_events.values():
        key = (e.flow_run_id, e.seq)
        if key in seen_te:
            v.append(f"I-10: flow run {e.flow_run_id}: duplicate transition-event seq {e.seq}")
        seen_te.add(key)
    return v


_FLOW_TRIGGERS = {"timer", "run_completed", "run_aborted", "external"}
_FLOW_STATE_KINDS = {"task", "wait", "end"}
_FLOW_OUTCOMES = {"completed", "aborted"}


def _flow_totality(s: SystemState) -> list[str]:
    """I-14 (flow spec): every non-end state routes every fate the model
    admits — the mechanical form of 'exceptions are managed'. Task states
    cover run_completed and run_aborted; wait states cover timer/external;
    end states have no outgoing edges. Cross-flow references refused."""
    v: list[str] = []
    for fid, f in s.automaton_flows.items():
        init = s.flow_states.get(f.initial_state_id)
        if init is None or init.flow_id != fid:
            v.append(f"I-14: flow {fid}: initial_state_id "
                     f"'{f.initial_state_id}' is not a state of this flow")
    for tid, t in s.flow_transitions.items():
        if t.trigger not in _FLOW_TRIGGERS:
            v.append(f"I-14: transition {tid}: unknown trigger '{t.trigger}'")
        fr = s.flow_states.get(t.from_state_id)
        to = s.flow_states.get(t.to_state_id)
        if fr is not None and fr.flow_id != t.flow_id:
            v.append(f"I-14: transition {tid}: from_state {t.from_state_id} "
                     f"belongs to another flow")
        if to is not None and to.flow_id != t.flow_id:
            v.append(f"I-14: transition {tid}: to_state {t.to_state_id} "
                     f"belongs to another flow")
    for sid, st in s.flow_states.items():
        if st.kind not in _FLOW_STATE_KINDS:
            v.append(f"I-14: state {sid}: unknown kind '{st.kind}'")
            continue
        triggers = {t.trigger for t in s.flow_transitions.values()
                    if t.from_state_id == sid}
        if st.kind == "task":
            if st.runbook_id is None:
                v.append(f"I-14: task state {sid}: runbook_id required")
            if "run_completed" not in triggers:
                v.append(f"I-14: task state {sid}: no run_completed transition")
            if "run_aborted" not in triggers:
                v.append(f"I-14: task state {sid}: no run_aborted transition "
                         f"(failure must land somewhere)")
        elif st.kind == "wait":
            if st.runbook_id is not None:
                v.append(f"I-14: wait state {sid}: runbook_id must be None")
            if not triggers & {"timer", "external"}:
                v.append(f"I-14: wait state {sid}: no timer/external transition")
        else:  # end
            if st.runbook_id is not None:
                v.append(f"I-14: end state {sid}: runbook_id must be None")
            if st.outcome not in _FLOW_OUTCOMES:
                v.append(f"I-14: end state {sid}: outcome must be "
                         f"completed|aborted, got '{st.outcome}'")
            if triggers:
                v.append(f"I-14: end state {sid}: no outgoing transitions allowed")
    return v


def _transition_determinism(s: SystemState) -> list[str]:
    """I-15 (flow spec, no ranking): transitions sharing (from_state,
    trigger) are a set. At most one guardless per set — two guardless is
    statically ambiguous. Runtime ambiguity (multiple guards true) is a
    definition fault handled by the executor (abort + disclosure)."""
    v: list[str] = []
    guardless: dict[tuple[str, str], int] = {}
    for t in s.flow_transitions.values():
        if t.guard is None:
            key = (t.from_state_id, t.trigger)
            guardless[key] = guardless.get(key, 0) + 1
    for (sid, trig), n in guardless.items():
        if n > 1:
            v.append(f"I-15: state {sid} trigger '{trig}': {n} guardless "
                     f"transitions — statically ambiguous")
    return v


def _flow_run_closure(s: SystemState) -> list[str]:
    """I-16 (flow spec): a flow run in done/aborted must sit in a kind=end
    state — the I-13 closure-bar pattern, one level up. current_state must
    belong to the run's flow."""
    v: list[str] = []
    for rid, r in s.flow_runs.items():
        st = s.flow_states.get(r.current_state_id)
        if st is None:
            continue  # RI reports the dangling reference
        if st.flow_id != r.flow_id:
            v.append(f"I-16: flow run {rid}: current state {r.current_state_id} "
                     f"belongs to another flow")
        if r.state in ("done", "aborted") and st.kind != "end":
            v.append(f"I-16: flow run {rid}: closed as {r.state} outside an "
                     f"end state (in {r.current_state_id})")
    return v


def _step_policy_declared(s: SystemState) -> list[str]:
    """Ratified O2 (F-F2): every task state declares its step-failure
    policy — abort | skip | retry:<n>=1 — explicit, no silent default.
    wait/end states must not declare one. Transcript re-validation
    (step_failed vs declared consequence) is an executor/referee duty;
    the validator pins the declaration."""
    v: list[str] = []
    for sid, st in s.flow_states.items():
        p = st.step_policy
        if st.kind == "task":
            if p is None:
                v.append(f"STEP-POLICY: task state {sid}: step_policy required "
                         f"(abort | skip | retry:<n>)")
            elif not _valid_step_policy(p):
                v.append(f"STEP-POLICY: task state {sid}: malformed "
                         f"step_policy '{p}'")
        elif p is not None:
            v.append(f"STEP-POLICY: {st.kind} state {sid}: step_policy must "
                     f"be None")
    return v


def _valid_step_policy(p: str) -> bool:
    if p in ("abort", "skip"):
        return True
    if p.startswith("retry:"):
        try:
            return int(p.split(":", 1)[1]) >= 1
        except ValueError:
            return False
    return False


MUTATION_RUNGS = ("configure", "role", "scenario", "wrap", "patch", "fork")
MUTATION_REASON_STATUSES = ("accepted", "pending")


def _mutation_record_closure(s: SystemState) -> list[str]:
    """I-17 (dsys-mutation-playbook): a mutation-playbook DecisionRecord
    must name a valid rung; a record touching the trust boundary must
    declare its voided guarantees. An adopted record must state its
    reason (spec §10: mutation without reason is not allowed); a stated
    reason_status must be accepted|pending. The validator checks
    completeness of the declaration, not its truth — whether the reason
    is truly evidenced is author-declared (declared trust, cf. F-M4)."""
    v: list[str] = []
    for rid, r in s.decision_records.items():
        if r.playbook != "dsys-mutation-playbook":
            continue
        if r.rung is not None and r.rung not in MUTATION_RUNGS:
            v.append(f"I-17: mutation record {rid}: unknown rung '{r.rung}' "
                     f"(expected one of {', '.join(MUTATION_RUNGS)})")
        if r.reason_status is not None and r.reason_status not in MUTATION_REASON_STATUSES:
            v.append(f"I-17: mutation record {rid}: unknown reason_status "
                     f"'{r.reason_status}' (expected accepted|pending)")
        if r.verdict == "adopted":
            if r.rung is None:
                v.append(f"I-17: mutation record {rid}: adopted with no rung "
                         f"selected")
            if r.touches_trust_boundary and not r.voided_guarantees:
                v.append(f"I-17: mutation record {rid}: touches trust boundary "
                         f"with no voided_guarantees declared")
            if not r.reason.strip():
                v.append(f"I-17: mutation record {rid}: adopted with no "
                         f"reason stated (mutation without reason is not allowed)")
    return v


def validate(s: SystemState) -> list[str]:
    """Run every invariant; return violation messages (empty = clean)."""
    out: list[str] = []
    out += _referential_integrity(s)
    out += _claim_materialization(s)
    out += _no_self_ratify(s)
    out += _disposition_modes(s)
    out += _disclosure_triage(s)
    out += _standing_supersession(s)
    out += _overrule_backing(s)
    out += _citation_integrity(s)
    out += _dialectic_separator(s)
    out += _null_option_triage(s)
    out += _knowledge_lifecycle(s)
    out += _playbook_triad(s)
    out += _briefings_and_ratification(s)
    out += _session_transaction_ledger(s)
    out += _directive_application(s)
    out += _promotion_release(s)
    out += _run_lifecycle(s)
    out += _automaton_ordering(s)
    out += _flow_totality(s)
    out += _transition_determinism(s)
    out += _flow_run_closure(s)
    out += _step_policy_declared(s)
    out += _mutation_record_closure(s)
    out += _drain_closure_bar(s)
    out += _orphan_queue(s)
    return out


# ---------------------------------------------------------------------------
# Refusal semantics: the operations that must say no with a reason
# ---------------------------------------------------------------------------

def try_apply_directive(s: SystemState, directive_id: str) -> tuple[bool, str]:
    """Apply a directive iff its gate check passed and no upheld local_wins veto."""
    d = s.directives.get(directive_id)
    if d is None:
        return False, "directive missing"
    gcs = [g for g in s.gate_checks.values() if g.directive_id == directive_id]
    if not gcs or gcs[-1].verdict != GateCheckVerdict.PASSED:
        return False, "no passed gate check — directive rejected, never converted"
    vetoes = [x for x in s.local_vetoes.values() if x.directive_id == directive_id]
    for x in vetoes:
        pol = next((p for p in s.authority_policies.values()), None)
        if x.status == VetoStatus.UPHELD and (pol is None or pol.on_conflict == OnConflict.LOCAL_WINS):
            return False, f"local veto {x.id} upheld — directive rejected"
    return True, "ok"


def try_close_completed(s: SystemState, run_id: str) -> tuple[bool, str]:
    req = [c for c in s.conditions.values() if c.run_id == run_id and c.required]
    bad = [c.id for c in req if not c.satisfied]
    if bad:
        return False, f"required conditions unsatisfied: {bad}"
    return True, "ok"


def try_promote(s: SystemState, artifact_id: str, version: str,
                disposition_id: str) -> tuple[bool, str]:
    if any(r.version == version for r in s.releases.values()):
        return False, f"release version {version} already exists"
    art = s.artifacts.get(artifact_id)
    if art is None:
        return False, "artifact missing"
    if not any(pb.domain == art.domain for pb in s.playbooks.values()):
        return False, f"domain '{art.domain}' has no dyad playbook (playbook before automation)"
    d = s.dispositions.get(disposition_id)
    if d is None or d.proposer_id == d.disposer_id:
        return False, "irreversible publish needs an Operator disposition (N6)"
    if d.mode != DispositionMode.AUTHORIZE:
        return False, "irreversible publish needs an AUTHORIZE-mode disposition (N6)"
    if d.status not in (DispositionStatus.APPROVED, DispositionStatus.ACTED):
        return False, "irreversible publish needs an approved AUTHORIZE-mode disposition (N6)"
    if not d.state_ref or d.state_ref != art.content_hash:
        return False, "authorization is stale: artifact changed since disposition (N6)"
    return True, "ok"


def try_materialize(s: SystemState, claim_id: str) -> tuple[bool, str]:
    claim = s.claims.get(claim_id)
    if claim is None:
        return False, "claim missing"
    recs = [r for r in s.falsification_records.values()
            if r.claim_id == claim_id and r.outcome == FalsificationOutcome.SURVIVED
            and r.external_separator.strip()]
    if not recs:
        return False, "no surviving falsification record with external separator (IFF1/IFF2)"
    return True, "ok"
