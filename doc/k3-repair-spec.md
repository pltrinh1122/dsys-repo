# K3 conditional-design spec — the governed check-now path

**Status: INVALID (DR-CMD-040)** — the complete extension request
was found invalid 2026-09-21: its because-Z (operator urgency on
out-of-band release knowledge) was stress-tested as misplaced
(the operator already holds the information; `updater.poll_interval`
is configurable recourse; the drive is governed regardless of
trigger; the motivation was authored post-hoc after the design).
Preserved as prior art — the Harness-held trigger design, AX1/AX2,
and the check-vs-drive distinction are cited by the scenario
simulation matter (DR-CMD-041). Terminal: returns only as a new
matter with new S1–S5. **AX1** (invocation always through a
Harness, never directly to an Automaton) and **AX2** (the
Automaton driver, not the unittest suites, is a strapped Harness
instance) survive independently as the operator's disposed
architectural premises, recorded here and not invalidated with
the matter.

## Glossary

- **Automaton:** the deterministic execution plane — `AutomatonFlow`
  entities (`FlowState`/`FlowTransition`/`FlowRun`) advanced without
  inference. The updater is an automaton.
- **Harness:** the interaction plane — guided runs of turns aimed at
  definition-of-done conditions, with strap/unstrap gates (StrapGate),
  DR-1 coexistence (at most one non-closed run per (principal,
  authority-scope), ratified 2026-09-18), and authority precedence.
  (dyad-architecture-doc.)
- **Driver:** the deterministic walker that advances a flow run
  transition by transition. Today: the bespoke `drive()` in
  `core/package/updater.py` — the K3 kill's "test harness."
- **Unittest harness:** the assertion suites (`updater_golden_run.py`,
  `bridge_golden_run.py`, the package PASS/FAIL runner). Outside the
  axioms' scope by explicit scoping.
- **Strapped:** a Harness run with the strap gate engaged — fully
  deterministic, zero inference. The test configuration of a Harness.
- **External trigger:** the `external` value of the flow's trigger
  alphabet (`Trigger = Literal['timer', 'run_completed', 'run_aborted',
  'external']`, updater-spec §2) — an invocation from outside the
  timer-driven watch cycle.
- **Check-now:** an ambient-desired, out-of-cycle execution of the
  updater's `checking` state (read-only: feed poll + version compare).
- **Drive-now:** an ambient-desired execution of the mutating drive.
  **Not** part of this matter (see F3).
- **Trigger record:** the recorded input event of an external
  invocation — on the Harness run's transcript (the initiation) and on
  the flow run (the input).
- **Standing authorization:** the operator's standing disposition
  covering an action without per-instance approval (cf. installer-spec
  commit authority, ratified 2026-09-20).

## The kill restated

K3 (updater-spec §9): "updater run supports ambient agent invocation" —
**KILLED**. `idle` admits `timer` only — no `external` trigger edge. No
invocation surface exists: no CLI command, no dialog request type, no
ambient-callable entry point. The only driver is the test harness, and
the operator's counter ("the test harness is an actual `Harness`
instance") was itself falsified: `drive()` instantiates no `HarnessRun`,
uses no conditions/turns/strap-gates — a bespoke deterministic walker,
called by golden-run test code, not by the ambient agent. What survives:
the §1 exclusion of `external` stands as designed — the updater's
autonomy derives from standing policy (timer-driven), not ambient
invocation; under the authority model the ambient proposes, it does not
initiate automaton runs. Repair direction: *if* check-now is ever
wanted, it needs an `external` edge on `idle` plus a governed initiation
path; whether it should exist at all is a disposition.

## Disposed premises (axioms)

- **AX1 — invocation is always through a `Harness`, never directly to
  an `Automaton`.** Disposed 2026-09-21. System-wide architectural
  invariant (candidate for its own record): the Harness is the sole
  invocation plane; the automaton exposes trigger edges but no
  ambient-callable entry point.
