# D6 `agent` Source — Design Spec (DR-CMD-078)

**Status:** built 2026-09-26 (ambient run, uncommitted); J-calls (J-G, J-H,
J-I) ratified DR-CMD-080. Full build **RATIFIED as built, DR-CMD-082
(Item 10, 2026-09-26)**. Disposition records:
`doc/decision-records/DR-CMD-078-d6-agent-source-opened.md`,
`doc/decision-records/DR-CMD-080-d6-jcalls-ratified.md`.

## Glossary

- **D6 (Initiative):** the design dimension answering "what may activate the
  agent" — a structural (scalar-free) triple of *source* × *gating* ×
  *authorization*. Gating: may the trigger fire? Authorization: may the agent
  act on it (may-act) or only propose (stage-only)?
- **Trigger source:** the origin class of an activation event. The enum is
  now `{operator, world, self, agent}` (was `{operator, world, self}` before
  DR-CMD-078).
- **Stigmergic coordination:** coordination through a shared medium rather
  than direct signaling. dsys agents stage proposals into the
  accretion-backed staging area (or change world state); other agents
  discover them on their own cadence. No agent ever directly triggers
  another — the architecture has no message-passing activation path.
- **Stigmergic trigger:** the theory this spec records — an `agent`-source
  trigger is a *staging state change* observed through the staging medium.
  The trigger rides **through** staging, never around it: the state change
  IS a staging record, so proposer≠disposer is untouched. The new source
  changes WHEN the coordinator wakes, not WHAT it may do.
- **Authenticated-agent gate:** the gating rule for the `agent` source.
  Admits a staging-event trigger iff (a) the staging file's hash chain
  verifies end-to-end AND (b) the record's author id names a verified built
  agent. Both conditions are attested by the staging-event feed before the
  event reaches the gate; a broken chain or unknown author fails closed
  (event unattested → gate denies).
- **Staging-event feed** (`StagingEventListener`): the substrate listener
  the `agent` source subscribes to. Tails the accretion-backed
  `staging.jsonl`, watermarked at the last emitted record seq, and emits one
  `TriggerEvent` per new *proposal* record (kind == "proposal").
  Disposition records and the listener owner's own proposals do not emit.
- **Verified built agent:** an agent id whose profile validated → compiled →
  verified green through the factory (the six-profile ensemble, or a later
  verified build). The feed holds this set as its attestation registry.
- **Attestation (pre-computed):** the feed sets `session_authenticated=True`
  on an event only after verifying chain + author itself. The activation
  gate's existing `authenticated` keyword then admits on that flag — no new
  gate-semantics keyword, no `GATE_SEMANTICS_VERSION` bump.
- **Reconciliation backstop:** the coordinator's retained SELF scheduler
  cadence, which re-sweeps the staging area independently of the event feed
  (covers missed events and crash-between-append-and-drain; the sweep is
  idempotent and content-hash-ordered, so re-running is safe).
- **J-items:** build-time judgment calls documented in this spec (J-G, J-H,
  J-I below).

## Design

### 1. Enum

`TriggerSource` gains `AGENT = "agent"`. The D6 reference text becomes
"source {operator, world, self, agent} × gating × authorization". Schema
change: SCHEMA_VERSION 1.1 → 1.2 (at the time, no documented bump rule
existed — recorded as-built, the same discipline gap noted under
DR-CMD-077; rule adopted 2026-09-26 by DR-CMD-082 and now stated at the
SCHEMA_VERSION definition site in `core/package/factory_compiler.py`).

### 2. Coordinator binding

The coordinator binds `agent`:

- gate: `"authenticated-agent staging event; chain+registry attested"` —
  contains the `authenticated` keyword, so the reference gate semantics
  (v1.0, unchanged) admit iff `session_authenticated is True`.
- authorization: `"stage-only"` — staff S4 holds; the coordinator still
  never acts, only stages arbitration proposals.

SELF (`scheduler-cadence; staging-area sweeps`) and OPERATOR
(`authenticated-session`) bindings are unchanged.

