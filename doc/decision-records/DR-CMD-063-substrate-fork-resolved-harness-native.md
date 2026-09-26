# DR-CMD-063 — Step-2 substrate fork RESOLVED: harness-native agents

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:26 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *step-2 substrate fork* (open in DR-CMD-061): whether factory-built agents are dsys-harness-native entities or built against a substrate-neutral interface with a dsys adapter. Resolved in favor of **harness-native**.

## Decision

**ADOPTED** — factory-built agents are **harness-native**: resident in the dsys harness plane, invoked through a Harness per AX1 (never directly to an Automaton). The runtime contract reuses existing dsys machinery rather than inventing new substrate: the event log, replay, the DR-2 disposition modes (ratify|authorize|set_standing|overrule|triage), contracted tools. No abstract substrate interface is built at this time.

**Rationale:** concrete and verifiable now — the runtime contract's components already exist and are golden-run-verified, so the conformance verifier (step 4) can be built against them immediately. The substrate-neutral abstraction is **deferred, not killed**: it is extracted only if and when a second substrate materializes (not planned, not pursued). Per the standing rule from DR-CMD-058 (BPMN exporter deferred until an interchange requirement materializes), abstraction is earned by a second customer.

## Consequences (what changes, per G4)

- The step-2 spec (agent substrate + runtime contract) is being drafted by the ambient as a **DRAFT** doc: harness-resident entity = profile + model backend + tool bindings + trigger wiring + instrumentation + verification hooks, invoked per AX1.
- Steps 3 (compiler spec) and 4 (conformance-verifier spec) unblock once the step-2 spec is ratified-or-amended — they build against the harness-native substrate.
- This disposition does **not** ratify: the step-2 spec itself (still DRAFT until Peter disposes it), the machine-native schema as a whole (built-but-unratified; derived-scalar revision per DR-CMD-062), or the C1–C5 couplings (still proposed).

## Uncertainties (G6)

- **U1 — Scope boundary:** the execution-plane scope question, open (carried from DR-CMD-060).
- **U2 — Classification:** the forces/bounds/outcomes classification question, open (carried from DR-CMD-060).
- **U3 — Scalar fate:** **closed** (DR-CMD-062).
- **U4 — Step-2 substrate fork:** **closed** by this record — harness-native.
- **Q1 — Backend binding interface:** which model backend(s) a harness-native agent binds to and how the binding is declared; open for the step-2 draft.
- **Q2 — Actuation path:** direct contracted-tool calls vs. driving Automaton flows. Proposed (not disposed): direct calls for tool actions, flows for governed workflows. Open for the step-2 draft.
- **Q3 — Staging-area durability:** where staged-but-undisposed intents live and survive crashes. Proposed (not disposed): accretion-backed. Open for the step-2 draft.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- Next disposition identifier: DR-CMD-064.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the substrate fork only): this record. The step-2 substrate/runtime spec draft is in progress under the ambient's hand and returns for ratify-or-amend. Commit and push return as follow-on dispositions.