- **AX2 — an `Automaton` driver used in testing is an instance of a
  `Harness`.** Disposed 2026-09-21, scoped: covers the *driver* (the
  deterministic walker), **not** the unittest harness (the assertion
  suites, which stay outside, asserting on transcripts). The K3 kill's
  falsified counter becomes a requirement: the driver is a strapped
  Harness instance — deterministic, zero inference, conditions as
  definition-of-done, DR-1 and transcript machinery for free.

## Motivation (S5 — because Z)

The updater polls on its fixed `updater.poll_interval`; when the
operator learns of a release out-of-band — a security advisory, a
peer notice — there is no governed way to check *now*. The only
paths are waiting for the timer or manual intervention outside any
governed invocation plane. Check-now closes that gap: operator
urgency, expressed to the ambient, shortens the loop through the
Harness-held trigger instead of around it.

*If* disposed, dsys should gain a Harness-held check-now path such
that an out-of-cycle check runs without touching the drive
authority, because the operator currently has no governed way to
check immediately on learning of a release out-of-band.

## Narrowed claim (conditional)

*If* an ambient-invoked check-now path is disposed to exist, it is
governed: (1) an `external` trigger edge `idle → checking`, **Harness-held**
— the Harness is the sole invoker; (2) the Harness fires the trigger
only when its conditions are satisfied under authority the model
permits; (3) the trigger is a recorded input event on both transcripts,
so R1 replay is preserved by re-validation, never re-invocation. The
check-vs-drive distinction is load-bearing: the Harness may initiate
*observation*; the policy gate remains the sole authority that can
initiate the mutating drive.

## Scope (dual, decomposed at START — conjunctive adoption)

- **Runtime scope:** the flow table gains the `external` edge (trigger
  alphabet extends; I-14 totality over the extended alphabet); the
  initiation authority rule; the driver-as-Harness-instance migration.
- **Package scope:** the trigger record, golden-run cases (including a
  strapped-Harness driver), validators for the new invariants.
- Conjunctive adoption.

## Decisions

- **D1 — the `external` edge lands on `checking`, never `driving`.**
  `idle --external--> checking`: the invoked party is the read-only
  feed poll + version compare. The mutating drive stays behind the
  policy gate (`gate --run_completed[decision=='drive']--> driving`),
  which answers to standing policy, not to the invoker. An
  ambient/Harness-desired *drive* would need its own disposition; it is
  not this matter. *Recommendation; disposition open.*
- **D2 — the edge is Harness-held (AX1).** The automaton declares the
  trigger in its alphabet and the edge in its table; the Harness holds
  the only legitimate trigger source. There is no ambient-callable
  entry point on the driver — a direct ambient→automaton invocation is
  not routable, by axiom, not by firewall. Initiation authority: the
  Harness fires only when its check-now condition is satisfied. Whether
  that condition rests on standing authorization (recommended:
  standing authorization explicitly covering ambient-initiated checks,
  named at disposition) or a per-initiation propose→disposition cycle is
  disposition-open. Non-rubber-stamp requirement: the check-now
  condition cannot be satisfied by ambient prompt alone. A Harness
  that fires on the ambient's bare request is a compliant-but-hollow
  pass-through and circumvents AX1 (see F1). The "prompt suffices"
  option is refused in this spec — it is not disposition-open.
- **D3 — the driver is a strapped Harness instance (AX2, scoped).** The
  deterministic walker becomes a Harness run with the strap gate
  engaged: zero inference, conditions as definition-of-done (e.g.
  "drive reached a terminal state," "transcript validates against the
  golden"), DR-1 coexistence, transcript machinery. The unittest suites
  (`updater_golden_run.py` et al.) are unchanged in kind — they drive
  the Harness-instance driver and assert on transcripts. Production and
  test drivers become the same machinery, differing only in strap
  configuration and conditions: one invocation plane, no test-double
  divergence.
- **D4 — the trigger record is dual, and replay has two modes.** The
  Harness run's transcript records the initiation (which principal,
  which condition fired, under what authorization); the flow run
  records the `external` trigger as a recorded input event. Replay is
  then mode-separated, per the architecture's foundational premise
  that inference outputs cannot be reproduced by re-running: the
  Harness transcript re-validates **as a record** (it happened as
  recorded — its LLM turns are not re-executed); the automaton
  replays **deterministically from recorded inputs** (same trigger
  record in, same transitions out). For the automaton side to be
  deterministic, the trigger record must capture every
  non-determinism source as data: principal, condition,
  authorization basis, and timestamp (wall-clock time of the request
  is an input, not a recomputation). Replay never re-invokes.
  (R1 preserved by construction.)
