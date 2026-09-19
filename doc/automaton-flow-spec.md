# Automaton Flow Spec — FSM orchestration of run-books

Status: specified 2026-09-19, **not implemented** — awaiting Peter's approval.
Parent: the 2026-09-19 AutomatonPlayBook/RunBook collapse (glossary,
"Retired terms"). This is new machinery, not a restoration: the old
AutomatonPlayBook was an unmodeled grouping label; the flow models states
and transitions as entities so exception paths are *validatable*.

## 1. Motivation

Two automaton-plane needs have no modeled answer today:

- **Exceptions across run-books.** `AutomatonRun` anticipates run-local
  policy (retries, skip, compensation, abort — its docstring), but when a
  run-book *aborts*, nothing models what runs next. Compensation chaining
  is currently folklore.
- **Recurring operations.** E.g. an ingestion automaton pulling fresh
  updates from the world periodically: idle → timer → run → idle → ….
  No entity models the cycle.

## 2. What this is not (rejected alternative)

**Failure-pointer chaining** — `RunBook.on_failure → runbook_id`,
`RunBook.schedule → cron` — was considered and rejected. It is a
*degenerate implicit FSM*: each run-book becomes one state with one
failure edge, states and transitions unmodeled and therefore
unvalidatable. It is exactly the kind of fiction the collapse just
removed. States and transitions are entities or they are nothing.

## 3. Entities

```python
class AutomatonFlow(E):
    """[auto] Finite-state machine orchestrating run-books: states bound to
    run-books, mechanical transitions on events. Zero inference: transition
    selection is priority-ordered guard evaluation over allowlisted
    expressions, never judgment."""
    name: str
    release_version: str          # pinned to releases, like RunBook
    initial_state_id: str         # validated: a state of this flow

class FlowState(E):
    """[auto] One FSM state."""
    flow_id: str
    name: str
    kind: str                     # task | wait | end
    runbook_id: str | None        # required iff kind == task; else None
    outcome: str | None           # iff kind == end: completed | aborted
    step_policy: str | None       # required iff kind == task: abort | skip |
                                  # retry:<n> (n>=1). Explicit — no silent
                                  # default. See §4.

class FlowTransition(E):
    """[auto] One guarded edge. Transitions sharing (from_state_id, trigger)
    are a set, never a ranking: at runtime every guard is evaluated and
    exactly one true wins (see I-15). No priority field — ambiguity is a
    fault, not an ordering problem."""
    flow_id: str
    from_state_id: str
    trigger: str                  # timer | run_completed | run_aborted | external
    guard: str | None             # AST-allowlisted expr over {payload.*, run.status}
    to_state_id: str

class FlowRun(E):
    """[auto] One execution of a flow. The scheduler; per-state work runs as
    child AutomatonRuns."""
    flow_id: str
    current_state_id: str
    state: str                    # running | done | aborted

class FlowTransitionEvent(E):
    """[auto] Append-only transition log of a FlowRun — the flow-level source
    of truth. Replay re-derives states from this log; never reinvokes."""
    flow_run_id: str
    seq: int
    from_state_id: str
    to_state_id: str
    trigger: str
    payload: str                   # small, fixed-shape
```

**AutomatonRun delta** (additive, existing contract untouched):

```python
    parent_flow_run_id: str | None   # set when spawned by a FlowRun
    flow_state_id: str | None        # the state this run executed for
```

## 4. Layering: run-local vs flow-level (ratified 2026-09-19)

The crisp rule: a run-book's local policy handles what happens *inside*
one run-book execution; anything surfacing as `run_aborted` belongs to
the flow. The mechanical half, ratified via the decision-making playbook
(O2; O1 merged as tagged residual, O3 killed):

- Step-failure handling is **not a run-book property** — the schema gives
  run-books no failure-suppression machinery (Step is runbook_id/seq/expr/
  tool_id only), so record-level swallowing is already impossible. The
  only possible swallower is the executor, which is declared trust.
- The executor's step-failure behavior is therefore **part of the
  validated definition**: every task FlowState declares `step_policy`
  (`abort` | `skip` | `retry:<n>`, explicit, required). Validator checks
  presence and shape.
