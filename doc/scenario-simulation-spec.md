# Scenario-simulation spec

**Status: ADOPTED (DR-CMD-041)** — uncommitted, not built.
Adopted 2026-09-21 on the remediated spec (draft verdict: adopt;
14/14 conditionals hold; both evaluation conditions remediated
in-spec — D9 driver-built provisioning, D1 seed-not-confine rule
+ retroactive briefs).

**Matter:** *scenario simulation* (ambient-authored) — live
expansion proposal, re-entered at START narrowed 2026-09-21 after
two falsification rounds. The original matter ("ambient-driven
simulation") was falsified: ambient-initiated *driving* reintroduced
K3's killed F1 (ambient-initiated automaton execution) and conflated
authorship with execution. The survivor, evaluated 2026-09-21
(`refuse (not-ready)` in the staging sense — A1 holds, fourteen
conditionals unevaluated), is specified here against that
evaluation's punchlist. The evaluation's two conditions were
remediated in-spec 2026-09-21 (D9: driver-built provisioning;
D1: seed-not-confine rule + retroactive briefs) — draft verdict
on the remediated spec: **adopt**. Disposition, when it comes, takes the next
DecisionRecord identifier after K1's reserved DR-CMD-039 and the
pending K3 invalidity record.

**Claim (S1, narrowed):** dsys should gain ambient-authored
scenario simulations such that the ambient authors scenario specs
from falsification-derived briefs, the strapped driver executes them
against sandbox copies, and scenarios meeting a coverage criterion
harden into regression cases only on operator disposition — because
the ambient's different adversarial priors discover scenarios the
operator wouldn't have enumerated, and fixed golden runs can't cover
what was never imagined.

**Scope (S2):** dual, decomposed, conjunctive. *Runtime:* two new
invariants — simulation containment (I-21) and transcript separation
(I-22). No new invocation authority: the ambient never initiates
execution. *Package:* the authorship pipeline (briefs, scenario
specs), sandbox-copy provisioning, the hardening pipeline
(coverage predicate I-23, operator gate I-24), golden-run extension.

**Proposer (S3):** the operator. The proposer≠disposer separation
binds the ambient, not the operator; the playbook's evaluation runs
undiminished.

**Prior art (S4):** the scenario concept (cli-interface-spec.md
§3.4.1); the golden runs (static scenario execution); the K-series
falsification record (K1/K2/K3 kills — the risk map briefs are
drawn from); K3's invalidated design (reusable mechanism, void
motivation); the property-based generator split (F-A: systematic
input-space coverage, complementary, not competing).

**Motivation (S5, refined):** the value is *discovery*, not volume.
The operator hand-authors fixture variations; unenumerated-but-
imaginable scenarios go untested. The ambient's different
adversarial priors find cases the operator wouldn't have thought
of. The coverage criterion keeps the review set small — the
operator's binding constraint is attention, not time.

## 0. Glossary

- **Scenario:** a declarative exercise specification — actors,
  turns, inputs, expectations (`{actor, input, expect}`). Says
  what should happen and what counts as passing. Never executes
  itself; a driver interprets it. (cli-interface-spec.md §3.4.1.)
- **Scenario spec:** a scenario as data (YAML declaration
  interpreted by the driver — the §3.4.1 phase-2 target). The
  unit the ambient authors and the driver executes.
- **Brief (falsification-derived brief):** a written charge for
  scenario authorship: `{source_falsification, survivor_under_test,
  risk_question, budget}`. Drawn from the falsification record
  (kills and their falsifying observations). Briefs *seed* the
  ambient's imagination; they do not confine it (see G6 Q1).
- **Hardening:** promoting an executed scenario into the
  regression suite: the scenario file is placed with the
  standing scenarios and a golden-run case is added. Hardening
  is gated (D5) and measured (D4).
- **Coverage criterion:** the predicate a candidate scenario
  must satisfy to be hardenable: it exercises at least one
  (transition, guard-outcome) pair of the target flow's
  transition table not covered by the existing suite, or it
  exhibits a real failure (bug-finding alternative). Enforced
  by I-23.
- **Sandbox copy:** a provisioned copy of the installation's
  declared state (from the installation manifest — D9), rooted
  under a sandbox path, never the live installation
  (`~/dsys-inst`). Simulations execute against sandbox copies
  only.
- **Simulation transcript:** the run record of a scenario
  execution against a sandbox copy, marked `kind: simulation`
  at construction. Ontologically separate from production
  records (D7, I-22).
- **Strapped driver:** the existing deterministic scenario
  driver (`dsys scenario run`), operating under its strap:
  mediated turns, `referee validate` judging, transcript
  re-validation for replay. No new driver is built.
- **Operator gate:** the hardening authorization: a scenario
  hardens only on operator disposition — a per-scenario
  DecisionRecord or a standing disposition covering narrow
  scenario classes. The ambient proposes (scenario file +
  coverage report); the operator disposes.