- **D5 — no bypass of the policy gate.** A check-now that surfaces a
  newer version under `policy=auto` still passes through `gate`:
  the *policy* drives, not the invoker. A check-now under
  `policy=notify` surfaces and returns to `idle`. Composes with K1: a
  policy-driven drive commits via the K1 writer on the normal path.
- **D6 — rate/abuse is standing policy's answer.** The timer has
  `updater.poll_interval`; the external path needs the same kind of
  bound — recommended: a check-now cooldown condition on the Harness
  (existing machinery, not new). *Recommendation; disposition open.*
- **D7 — existential flag (explicit).** Whether check-now exists at all
  is the Operator's disposition; the current answer is no, and this
  spec does not change it. Everything above is the governed shape *if*
  disposed into existence.

## Falsification

- **F1 — "the ambient should invoke the automaton directly."** Killed by
  AX1: direct invocation bypasses DR-1, strap gates, conditions, and
  the authority model ("ambient proposes; operator disposes"). The
  axiom is not a firewall rule around a real door — there is no door.
- **F2 — "the unittest suites must become Harness instances too."**
  Killed by the explicit scoping: suites stay outside, asserting. Making
  the assertions themselves Harness runs would tangle the verification
  plane with the invocation plane for no gain.
- **F3 — "`external` should reach `driving` (drive-now)."** Killed: an
  invoker-initiated mutating drive breaks the authority model no matter
  which plane carries it. The policy gate is the sole drive authority;
  drive-now would need its own governed matter and its own disposition.
- **F4 — "the external trigger breaks deterministic replay."** Killed by
  construction (D4): the trigger is a recorded input event on both
  transcripts; replay re-validates, never re-invokes. An unrecorded
  trigger would break R1 — which is why D4 is a decision, not an
  observation.

## Acceptance (checkable sequences)

1. Flow table: `idle --external--> checking` present; `_flow_totality`
   passes over the extended alphabet (`timer`, `run_completed`,
   `run_aborted`, `external`); `_transition_determinism` holds
   (`timer` and `external` out of `idle` are distinct triggers, no
   guard overlap).
2. No ambient-callable entry point: the driver's trigger source is
   exclusively a Harness run (fixture: the World records trigger
   provenance; a direct ambient trigger has no route — acceptance of
   AX1/F1).
3. A Harness-fired check-now under `policy=notify` with a newer version
   surfaces the candidate and returns to `idle` — no drive
   (acceptance of D1/D5: observation only).
4. A Harness-fired check-now under `policy=auto` with a newer version
   drives through the policy gate (acceptance of D5: the *policy*
   drives, not the invoker).
5. Replay: a drive initiated via `external` replays byte-equal against
   the recorded transcripts including the trigger record
   (acceptance of D4/F4).
6. The driver runs strapped: the Harness-instance driver performs zero
   inference across a golden run (acceptance of D3/AX2).
7. Two check-now triggers inside the cooldown → the second is refused
   or deferred by the Harness condition (acceptance of D6).

## Open questions (G6)

- Q1: existential — should check-now exist at all? (Operator's; the
  current answer is no.)
- Q2: the exact Harness condition set governing the check-now trigger
  (build detail; includes the D2 authority recommendation).
- Q3: the trigger record's canonical form (build detail; composes with
  K1's payload canonicalization — one canonicalization discipline,
  not two).
- Q4: the production Harness host — which Harness run fires the
  trigger in a deployed instance, and how the ambient reaches *it*
  (composes with the dialog-protocol exploration, §15.8 initiation
  design as prior art, not standing machinery).
