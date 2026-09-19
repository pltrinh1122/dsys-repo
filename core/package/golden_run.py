"""Golden run: one end-to-end provenance chain across all four planes,
plus the refusal cases. Asserts: clean state validates with zero violations;
each negative case is refused/flagged with its exact reason."""
from __future__ import annotations

from .schema import (
    Application, ArtifactPackage, AutomatonEvent, AutomatonRelease,
    AutomatonFlow, AutomatonRun, AuthorityPolicy, AuthorityScope, Bond,
    BondState, Briefing, Claim, ClaimState, CommonsPlaybook, Condition,
    CovenantGate, Directive, Disposition, DispositionMode, DispositionResponse,
    DispositionStatus, Dyad, DyadTransaction, Disclosure, DisclosureKind,
    DisclosureStatus, DecisionRecord, Evidence, FlowRun, FlowState,
    FlowTransition, FlowTransitionEvent, MODE_SILENCE, NULL_OPTION,
    SilenceMeaning, FalsificationOutcome, FalsificationRecord, Falsifier,
    GateCheck, GateCheckVerdict, HarnessRun, Hat, Human, Agent, Intent,
    IntentState, InteractionPreference, KnowledgeStage, KnowledgeUnit,
    Ledger, LedgerEntry, LocalVeto, MaterializationVerdict,
    MaterializationVerdictRec, OnConflict, Playbook, Principal,
    PromotionRecord, Proposal, RatificationRecord, RatificationVerdict,
    RunBook, RunState, ClosureReason, Session, SessionKind, SessionState,
    Step, StrapGate, StrapVerdict, Subagent, SubagentMode, SystemState,
    Thread, ThreadState, Tool, TxnState, VetoStatus,
)
from .validators import (
    try_apply_directive, try_close_completed, try_materialize, try_promote, validate,
)
from .views import verification_view

TS = "2026-09-18T14:00:00-07:00"


def _add(s, coll, key, ent):
    """Store ent in collection coll under key, stamping ent.id = key."""
    getattr(s, coll)[key] = ent.model_copy(update={"id": key})


