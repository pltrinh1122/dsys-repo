# D1–D7 Harness-Native Agent Substrate — Specification (DRAFT)

## 0. Status

DRAFT. Step 2 of the ratified D1–D7 agent factory plan (DR-CMD-061): the
substrate and runtime contract for factory-built agents. Step-2 fork resolved
2026-09-26 (Peter), DR-CMD-063: **harness-native** — factory-built agents are
dsys harness-plane entities, not substrate-neutral. This spec is a proposal;
it is not ratified.

## 1. Purpose

Define what the factory (plan steps 3–5) *produces*: a runnable agent that
occupies its `AgentBehaviorProfile` position, resident in the dsys harness
plane, invoked through a Harness per AX1 (invocation always through a
Harness, never directly to an Automaton).

## 2. The substrate

A harness-native agent is the closed assembly of seven components. Every
component is derived from the agent's profile; the construction semantics
in `core/package/agent_behavior.py` (DR-CMD-062) define the facet-to-component
mapping the factory's compiler (step 3) will implement.

1. **Profile** — a validated `AgentBehaviorProfile`. Positions derived from
   facets (D2 is the binary enum {principal_wins_ties, world_wins_ties},
   DR-CMD-077). The agent's charter: what the
   conformance verifier (step 4) checks the built agent against.
2. **Backend binding** — a handle to the harness inference facility,
   parameterized by D3 (temperature/seed/pinning per the derivation).
   Interface defined here (§6); the concrete binding is built in step 5.
3. **Tool bindings** — D5 realized. `read_scope` becomes data-source grants;
   `write_scope` becomes the tool allowlist over contracted tools. No tool
   outside `write_scope` is bound: unlisted effects are unreachable by
   construction, not by policy.
4. **Trigger wiring** — D6 realized. Per enabled source: a listener, an
   activation gate (may the trigger fire?), and an authorization rule
   (may the agent act on it? "stage-only" vs "may-act"). Two-stage pipeline;
   activation is distinct from authorization (DR-CMD-062, C4).
5. **Instrumentation** — D4 realized. Event/intent/verification streams feed
   the harness event log. `inspectors` are read grants on the log;
   `retention` is the storage policy.
6. **Verifiers** — D7 realized. Per enabled target, a verifier component
   sitting at the corresponding trust boundary (§5).
7. **Actuation loop** — D1 realized. `stage → disposition → execute`.
   The staging area holds proposed actions with their verification
   evidence. The disposition interface routes: per-event → operator,
   standing dispositions → pre-authorized rule table, escalate → operator.

## 3. Runtime contract

- **Invocation.** The harness invokes the agent when a trigger passes its
  activation gate. Envelope: `{trigger source, event, profile name+version,
  run id}`. The agent never invokes itself into execution; self-source
  triggers pass through the same gate.
- **Inference.** The agent may infer freely: it is harness-plane. The
  zero-inference constraint applies across the automaton boundary, not here.
- **Staging.** The agent's output is staged proposals — actions plus the
  verification evidence for each — never direct commits. Exception: actions
  matching a standing disposition (D1), which are pre-authorized.
- **Disposition.** Staged proposals are disposed through the DR-2 modes
  (ratify | authorize | set_standing | overrule | triage). The operator
  disposes per-event and escalated items. The ambient/factory never disposes.
- **Actuation.** Only disposed or pre-authorized actions execute, and only
  through bound contracted tools.
- **Observation.** Every transition — trigger, inference summary, staging,
  disposition, actuation, verification — is logged per D4. Inspectors query
  the log; nobody edits it.

## 4. Trust boundaries (D7 targets, placed)

- **trigger_target:** trigger → agent. The activation gate authenticates the
  trigger (allowlist + signature for world; authenticated session for
  operator).
- **intent_target:** principal → agent. Verifies the intent presented is the
  principal's (not injected, not stale).
- **world_target:** world → agent. Independent corroboration of world claims
  before the agent treats them as ground truth.
- **event_target:** agent → log. Integrity and attribution of the trace
  itself.

## 5. Reuse vs. new

**Reuse** (exists; the substrate wires it, not rebuilds it): the profile
schema + derivations (DR-CMD-062); contracted tools (DR-CMD-056/057);
the event log + replay (updater, bridge); disposition modes (DR-2); AX1/AX2.

**New** (specified here, built in step 5): per-source trigger wiring; the
staging area + disposition interface; the backend binding interface;
verifier components at the four trust boundaries.

