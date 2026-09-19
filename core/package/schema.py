"""Dyad System Architecture — unified entity schema (data plane).

Four planes:
  Dyad           — Human, Agent, Dyad, Bond, CovenantGate, Intent, Claim,
                   Falsifier, FalsificationRecord, Evidence, KnowledgeUnit,
                   MaterializationVerdict, Playbook, CommonsPlaybook, Hat,
                   Disposition, Session, DyadTransaction, Ledger, LedgerEntry,
                   Subagent, Briefing, Proposal, RatificationRecord
  Harness        — Principal, HarnessRun, Condition, Thread,
                   InteractionPreference, ArtifactPackage, StrapGate,
                   AuthorityPolicy, LocalVeto
  Chief-of-Staff — Directive, GateCheck, Application, PromotionRecord,
                   AutomatonRelease
  Automaton      — RunBook, Step, Tool, AutomatonRun, AutomatonEvent,
                   AutomatonFlow, FlowState, FlowTransition, FlowRun,
                   FlowTransitionEvent,

Source key (all observed/read 2026-09-18):
  [leo]    dyad-leo DYAD.md (private repo; read via authenticated browser)
  [bond-r] dyad-bond README (public; observed)
  [bond-d] dyad-bond DYAD.md (public; read via raw fetch)
  [pract]  the-dyad-practice README (public; observed)
  [auto]   Automaton design package (2026-09-18)
  [harn]   Harness design package v1.1.0 + Round-2 additions
  [cos]    Chief-of-Staff design package + Round-2 additions
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class E(BaseModel):
    """Base entity: immutable, identity-keyed. id is stamped by the store."""
    model_config = ConfigDict(frozen=True)
    id: str = ""


# ---------------------------------------------------------------------------
# Dyad plane
# ---------------------------------------------------------------------------

class Human(E):
    """[leo] The Operator: holds intent and stakes. Terminal disposition
    authority — 'the agent detects; the human disposes' [bond-r]."""
    name: str


class Agent(E):
    """[leo] The agent (Leo in dyad-leo): holds diligence and execution.
    Identity claims sanctioned only via the single identity source [leo §7];
    birth-id recomputed, never trust-stored [bond-d]."""
    name: str


class Dyad(E):
    """[pract][bond-r][leo] The irreducible Human+Agent team ('1+1=3').
    Neither role replaceable by the other [leo N1]."""
    name: str
    human_id: str
    agent_id: str
    birth_id: str          # frozen at birth; immutable [bond-d]
    constitution_ref: str  # e.g. DYAD.md hash pinned at session start [leo §0]


class BondState(str, Enum):
    COVALENT = "covalent"  # produced by running the falsification law on the bond [bond-d]
    IONIC = "ionic"        # law bypassed: override or rubber-stamp [bond-d]
    MELD = "meld"          # law disabled: two models merged into one [bond-d]


class Bond(E):
    """[bond-r][bond-d] The covalent bond state of a dyad."""
    dyad_id: str
    state: BondState
    belief: str  # held falsifiably under no-dogma [bond-d]


class CovenantGate(E):
    """[bond-r] Materialization gates: IFF1 epistemics (materialize iff
    falsifiable+testable), IFF2 no-oracle (external separator required),
    IFF3 wu-wei (falsification stays livable)."""
    name: str
    test: str


class IntentState(str, Enum):
    STATED = "stated"
    CLARIFIED = "clarified"
    DISPOSED = "disposed"


class Intent(E):
    """[leo][bond-r] The Operator's overall intent (personal/professional).
    Held by the human; the agent may clarify only where permitted."""
    dyad_id: str
    text: str
    state: IntentState = IntentState.STATED


class ClaimState(str, Enum):
    DRAFT = "draft"
    UNDER_FALSIFICATION = "under_falsification"
    SURVIVED = "survived"
    REFUTED = "refuted"


class Claim(E):
    """[pract][bond-d] A falsifiable proposition. Earns its place in the
    shared model only by surviving genuine falsification — nothing exempt."""
    dyad_id: str
    intent_id: Optional[str] = None
    text: str
    state: ClaimState = ClaimState.DRAFT
    canonical_home: str  # single-home: each fact lives in exactly one home [bond-d]


class Falsifier(E):
    """[bond-r][bond-d] The named falsifier of a claim. two-models: must be an
    independent second model, else the falsification is meld-counterfeit."""
    claim_id: str
    kind: str  # e.g. 'independent_model', 'external_audit', 'durability_over_time'
    description: str


class FalsificationOutcome(str, Enum):
    SURVIVED = "survived"
    REFUTED = "refuted"


class FalsificationRecord(E):
    """[bond-r][pract] One falsification attempt. IFF2: testability requires an
    external separator — independent audit or durability over time."""
    claim_id: str
    falsifier_id: str
    method: str
    outcome: FalsificationOutcome
    external_separator: str
    ts: str


class Evidence(E):
    """[pract] Contributor / timestamp / testimonial / audit evidence attached
    to a falsification record or knowledge unit."""
    record_id: str
    kind: str
    ref: str


class KnowledgeStage(str, Enum):
    DIALECTIC = "dialectic"  # live cycles under falsification [bond-d]
    KB = "kb"                # settled; safe to cite [bond-d]


class KnowledgeUnit(E):
    """[pract][bond-d] Settled knowledge: claim + refutation + ledger pointer +
    evidence. Graduates dialectic -> kb only after surviving falsification."""
    claim_id: str
    refutation: Optional[str] = None
    ledger_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    canonical_home: str
    stage: KnowledgeStage = KnowledgeStage.DIALECTIC


class MaterializationVerdict(str, Enum):
    MATERIALIZED = "materialized"
    BLOCKED = "blocked"


class MaterializationVerdictRec(E):
    """[bond-r] A claim materializes into the shared model iff it clears the
    covenant gates (IFF1/IFF2/IFF3)."""
    claim_id: str
    gate_results: dict[str, bool]
    verdict: MaterializationVerdict


class Playbook(E):
    """[leo §21] Every recurring domain gets a playbook before automation.
    Exactly three plays: start a thing, stop a thing, keep a thing."""
    dyad_id: str
    domain: str
    play_start: str
    play_stop: str
    play_keep: str
    origin: str  # 'commons' | 'dyad'  [pract]: dyads own specializations of Commons playbooks


class CommonsPlaybook(E):
    """[pract] Shared playbooks from the Commons, e.g. Proposal-Framing:
    propose one path; strongest counter; reconciliation; ask one Y/N."""
    name: str
    steps: list[str]


class Hat(E):
    """[bond-d] Channel hats: Bond Operator (proposer+ratifier), Founding
    Operator (form gate), Steward Operator (intake/coordination). A
    disposition reaches only the hat that owns it."""
    dyad_id: str
    name: str
    seat: str


class DispositionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTED = "acted"


class DispositionMode(str, Enum):
    """[§8.2] The five modes of Operator disposition. Ratify resolves a
    decision matter; authorize permits a named action (esp. irreversible);
    set_standing establishes persistent policy; overrule defeats a standing
    veto; triage disposes of an upward disclosure."""
    RATIFY = "ratify"
    AUTHORIZE = "authorize"
    SET_STANDING = "set_standing"
    OVERRULE = "overrule"
    TRIAGE = "triage"


class DispositionResponse(str, Enum):
    """E3: CTA response grammar. A counter-proposal keeps the disposition
    proposed and spawns a linked re-entry."""
    YES = "yes"
    NO = "no"
    COUNTER = "counter"


class SilenceMeaning(str, Enum):
    """E5: what silence means per disposition mode. Declared as data so
    consumption sites consult it instead of deriving it per run."""
    NO_DECISION = "no_decision"            # ratify: unratified means draft
    NO_ACTION = "no_action"                # authorize: no authorization, no action
    OUTCOME_REFUSED = "outcome_refused"    # triage: silence is not triage
    SUSTAIN_MUST_BE_RECORDED = "sustain_must_be_recorded"  # set_standing/overrule


MODE_SILENCE: dict["DispositionMode", SilenceMeaning] = {
    DispositionMode.RATIFY: SilenceMeaning.NO_DECISION,
    DispositionMode.AUTHORIZE: SilenceMeaning.NO_ACTION,
    DispositionMode.SET_STANDING: SilenceMeaning.SUSTAIN_MUST_BE_RECORDED,
    DispositionMode.OVERRULE: SilenceMeaning.SUSTAIN_MUST_BE_RECORDED,
    DispositionMode.TRIAGE: SilenceMeaning.OUTCOME_REFUSED,
}


def resolve_silence(mode: "DispositionMode") -> SilenceMeaning:
    """E5: the declared meaning of 'no disposition' for a mode."""
    return MODE_SILENCE[mode]


NULL_OPTION = "decide nothing"  # E5: the playbook's canonical null option label


class Disposition(E):
    """[bond-r][bond-d][leo N6] Terminal human authority. The agent detects /
    proposes; the human disposes. proposer != disposer (no-self-ratify).
    DFD: genuine non-strawman anti-thesis -> synthesis; at most one [CTA·Y/N]
    per turn. Irreversible actions need explicit Operator authorization.
    Mode selects which definition-of-done applies [§8.2]."""
    dyad_id: str
    session_id: Optional[str] = None
    text: str
    hat_id: str
    proposer_id: str   # the agent
    disposer_id: str   # the human — terminal
    cta: Optional[str] = None  # at most one 'Y/N'
    status: DispositionStatus = DispositionStatus.PROPOSED
    mode: DispositionMode = DispositionMode.RATIFY
    action_ref: Optional[str] = None      # authorize: the explicitly named action
    standing_domain: Optional[str] = None  # set_standing: persistent policy domain
    veto_id: Optional[str] = None          # overrule: the LocalVeto defeated
    disclosure_ref: Optional[str] = None   # triage: the upward disclosure disposed
    supersedes_disposition_id: Optional[str] = None  # set_standing: prior policy superseded
    state_ref: Optional[str] = None        # E2 authorize: artifact hash at disposition
    absorbed_into_directive_id: Optional[str] = None  # E7 overrule: amendment absorbing the veto's reason
    response: Optional[DispositionResponse] = None  # E3: CTA answer (None = not yet answered)
    counter_text: Optional[str] = None              # E3: the counter-proposal text
    reentry_ref: Optional[str] = None               # E3: re-entered matter/run spawned by a counter


class DisclosureKind(str, Enum):
    """[leo] What was disclosed upward: conflict, error, or uncertainty."""
    CONFLICT = "conflict"
    ERROR = "error"
    UNCERTAINTY = "uncertainty"


class DisclosureStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"


class Disclosure(E):
    """[leo] Upward disclosure of a conflict, error, or uncertainty. Silence
    is not triage: every non-open disclosure is cited by exactly one triage
    disposition, and no disclosure is cited by more than one.
    [DR-5/A1] seq is a write-path-minted monotonic counter (no clock in the
    architecture): it orders disclosures for the drain-duty backlog rule.
    Declared trust — no validator can verify who minted a seq."""
    dyad_id: str
    kind: DisclosureKind
    text: str
    status: DisclosureStatus = DisclosureStatus.OPEN
    seq: int = 0


class DecisionRecord(E):
    """[playbook] The record of a playbook run. Options
    carry gate trails; supporting premises are explicit record-ID
    citations (E1) so citation integrity is checkable. Rehearsal records
    are quarantined: they cannot be cited as premises (E1). Dialectic
    runs name their separator (E4). The dsys-mutation-playbook (second
    playbook) writes the same entity with playbook='dsys-mutation-playbook',
    a selected rung, declared voided guarantees, and a classified reason
    (I-17)."""
    playbook: str = "decision-making"  # or "dsys-mutation-playbook"
    matter: str = ""
    options: list[str] = Field(default_factory=list)
    gate_trails: list[str] = Field(default_factory=list)
    selected: Optional[str] = None
    selector_id: str = ""
    proposer_id: str = ""
    verdict: str = "draft"  # adopted | killed | merged | deferred | superseded | draft
    consequences: str = ""
    uncertainties: str = ""
    premises: list[str] = Field(default_factory=list)
    dialectic: bool = False
    separator_id: Optional[str] = None
    thesis: Optional[str] = None
    antithesis: Optional[str] = None
    synthesis: Optional[str] = None
    rehearsal: bool = False
    disposition_id: Optional[str] = None
    # --- dsys-mutation-playbook fields (I-17) ---
    rung: Optional[str] = None  # configure|role|scenario|wrap|patch|fork
    touches_trust_boundary: bool = False
    voided_guarantees: list[str] = Field(default_factory=list)
    reason: str = ""  # the mutation's reason; required on adoption (spec §10)
    reason_status: Optional[str] = None  # accepted | pending (spec §10)


class SessionKind(str, Enum):
    SUBSTRATE = "substrate"    # long-lived [leo]
    WORKSTREAM = "workstream"  # task-bounded [leo]
    ENGAGEMENT = "engagement"  # interactive [leo]


class SessionState(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class Session(E):
    """[leo] Five verbs: plan/start/stop/pause/resume. One owner; an explicit
    boundary; a falsifiable claim (what would prove the session failed).
    Runs on snapshot isolation — never on live state."""
    dyad_id: str
    kind: SessionKind
    state: SessionState = SessionState.PLANNED
    owner_id: str
    boundary: str
    falsifiable_claim: str


class TxnState(str, Enum):
    BEGUN = "begun"
    COMMITTED = "committed"
    ABORTED = "aborted"


class DyadTransaction(E):
    """[leo] The dyad loop as a database transaction: begin / do /
    commit-or-abort. Commit publishes state + ledger entry atomically; abort
    returns to the last committed state and records the attempt."""
    session_id: str
    state: TxnState = TxnState.BEGUN
    ops: list[str] = Field(default_factory=list)


class Ledger(E):
    """[leo §26] The dyad's memory and audit trail. Memory not written down
    is not trusted."""
    dyad_id: str


class LedgerEntry(E):
    """[leo][bond-d] Timestamped entry; the ledger is the write-ahead log of
    the dyad loop. Commit/abort of a transaction always lands here."""
    ledger_id: str
    ts: str
    kind: str  # 'commit' | 'abort' | 'note' | 'decision' | ...
    payload: str
    session_id: Optional[str] = None
    txn_id: Optional[str] = None


class SubagentMode(str, Enum):
    READ_ONLY = "read_only"
    ACTIVE = "active"


class Subagent(E):
    """[leo] Registered specialists, e.g. M265 Facilitator (session hygiene),
    FIA Fiduciary Intelligence Analyst (read-only: advises, never acts),
    Travel Specialist (read-only planner; Operator approves)."""
    dyad_id: str
    name: str
    mandate: str
    mode: SubagentMode


class Briefing(E):
    """[leo §24] The dyad thinks in briefings. A briefing that does not end
    with a checkable artifact is a conversation, not work."""
    dyad_id: str
    session_id: str
    artifact_ref: str  # required: the checkable artifact


class Proposal(E):
    """[leo §25] A proposal with checkable ratification criteria."""
    dyad_id: str
    text: str
    criteria: list[str]


class RatificationVerdict(str, Enum):
    RATIFIED = "ratified"
    RETURNED_TO_DRAFT = "returned_to_draft"


class RatificationRecord(E):
    """[leo §25] A proposal that fails its criteria does not die; it returns
    to draft with its failure attached."""
    proposal_id: str
    verdict: RatificationVerdict
    failure: Optional[str] = None


# ---------------------------------------------------------------------------
# Harness plane
# ---------------------------------------------------------------------------

class Principal(E):
    """[harn] The body a run belongs to (a dyad or a human)."""
    name: str


class RunState(str, Enum):
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"


class ClosureReason(str, Enum):
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ABORTED = "aborted"


class AuthorityScope(str, Enum):
    """[harn] What a run's uncommitted state may contend over. Execution runs
    do the work; governance runs oversee it (Chief-of-Staff: gate checks,
    vetoes, directives). Scopes are disjoint by construction, so a
    governance run coexists with the execution run it manages."""
    EXECUTION = "execution"
    GOVERNANCE = "governance"


class HarnessRun(E):
    """[harn] Guided human/LLM turns targeting machine-evaluable definition-of-
    done conditions. Threads are flat; at most one non-closed run per
    (principal, authority-scope). A Chief-of-Staff run is a HarnessRun with
    authority_scope=GOVERNANCE whose exclusive outputs are lifecycle
    directives [cos]."""
    principal_id: str
    dyad_id: Optional[str] = None
    session_id: Optional[str] = None  # workstream session that spawned it [leo]
    state: RunState = RunState.OPEN
    closure_reason: Optional[ClosureReason] = None
    authority_scope: AuthorityScope = AuthorityScope.EXECUTION
    open_seq: int = 0  # [DR-5/A1] write-path counter value at run open;
    # the drain-duty backlog is disclosures with seq < open_seq


class Condition(E):
    """[harn] Definition-of-done condition in the shared expression language.
    Required conditions gate completed closure."""
    run_id: str
    expr: str
    required: bool
    satisfied: bool = False


class ThreadState(str, Enum):
    AWAITING_LLM = "awaiting_llm"
    SETTLED = "settled"
    SUSPENDED = "suspended"


class Thread(E):
    """[harn] Flat thread; derived 3-valued state."""
    run_id: str
    state: ThreadState = ThreadState.SETTLED


class InteractionPreference(E):
    """[harn] Human-controllable LLM posture: challenge_claims,
    clarify_intent, invoked_preference."""
    run_id: str
    challenge_claims: bool = False
    clarify_intent: bool = False
    invoked_preference: str = ""


class ArtifactPackage(E):
    """[harn] Machine-native output: pydantic schema + instances + generated
    surface. Enters Automaton only through immutable step-changes."""
    run_id: str
    domain: str  # must be covered by a dyad Playbook before automation [leo §21]
    schema_name: str
    instance_ref: str
    surface_ref: str
    content_hash: str = ""  # E2: canonical hash at close; authorize binds to it


class StrapVerdict(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    PENDING = "pending"


class StrapGate(E):
    """[harn] Run-lifecycle strap/unstrap gates over required conditions."""
    run_id: str
    required_condition_ids: list[str] = Field(default_factory=list)
    verdict: StrapVerdict = StrapVerdict.PENDING


class OnConflict(str, Enum):
    FLEET_WINS = "fleet_wins"  # default [cos]
    LOCAL_WINS = "local_wins"


class AuthorityPolicy(E):
    """[cos] Fleet vs local precedence for directive conflicts."""
    scope: str
    on_conflict: OnConflict = OnConflict.FLEET_WINS


class VetoStatus(str, Enum):
    UPHELD = "upheld"
    OVERRULED = "overruled"


class LocalVeto(E):
    """[cos] Principal-owned veto targeting a proposed directive. Logged
    whether upheld or overruled — dissent is data."""
    principal_id: str
    directive_id: str
    status: VetoStatus


# ---------------------------------------------------------------------------
# Chief-of-Staff plane
# ---------------------------------------------------------------------------

class Directive(E):
    """[cos] Lifecycle directive from a Chief-of-Staff run. References other
    runs by identity; targets are not nested. Reversible countermands carry
    supersedes_directive_id. Closed-run freeze dominates: terminal
    transitions are not supersedable."""
    source_run_id: str
    target_run_id: str
    action: str  # e.g. 'pause', 'resume', 'close_completed', 'promote'
    supersedes_directive_id: Optional[str] = None
    disposition_id: Optional[str] = None


class GateCheckVerdict(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"


class GateCheck(E):
    """[cos] Every directive application records a GateCheck with per-gate
    results. Initiation is fleet-level; validation is target-level. A
    Chief-of-Staff directive has no bypass privilege."""
    directive_id: str
    target_run_id: str
    per_gate: dict[str, bool] = Field(default_factory=dict)
    verdict: GateCheckVerdict


class Application(E):
    """[cos] The deterministic, zero-inference applier is the only mutation
    channel. Failure rejects the directive — never silently converts."""
    directive_id: str
    gate_check_id: str
    target_event_ref: str


class PromotionRecord(E):
    """[cos] Mechanical, zero-inference promote of an artifact to an immutable
    AutomatonRelease. Preconditions: validated source artifact, unique release
    version, applied source directive when cited, Operator disposition for the
    irreversible publish [leo N6]."""
    artifact_id: str
    release_version: str
    directive_id: Optional[str] = None
    disposition_id: str
    preconditions_ok: bool = False


class AutomatonRelease(E):
    """[cos] Immutable release shipped to the Automaton plane."""
    version: str  # unique
    artifact_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Automaton plane
# ---------------------------------------------------------------------------

class RunBook(E):
    """[auto] The executable unit of the automaton plane: strictly sequential
    steps; invokes tools. Collapsed 2026-09-19 from the AutomatonPlayBook /
    RunBook pair — the "FSM orchestrating run-books" distinction was unmodeled
    (no State/Transition entities; sequencing lives in Step.seq), so the pair
    was one entity wearing two names. release_version pins the shipped release.
    Zero inference inside."""
    release_version: str
    name: str


class Step(E):
    """[auto] One step: AST-allowlisted expression (compiled once) + tool."""
    runbook_id: str
    seq: int
    expr: str
    tool_id: str


class Tool(E):
    """[auto] Tool invoked by a run-book step."""
    name: str


class AutomatonRun(E):
    """[auto] Single-threaded actor, single-writer lease, immutable cfg,
    mutable ctx, deterministic idempotency keys, timer events, retries,
    skip, compensation, abort. Runs a single RunBook; when spawned by a
    flow, parent_flow_run_id/flow_state_id record which flow state this
    run executed for."""
    runbook_id: str
    state: str
    idempotency_key: str
    parent_flow_run_id: str | None = None
    flow_state_id: str | None = None


class AutomatonEvent(E):
    """[auto] Append-only event log — the source of truth. Replay never
    reinvokes tools."""
    run_id: str
    seq: int
    kind: str
    payload: str


class AutomatonFlow(E):
    """[auto] Finite-state machine orchestrating run-books: states bound to
    run-books, mechanical transitions on events. New machinery 2026-09-19 —
    not a restoration of AutomatonPlayBook (an unmodeled label collapsed
    into RunBook). Zero inference: transition selection is set-evaluation
    of allowlisted guards (I-15), never judgment."""
    name: str
    release_version: str
    initial_state_id: str


class FlowState(E):
    """[auto] One FSM state. task runs a run-book under a declared
    step_policy; wait holds for timer/external; end is terminal."""
    flow_id: str
    name: str
    kind: str  # task | wait | end
    runbook_id: str | None = None  # required iff kind == task
    outcome: str | None = None  # iff kind == end: completed | aborted
    step_policy: str | None = None  # required iff kind == task:
    # abort | skip | retry:<n> (n>=1). Explicit — no silent default.


class FlowTransition(E):
    """[auto] One guarded edge. Transitions sharing (from_state_id, trigger)
    are a set, never a ranking: at runtime every guard is evaluated and
    exactly one true wins (I-15). Ambiguity is a fault, not an ordering
    problem."""
    flow_id: str
    from_state_id: str
    trigger: str  # timer | run_completed | run_aborted | external
    guard: str | None = None  # AST-allowlisted expr over {payload.*, run.status}
    to_state_id: str


class FlowRun(E):
    """[auto] One execution of a flow. The scheduler; per-state work runs as
    child AutomatonRuns."""
    flow_id: str
    current_state_id: str
    state: str  # running | done | aborted


class FlowTransitionEvent(E):
    """[auto] Append-only transition log of a FlowRun — the flow-level source
    of truth. Replay re-derives states from this log; never reinvokes."""
    flow_run_id: str
    seq: int
    from_state_id: str
    to_state_id: str
    trigger: str
    payload: str


# ---------------------------------------------------------------------------
# Whole system
# ---------------------------------------------------------------------------

class SystemState(BaseModel):
    """The full entity graph across all four planes."""
    humans: dict[str, Human] = Field(default_factory=dict)
    agents: dict[str, Agent] = Field(default_factory=dict)
    dyads: dict[str, Dyad] = Field(default_factory=dict)
    bonds: dict[str, Bond] = Field(default_factory=dict)
    covenant_gates: dict[str, CovenantGate] = Field(default_factory=dict)
    intents: dict[str, Intent] = Field(default_factory=dict)
    claims: dict[str, Claim] = Field(default_factory=dict)
    falsifiers: dict[str, Falsifier] = Field(default_factory=dict)
    falsification_records: dict[str, FalsificationRecord] = Field(default_factory=dict)
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    knowledge_units: dict[str, KnowledgeUnit] = Field(default_factory=dict)
    materializations: dict[str, MaterializationVerdictRec] = Field(default_factory=dict)
    playbooks: dict[str, Playbook] = Field(default_factory=dict)
    commons_playbooks: dict[str, CommonsPlaybook] = Field(default_factory=dict)
    hats: dict[str, Hat] = Field(default_factory=dict)
    dispositions: dict[str, Disposition] = Field(default_factory=dict)
    disclosures: dict[str, Disclosure] = Field(default_factory=dict)
    decision_records: dict[str, DecisionRecord] = Field(default_factory=dict)
    sessions: dict[str, Session] = Field(default_factory=dict)
    transactions: dict[str, DyadTransaction] = Field(default_factory=dict)
    ledgers: dict[str, Ledger] = Field(default_factory=dict)
    ledger_entries: dict[str, LedgerEntry] = Field(default_factory=dict)
    subagents: dict[str, Subagent] = Field(default_factory=dict)
    briefings: dict[str, Briefing] = Field(default_factory=dict)
    proposals: dict[str, Proposal] = Field(default_factory=dict)
    ratifications: dict[str, RatificationRecord] = Field(default_factory=dict)
    principals: dict[str, Principal] = Field(default_factory=dict)
    harness_runs: dict[str, HarnessRun] = Field(default_factory=dict)
    conditions: dict[str, Condition] = Field(default_factory=dict)
    threads: dict[str, Thread] = Field(default_factory=dict)
    interaction_prefs: dict[str, InteractionPreference] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactPackage] = Field(default_factory=dict)
    strap_gates: dict[str, StrapGate] = Field(default_factory=dict)
    authority_policies: dict[str, AuthorityPolicy] = Field(default_factory=dict)
    local_vetoes: dict[str, LocalVeto] = Field(default_factory=dict)
    directives: dict[str, Directive] = Field(default_factory=dict)
    gate_checks: dict[str, GateCheck] = Field(default_factory=dict)
    applications: dict[str, Application] = Field(default_factory=dict)
    promotions: dict[str, PromotionRecord] = Field(default_factory=dict)
    releases: dict[str, AutomatonRelease] = Field(default_factory=dict)
    runbooks: dict[str, RunBook] = Field(default_factory=dict)
    steps: dict[str, Step] = Field(default_factory=dict)
    tools: dict[str, Tool] = Field(default_factory=dict)
    automaton_runs: dict[str, AutomatonRun] = Field(default_factory=dict)
    automaton_events: dict[str, AutomatonEvent] = Field(default_factory=dict)
    automaton_flows: dict[str, AutomatonFlow] = Field(default_factory=dict)
    flow_states: dict[str, FlowState] = Field(default_factory=dict)
    flow_transitions: dict[str, FlowTransition] = Field(default_factory=dict)
    flow_runs: dict[str, FlowRun] = Field(default_factory=dict)
    flow_transition_events: dict[str, FlowTransitionEvent] = Field(default_factory=dict)