def build_state() -> SystemState:
    s = SystemState()
    # -- Dyad plane ---------------------------------------------------------
    _add(s, "humans", "h-op", Human(name="Operator"))
    _add(s, "agents", "a-leo", Agent(name="Leo"))
    _add(s, "dyads", "d1", Dyad(name="leo", human_id="h-op", agent_id="a-leo",
                                birth_id="sha:1ab6ad0", constitution_ref="DYAD.md#903"))
    _add(s, "bonds", "b1", Bond(dyad_id="d1", state=BondState.COVALENT,
        belief="over a biological lifetime only a covalent bond reaches 1+1>2"))
    _add(s, "covenant_gates", "IFF1", CovenantGate(name="epistemics",
        test="materialize iff falsifiable and testable"))
    _add(s, "covenant_gates", "IFF2", CovenantGate(name="no-oracle",
        test="testability requires an external separator"))
    _add(s, "covenant_gates", "IFF3", CovenantGate(name="wu-wei",
        test="the falsification process stays livable"))
    _add(s, "intents", "i1", Intent(dyad_id="d1",
        text="ship the monthly close run-book", state=IntentState.CLARIFIED))
    _add(s, "claims", "c1", Claim(dyad_id="d1", intent_id="i1",
        text="the close run-book is deterministic under replay",
        state=ClaimState.SURVIVED, canonical_home="kb/determinism.md"))
    _add(s, "falsifiers", "f1", Falsifier(claim_id="c1", kind="independent_model",
        description="second model replays the event log and diffs state"))
    _add(s, "falsification_records", "fr1", FalsificationRecord(
        claim_id="c1", falsifier_id="f1", method="replay-diff",
        outcome=FalsificationOutcome.SURVIVED,
        external_separator="independent audit of 3 monthly closes", ts=TS))
    _add(s, "evidence", "e1", Evidence(record_id="fr1", kind="audit",
        ref="audit/2026-09-close.md"))
    _add(s, "ledgers", "l1", Ledger(dyad_id="d1"))
    _add(s, "knowledge_units", "ku1", KnowledgeUnit(
        claim_id="c1", refutation="none found in 3 audits",
        ledger_id="l1", evidence_ids=["e1"],
        canonical_home="kb/determinism.md", stage=KnowledgeStage.KB))
    _add(s, "materializations", "m1", MaterializationVerdictRec(
        claim_id="c1",
        gate_results={"IFF1": True, "IFF2": True, "IFF3": True},
        verdict=MaterializationVerdict.MATERIALIZED))
    _add(s, "playbooks", "p-close", Playbook(dyad_id="d1", domain="monthly-close",
        play_start="open the close workstream", play_stop="freeze the ledger on sign-off",
        play_keep="reconcile drift weekly", origin="dyad"))
    _add(s, "commons_playbooks", "cp-pf", CommonsPlaybook(name="Proposal-Framing",
        steps=["propose one path", "strongest counter", "reconciliation", "ask one Y/N"]))
    _add(s, "hats", "hat-bo", Hat(dyad_id="d1", name="Bond Operator",
                                  seat="proposer+ratifier"))
    _add(s, "dispositions", "disp1", Disposition(
        dyad_id="d1", session_id="sess-ws1",
        text="promote the close artifact to release 1.0.0", hat_id="hat-bo",
        proposer_id="a-leo", disposer_id="h-op", cta="Y/N",
        mode=DispositionMode.AUTHORIZE, action_ref="promote art1 to release 1.0.0",
        state_ref="h-art1-001",
        status=DispositionStatus.APPROVED))
    _add(s, "sessions", "sess-ws1", Session(dyad_id="d1",
        kind=SessionKind.WORKSTREAM, state=SessionState.ACTIVE, owner_id="h-op",
        boundary="may not touch payroll runs",
        falsifiable_claim="the close ships without a reopen"))
    _add(s, "transactions", "t1", DyadTransaction(session_id="sess-ws1",
        state=TxnState.COMMITTED, ops=["begin", "draft artifact", "commit"]))
    _add(s, "ledger_entries", "le1", LedgerEntry(ledger_id="l1", ts=TS,
        kind="commit", payload="close artifact committed", session_id="sess-ws1",
        txn_id="t1"))
    _add(s, "subagents", "sa-m265", Subagent(dyad_id="d1", name="M265 Facilitator",
        mandate="session hygiene", mode=SubagentMode.ACTIVE))
    _add(s, "subagents", "sa-fia", Subagent(dyad_id="d1",
        name="FIA Fiduciary Intelligence Analyst",
        mandate="read-only analyst: advises, never acts", mode=SubagentMode.READ_ONLY))
    _add(s, "proposals", "pr1", Proposal(dyad_id="d1",
        text="promote close artifact", criteria=["all required conditions satisfied",
                                                 "operator disposition recorded"]))
    _add(s, "ratifications", "r1", RatificationRecord(proposal_id="pr1",
        verdict=RatificationVerdict.RATIFIED))
    # -- Harness plane ------------------------------------------------------
    _add(s, "principals", "pr-d1", Principal(name="dyad leo"))
    _add(s, "harness_runs", "hr1", HarnessRun(principal_id="pr-d1", dyad_id="d1",
        session_id="sess-ws1", state=RunState.OPEN))
    _add(s, "conditions", "cond1", Condition(run_id="hr1",
        expr="replay(log) == state", required=True, satisfied=True))
    _add(s, "conditions", "cond2", Condition(run_id="hr1",
        expr="audit_signed == true", required=True, satisfied=True))
    _add(s, "threads", "th1", Thread(run_id="hr1", state=ThreadState.SETTLED))
    _add(s, "interaction_prefs", "ip1", InteractionPreference(run_id="hr1",
        challenge_claims=True, clarify_intent=True, invoked_preference="challenge-first"))
    _add(s, "artifacts", "art1", ArtifactPackage(run_id="hr1", domain="monthly-close",
        schema_name="CloseReport", instance_ref="inst/close-09",
        surface_ref="ui/close-09", content_hash="h-art1-001"))
    _add(s, "strap_gates", "sg1", StrapGate(run_id="hr1",
        required_condition_ids=["cond1", "cond2"], verdict=StrapVerdict.PASSED))
    _add(s, "briefings", "br1", Briefing(dyad_id="d1", session_id="sess-ws1",
        artifact_ref="art1"))
    _add(s, "authority_policies", "ap1", AuthorityPolicy(scope="fleet",
        on_conflict=OnConflict.FLEET_WINS))
    # -- Chief-of-Staff plane ----------------------------------------------
    _add(s, "harness_runs", "cos1", HarnessRun(principal_id="pr-d1", dyad_id="d1",
        state=RunState.OPEN, authority_scope=AuthorityScope.GOVERNANCE))
    _add(s, "directives", "dir1", Directive(source_run_id="cos1",
        target_run_id="hr1", action="promote", disposition_id="disp1"))
    _add(s, "gate_checks", "gc1", GateCheck(directive_id="dir1",
        target_run_id="hr1",
        per_gate={"target_open": True, "conditions_satisfied": True,
                  "disposition_recorded": True},
        verdict=GateCheckVerdict.PASSED))
    _add(s, "applications", "app1", Application(directive_id="dir1",
        gate_check_id="gc1", target_event_ref="hr1.promote"))
    _add(s, "promotions", "prom1", PromotionRecord(artifact_id="art1",
        release_version="1.0.0", directive_id="dir1", disposition_id="disp1",
        preconditions_ok=True))
    _add(s, "releases", "rel1", AutomatonRelease(version="1.0.0",
        artifact_ids=["art1"]))
    # E1 clean chain: adopted non-rehearsal record citing an approved disposition
    _add(s, "decision_records", "rec1", DecisionRecord(
        matter="adopt the refined I-9 invariant", selector_id="h-op",
        proposer_id="a-leo", verdict="adopted", premises=["disp1"]))
    # -- Automaton plane ----------------------------------------------------
    _add(s, "runbooks", "rb1", RunBook(release_version="1.0.0",
        name="close-steps"))
    _add(s, "tools", "tool-post", Tool(name="post_journal"))
    _add(s, "steps", "st1", Step(runbook_id="rb1", seq=1,
        expr="total(debits) == total(credits)", tool_id="tool-post"))
    _add(s, "automaton_runs", "ar1", AutomatonRun(runbook_id="rb1",
        state="running", idempotency_key="close-2026-09"))
    _add(s, "automaton_events", "ae1", AutomatonEvent(run_id="ar1", seq=1,
        kind="step_completed", payload="st1 ok"))
    # -- Automaton flow: ingest-world -------------------------------------
    _add(s, "automaton_flows", "flow-ingest", AutomatonFlow(
        name="ingest-world", release_version="1.0.0",
        initial_state_id="fs-idle"))
    _add(s, "flow_states", "fs-idle", FlowState(
        flow_id="flow-ingest", name="idle", kind="wait"))
    _add(s, "flow_states", "fs-pulling", FlowState(
        flow_id="flow-ingest", name="pulling", kind="task",
        runbook_id="rb-ingest", step_policy="abort"))
    _add(s, "flow_states", "fs-quarantine", FlowState(
        flow_id="flow-ingest", name="quarantine", kind="task",
        runbook_id="rb-quarantine", step_policy="retry:3"))
    _add(s, "flow_states", "fs-end-ok", FlowState(
        flow_id="flow-ingest", name="end_ok", kind="end",
        outcome="completed"))
    _add(s, "flow_states", "fs-end-dead", FlowState(
        flow_id="flow-ingest", name="end_dead", kind="end",
        outcome="aborted"))
    _add(s, "runbooks", "rb-ingest", RunBook(release_version="1.0.0",
        name="ingest-steps"))
    _add(s, "runbooks", "rb-quarantine", RunBook(release_version="1.0.0",
        name="quarantine-steps"))
    _add(s, "tools", "tool-ingest", Tool(name="pull_updates"))
    _add(s, "tools", "tool-quarantine", Tool(name="park_partial"))
    _add(s, "steps", "st-ingest", Step(runbook_id="rb-ingest", seq=1,
        expr="has_updates(world)", tool_id="tool-ingest"))
    _add(s, "steps", "st-quar", Step(runbook_id="rb-quarantine", seq=1,
        expr="partial_valid(state)", tool_id="tool-quarantine"))
    _add(s, "flow_transitions", "ft1", FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-idle", trigger="timer",
        to_state_id="fs-pulling"))
    _add(s, "flow_transitions", "ft2", FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-pulling",
        trigger="run_completed", to_state_id="fs-idle"))
    _add(s, "flow_transitions", "ft3", FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-pulling",
        trigger="run_aborted", to_state_id="fs-quarantine"))
    _add(s, "flow_transitions", "ft4", FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-quarantine",
        trigger="run_completed", to_state_id="fs-idle"))
    _add(s, "flow_transitions", "ft5", FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-quarantine",
        trigger="run_aborted", to_state_id="fs-end-dead"))
    _add(s, "flow_runs", "fr1", FlowRun(flow_id="flow-ingest",
        current_state_id="fs-pulling", state="running"))
    _add(s, "automaton_runs", "ar2", AutomatonRun(runbook_id="rb-ingest",
        state="running", idempotency_key="fr1:fs-pulling:1",
        parent_flow_run_id="fr1", flow_state_id="fs-pulling"))
    _add(s, "flow_transition_events", "fte1", FlowTransitionEvent(
        flow_run_id="fr1", seq=1, from_state_id="fs-idle",
        to_state_id="fs-pulling", trigger="timer", payload="6h tick"))
    return s