- **Discovery (vs volume):** the matter's value theory.
  Volume (many scenarios) is not the good; discovery (scenarios
  the operator wouldn't have enumerated) is. The coverage
  criterion is the instrument: it selects for novelty, which
  keeps the operator's review load small.

## Decisions

- **D1 — briefs derive from the falsification record.** Every
  authorship run is charged by one or more briefs. A brief cites
  the falsification it derives from (e.g. "K2's F-B: unwritable
  accretion path — does the survivor hold under
  permission-flapping mid-drive?"), names the survivor under
  test, states the risk question, and carries a budget (max
  scenarios authored per brief — bounds the attention cost of
  authoring-without-yield; see F-S1). Free exploration is not a
  mode: unbriefed authorship is not hardened, however
  interesting the transcript. **Seed-not-confine rule:** a brief
  may name the survivor and the risk question, never the
  expected transcript — the brief seeds the ambient's
  imagination; it does not confine it to re-deriving the
  operator's scenarios. **Retroactive briefs:** an off-brief
  discovery may still harden iff the operator writes a
  retroactive brief citing the discovery; the brief then enters
  the record like any other, and the pipeline proceeds
  unchanged.
- **D2 — authorship is inference-outside-execution.** The
  ambient authors scenario specs as discrete step-changes
  (data files, no executable content — scripts are demoted to
  step-implementation kind per §3.4.1 and are never authored
  as scenarios). Agent outputs are parsed, never trusted
  (§3.4.1). Authorship may be wrong (bug-compatible scenarios,
  F-A1): wrongness is *useful* — a scenario asserting wrong
  behavior fails on execution, surfacing the misconception for
  adjudication — provided it never enters the suite
  unexamined (D5). No new network touch: authorship may consult
  the ambient's context, but scenario specs are offline data and
  execution is hermetic per the existing driver (P2 holds by
  construction — nothing in this spec adds a network reach).
- **D3 — execution is the existing strapped driver.** `dsys
  scenario run SPEC --transcript FILE` against a sandbox copy.
  No new execution machinery, no new invocation authority, no
  ambient-initiated runs. P1: no new CLI command for execution;
  the surface already exists and conforms to DR-CLI-001.
  Hardening's mechanical step (file placement + golden-run case)
  is an operator act, not a command, in v1.
- **D4 — the coverage criterion is a predicate over the flow
  table.** I-23: `covers_new_pair(scenario, suite, flow_table)`
  is true iff the scenario's transcript exercises at least one
  (transition, guard-outcome) pair absent from the suite's
  covered set, or the transcript exhibits a real failure
  (nontrivial exit, validator violation — the bug-finding
  alternative). Guard-outcomes include refusals: a scenario
  that drives the policy-gate to `defer`, or the installer to
  the K2 accretion refusal, covers pairs the happy path never
  touches. Coverage is measured, not judged.
- **D5 — hardening requires operator disposition.** I-24: a
  scenario enters the regression suite only with a cited
  disposition — per-scenario DecisionRecord, or a standing
  disposition covering a *narrow* scenario class (F-S2: the
  K3 non-rubber-stamp lesson applies; a standing "harden
  anything covering" is a rubber stamp and is refused).
  Sequence per hardening: (1) I-23 passes, (2) disposition
  recorded citing the coverage report, (3) spec file placed,
  (4) golden-run case added and full chain PASS.
- **D6 — containment is path discipline + validator.** I-21:
  every World constructed for scenario execution asserts
  `install_home` is rooted under the sandbox root and names
  neither the live installation path nor any path outside it.
  Violation → the run is refused before execution. No
  OS-level sandboxing is required (the installer-spec's "no
  Docker v1" non-goal stands): the only mutating tool takes an
  explicit path argument, so path discipline is sufficient and
  checkable.
- **D7 — transcripts are ontologically separated.** Every
  simulation transcript is constructed with `kind: simulation`.
  I-22: production record writers (K1's accretion writer,
  DR-5 disclosure views) reject `kind: simulation` transcripts;
  replay corpora never ingest them. Separation is structural
  (a kind the production writers cannot accept), not a marking
  convention the writers could ignore.
- **D8 — generator composes, ambient imagines.** Property-based
  generation covers the input space (systematic, seeded,
  reproducible); ambient authorship covers adversarial
  imagination (briefed, non-reproducible, human-gated). Both
  feed the same hardening pipeline (D4, D5). Neither replaces
  the other; the claim's "such that" is satisfied by the pair.
- **D9 — sandboxes are provisioned from the manifest, by the
  driver.** A sandbox copy is derived from the live
  installation's installation manifest (declared state), not
  hand-built, and the derivation is a **driver step**: the
  strapped driver provisions the sandbox before executing the
  scenario, under the same strap as every other turn
  (mediated, transcript-recorded). No `install.sh` change —
  P4 holds by absence: the installer surface, `doctor`, and
  the idempotency sequences are untouched, because
  provisioning lives in the driver, not the installer.
  Rationale (F-S3): hand-built sandboxes drift from the
  installation, and simulations of a drifted copy lie about
  the installation. Manifest-derived, driver-provisioned
  copies make "simulation testing *of the installation*" a
  true statement.

## Validators (R3)

I-21 through I-24, predicates not procedures. Numbering is
provisional pending K1's disposition (DR-CMD-039), which
proposed I-18–I-20.

- **I-21 — simulation-containment:** no scenario-execution
  World names the live installation path or any path outside
  the sandbox root.
- **I-22 — transcript-separation:** no `kind: simulation`
  transcript is acceptable to any production record writer or
  replay corpus.
- **I-23 — coverage-criterion:** `covers_new_pair` as in D4.
- **I-24 — hardening-gate:** suite membership implies a cited
  operator disposition.

## Replay story (R1)

Scenario specs are data; the strapped driver is deterministic;
replay is transcript re-validation, never behavior re-execution
(§3.4.1). Simulation transcripts re-validate identically; their
`kind: simulation` marking is part of the transcript and is
itself re-validated. Existing transcripts are unaffected: no
production transcript changes kind, and I-22 bars ingestion.

## Trust declarations (R5)

- The ambient's priors are **untrusted**: authorship is
  valuable *because* the priors differ, and dangerous for the
  same reason — hence the coverage predicate (D4) and the
  operator gate (D5). Neither is waivable.
- Sandbox copies are **non-production** by construction
  (D9) and by enforcement (I-21, I-22). A simulation result
  warrants no production action.
- The strapped driver is **trusted** standing machinery; this
  spec builds no new executor.

## Falsifications of this design

- **F-S1 — "coverage-measured hardening converges."**
  Falsifier: briefs whose authored scenarios never increase
  coverage — the pipeline authorizes attention with no yield.
  *Answered:* briefs carry budgets (D1); zero-yield briefs
  retire the brief, not the pipeline. Attention is bounded by
  construction.
- **F-S2 — "the operator gate doesn't rubber-stamp."**
  Falsifier: a standing disposition so broad ("harden all
  covering scenarios") that D5 is vacuous. *Answered:* standing
  classes must be narrow; per-scenario DecisionRecords are the
  default. A gate that approves everything is not a gate.
- **F-S3 — "sandbox simulations are faithful."** Falsifier: a
  sandbox whose declared state has drifted from the live
  installation, producing results that misdescribe the
  installation. *Answered:* D9 (manifest-derived provisioning).
  Residual: manifest fidelity itself — the manifest must
  actually describe the installation (installer-spec's problem,
  cited not solved here).

## Acceptances (A5 — checkable sequences)

1. **End-to-end hardening:** brief from K2's F-B (unwritable
   accretion) → ambient authors scenario spec → `dsys scenario
   run` against a manifest-provisioned sandbox → transcript
   covers a new (transition, guard-outcome) pair (I-23 PASS) →
   operator disposition recorded → spec placed, golden-run
   case added → full chain PASS, 0 violations.
2. **Containment:** construct a scenario World with
   `install_home=~/dsys-inst` → I-21 violation → run refused
   before execution, nothing mutated.
3. **Separation:** present a `kind: simulation` transcript to
   the accretion writer → rejected (I-22); absent from
   disclosure views.
4. **Gate:** scenario passing I-23 with no cited disposition
   → hardening refused (I-24); suite unchanged.
5. **Anti-flood:** briefs rephrasing existing golden-run cases
   → I-23 fails on all → nothing hardened, attention spent
   only on the coverage report.
6. **Refusal coverage:** a scenario driving the K2 accretion
   refusal path hardens (refusal pairs count) and its golden-run
   case asserts the refusal.

## X4 deltas (prior-art non-duplication)

- **vs golden runs:** delta = the authorship source (ambient,
  briefed) + the coverage gate (I-23) + the operator gate
  (I-24). The golden run is the *executor and suite*; this
  matter is the *pipeline that feeds it*.
- **vs §3.4.1 scenarios:** delta = the pipeline around the
  runner (briefs → authorship → coverage → gate → hardening).
  The runner is used, not duplicated.
- **vs the property-based generator:** complementary (D8),
  not overlapping — input space vs adversarial imagination,
  same hardening pipeline.

## G6 — open questions

- **Q1:** Standing-disposition classes: what narrow classes
  are safe (e.g. "refusal-path scenarios for flows with a
  published transition table")? Enumerate before first use.
- **Q2:** Manifest fidelity: who asserts the installation
  manifest describes the live installation, and how often?
  (Upstream of D9; cite installer-spec.)
- **Q3:** Does the coverage criterion generalize beyond flow
  transition tables — to run-books, harness runs? Or is
  scenario simulation flow-scoped in v1?

(Former Q1 — the brief seed-vs-confine line — resolved
2026-09-21 by D1's seed-not-confine rule plus retroactive
briefs.)
