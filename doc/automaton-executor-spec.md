# Automaton Executor Spec — the runtime that steps the automaton plane

Status: specified 2026-09-20, **not implemented** — awaiting Peter's approval.
Parents: `automaton-flow-spec.md` §6 (executor duties), component registry
(`automaton-executor`: "no executor spec yet" — this is that spec).

## 1. What it is

The automaton-executor is the runtime that *steps* the automaton plane —
nothing more. It advances `AutomatonRun`s through their run-books and
drives `FlowRun`s through their transitions, appending to the append-only
event logs. It is a **step function, not a server**: each invocation loads
state, advances as far as mechanically determined, appends events, exits.
There is no daemon mode, no loop, no "waiting for inputs" — the loop, if
any, belongs to the wrapper (cron/script, outside the architecture), which
owns the schedule. The executor owns *trigger validation*.

This is the "advances" in "dsys issues, ingests, advances."

## 2. What it is not (rejected alternatives)

- **Not a daemon / server loop.** The model has no clock and no live
  loops (DR-5). A long-running executor would smuggle both in through the
  runtime. Periodicity comes from the wrapper invoking `advance`; the
  executor processes what it is given.
- **Not a scheduler.** It never decides *when* to act. `--trigger timer`
  is accepted and validated, never scheduled.
- **Not an agent.** It never prompts, never judges, never translates
  agent output into automaton-plane records (phase-2 driver rule). Its
  only record inputs are init args, typed `--external` payloads, and tool
  results — recorded as bytes, never adjudicated.
- **Not the installer.** `install.sh` is a script that consumes releases;
  the executor steps run-books. Separate mechanisms (falsified
  2026-09-20: "the installer automaton" does not exist).

## 3. The clock boundary (reconciling flow-spec §6 with DR-5)

Flow-spec §6 says the executor "owns the clock and the actuation"; DR-5
says the model has no clock. Both hold, at different layers:

