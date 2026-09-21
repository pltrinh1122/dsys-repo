# DR-CMD-032 — Next best action: narrowed updater re-entry (O2)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:49 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Next best action, given X4's refuse-back of 'updater' (DR-CMD-031 run).

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — Commit the working tree locally.** G1–G4 ✓. Not selected — hygiene; remains the operator's trigger.
- **O2 — Re-enter governed `/pb-extend` with the narrowed updater claim** (ambient-drafted, operator-approved by this ratification). G1–G4 ✓. **Selected.**
- **O3 — Frame the bridge expansion matter.** G1–G4 ✓. Not selected — premature; the narrowed updater claim goes first.
- **O4 — Pydantic pin + first models.** Not selected — premature (needs the narrowed claim's flow).
- **O5 — Defer.** G1–G4 ✓. Not selected — strands. **O6 — Decide nothing.** The null. Not selected.

No STOP kills.

## Decision

**Ratified O2** — the narrowed claim framing is operator-approved by this ratification.

Narrowed claim: "dsys should gain a release-monitor automaton such that it watches dsys releases and, on a new release, drives an upgrade by invoking `install.sh --release` (existing), recording the step-change via the promotion bridge, honoring accretion-repo tree discipline, and executing as a FlowRun via the DR-CMD-030 bridge — the monitor/trigger logic being the new delta, the perform step composed, not duplicated."

## Consequences (G4)

1. Governed `/pb-extend` re-entry executed immediately (this turn) on the narrowed claim.
2. Outcome (recorded here for completeness): **X4 clear** (delta named); draft verdict **refuse(not-ready)** — most conditionals unevaluated (no spec yet), R4 holds (no inference in the watch/compare/invoke loop), no conditional fails, no gate fires. The matter now needs its spec: pydantic models (DR-CMD-028), replay story (R1), trust declaration (R5 — who authorizes auto-upgrades), hermeticity story (P2 — the network watch), falsification (A1).
3. No records written by the run itself (records only on disposition).

## Checkability (G5)

Binding. Checkable: this record exists; the run report carries `Mode: governed` (or not).

## Premises

- `/pb-decide` next-best-action analysis, 2026-09-21 chat.
- DR-CMD-031 (X4 refuse-back; the routing this re-entry follows).

## Uncertainties (G6)

- O1's commit still pending — the operator's call.
- The spec-authoring step is the next substantive move (no DR for the act of authoring; records follow disposition).
- Numbering: this ratification takes **DR-CMD-032**. Next identifier: **DR-CMD-033**.
