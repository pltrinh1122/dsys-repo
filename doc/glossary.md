# Dyad System Architecture — Glossary

Post-falsification ontology (§8–§11 of the CLI interface spec).
Each term is defined by its relations, starting from **dyad**.

**Dyad** — the root and the enduring unit: exactly two members, agent +
operator, plus the irreducible relation between them (bond, constitution,
common ground). Never *operated*, only *participated in*; exercised
*through* the harness. A dyad constitutes a principal.

**Agent** — the dyad's diligence-and-execution member. Acts *within* the
principal's runs, never as a principal itself. Proposes, detects, gates,
frames options — never disposes.

**Operator** — the dyad's stakes-and-intent member, the human. Terminal
disposition authority: the agent detects, the human disposes. The operator
is the principal's *disposer*, not the principal — the one through whom the
principal's judgments are exercised.

**Bond** — the covalent relation R between agent and operator. Superadditive
by definition: 1+1>2. The relational surplus no additive account of the
dyad can capture.

**Constitution** — the dyad's charter; what governs the pairing. A dyad
without one is two strangers — the entity refuses them.

**Principal** — "the body a run belongs to (a dyad or a human)." The *for
whom*: the third term that proposer and disposer both serve. Runs are
slotted per (principal, scope) — DR-1. The extant principal is the dyad
itself ("dyad leo").

**Harness** — the interaction structure, not an entity: guided turns of
human-prompts + LLM responses aimed at definition-of-done conditions. The
medium of the dyad's exercise.

**HarnessRun** — the structured *process*: the exercise. Has a principal
(for whom), a session, a state (OPEN/PAUSED/CLOSED), and an authority
scope. Its parties are principal, agent (who works), human (who prompts
and disposes) — but the run is not their sum. One dyad → many runs, across
time and scopes.

**Session** — the interactional container a run belongs to.

**AuthorityScope** — execution | governance. The two lanes; DR-1 grants
each principal one non-closed run per lane.