- Executor duty: on step failure, apply the declared policy and record
  `step_failed` + the applied action in the run log.
- **Transcript re-validation**: a `step_failed` event not followed by the
  declared policy's consequence is a violation — e.g. policy=`abort` but
  the run continued to the next step; policy=`retry:3` but a fourth
  attempt appears. Silent swallowing becomes *log-visible* deviation,
  which the referee flags. This is the most the trust model can buy:
  executor log honesty remains declared trust (same class as seq/timer
  minting) — tagged, not checkable.
- I-14 is unchanged: every policy's exhaustion surfaces as `run_aborted`,
  which I-14 already routes.

## 5. Triggers, guards, and the zero-inference argument

- Trigger kinds are a closed enum: `timer | run_completed | run_aborted |
  external`. Step-level events stay inside the run-book; the flow sees
  only run-level outcomes, timers, and injected externals.
- Guards are expressions in the existing AST-allowlisted subset, over a
  narrow context: the triggering event's `payload.*` plus `run.status`.
  No agent, no prompt, no judgment — transition selection is mechanical
  evaluation, deterministic given the log. Where several transitions share
  (from_state, trigger), every guard is evaluated as a set: exactly one
  true wins; none true falls to a guardless default if one exists;
  otherwise — or on multiple true — the trigger is unhandled (see §6).

## 6. Executor duties (declared trust, unvalidated)

The model validates flow *definitions* and run *transitions*; the executor
(the runtime driving the automaton) owns the clock and the actuation.
Declared trust, same class as `Disclosure.seq` minting (DR-5):

- mint `timer` / `external` triggers — there is **no modeled clock**,
  consistent with the DR-5 boundary (no clock/timeout in the model);
- evaluate transitions as sets per I-15 (no ranking): every guard,
  exactly-one-true wins; none-true falls to a guardless default; none-true
  with no default, or multiple-true, is unhandled;
- on step failure, apply the task state's declared `step_policy`
  (§4) and record `step_failed` + the applied action in the run log;
- on entering a task state, spawn a child `AutomatonRun` with
  `idempotency_key = f"{flow_run_id}:{state_id}:{entry_seq}"`;
- **unhandled trigger in a non-end state → abort the flow run and mint a
  Disclosure** with `kind="automaton-exception"` and a fixed template
  (flow id, run id, state, trigger — no prose, no judgment). The
  disclosure enters the DR-5 drain: the automaton's cry for help is
  routed, not lost. This is automaton→harness *signaling*, not promotion —
  disclosures request disposition; they promote nothing.

## 7. Invariants / validators

- **FK integrity** (extends the existing table): flows→releases,
  states→flows (+ runbook when task), transitions→flows/states,
  flow_runs→flows/states, transition_events→flow_runs,
  automaton_runs.parent_flow_run_id→flow_runs.
- **I-14 — flow totality** (`_flow_totality`): the mechanical form of
  "exceptions are managed." Every non-end state must route every fate the
  model admits:
  - `initial_state_id` resolves to a state of the flow;
  - `kind=task`: ≥1 transition on `run_completed` **and** ≥1 on
    `run_aborted` — failure always lands somewhere;
  - `kind=wait`: ≥1 transition on `timer` or `external`;
  - `kind=end`: no outgoing transitions; `runbook_id` is None;
    `outcome ∈ {completed, aborted}`;
  - `kind=task`: `runbook_id` required; `kind=wait`: `runbook_id` None.
- **I-15 — transition determinism, no ranking** (`_transition_determinism`):
  transitions sharing `(from_state_id, trigger)` are never ranked. Static:
  at most one guardless transition per `(from_state_id, trigger)` — two
  guardless is statically ambiguous → refusal. Runtime (executor duty,
  declared): evaluate every guard as a set; exactly one true → take it;
  none true and a guardless default exists → take it; none true and no
  default → unhandled → abort + disclosure; more than one true →
  definition fault → abort + disclosure. Determinism is preserved — the
  outcome is always defined — with no priority discrimination: ambiguity
  is a fault, not an ordering problem.