def run() -> dict:
    """Returns {'violations': [...], 'refusals': [...], 'ok': bool}."""
    s = build_state()
    violations = validate(s)
    refusals: list[str] = []

    # 1. clean chain validates
    assert violations == [], f"golden chain violations: {violations}"

    # 2. close_completed on an incomplete run is refused
    s2 = build_state()
    s2.conditions["cond2"] = s2.conditions["cond2"].model_copy(
        update={"satisfied": False})
    ok, reason = try_close_completed(s2, "hr1")
    assert not ok and "cond2" in reason, "incomplete close must be refused"
    refusals.append(f"close_completed refused: {reason}")

    # 3. duplicate release version is refused
    ok, reason = try_promote(s, "art1", "1.0.0", "disp1")
    assert not ok and "already exists" in reason
    refusals.append(f"duplicate promotion refused: {reason}")

    # 4. materialization without a surviving record is refused
    s4 = build_state()
    s4.falsification_records["fr1"] = s4.falsification_records["fr1"].model_copy(
        update={"outcome": FalsificationOutcome.REFUTED,
                "external_separator": ""})
    ok, reason = try_materialize(s4, "c1")
    assert not ok and "IFF1/IFF2" in reason
    refusals.append(f"materialization refused: {reason}")

    # 5. upheld local_wins veto rejects the directive
    s5 = build_state()
    s5.authority_policies["ap1"] = s5.authority_policies["ap1"].model_copy(
        update={"on_conflict": OnConflict.LOCAL_WINS})
    s5.local_vetoes["v1"] = LocalVeto(id="v1", principal_id="pr-d1",
        directive_id="dir1", status=VetoStatus.UPHELD)
    ok, reason = try_apply_directive(s5, "dir1")
    assert not ok and "veto" in reason
    refusals.append(f"vetoed directive refused: {reason}")
    assert validate(s5) == [], f"veto-logged state must stay clean: {validate(s5)}"

    # 6. self-disposition is flagged
    s6 = build_state()
    s6.dispositions["disp1"] = s6.dispositions["disp1"].model_copy(
        update={"disposer_id": "a-leo"})
    bad = validate(s6)
    assert any("no-self-ratify" in x for x in bad), "self-disposition must be flagged"
    refusals.append("self-disposition flagged: no-self-ratify")

    # 7. two open execution runs under one principal violate the refined invariant
    s7 = build_state()
    s7.harness_runs["hr2"] = HarnessRun(id="hr2", principal_id="pr-d1",
        dyad_id="d1", state=RunState.OPEN,
        authority_scope=AuthorityScope.EXECUTION)
    bad7 = validate(s7)
    assert any("I-9" in x and "execution" in x for x in bad7), \
        "second open execution run must violate I-9"
    refusals.append(f"second execution run refused: {[x for x in bad7 if 'I-9' in x][0]}")

    # 8. authorize-mode disposition without a named action is refused
    s8 = build_state()
    s8.dispositions["disp2"] = Disposition(id="disp2", dyad_id="d1",
        text="go ahead", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.AUTHORIZE,
        status=DispositionStatus.APPROVED)
    bad8 = validate(s8)
    assert any("authorize mode without named action" in x for x in bad8), \
        "nameless authorization must violate I-2"
    refusals.append(f"nameless authorization refused: "
                    f"{[x for x in bad8 if 'authorize mode' in x][0]}")

    # 9. irreversible publish on a ratify-mode disposition is refused
    s9 = build_state()
    s9.dispositions["disp9"] = Disposition(id="disp9", dyad_id="d1",
        text="looks fine", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.RATIFY,
        status=DispositionStatus.APPROVED)
    ok, reason = try_promote(s9, "art1", "2.0.0", "disp9")
    assert not ok and "AUTHORIZE-mode" in reason, \
        "ratify-mode disposition must not authorize irreversible publish"
    refusals.append(f"ratify-mode publish refused: {reason}")

    # 10. non-open disclosure without its triage disposition is flagged
    s10 = build_state()
    s10.disclosures["dis1"] = Disclosure(id="dis1", dyad_id="d1",
        kind=DisclosureKind.CONFLICT, text="two owners claim the close",
        status=DisclosureStatus.DISMISSED)
    bad10 = validate(s10)
    assert any("without its triage disposition" in x for x in bad10), \
        "untriaged disclosure must violate I-2"
    refusals.append(f"untriaged disclosure flagged: "
                    f"{[x for x in bad10 if 'triage disposition' in x][0]}")

    # 11. parallel standing policies on one domain are flagged
    s11 = build_state()
    for i in ("a", "b"):
        s11.dispositions[f"ds{i}"] = Disposition(id=f"ds{i}", dyad_id="d1",
            text=f"policy {i}", hat_id="hat-bo", proposer_id="a-leo",
            disposer_id="h-op", mode=DispositionMode.SET_STANDING,
            standing_domain="interaction-preferences",
            status=DispositionStatus.APPROVED)
    bad11 = validate(s11)
    assert any("supersession roots" in x for x in bad11), \
        "parallel standing policies must violate I-2"
    refusals.append(f"parallel standing policies flagged: "
                    f"{[x for x in bad11 if 'supersession roots' in x][0]}")

    # 12. overruled veto without a backing overrule disposition is flagged
    s12 = build_state()
    s12.local_vetoes["v9"] = LocalVeto(id="v9", principal_id="pr-d1",
        directive_id="dir1", status=VetoStatus.OVERRULED)
    bad12 = validate(s12)
    assert any("without a backing overrule disposition" in x for x in bad12), \
        "unbacked overruled veto must violate I-2"
    refusals.append(f"unbacked overruled veto flagged: "
                    f"{[x for x in bad12 if 'backing overrule' in x][0]}")

    # 13. premise citing a quarantined rehearsal record is flagged
    s13 = build_state()
    s13.decision_records["rec-sim"] = DecisionRecord(id="rec-sim",
        matter="simulated principal synthesis", selector_id="h-op",
        proposer_id="a-leo", verdict="adopted", rehearsal=True)
    s13.decision_records["rec2"] = DecisionRecord(id="rec2",
        matter="downstream matter", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", premises=["rec-sim"])
    bad13 = validate(s13)
    assert any("quarantined rehearsal record" in x for x in bad13), \
        "premise citing rehearsal must violate I-11"
    refusals.append(f"rehearsal premise flagged: "
                    f"{[x for x in bad13 if 'quarantined' in x][0]}")

    # 14. premise citing an undecided record is flagged
    s14 = build_state()
    s14.decision_records["rec-draft"] = DecisionRecord(id="rec-draft",
        matter="unfinished matter", selector_id="h-op", proposer_id="a-leo",
        verdict="draft")
    s14.decision_records["rec3"] = DecisionRecord(id="rec3",
        matter="downstream matter", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", premises=["rec-draft"])
    bad14 = validate(s14)
    assert any("undecided record" in x for x in bad14), \
        "premise citing a draft must violate I-11"
    refusals.append(f"undecided premise flagged: "
                    f"{[x for x in bad14 if 'undecided' in x][0]}")

    # 15. dialectic run without a designated separator is flagged
    s15 = build_state()
    s15.decision_records["rec4"] = DecisionRecord(id="rec4",
        matter="principal definition", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", dialectic=True)
    bad15 = validate(s15)
    assert any("without designated separator" in x for x in bad15), \
        "undesignated separator must violate I-12"
    refusals.append(f"undesignated separator flagged: "
                    f"{[x for x in bad15 if 'designated separator' in x][0]}")

    # 16. self-separation unlabeled as rehearsal is flagged
    s16 = build_state()
    s16.decision_records["rec5"] = DecisionRecord(id="rec5",
        matter="principal definition", selector_id="h-op", proposer_id="a-leo",
        separator_id="a-leo", verdict="adopted", dialectic=True)
    bad16 = validate(s16)
    assert any("must be labeled rehearsal" in x for x in bad16), \
        "self-separation must violate I-12"
    refusals.append(f"self-separation flagged: "
                    f"{[x for x in bad16 if 'labeled rehearsal' in x][0]}")

    # E4 clean shapes: self-separation labeled rehearsal, external separator
    s16b = build_state()
    s16b.decision_records["rec6"] = DecisionRecord(id="rec6",
        matter="rehearsed dialectic", selector_id="h-op", proposer_id="a-leo",
        separator_id="a-leo", verdict="adopted", dialectic=True,
        rehearsal=True)
    s16b.decision_records["rec7"] = DecisionRecord(id="rec7",
        matter="audited dialectic", selector_id="h-op", proposer_id="a-leo",
        separator_id="ext-auditor", verdict="adopted", dialectic=True)
    assert validate(s16b) == [], \
        f"clean dialectic shapes must pass: {validate(s16b)}"

    # 17. stale authorization (artifact changed since disposition) is refused
    s17 = build_state()
    s17.dispositions["d17"] = Disposition(id="d17", dyad_id="d1",
        text="promote art1", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.AUTHORIZE,
        action_ref="promote art1 to release 2.0.0", state_ref="stale-hash",
        status=DispositionStatus.APPROVED)
    ok, reason = try_promote(s17, "art1", "2.0.0", "d17")
    assert not ok and "stale" in reason, \
        "stale authorization must refuse the publish"
    refusals.append(f"stale authorization refused: {reason}")

    # 18. approved authorize disposition without state binding is flagged
    s18 = build_state()
    s18.dispositions["d18"] = Disposition(id="d18", dyad_id="d1",
        text="promote art1", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.AUTHORIZE,
        action_ref="promote art1 to release 2.0.0",
        status=DispositionStatus.APPROVED)
    bad18 = validate(s18)
    assert any("without state binding" in x for x in bad18), \
        "unbound authorization must violate I-2"
    refusals.append(f"unbound authorization flagged: "
                    f"{[x for x in bad18 if 'state binding' in x][0]}")

    # 19. counter-proposal without counter text is flagged
    s19 = build_state()
    s19.dispositions["d19"] = Disposition(id="d19", dyad_id="d1",
        text="escalate dis1", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.TRIAGE,
        disclosure_ref="disX", response=DispositionResponse.COUNTER,
        status=DispositionStatus.PROPOSED)
    bad19 = validate(s19)
    assert any("counter response without counter text" in x for x in bad19), \
        "textless counter must violate I-2"
    refusals.append(f"textless counter flagged: "
                    f"{[x for x in bad19 if 'counter response' in x][0]}")

    # 20. counter-proposed disposition left approved is flagged
    s20 = build_state()
    s20.dispositions["d20"] = Disposition(id="d20", dyad_id="d1",
        text="escalate dis1", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.TRIAGE,
        disclosure_ref="disX", response=DispositionResponse.COUNTER,
        counter_text="No. Escalate. Name the hat.",
        status=DispositionStatus.APPROVED)
    bad20 = validate(s20)
    assert any("cannot be approved" in x for x in bad20), \
        "approved counter must violate I-2"
    refusals.append(f"approved counter flagged: "
                    f"{[x for x in bad20 if 'cannot be approved' in x][0]}")

    # 21. absorption citing a missing directive is flagged (referential)
    s21 = build_state()
    s21.dispositions["d21"] = Disposition(id="d21", dyad_id="d1",
        text="overrule v7", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.OVERRULE, veto_id="v7",
        absorbed_into_directive_id="dir-missing",
        status=DispositionStatus.APPROVED)
    bad21 = validate(s21)
    assert any("missing" in x for x in bad21), \
        "absorption citing a missing directive must violate RI"
    refusals.append(f"dangling absorption flagged: "
                    f"{[x for x in bad21 if 'missing' in x][0]}")

    # 22. absorption on a non-overrule disposition is flagged
    s22 = build_state()
    s22.dispositions["d22"] = Disposition(id="d22", dyad_id="d1",
        text="adopt x", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.RATIFY,
        absorbed_into_directive_id="dir1",
        status=DispositionStatus.APPROVED)
    bad22 = validate(s22)
    assert any("absorption is an overrule pattern" in x for x in bad22), \
        "non-overrule absorption must violate I-2"
    refusals.append(f"misplaced absorption flagged: "
                    f"{[x for x in bad22 if 'overrule pattern' in x][0]}")

    # E7 clean shape: overruled veto + backing approved overrule with absorption
    s22b = build_state()
    s22b.local_vetoes["v7"] = LocalVeto(id="v7", principal_id="pr-d1",
        directive_id="dir1", status=VetoStatus.OVERRULED)
    s22b.dispositions["dov1"] = Disposition(id="dov1", dyad_id="d1",
        text="overrule v7, absorb reason into dir1 amendment",
        hat_id="hat-bo", proposer_id="a-leo", disposer_id="h-op",
        mode=DispositionMode.OVERRULE, veto_id="v7",
        absorbed_into_directive_id="dir1", status=DispositionStatus.APPROVED)
    assert validate(s22b) == [], \
        f"clean absorption must pass: {validate(s22b)}"

    # E5a. the silence table is declared for all five modes
    assert MODE_SILENCE == {
        DispositionMode.RATIFY: SilenceMeaning.NO_DECISION,
        DispositionMode.AUTHORIZE: SilenceMeaning.NO_ACTION,
        DispositionMode.SET_STANDING: SilenceMeaning.SUSTAIN_MUST_BE_RECORDED,
        DispositionMode.OVERRULE: SilenceMeaning.SUSTAIN_MUST_BE_RECORDED,
        DispositionMode.TRIAGE: SilenceMeaning.OUTCOME_REFUSED,
    }, "MODE_SILENCE table mismatch"

    # 23. triage record selecting the null option is flagged
    s23 = build_state()
    s23.disclosures["dis2"] = Disclosure(id="dis2", dyad_id="d1",
        kind=DisclosureKind.UNCERTAINTY, text="stale precondition report",
        status=DisclosureStatus.ACKNOWLEDGED)
    s23.dispositions["disp-t"] = Disposition(id="disp-t", dyad_id="d1",
        text="triage dis2", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.TRIAGE,
        disclosure_ref="dis2", status=DispositionStatus.APPROVED)
    s23.decision_records["rec8"] = DecisionRecord(id="rec8",
        matter="outcome for dis2", selector_id="h-op", proposer_id="a-leo",
        options=["acknowledge", NULL_OPTION], selected=NULL_OPTION,
        verdict="adopted", disposition_id="disp-t")
    bad23 = validate(s23)
    assert any("silence is not an outcome" in x for x in bad23), \
        "triage null-option must violate I-2"
    refusals.append(f"triage null-option flagged: "
                    f"{[x for x in bad23 if 'silence is not an outcome' in x][0]}")

    # 24. authorize with no disposition at all: silence is NO_ACTION
    s24 = build_state()
    ok, reason = try_promote(s24, "art1", "3.0.0", "no-such-disp")
    assert not ok and "needs an Operator disposition" in reason, \
        "missing disposition must refuse the publish"
    refusals.append(f"silent publish refused: {reason}")

    # 25. DR-5/B3 closure bar: a governance run closed with undisposed backlog
    s25 = build_state()
    s25.disclosures["dis-old"] = Disclosure(id="dis-old", dyad_id="d1",
        kind=DisclosureKind.CONFLICT, text="owner conflict on close",
        status=DisclosureStatus.OPEN, seq=4)
    s25.harness_runs["cos2"] = HarnessRun(id="cos2", principal_id="pr-d1",
        dyad_id="d1", state=RunState.CLOSED,
        closure_reason=ClosureReason.COMPLETED,
        authority_scope=AuthorityScope.GOVERNANCE, open_seq=10)
    bad25 = validate(s25)
    assert any("undisposed backlog disclosure" in x for x in bad25), \
        "closing over backlog must violate I-13"
    refusals.append(f"backlog closure flagged: "
                    f"{[x for x in bad25 if 'I-13' in x][0]}")

    # 25b. clean: only new arrivals (seq >= open_seq) may remain at close
    s25b = build_state()
    s25b.disclosures["dis-new"] = Disclosure(id="dis-new", dyad_id="d1",
        kind=DisclosureKind.ERROR, text="fresh error report",
        status=DisclosureStatus.OPEN, seq=12)
    s25b.harness_runs["cos2"] = HarnessRun(id="cos2", principal_id="pr-d1",
        dyad_id="d1", state=RunState.CLOSED,
        closure_reason=ClosureReason.COMPLETED,
        authority_scope=AuthorityScope.GOVERNANCE, open_seq=10)
    assert validate(s25b) == [], \
        f"new-arrival close must pass: {validate(s25b)}"

    # 26. DR-5/B1 orphan queue: open disclosures, no non-closed governance run
    s26 = build_state()
    s26.disclosures["dis-q"] = Disclosure(id="dis-q", dyad_id="d1",
        kind=DisclosureKind.UNCERTAINTY, text="unreviewed uncertainty",
        status=DisclosureStatus.OPEN, seq=7)
    s26.harness_runs["cos1"] = s26.harness_runs["cos1"].model_copy(
        update={"state": RunState.CLOSED,
                "closure_reason": ClosureReason.COMPLETED})
    bad26 = validate(s26)
    assert any("no non-closed governance run draining" in x for x in bad26), \
        "orphaned queue must violate I-13"
    refusals.append(f"orphan queue flagged: "
                    f"{[x for x in bad26 if 'I-13' in x][0]}")

    # DR-5/A2 verification view: kind-then-seq order, in-flight flags
    assert verification_view(build_state()) == [], "empty queue on golden state"
    sV = build_state()
    sV.disclosures["dis-v1"] = Disclosure(id="dis-v1", dyad_id="d1",
        kind=DisclosureKind.CONFLICT, text="c", status=DisclosureStatus.OPEN,
        seq=5)
    sV.disclosures["dis-v2"] = Disclosure(id="dis-v2", dyad_id="d1",
        kind=DisclosureKind.ERROR, text="e", status=DisclosureStatus.OPEN,
        seq=3)
    sV.disclosures["dis-v3"] = Disclosure(id="dis-v3", dyad_id="d1",
        kind=DisclosureKind.UNCERTAINTY, text="u",
        status=DisclosureStatus.OPEN, seq=9)
    sV.dispositions["disp-v"] = Disposition(id="disp-v", dyad_id="d1",
        text="triage dis-v2", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.TRIAGE,
        disclosure_ref="dis-v2", status=DispositionStatus.PROPOSED)
    rows = verification_view(sV)
    assert [r.id for r in rows] == ["dis-v1", "dis-v2", "dis-v3"], \
        f"view order must be kind-then-seq: {[r.id for r in rows]}"
    assert [r.triage_in_flight for r in rows] == [False, True, False], \
        "in-flight flag must mark the PROPOSED triage CTA"
    assert validate(sV) == [], f"view state must stay clean: {validate(sV)}"

    # 27. flow with an initial state outside itself is refused (I-14)
    s27 = build_state()
    s27.automaton_flows["flow-ingest"] = \
        s27.automaton_flows["flow-ingest"].model_copy(
            update={"initial_state_id": "no-such-state"})
    bad27 = validate(s27)
    assert any("not a state of this flow" in x for x in bad27), \
        "dangling initial state must violate I-14"
    refusals.append(f"bad initial state flagged: "
                    f"{[x for x in bad27 if 'I-14' in x][0]}")

    # 28. task state with no run_aborted route is refused (I-14)
    s28 = build_state()
    del s28.flow_transitions["ft3"]  # pulling --run_aborted--> quarantine
    bad28 = validate(s28)
    assert any("no run_aborted transition" in x for x in bad28), \
        "unrouted abort must violate I-14"
    refusals.append(f"unrouted abort flagged: "
                    f"{[x for x in bad28 if 'I-14' in x][0]}")

    # 29. wait state with no timer/external transition is refused (I-14)
    s29 = build_state()
    del s29.flow_transitions["ft1"]  # idle --timer--> pulling
    bad29 = validate(s29)
    assert any("no timer/external transition" in x for x in bad29), \
        "untriggerable wait must violate I-14"
    refusals.append(f"untriggerable wait flagged: "
                    f"{[x for x in bad29 if 'I-14' in x][0]}")

    # 30. end state with an outgoing edge is refused (I-14)
    s30 = build_state()
    s30.flow_transitions["ftX"] = FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-end-ok", trigger="external",
        to_state_id="fs-idle")
    bad30 = validate(s30)
    assert any("no outgoing transitions allowed" in x for x in bad30), \
        "end-state edge must violate I-14"
    refusals.append(f"end-state edge flagged: "
                    f"{[x for x in bad30 if 'I-14' in x][0]}")

    # 31. flow run closed outside an end state is refused (I-16)
    s31 = build_state()
    s31.flow_runs["fr1"] = s31.flow_runs["fr1"].model_copy(
        update={"state": "done"})  # still sitting in task state fs-pulling
    bad31 = validate(s31)
    assert any("outside an end state" in x for x in bad31), \
        "closure outside end must violate I-16"
    refusals.append(f"mid-cycle closure flagged: "
                    f"{[x for x in bad31 if 'I-16' in x][0]}")

    # 32. task state with no declared step_policy is refused (ratified O2)
    s32 = build_state()
    s32.flow_states["fs-pulling"] = s32.flow_states["fs-pulling"].model_copy(
        update={"step_policy": None})
    bad32 = validate(s32)
    assert any("step_policy required" in x for x in bad32), \
        "undeclared step policy must violate the ratified rule"
    refusals.append(f"undeclared step policy flagged: "
                    f"{[x for x in bad32 if 'STEP-POLICY' in x][0]}")

    # 33. malformed step_policy is refused (ratified O2)
    s33 = build_state()
    s33.flow_states["fs-quarantine"] = \
        s33.flow_states["fs-quarantine"].model_copy(
            update={"step_policy": "retry:0"})
    bad33 = validate(s33)
    assert any("malformed step_policy" in x for x in bad33), \
        "retry:0 must violate the ratified rule"
    refusals.append(f"malformed step policy flagged: "
                    f"{[x for x in bad33 if 'STEP-POLICY' in x][0]}")

    # 34. two guardless transitions on one (from, trigger) is refused (I-15)
    s34 = build_state()
    s34.flow_transitions["ftDup"] = FlowTransition(
        flow_id="flow-ingest", from_state_id="fs-pulling",
        trigger="run_completed", to_state_id="fs-end-ok")
    bad34 = validate(s34)
    assert any("statically ambiguous" in x for x in bad34), \
        "duplicate guardless must violate I-15"
    refusals.append(f"ambiguous transition flagged: "
                    f"{[x for x in bad34 if 'I-15' in x][0]}")

    # 35. clean mutation-playbook record passes (I-17)
    s35 = build_state()
    s35.decision_records["mrec1"] = DecisionRecord(id="mrec1",
        playbook="dsys-mutation-playbook",
        matter="add lineage view to dsys referee",
        options=["configure", "role", "scenario", "wrap", "patch", "fork"],
        selected="fork", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", rung="fork", touches_trust_boundary=True,
        voided_guarantees=["referee outputs not comparable across trees",
                           "fleet attestation must name the fork"],
        reason="disclosure d-118 shows referee outputs diverging across "
               "fleet trees; observations in transcript t-44",
        reason_status="accepted")
    assert validate(s35) == [], \
        f"clean mutation record must pass: {validate(s35)}"

    # 36. trust-boundary mutation without voided guarantees is refused (I-17)
    s36 = build_state()
    s36.decision_records["mrec2"] = DecisionRecord(id="mrec2",
        playbook="dsys-mutation-playbook", matter="patch the referee",
        selected="patch", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", rung="patch", touches_trust_boundary=True)
    bad36 = validate(s36)
    assert any("voided_guarantees" in x for x in bad36), \
        "undeclared voids must violate I-17"
    refusals.append(f"undeclared voids flagged: "
                    f"{[x for x in bad36 if 'I-17' in x][0]}")

    # 37. mutation record with an unknown rung is refused (I-17)
    s37 = build_state()
    s37.decision_records["mrec3"] = DecisionRecord(id="mrec3",
        playbook="dsys-mutation-playbook", matter="rewrite everything",
        selected="rewrite", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", rung="rewrite")
    bad37 = validate(s37)
    assert any("unknown rung" in x for x in bad37), \
        "unknown rung must violate I-17"
    refusals.append(f"unknown rung flagged: "
                    f"{[x for x in bad37 if 'I-17' in x][0]}")

    # 38. adopted mutation record with no reason is refused (I-17, spec §10)
    s38 = build_state()
    s38.decision_records["mrec4"] = DecisionRecord(id="mrec4",
        playbook="dsys-mutation-playbook", matter="tune the referee",
        selected="configure", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", rung="configure")
    bad38 = validate(s38)
    assert any("no reason" in x for x in bad38), \
        "reasonless adoption must violate I-17"
    refusals.append(f"reasonless mutation flagged: "
                    f"{[x for x in bad38 if 'I-17' in x][0]}")

    # 39. mutation record with an unknown reason_status is refused (I-17)
    s39 = build_state()
    s39.decision_records["mrec5"] = DecisionRecord(id="mrec5",
        playbook="dsys-mutation-playbook", matter="tune the referee",
        selected="configure", selector_id="h-op", proposer_id="a-leo",
        verdict="adopted", rung="configure",
        reason="operator judged the thresholds too strict",
        reason_status="certified")
    bad39 = validate(s39)
    assert any("unknown reason_status" in x for x in bad39), \
        "unknown reason_status must violate I-17"
    refusals.append(f"bad reason_status flagged: "
                    f"{[x for x in bad39 if 'I-17' in x][0]}")

    return {"violations": violations, "refusals": refusals, "ok": True}
