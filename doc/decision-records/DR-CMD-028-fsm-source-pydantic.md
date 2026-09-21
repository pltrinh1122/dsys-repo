# DR-CMD-028 — FSM state-flow source format: pydantic (O1)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:45 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Source format for defining FSM state-flows (updater automaton and future automata) — 'pydantic' or other.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — pydantic models** (states, transitions, guards as typed models): G1 ✓ G2 ✓ (core already speaks pydantic — verified schema.py/validators.py package; guards are AST-allowlisted Python) G3 ✓ G4 ✓. **Selected.**
- **O2 — YAML + schema:** G1–G4 ✓. Not selected — weakened: its schema would be pydantic, so distinctness from O1 is serialization-only.
- **O3 — mermaid.js as source-of-truth:** G1–G4 ✓ (survived gating). Not selected — died on the merits: cannot host typed guards or the AST-allowlist; diagrams are generated from the source, not the source.
- **O4 — decide nothing.** The null. Not selected.

No STOP kills.

## Decision

**Ratified O1 — pydantic.**

## Consequences (G4)

1. FSM state-flows are defined as pydantic models (compiling to FlowState/FlowTransition per DR-CMD-030).
2. YAML/JSON remain available as *serializations* of the models — a serialization choice, not a separate format decision.
3. Mermaid is a derived view of the models (DR-CMD-029's generator consumes them).

## Checkability (G5)

Binding. Checkable: flows exist in-repo as pydantic models (or not).

## Premises

- `/pb-decide` option/gate analysis, 2026-09-21 chat.
- Architecture: machine-native pydantic packages (verified); v1 Python-syntax expression language, AST-allowlisted.

## Uncertainties (G6)

- Pydantic v1 vs v2 pin — open, to be fixed when the models are authored.
- Numbering: this ratification takes **DR-CMD-028**.