- **I-16 — flow-run closure** (`_flow_run_closure`): a FlowRun in
  `done`/`aborted` must sit in a `kind=end` state — the I-13 closure-bar
  pattern, one level up.
- **Step-policy declaration** (`_step_policy_declared`, ratified 2026-09-19): every `kind=task` FlowState declares `step_policy`
  (`abort` | `skip` | `retry:<n>`, `n>=1`); `kind=wait/end` must not
  declare one. Malformed values (e.g. `retry:0`) are refused.

Estimated golden-run growth: +8 refusal cases (bad initial state,
task state missing abort route, wait state with no timer, end state
with outgoing edge, run closed outside an end state, task state
missing step_policy, malformed retry count, ambiguous guardless
transition set).

## 8. Worked example: `ingest-world`

States: `idle` (wait), `pulling` (task, rb-ingest), `quarantine` (task,
rb-quarantine), `end_ok` (end, completed), `end_dead` (end, aborted).

| from       | trigger       | guard | to         |
|------------|---------------|-------|------------|
| idle       | timer         | —     | pulling    |
| pulling    | run_completed | —     | idle       |
| pulling    | run_aborted   | —     | quarantine |
| quarantine | run_completed | —     | idle       |
| quarantine | run_aborted   | —     | end_dead   |

Totality check: `idle` has its timer ✓; `pulling` and `quarantine`
cover completed + aborted ✓; ends have no outgoing ✓. A poisoned feed
aborts `pulling` → `quarantine` parks partial state → if quarantine
itself aborts → `end_dead`, flow run aborted. A trigger nobody routed
(e.g. `external` arriving at `pulling`) → executor aborts + mints the
`automaton-exception` disclosure → CoS drain duty.

## 9. Falsifiers

- **F-F1 (clock).** Executor-minted timers are declared trust; the model
  validates routing, not timeliness. A flow whose timer never fires is
  indistinguishable from idle — the same liveness-gap class as DR-5's
  open-but-idle governance run. No mechanical mitigation; noted, not
  solved.
- **F-F2 (layering) — resolved 2026-09-19 via the decision-making
  playbook, ratified.** The documentary rule is now mechanical (O2):
  step-failure handling lives in the validated definition as
  `FlowState.step_policy` (§4), transcript re-validated. O1 merged as the
  tagged residual (executor log honesty = declared trust); O3
  (decide nothing) killed — it contradicted the spec's §1 motivation.
  Antithesis considered: a lying executor lies in the log — rebutted as
  bounding, not killing: O2 converts silent swallowing into log-visible
  deviation, the most the trust model can buy.
- **F-F3 (priority) — resolved 2026-09-19 by direction: no priority
  discrimination.** Explicit priority *and* implicit declaration-order both
  rejected. Transitions sharing (from, trigger) are evaluated as a set
  (I-15): exactly-one-true wins; multiple-true is a definition fault →
  abort + disclosure, not a ranking problem. Static check retained: at
  most one guardless per (from, trigger).
- **F-F4 (escalation).** The automaton→harness disclosure write is an
  executor duty with a fixed template — zero inference, but a
  cross-plane write all the same. Justification: it signals, it does not
  promote; and without it the unhandled-trigger case is silent death,
  the one outcome worse than a declared-trust write.
- **F-F5 (rejected alternative).** §2's failure-pointer chaining stays
  rejected: unmodeled edges cannot satisfy I-14.

## 10. Implementation checklist (on approval)

1. schema.py: five new entities + two `AutomatonRun` fields.
2. validators.py: FK rows + `_flow_totality` (I-14) +
   `_transition_determinism` (I-15) + `_flow_run_closure` (I-16) +
   `_step_policy_declared` (ratified O2).
3. golden_run.py: `ingest-world` flow + states + transitions, one open
   FlowRun mid-cycle, five new refusal cases.
4. README + architecture doc: automaton-plane section.
5. Glossary: add AutomatonFlow, FlowState, FlowTransition, FlowRun,
   FlowTransitionEvent.
6. Re-verify (`python3 -m package`), rebuild ZIPs.