### 3. Mechanism: the staging-event feed

`StagingEventListener(writer, verified_agents, own_agent)`:

- On construction, watermarks at the current file head — only *new*
  appends emit (history is the SELF sweep's jurisdiction).
- `drain()` reads records with seq > watermark, oldest first; advances the
  watermark past everything read (emitted or not — a skipped record is not
  re-emitted; the sweep covers it).
- Emits only `kind == "proposal"` records whose author != own_agent.
- Per emitted event: `source="agent"`, `event_id=f"staging-ev-{seq:06d}"`,
  `source_id=<author>`, `payload={staging_seq, record_hash, kind, author}`,
  `session_authenticated = chain_ok and author_ok` where `chain_ok` is the
  writer's whole-file `verify()` and `author_ok` is membership in
  `verified_agents`. Broken chain → every event in the drain unattested
  (fail-closed). Spoofed/unknown author → that event unattested.
- Deterministic: seq counters only; no clock, no randomness.

### 4. What the coordinator does when woken

Identical to a cadence sweep: run the arbitration (route/sequence/conflict
detection over pending proposals), stage the arbitration proposal with
`trigger_ref="agent:staging-event"` (the wake source is recorded, not
hidden). Disposition stays pending; proposer≠disposer holds by
construction.

### 5. Reference level

D6's reference description now reads: sources name *activation origins*;
`agent` names activation-by-observed-staging-state-change under the
stigmergic-trigger theory — triggers through the medium, never around it.
Direct agent-to-agent triggering (message-passing activation) remains
unnameable and architecturally out of scope: it would route around the
staging area where disposition happens.

## Judgment calls

- **J-G. Retain the SELF cadence as reconciliation backstop: YES.**
  The event feed can miss (crash between append and drain; watermark
  skips). The sweep is idempotent and content-hash-ordered, so re-running
  it is safe and deterministic. Event-driven waking is the fast path;
  cadence is the correctness backstop. Removing the cadence would make the
  coordinator's completeness depend on feed liveness — a new availability
  assumption the architecture should not take on silently.
- **J-H. Coordinator-only binding now; schema-wide enum: YES.**
  Mirrors the D5 write_scope treatment (the channel set exists schema-wide;
  only the executor binds tools today). Other profiles gain nothing by
  binding `agent` now — the analyst/advisor/author/monitor neither mediate
  nor need wake-on-staging — and binding it speculatively would widen
  their activation surface without a capability need. The enum addition is
  the schema change; the binding is the per-profile choice.
- **J-I. Attestation pre-computed at the listener, not verified by the
  gate: YES.** The gate's reference semantics (v1.0) already admit on
  `session_authenticated`; the listener is the component that *holds* the
  writer and the verified-agent registry, so it is the component that can
  check them. Gate-side verification would require threading writer +
  registry references through the gate — new coupling for no new
  assurance. The gate text documents the attestation contract
  ("chain+registry attested") so the promise is declared, not silent.

## Verification

Golden-run cases (factory_golden_run.py, A-* battery):

- **A1:** agent-source trigger admitted on an authenticated staging event
  (analyst stages → feed drains → `session_authenticated=True` →
  coordinator agent wiring admits, authorization stage-only).
- **A2:** refused on spoofed author id (`mallory` not in verified registry
  → unattested → gate denies; nothing staged, no tool calls).
- **A3:** refused on broken record chain (tampered staging.jsonl → chain
  verify fails → all drained events unattested → denied).
- **A4:** arbitration staged on an agent-source trigger cites
  `trigger_ref="agent:staging-event"`, disposition stays pending, and a
  may-act authorization on the agent source still refuses at [staff/S4]
  (M5's temptation re-run against the new source).
- **M6 updated:** coordinator now binds `{operator, self, agent}`; the
  afferent path cites all three honestly.

Full suites (factory, agent-behavior, archetype self-test, bridge,
updater, drive contract, acquisition, PVB workflow, scenario sim,
playbook) must stay green; two consecutive factory runs byte-identical.
