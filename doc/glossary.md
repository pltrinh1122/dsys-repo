# Dyad System Architecture — Glossary

Post-falsification ontology (§8–§11 of the CLI interface spec).
Each term is defined by its relations, starting from **dyad**.

**Dyad** — the root and the enduring unit: exactly two members, agent +
operator, plus the irreducible relation **R** between them (sanctioned
gloss: *common ground*). Never *operated*, only *participated in*;
exercised *through* the harness. A dyad constitutes a principal.
Superset claim (ratified 2026-09-20): the dyad is forever a superset of
the agent — dyad = {agent, operator} + R strictly contains the agent,
and no capability curve crosses the containment. The agent's
evolutionary path is ever-better proposing; principal-hood,
judgment-as-verdict, and R are not capabilities to be gained but
normative positions no computation confers. Tripwire: repealing the
Principal definition (agent excluded) or admitting agent disposition
repeals this with it — it would be a different architecture.

**Agent** — the dyad's diligence-and-execution member. Acts *within* the
principal's runs, never as a principal itself. Proposes, detects, gates,
frames options — never disposes. A member of the dyad, never the dyad:
the dyad strictly contains the agent (see **Dyad**, superset claim),
and the agent cannot evolve into the dyad — proposing never becomes
disposing, however capable the proposal engine grows.

**Operator** — the dyad's stakes-and-intent member, the human. Terminal
disposition authority: the agent detects, the human disposes. The operator
is the principal's *disposer*, not the principal — the one through whom the
principal's judgments are exercised.

**R** — the dyad's irreducible common ground (sanctioned gloss: *common
ground*; lexicon decision ratified 2026-09-20 — canonical 'R': "common
ground" fails L2, reading as decomposable overlap; "constitution" fails
L1/L3; "bond" fails L1; "shared context" fails L3 on the context-window
collision). The stateful relation between agent and operator,
attributable to neither member alone — it lives in the interaction
history. Constituents: shared lexicon (terms with disposed meanings),
interaction conventions (the pair's protocol), mutual models (each
modeled *as* proposer/disposer), the history of judgment (disposed
Y/N/counters as revealed taste — tunes proposals prospectively,
sharpens verdicts retrospectively), earned trust (each plays their
role). Irreducible (between, not within), accretive (earned through
episodes, never installed), normative (governs what counts as a good
proposal and a sound disposition *for this dyad*). Partially bankable:
the banked part (written conventions, DecisionRecords, disposed
vocabulary) is accountable; the unbanked part (feel, unspoken
expectation) is real but unauditable — the agent acting on unbanked R
("what the operator would want") is inference-about-intent, which the
gates constrain.

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

**Custom slash-command** — an operator-invoked command of the ambient
agent, defined in-repo (e.g. `/pb-decide`, `doc/slash-commands/`),
supported by agent recognition for the chat window. Not a platform
hook (event-driven by construction); not a Muse skill
(agent-invoked by relevance, no user-only mode) — though for
Claude Code the skill container fits
(`disable-model-invocation: true`). Runs in the ambient layer
only: never installed, never on the CLI tree, never invokable by
the automaton executor. The ambient proposes (enumerates, gates,
drafts); the operator disposes. Part of the dsys project, not the
dsys product.

**DecisionRecord** — the record of a playbook run. Writable, citable —
unlike simulations.

**Automaton** — the deterministic execution engine. Zero inference inside;
every human judgment codified beforehand as configuration; deterministic
replay mandatory. The anti-harness: where the harness is prompts and
judgment, the automaton is consequence.

**automaton-executor** — the runtime that steps the automaton plane
(DR-CMD-054, built: `lib/dsys/executor.py`): a step function — each
invocation loads state, advances to quiescence, appends events, exits.
Not a daemon, scheduler, agent, or installer. AX2's deterministic
walker. CLI: `dsys automaton init|init-flow|advance|replay` (full
profile only); spec `doc/automaton-executor-spec.md`.

