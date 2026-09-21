# DR-CMD-030 — State-flow execution: source→core bridge on FlowRun (O1)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:45 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Machinery to execute FSM state-flow sources (e.g., pydantic-defined flows) for the updater automaton — build or not, and what.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — source→core bridge:** compile pydantic flow definitions into FlowState/FlowTransition entities; drive via the existing FlowRun scheduler; no new execution semantics. G1 ✓ G2 ✓ (updater requirement, operator-sourced) G3 ✓ (uses FlowRun — explicitly non-duplicative) G4 ✓. **Selected.**
- **O2 — standalone state-flow engine** (new execution semantics): G1 ✓ G2 ✓, **G3 ✗ — killed.** Duplicates the standing FlowRun scheduler and AutomatonFlow semantics (I-14/I-15/I-16, 2026-09-19) with no named delta. Routed: fold into O1 or name the delta and re-enter.
- **O3 — decide nothing.** The null. Not selected.

STOP: O2 killed (G3, cited).

## Decision

**Ratified O1 — the bridge; no new engine.**

## Consequences (G4)

1. No new execution semantics: FlowRun remains the scheduler.
2. The missing piece is built: pydantic (DR-CMD-028) → FlowState/FlowTransition instantiation + driver advancing FlowRun.
3. Pipeline composed: pydantic source → FlowRun executes → mermaid renders (DR-CMD-029).
4. The bridge (and the pydantic→mermaid generator) are expansion matters for governed `/pb-extend` — proposed, not yet admitted.

## Checkability (G5)

Binding. Checkable: a pydantic-defined flow compiles to FlowStates and a FlowRun advances it (or not).

## Premises

- `/pb-decide` option/gate analysis, 2026-09-21 chat.
- Architecture: AutomatonFlow — FlowState, FlowTransition (AST-allowlisted guards), FlowRun (scheduler), FlowTransitionEvent, I-14/I-15/I-16.
- DR-CMD-028 (pydantic source), DR-CMD-029 (mermaid renderer).

## Uncertainties (G6)

- The 'updater' automaton itself is still undisposed (proposed only) — flagged in the draft verdict; the operator disposed regardless. This machinery presumes the matter.
- Scope split for the later expansion matter: the compiler is package-side tooling, the entities runtime.
- Numbering: this ratification takes **DR-CMD-030**. Next identifier: **DR-CMD-031**.
