# DR-CMD-061 — D1–D7 agent factory plan RATIFIED (steps 0–7)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:19 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *D1–D7 agent factory plan* — the ambient's proposed eight-step plan to manifest a factory for building D1–D7 agents (factory = deterministic compiler from profile to runnable agent, plus a conformance verifier proving each built agent occupies its profiled position), ratified step by step (0. ratify · 1. ratify · 2. ratify · 3. ratify · 4. ratify · 5. ratify · 6. ratify · 7. ratify).

## Decision

**RATIFIED** — all eight steps of the D1–D7 agent factory plan:

- **Step 0 — Disposition the foundation.** D1–D7 as reference architecture is unratified; the factory's authority derives either from ratified reference-architecture adoption (DR-CMD-060 remains earmarked for that adoption; **not consumed by this record**) or the factory proceeds as exploration. The fork is Peter's call; still pending.
- **Step 1 — Calibrate the dials (construction semantics).** For each dimension/facet, define what positions *construct to* — profile field → build decision. Fix scalar calibration (each scalar earns construction meaning or goes ordinal); recover dropped content (D2 conflict rule, D6 activation-vs-authorization distinction).
- **Step 2 — Define the agent substrate and runtime contract.** Factory-built agent = harness-resident entity (profile + model backend + tool bindings + trigger wiring + instrumentation + verification hooks), invoked through a Harness per AX1. Fork: dsys-harness-native agents only vs. substrate-neutral agent with a dsys adapter; pending Peter's disposition.
- **Step 3 — Specify the compiler: profile → build plan → agent.** Deterministic, total, closed (bridge B-1/B-2/B-3 template); pydantic source per DR-CMD-058.
- **Step 4 — Specify the conformance verifier: build → probe → check.** Per-dimension probes: replay probe (D3), scope probe (D5), trigger probe (D6), halt-on-unverified probe (D7).
- **Step 5 — Build compiler + verifier + substrate.** Factory deterministic even when its products are stochastic (two-plane logic); the factory never disposes profiles — it builds what it is given.
- **Step 6 — Golden run across the space.** Corners (thermostat-like, full-autonomy-like), dsys-adjacent, interiors; zero violations.
- **Step 7 — Peter's run-through, defects remediated or explicitly deferred, then ratify-or-amend.**

## Lineage (falsification chain this plan rests on)

The plan follows the 2026-09-26 falsification chain, each claim falsified with its surviving core:

1. "7-DoAB" shorthand — **falsified** (DOAB collision, digits-first convention inversion, count-brittleness demonstrated by D7's own addition, redundancy with "D1–D7"). Survivor: "D1–D7" as working shorthand.
2. "D1–D7 has a schema" — **falsified as stated** (scalars do no work; false precision; dropped D2 conflict rule and D6 activation/authorization; C1–C5 enforce unratified law; exercised on fictions). Survives as: partial, provisional codification — `core/package/agent_behavior.py` is built and golden-run-verified, **unratified**.
3. "dsys can be expressed in a D1–D7 schema" — **falsified** (two-plane category error: D3 holds of the automaton, false of the harness; posture not machinery; referential ambiguity; the expression violates dsys's own status norms; circularity — D1–D7 was abstracted from dsys). Survives as: dsys's per-plane behavioral posture is locatable.
4. "dsys decomposes into schema-expressible agents" — **falsified** (non-agent mechanical parts unexpressed; inter-agent relations unexpressed — profiles are monadic; the principal is the schema's presupposed ground, not another profile; no canonical decomposition; diachronic guarantees lost). The remainder is the architecture.
5. "D1–D7 is a description of an architecture but not an architecture" — **falsified** (reference architectures and architectural styles *are* architectures; the couplings refuse rather than describe; dsys's own methodology collapses ratified-enforced-description into architecture). Survives as: **D1–D7 is a reference architecture**, with the qualifier "reference" load-bearing.

**Working position adopted for the plan:** D1–D7 is a reference architecture. Its actual deficiency is status, not kind — undispositioned (DR-CMD-060 earmarked), partially enforced.

## Standing non-goal and reflexivity note (ratified with the plan)

- **Non-goal:** the factory builds *agents*, not systems. It cannot build dsys; it builds entities that can participate in dsys as harness-plane residents. It does not operate agents (runtime/ops is separate) and does not choose positions (Peter disposes positions).
- **Reflexivity:** profile the factory itself in D1–D7 and publish it (operator-disposed builds, high verification via conformance). A factory that builds positioned agents while hiding its own position violates the norms it is built to enforce.

## Consequences (what changes, per G4)

- The eight-step factory plan is the ratified roadmap; work may proceed stepwise against it. Steps 3 and 4 may run as parallel tracks once step 1 lands; all other steps are sequential.
- The next concrete work is step 1 (construction-semantics table) — judgment work for Peter's review, not machinery.
- Ratification of the plan does **not** ratify: the reference architecture itself (DR-CMD-060 still open), the schema (`agent_behavior.py` remains built-but-unratified), the C1–C5 couplings (still proposed), or either pending fork.

## Uncertainties (G6)

- **U1 — Step-0 foundation fork:** ratified reference-architecture adoption vs. factory-as-exploration. Peter's call; unresolved.
- **U2 — Step-2 substrate fork:** dsys-harness-native only vs. substrate-neutral with dsys adapter. Peter's call; unresolved.
- **U3 — Scalar fate:** step 1 may calibrate the 0.0–1.0 scalars or replace them with ordinals; the schema's scalar representation is provisional until then.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- DR-CMD-060 remains earmarked for reference-architecture adoption — **not consumed**.
- Next disposition identifier: DR-CMD-062.

## State

**The tree is UNCOMMITTED at disposition** (Peter ratified the plan only): this record. No spec, code, or matter-doc changes authorized by this disposition. Commit and push return as follow-on dispositions.