**quiescence** — the state of a run with no more mechanically determined
work: no applicable steps/transitions, a parked step, or an end state.
Quiescence is sticky (I-29): once parked with no new input, an advance
appends nothing.

**wrapper** — the cron/script, outside the architecture, that owns the
schedule and invokes `automaton advance`. It drives; it never initiates
(the D4 K3 tripwire governs wrapper establishment: any initiation path
the ambient can program or trigger is K3 revived, terminally invalid).

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

**component registry** — the architecture's component set as dist
metadata (`components.json` at the dist root; 2026-09-20): each
component declares its kind (`shipped` | `specified-only`), the
profiles it ships in, and its defining artifacts. The installer
*carries* it verbatim into `var/manifest.json` — it authors nothing
and maintains nothing (F-I11); **`dsys doctor`** owns the status,
evaluating each entry against the live tree: instantiated |
specified-only | absent | mutated (F-I10). The device that keeps a
partial architecture from reporting all-green.

**release** (dsys) — a tag on `github.com/pltrinh1122/dsys-repo`
(`v<dist_version>`) published as a GitHub Release with two attached
assets: `dsys-<tag>.tar.gz` (a `git archive` of the tag — the tag *is*
the content manifest) and `dsys-<tag>.tar.gz.sha256` (the release's
own attestation of the tarball's hash). The installer's `--release`
source: it acquires the assets, verifies sha256(tarball) against the
published checksum (or a pinned `--release-sha256`), and records
`{"mode": "release", "tag", "tarball_sha256"}` in the manifest as
provenance (F-I12, F-I13). An instance installed this way is literally
an instantiation of a release version.

**dsys-mutation-playbook** — the second playbook (2026-09-19),following the pattern of the decision-making **Playbook**: DoD
conditionals, START/STOP/KEEP, own gates (G1–G4 + M1–M4), shared
DecisionRecord, single disposition machinery. Decides whether and how
to mutate the installed dsys across the rung ladder configure | role |
scenario | wrap | patch | fork. Maximum flexibility, declared mutation:
the playbook cannot prevent mutation, only declare it (I-17). Every
mutation matter states a reason, classified `accepted` (evidenced by
observations in artifacts/afferent) or `pending` (human disposition,
unevidenced); mutation without reason is not allowed (I-17, spec §10).

**factory** — the authoring-and-building system (spec 2026-09-20,
unratified): produces AutomatonRelease candidates from
operator-prompted ambient authoring. A harness-plane system with a
deterministic core (build, verify) — the governed "outside" where
step-changes are authored. Entities: FactoryProject, AuthoringTurn,
Draft, BuildRun, VerificationResult; dispositions are DecisionRecords
with playbook=factory; authoring runs are HarnessRuns under a factory
standing-policy domain (no separate run entity — F-FACT-4).

**Draft** — a candidate artifact, content-addressed, inert by
construction. Authored (the ambient proposes, the operator disposes),
never trusted, only checkable. Kinds: runbook | flow | condition |
config | scenario | policy; tagged compiled | carried | mixed.

**authorship** — the judgmental activity producing drafts: the ambient
proposes within typed request schemas, the operator disposes;
publication is the Operator's act through the ambient's hands. The
factory's judgmental side; derivation is its mechanical side.

**derivation** — pure, mechanical, semantics-preserving
transformation: compile, seal, package, hash. Crosses no
representation gap requiring judgment. The factory's BuildRun *is*
derivation — nothing more.

**implementation** — realization across a representation gap
*requiring judgment*. The standing example is our own
markdown→Python workflow: choosing schemas, validators, and refusal
cases was irreducibly judgmental, no pure function could have done
it. In factory terms an implementation is a Draft (authored), never
a BuildRun. "The build implements the spec" is loose talk;
precisely, the build *derives* the release from the draft.

**BuildRun** — the factory's recorded derivation run: draft hashes +
toolchain version → release bytes hash. A pure function (I-F2): no
inference backend, no network, no clock. Not implementation
(falsified 2026-09-20) — a run is not its product, and a pure
function cannot implement.

**runner** — the derivation executor (spec 2026-09-20, unratified):
takes a DerivationManifest and returns release bytes plus a
RunnerReceipt — purely, deterministically. Build-time; the automaton
is run-time. Takes no dispositions: zero discretion, executes
authorized derivations and attests the conditions; its refusals are
check results, not dispositions. In the trust base by declaration;
dishonesty mitigated by diversity (independent re-derivation,
receipts compared), a disposition/standing-policy choice.

**DerivationManifest** — the hermetic input closure the runner
accepts: content-addressed draft refs (+ hashes), toolchain pin
(version + hash), derivation parameters. Assembled by the factory
before submission — closure assembly is part of becoming buildable
(C-1). The cache key.

**RunnerReceipt** — the runner's own record, cited by BuildRun:
manifest hash, runner identity, pin verified, hermeticity
attestation, output bytes hash, double-derive result, pass/fail.
Separate record, separate accountability (F-RUN-1); one BuildRun may
cite several (diversity). No timestamps — the architecture has no
clock.

**DerivationCache** — content-addressed memoization: manifest hash
→ (output bytes hash, original receipt ref). Hits cite the original
receipt, never mint attestation (F-RUN-3).

**`--dev` loop** — the dyad's workflow for developing dsys itself
(software, specs, or both): mutate → install → exercise → verify →
iterate (installer-spec §12, 2026-09-20). An extension by
*specification*, not a system: specified `--dev` mode (working-tree
install, provenance recorded not refused, fast converge, offline),
iteration DoD conditionals D1–D4, manifest `source` provenance
fields. No new entities (F-DEV-1); doctor's checking machinery
mode-agnostic, baseline differs (F-DEV-2); not a run-book —
dyad-executed, DoD-gated, mechanical segments as scenarios (F-DEV-3);
disposition economy — one disposition per matter, iterations checked
not decided, fresh dispositions only at matter boundaries (F-DEV-4).

**no supervisors, only checkers** — architectural principle (named
2026-09-20, from the `developer` falsification): coordination and
assurance come from checkable artifacts and gates, never from a
watching or guiding entity. Gates, not guides; receipts, not
reports; refusals, not supervision; dispositions, not directives.
The ambient is never made faithful — unfaithful execution simply
cannot pass the gates (F-FACT-5: never trusted, only checkable;
the referee judges afterward and enforces nothing). Tripwires: this
holds while a single operator disposes and `decide` stays excluded
as an inference type; it reopens if agents ever dispose or the
operator leaves the loop.

## Retired terms

- **Bond** — retired 2026-09-20, superseded by canonical **R** (lexicon
  decision: killed as the concept's name on L1 — affective only;
  denotes trust, not lexicon, models, or judgment history). Surviving
  content (relational surplus, 1+1>2) folded into R.

- **Constitution** — retired 2026-09-20, superseded by canonical **R**
  (lexicon decision: killed on L3 — Constitutional AI collision — and
  L1 — implies writtenness, but R is partially unbanked; a
  constitution that can't be written down is a contradiction).
  Surviving content (the normative/governing aspect) folded into R's
  normative property.

- **AutomatonPlayBook** — collapsed into **Run-book** 2026-09-19. The pair
  was one entity wearing two names: the "FSM orchestrating run-books"
  distinction was unmodeled (no State/Transition entities; sequencing
  lives in Step.seq). `release_version` now lives on RunBook;
  `AutomatonRun.runbook_id` replaces `playbook_id`. The collapse also
  removes the cross-plane name collision with the decision-making
  **Playbook**, which keeps the name.

- **BuildRun ~ implementation** — falsified 2026-09-20. Category
  error (BuildRun is a process entity — a recorded run;
  implementation is an artifact or an activity) compounded by a
  purity contradiction: BuildRun is *defined* pure and
  judgment-free (I-F2), while implementation *requires* judgment
  (realization across a representation gap — our own spec→package
  history is the standing proof). Survivor: BuildRun is
  *derivation*; in the factory an implementation is a *Draft*.
