# DR-CMD-064 — Q2 RESOLVED: hybrid actuation for built agents; flows for the factory's own build pipeline

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:31 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *Q2 — actuation path* (open in DR-CMD-063), decided via
  `/pb-decide`; plus a companion matter Peter disposed directly:
  *the factory's own actuation path* (not part of the /pb-decide run —
  recorded honestly below).

## Decision 1 — Q2: factory-built agents actuate HYBRID (Option A)

**ADOPTED** — Option A: a harness-native agent's actuation path is hybrid.
Single contracted-tool calls go **direct**; governed workflows go through
**automaton flows**.

**Discriminator (ratified):** a *tool action* is exactly one
contracted-tool call with all arguments bound at disposition time; a
*governed workflow* is anything requiring intermediate observation,
guards between steps, or unit replay → automaton flow.

**Rationale:** mirrors the existing architecture (in the updater, flow
transitions invoke tools directly while the workflow is the flow; flows
orchestrate, tools execute). The discriminator is mechanical enough for
the step-4 conformance verifier to probe.

### /pb-decide trail (run on the matter)

- **Matter (falsifiable):** "A harness-native D1–D7 agent's actuation path
  is correctly specified as [option]."
- **Option A — hybrid:** G1–G4 pass; checkable (G5) — the compiler's
  routing is golden-testable. Draft verdict: ADOPTED (this decision).
- **Option B — all through flows:** G1–G4 pass, checkable; survived as
  the ordered alternative. Defeated on selection: erases the
  harness/automaton plane discipline (the harness plane exists precisely
  so inference-side activity is not all automaton-governed); forces
  nested driving (agent → strapped driver → flow → tool) for every
  tool call; contradicts D5's specified realization as a tool allowlist.
- **Option C — all direct, flows never:** KILLED — abandons flow
  governance where the architecture requires it (I-14 totality, I-15
  transition determinism, replay identity for multi-step work); would
  force ad-hoc reimplementation of flow semantics already present in the
  updater/K1 machinery.
- **"Decide nothing":** KILLED at G4 — changes no commitment and leaves
  the blocking question open; the step-3 compiler spec cannot proceed
  without the actuation path. Recorded explicitly, not silently.

**Consequences (per G4):** substrate spec §7 Q2 is resolved (see State);
the step-3 compiler spec must implement the routing (direct vs. flow)
and finalize the discriminator's edge wording (G6 carried); steps 3+4
unblock.

## Decision 2 — the factory's OWN actuation path: flows (Option B)

**ADOPTED — disposed directly by Peter** (message: "if actuation path
for factory, then B. otherwise, A."), without a separate /pb-decide run.
Recorded honestly: the operator may dispose directly; proposer≠disposer
is satisfied (ambient proposed the framed Q2 fork; Peter disposed both
matters).

**Decision:** the factory's own build pipeline — compile (profile →
build plan → agent) and the conformance verifier (build → probe →
check) — runs as **automaton flows**.

**Rationale (recorded):** the factory's work is multi-step, guarded,
replayable — a governed workflow by the Decision-1 discriminator, so B
is where the discriminator lands it.

**Consequence:** governs **step-5 implementation only** — the compiler
and verifier are built as flows. It does **not** authorize operating
built agents (DR-CMD-061 non-goal stands: the factory does not operate
agents).

## Uncertainties (G6)

- **Q1 — Backend binding interface:** which model backend(s) and how the
  binding is declared; deferred to step 5. Open.
- **Q3 — Staging-area durability:** ephemeral or accretion-backed (proposed:
  accretion-backed). Carried as a parameter into steps 3+4. Open.
- U1 (scope boundary) and U2 (classification), carried from DR-CMD-060:
  still open. U3 (scalar fate) closed (DR-CMD-062). U4 (substrate fork)
  closed (DR-CMD-063). Q2 closed by this record.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- Next disposition identifier: DR-CMD-065.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed both matters
only): this record; the substrate spec §7 is amended to reflect Q2's
resolution. Steps 3 (compiler spec) and 4 (conformance-verifier spec)
unblock as parallel drafts. Commit and push return as follow-on
dispositions.