- The **model** has no clock: guards evaluate over trigger payloads and
  `run.status` only (I-15's narrow context). No wall-clock value may
  enter guard evaluation or replay.
- The **executor** is the declared-trust boundary where schedule-derived
  triggers enter: the wrapper (cron) decides *when*; the executor
  validates the trigger against the definition and mints the event.
  Timer *timeliness* is declared trust (F-F1's class) — the model
  validates routing, never punctuality.
- Invoking `--trigger timer` in a state with no timer transition is an
  **unhandled trigger** → abort + fixed-template disclosure (§7), exactly
  as if the model had received a trigger nobody routed. The executor does
  not "know" whether the timer was real.

## 4. Commands

Full profile only; base refuses with exit 1 naming the component
(same pattern as `session`).

```
dsys automaton init --runbook <id> [--ctx JSON]
                    [--on-step-failure abort|skip|retry:<n>]
dsys automaton init-flow --flow <id>
dsys automaton advance --run <id> [--external KIND --payload JSON]
                       [--max-steps N]
dsys automaton advance --flow-run <id> [--trigger timer|external
                       --payload JSON] [--max-steps N]
dsys automaton replay --run <id>
```

- `init` creates an `AutomatonRun` (`state=open`) and appends
  `run_created` (seq 0) carrying the immutable cfg: `runbook_id`,
  pinned `release_version`, failure policy (default `abort`), initial
  ctx. Init is **idempotent**: the idempotency key is the content hash of
  `(runbook_id, canonical cfg)` — re-init with identical cfg returns the
  existing open run instead of duplicating. (Deterministic idempotency
  keys, per the `AutomatonRun` contract.)
- `init-flow` creates a `FlowRun` at the flow's `initial_state_id`
  (`state=running`).
- `advance` steps to **quiescence**: no more applicable steps /
  transitions, a parked step, or an end state — bounded by `--max-steps`
  (default 1000, a resource bound, not semantics). Advancing a closed run
  is a no-op (exit 0, `closed:true`).
- `replay` re-validates a run's transcript (§9). Never reinvokes tools.

**Deferred (2026-09-20): single-step debugging.** A `step` operation
(exactly one mechanical step, same events as `advance`,
log-indistinguishable) was designed and then deferred: the debugging
need is not yet clear, and the instrumentation log — the append-only
event log plus `replay` — may be sufficient. If the log proves
insufficient, the pre-designed shape is: run-level only (a flow "step"
is ambiguous), `step` on a quiescent run appends nothing.

**Quiescence is sticky.** If the last event is `run_completed`,
`run_aborted`, or `step_parked` and no input arrived after it,
`advance` is a no-op — repeated invocation appends no duplicate
parked/terminal events.

**Driving discipline** (convention, not mechanism). Production flows
are wrapper-driven (cron) through `advance`; an operator-invoked
`advance` is intervention. The executor cannot tell the two apart —
the distinction lives in who invokes — and production must never
depend on hand-driving: hand-driven progress inherits the
operator-attention liveness hazard.

Exit codes reuse the CLI contract: `0` ok; `1` usage / config / tool
failure / lease busy; `5` replay violations. JSON envelope on stdout:
`{run_id, state, steps_advanced, events_appended, closed}`.

## 5. Run-level step semantics

The event log is the source of truth. The executor folds events from
seq 0 to reconstruct ctx (`run_created` carries initial ctx;
`step_completed` carries `ctx_delta`; `event_injected` carries external
payloads). Guards are the AST-allowlisted Python-subset expressions,
compiled once per `(runbook_id, release_version)` and cached in-process.
For the next uncompleted step (steps ordered by `seq`):

| Case | Executor action | Event |
|------|-----------------|-------|
| guard true | append `step_started`; invoke tool; on ok append `step_completed` (+ `ctx_delta`), continue | `step_started`, `step_completed` |
| guard false | append `step_parked`; **stop** — the run waits; a later `--external` may change ctx and unpark it | `step_parked` |
| tool fails, standalone run | apply the run's declared failure policy (§6), append `step_failed` + the consequence | `step_failed`, then `step_skipped` / retry / `run_aborted` |
| tool fails, flow child | apply the task state's `step_policy` (ratified O2) | same, per policy |
| no steps remain | append `run_completed` | `run_completed` |
| run-book has zero steps | `run_completed` immediately (vacuous) | `run_completed` |

A false guard is **not** a failure — it is "not yet." Failure is only
what the policy machinery handles. Run `state` is constrained to
`open | completed | aborted` (the schema's `state: str`, narrowed here).

## 6. Failure policies

- **Standalone run:** declared at `init` via `--on-step-failure`
  (`abort | skip | retry:<n>`, `n>=1`; default `abort`), recorded in the
  immutable cfg. This is the run-local policy the `AutomatonRun`
  docstring anticipates ("retries, skip, compensation, abort").
- **Flow child run:** the task `FlowState`'s `step_policy` governs
  (ratified O2); the init-time flag is ignored for flow children and
  must not be set for them.
- **Transcript re-validation** (flow-spec §4): a `step_failed` not
  followed by its policy's consequence is a violation (policy=`abort`
  but the run continued; `retry:3` but a fourth attempt appears).
  Silent swallowing becomes log-visible deviation.
- **Compensation** is a modeling matter, not executor magic: the
  executor provides skip/retry/abort; compensation chains are modeled as
  flows (flow-spec §1's motivation — folklore made validatable).

## 7. Flow-level driving

`advance --flow-run` processes one invocation as: accept an optional
`--trigger timer|external` (validated §3); then, until quiescence:

- In a `wait` state with no trigger supplied: stop (the flow waits; the
  wrapper will return with a trigger).
- On trigger: evaluate all transitions sharing `(from_state, trigger)`
  **as a set** (I-15): exactly one guard true → take it; none true with
  a guardless default → take it; none true without default, or multiple
  true → **unhandled** → abort the flow run and mint a `Disclosure`
  (`kind="automaton-exception"`, fixed template: flow id, run id,
  state, trigger — no prose), routed to the DR-5 drain. Signaling, not
  promotion (F-F4).
- On entering a `task` state: spawn a child `AutomatonRun` with
  `idempotency_key = f"{flow_run_id}:{state_id}:{entry_seq}"`
  (flow-spec §6), `parent_flow_run_id` / `flow_state_id` set, then
  advance it per §5. On child `completed`/`aborted`, feed
  `run_completed`/`run_aborted` back as the next trigger (these two
  triggers are executor-minted, never CLI-supplied).
- On entering an `end` state: close the flow run (`done` on
  `outcome=completed`, `aborted` on `outcome=aborted`) per I-16.
- Append every transition as a `FlowTransitionEvent` (gapless `seq`).

## 8. Tool contract

- Tools live in the dist: `lib/automaton/tools/`, mapped by tool name
  (the `Tool` entity's `name`). Signature:
  `run(ctx: dict) -> {"ok": bool, "result": <json>, "ctx_delta": <json>}`.
- **Deterministic** (declared; F-E2) and **idempotent** (required;
  crash recovery is at-least-once — F-E3). ctx and deltas stay small,
  JSON-shaped (the `FlowTransitionEvent.payload` discipline, extended).
- **Hermetic**: no network in the executor or tools (extends the
  per-command hermeticity story). Tools run in-process.
- Tools are **dist-shipped and release-pinned** (`runbook_id` +
  `release_version` recorded at init). A custom tool is a fork matter
  (dsys-mutation-playbook), not an executor option.

## 9. Replay (the determinism story)

`automaton replay --run <id>` re-folds the event log from seq 0 and
re-checks, **never reinvoking tools** ("transcript re-validation, not
behavior replay"):

- `seq` gapless from 0; every event's `run_id` matches;
- each step's guard re-evaluated against the ctx folded from the event
  prefix — the recorded outcome must match;
- every `step_failed` followed by its declared policy's consequence (§6);
- closure consistent: `run_completed` only after the last step's
  `step_completed`; `run_aborted` only via the abort policy.

Exit `0` = transcript valid; `5` = violations (referee's code). Replay
checks the *record*; it cannot detect a tool that lied deterministically
(F-E1 — declared trust, same class as `Disclosure.seq` minting).

## 10. Concurrency

One rule: **single writer per run per invocation**, enforced
ephemerally. The executor takes an OS file lock on the state file for
the duration of `advance`; a second concurrent invoker fails fast with
exit 1 (`automaton-lease-busy`). No lease records — the lease model was
superseded (session-sync); the lock is held only while stepping.

## 11. What the executor never does

- No inference, no prompts, no LLM calls — zero-inference posture is
  structural (there is no code path for it), not a policy.
- No network (hermetic, §8).
- No daemon, no scheduling, no wall-clock inside guards or replay (§3).
- No agent-output → automaton-plane record translation (phase-2 driver
  rule) — `--external` payloads are recorded as bytes; meaning is the
  wrapper's/operator's business (write-gated authority stays at the
  harness plane).
- No disclosures except the fixed-template `automaton-exception` (§7).
- No auto-merge, no conflict resolution (I-15's spirit, one level up).
- No node-addressed invocation: `{automaton-executor}.advance` is
  notation for `dsys automaton advance`, not a node address space —
  the CLI offers no automaton-plane addressees (2026-09-19
  falsification stands).
- No freeform input: triggers are the closed enum, payloads are JSON;
  `{input}` as uninterpreted prose would either smuggle inference in
  or collapse the trigger taxonomy I-14 routing depends on.

## 12. Falsifiers (pre-registered)

- **F-E1 (log honesty).** A lying executor writes a clean log over a
  dirty execution. Declared trust — replay bounds it to log-visible
  deviation (same class as flow-spec's O1 residual and DR-5's seq
  minting). No mechanical mitigation; tagged, not solved.
- **F-E2 (tool determinism).** A nondeterministic tool breaks replay
  silently: re-folding yields a different guard outcome than recorded.
  Mitigation is supply-chain, not runtime: tools are dist-shipped and
  release-pinned; custom tools are a fork matter.
- **F-E3 (at-least-once).** Crash between `step_started` and
  `step_completed` → the next advance re-invokes the tool. Hence the
  idempotency requirement in the tool contract (§8) — stated, not
  enforced.
- **F-E4 (quiescence bound).** `--max-steps` tripping is a resource
  stop, not a semantic one: the advance exits nonzero having recorded
  nothing semantic. A definition that cannot quiesce within the bound
  (e.g. a wait-less task cycle) is a definition smell; I-14 totality
  does not bound cycles, and this spec does not add that check.
- **F-E5 (trigger authenticity).** The executor cannot distinguish a
  genuine schedule-derived timer from a hand-invoked `--trigger timer`.
  Declared trust (F-F1's class): the wrapper owns authenticity.

## 13. Definition of done (this design)

- [ ] D1: every flow-spec §6 executor duty maps to a command/behavior
  in §§4–7 (clock → §3; set evaluation → §7; step_policy → §6;
  child spawn + idempotency key → §7; unhandled → disclosure → §7).
- [ ] D2: §5's table is total over {guard true/false} × {tool ok/fail}
  × {standalone, flow-child} — no undefined case.
- [ ] D3: the clock boundary (§3) keeps wall-clock out of guards and
  replay; timer timeliness is explicitly declared trust.
- [ ] D4: replay (§9) is specified without tool reinvocation.
- [ ] D5: crash recovery is at-least-once, with the tool-idempotency
  contract stated (§8, F-E3).
- [ ] D6: the component registry points at this spec; kind stays
  `specified-only` — designed is not shipped.
- [ ] D7: the `step` deferral (§4) is recorded with its reason; the
  access shapes rejected in §11 (node addressing, freeform input) cite
  their reasons.

## 14. Implementation checklist (on approval)

1. `lib/automaton/executor.py`: fold, guard eval (allowlisted AST,
   compiled once), step loop, flow driver, trigger validation.
2. `lib/automaton/tools/`: registry + reference tools.
3. CLI: `automaton init|init-flow|advance|replay` (full profile;
   base refuses); JSON envelopes; exit codes per §4.
4. Validators: narrow `AutomatonRun.state` to `open|completed|aborted`;
   transcript re-validation checks (§6, §9) as referee-callable
   functions.
5. Golden run: fixture run advanced by the executor in a scenario;
   refusal cases (bad policy value, guardless ambiguity at runtime,
   max-steps trip, lease busy).
6. component registry: `spec` → this file (done in this change).
7. README + architecture doc (automaton-plane section) + glossary
   (automaton-executor, quiescence, wrapper).
8. Re-verify (`python3 -m package`), rebuild ZIPs.