**CoS (Chief-of-Staff)** — a *role*, not a unit: a HarnessRun with
governance scope whose exclusive outputs are lifecycle directives. The
agent-as-CoS detects, gates, frames options, proposes dispositions. Each
dyad has a CoS function; "CoS of the fleet" is either distributive (each
member's CoS) or collective (one fleet governor — which would need a fleet
principal that doesn't exist yet).

**Condition** — a definition-of-done conditional in the harness, sharing
the automaton's expression language. Each satisfied condition yields a
machine-native artifact package.

**Thread** — the conversational thread within a run; three-valued state.

**CTA** — the turn's unit of proposal: one call-to-action per turn, awaiting
disposition, answered yes / no / counter.

**Disposition** — the atomic act: proposer (agent) + disposer (human), never
the same. Five modes, each with its own DoD — ratify, authorize,
set_standing, overrule, triage. Human disposition is terminal; simulations
write no records and are never cited as decided.

**Disclosure** — something requiring disposition, written as a record with a
sequence number. Lifecycle: OPEN → triaged (acknowledged / escalated /
converted / dismissed). DR-5 gives it a verification view — a read-only
aggregate of the OPEN queue, independent of any agent's presentation — plus
drainage mechanics: no governance run closes with backlog, and an OPEN
queue with no open governance run is itself a violation.

**Playbook (decision-making)** — a *set* of DoD conditionals (START / STOP /
KEEP, gates G1–G6), not a sequence. A procedure you *follow*, not a node you
command; embodied by the operator role. Sequencing belongs to run-books.

**DecisionRecord** — the record of a playbook run. Writable, citable —
unlike simulations.

**Automaton** — the deterministic execution engine. Zero inference inside;
every human judgment codified beforehand as configuration; deterministic
replay mandatory. The anti-harness: where the harness is prompts and
judgment, the automaton is consequence.

**Run-book** — the automaton plane's executable unit: strictly sequential
steps (each an AST-allowlisted expression, compiled once) invoking tools,
pinned to a shipped release by `release_version`. An `AutomatonRun` runs a
single run-book. The CLI offers no run-book addressee, and agent output
must never be translated into automaton-plane records.

**AutomatonFlow** — the FSM orchestrating run-books (2026-09-19): new
machinery, *not* a restoration of AutomatonPlayBook (whose "FSM
orchestrating run-books" distinction was unmodeled — no State/Transition
entities existed). A flow is defined by **FlowStates** (`task` binds a
run-book and declares an explicit `step_policy` — `abort | skip |
retry:<n>`; `wait` holds for `timer`/`external`; `end` declares
`completed | aborted`) and **FlowTransitions** (trigger `timer |
run_completed | run_aborted | external`, AST-allowlisted guard). A
**FlowRun** is the scheduler: per-state work runs as child AutomatonRuns
(`parent_flow_run_id` / `flow_state_id`); a **FlowTransitionEvent** log
records every transition, append-only — replay re-derives states from it.
Transitions sharing (from, trigger) are a *set*, never a ranking: no
priority discrimination; ambiguity is a fault (I-15), not an ordering
problem. Invariants: I-14 flow totality (every non-end state routes every
fate the model admits — the mechanical form of "exceptions are managed"),
I-15 transition determinism, I-16 flow-run closure bar. The ratified F-F2
remedy: step-failure handling lives in the validated definition
(`step_policy`), transcript re-validated — silent swallowing becomes
log-visible deviation.

**Directive** — a governance run's exclusive output: a lifecycle directive
targeting runs.

**Standing policy** — a durable directive (set_standing mode), e.g. the
unratified CoS drain-duty template: disclosure-written triggers a
governance drain run.

**Artifact** — machine-native output: schema + instances + generated
surface. Authorized by hash; freshness-bound.

**Fleet** — a collective of dyads, addressed by fleet_id: a git repo whose
manifest declares membership (attributed and versioned by commits, never
executed as code). Membership is declared; *activity* is verified against
state. Governed by the authority policy: fleet_wins vs local_wins, with
local vetoes.

**`accretion-repo`** (alias: `git-store`) — the git repository serving as
the durable store of a dsys installation's accreted state: `etc/` config,
`var/` state, transcripts, sync segments, the provenance log. Never the
venv or binaries — not relocatable, doesn't belong in version control.
An optional deployment choice, never a prereq. Provides durable bytes
with history — *not* provenance, which comes from hash-chained segments
plus validators wherever the bytes live. Distinct from the fleet manifest
repo (declares *membership*) and the source/release repo (build
tooling).

**Referee** — the judging function: runs validators and views over state.
Enforces nothing at invocation time; judges afterward. Exit 0 from
`execute` means the agent ran — only the referee says whether the
architecture accepts it.

**`dsys`** — the CLI (renamed from `dyad` 2026-09-19: the old name
caused operational confusion — at the prompt, `dyad <verb>` reads as
addressing the Dyad, while what is invoked is the system). Named for
the dyad *system*, not the Dyad relation. Its surface is harness-plane
agency only: role-framed invocation (`--as`, `--on`), fleet commands,
referee, scenarios, state, doctor. No dyad-plane commands exist, because
the dyad is participated in, not operated.

**dsys-mutation-playbook** — the second playbook (2026-09-19),
following the pattern of the decision-making **Playbook**: DoD
conditionals, START/STOP/KEEP, own gates (G1–G4 + M1–M4), shared
DecisionRecord, single disposition machinery. Decides whether and how
to mutate the installed dsys across the rung ladder configure | role |
scenario | wrap | patch | fork. Maximum flexibility, declared mutation:
the playbook cannot prevent mutation, only declare it (I-17). Every
mutation matter states a reason, classified `accepted` (evidenced by
observations in artifacts/afferent) or `pending` (human disposition,
unevidenced); mutation without reason is not allowed (I-17, spec §10).

## Retired terms

- **AutomatonPlayBook** — collapsed into **Run-book** 2026-09-19. The pair
  was one entity wearing two names: the "FSM orchestrating run-books"
  distinction was unmodeled (no State/Transition entities; sequencing
  lives in Step.seq). `release_version` now lives on RunBook;
  `AutomatonRun.runbook_id` replaces `playbook_id`. The collapse also
  removes the cross-plane name collision with the decision-making
  **Playbook**, which keeps the name.
