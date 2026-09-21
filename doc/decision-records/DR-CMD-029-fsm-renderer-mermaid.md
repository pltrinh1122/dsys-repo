# DR-CMD-029 — FSM state-flow renderer: mermaid.js (O1)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:45 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Renderer for FSM state-flow diagrams — 'mermaid.js' or other.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — mermaid.js:** G1 ✓ G2 ✓ (operator-proposed; de-facto markdown-embedded standard; renders natively in GitHub, where the specs live) G3 ✓ G4 ✓. **Selected.**
- **O2 — Graphviz/DOT:** G1–G4 ✓. Not selected — precise layout, but needs a binary and has no native GitHub render.
- **O3 — decide nothing.** The null. Not selected.

No STOP kills.

## Decision

**Ratified O1 — mermaid.js.**

## Consequences (G4)

1. Mermaid.js renders FSM state-flow diagrams.
2. Convention: commit `.mmd` sources; view-render via GitHub (zero build step; diffable text).
3. Follow-on work: the pydantic→mermaid generator (consumes DR-CMD-028's models) — an expansion matter for governed `/pb-extend`.

## Checkability (G5)

Binding. Checkable: rendered diagrams generated from the models exist (or not).

## Premises

- `/pb-decide` option/gate analysis, 2026-09-21 chat.

## Uncertainties (G6)

- Mermaid version pin — open.
- Numbering: this ratification takes **DR-CMD-029**.