## 6. Backend binding interface (deferred detail)

The interface the factory codes against in step 5:

- `infer(prompt, params) -> completion` — params derived from D3
  (temperature, seed, model pin).
- The facility is the harness's own inference backend (the ambient's
  facility); the agent does not bring its own model.
- Q1 (open): the exact facility handle. Deferred to step 5; the interface
  above is what step 3 compiles against.

## 7. Resolved and open questions

- **Q2 — actuation path: RESOLVED** (ratified DR-CMD-064, 2026-09-26).
  Factory-built agents actuate **hybrid**: a *tool action* is exactly
  one contracted-tool call with all arguments bound at disposition time
  (goes direct); a *governed workflow* — anything requiring intermediate
  observation, guards between steps, or unit replay — goes through
  automaton flows. The step-3 compiler spec must implement the routing
  and finalize the discriminator's edge wording.
- **Factory's own actuation path: RESOLVED** (ratified DR-CMD-064,
  disposed directly by Peter). The factory's build pipeline (compile and
  conformance verifier) runs as **automaton flows** — it is multi-step,
  guarded, replayable. Governs step-5 implementation only; does not
  authorize operating built agents (non-goal, §8).
- **Q1 — backend handle:** which concrete inference facility. Deferred to
  step 5 (see §6).
- **Q3 — staging durability: RESOLVED** (ratified DR-CMD-065,
  2026-09-26). Staging is **accretion-backed**: every staged proposal
  (actions + verification evidence) is committed to the accretion repo;
  pending proposals survive restarts and stay auditable, including ones
  never disposed. Ephemeral defeated (lighter, but a crash loses the
  pending queue silently and undisposed proposals leave no trace).

## 8. Non-goals

- The substrate does not operate agents: no scheduler, fleet management,
  or ops layer. Runtime operations are a separate matter.
- The substrate does not choose positions: Peter disposes profiles; the
  factory builds what it is given (DR-CMD-061).
- The substrate does not build systems: agents participate in dsys; dsys
  itself is not factory-built (DR-CMD-061 non-goal).

## 9. Glossary

- **Harness-native agent:** a factory-built agent resident in the dsys
  harness plane: profiled, invoked through a Harness per AX1, permitted
  inference, forbidden direct actuation except through disposition.
- **Substrate:** the seven components (§2) plus the runtime contract (§3):
  what a built agent *is* and how it *runs*.
- **Runtime contract:** the invocation / inference / staging / disposition /
  actuation / observation rules every factory-built agent runs under.
- **Trigger wiring:** the per-source listener + activation gate +
  authorization rule realizing D6.
- **Orphan:** a staged proposal whose disposition record says `"staged"`
  (admitted trigger, no standing disposition matched — DR-CMD-074 Item 5b)
  with no superseding triage record.
- **Orphan queue:** the derived set of untriaged orphans (see
  `doc/d1-d7-orphan-triage-spec.md`); membership recomputed from the
  append-only staging file, never stored.
- **Closure bar:** the structural invariant that nothing leaves the orphan
  queue except via a triaged disposition (`routed` / `refused` /
  `archived`) with a non-empty reason — the factory's I-13 echo
  (DR-CMD-081).
- **Staging-event feed** (`StagingEventListener`, DR-CMD-078): the listener
  the D6 `agent` source subscribes to. Tails the accretion-backed staging
  file and emits one trigger event per new proposal record authored by a
  verified built agent other than the owner. Attestation is pre-computed at
  the feed: the event is marked authenticated only if the staging chain
  verifies and the author is in the verified-built-agent registry; a broken
  chain or unknown author fails closed. The trigger rides *through* staging,
  never around it (stigmergic trigger).
- **Activation gate:** answers "may the trigger fire?" — the trigger is
  admitted or dropped.
- **Authorization rule:** answers "may the agent act on the admitted
  trigger?" — "stage-only" (propose for disposition) vs "may-act"
  (act within standing dispositions).
- **Staging area:** where the agent's proposed actions wait with their
  verification evidence until disposed or pre-authorized.
- **Disposition interface:** routes staged proposals to per-event operator
  disposition, the standing-disposition rule table, or escalation.
- **Contracted tool:** a tool whose behavior is specified, deterministic,
  and network-free (DR-CMD-056/057): the only effects a built agent may have.
- **Backend binding:** the agent's handle to the harness inference
  facility, parameterized by D3.
