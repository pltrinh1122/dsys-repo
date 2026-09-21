# DR-CMD-044 — Next best action: build the scenario simulation (O2)

- **Status:** ratified
- **Date:** 2026-09-21 ~07:55 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Next best action, given: K1 repair built and verified this turn (uncommitted), DR-CMD-042/043 ratified (uncommitted), scenario simulation adopted but unbuilt (DR-CMD-041), local `fe5e51b` ahead of origin.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — Commit the working tree locally** (K1 build + DR-CMD-042/043). G1–G4 ✓. Not selected — hygiene; remains the operator's trigger ("Y: commit").
- **O2 — Build the scenario simulation** (DR-CMD-041, adopted, unbuilt). G1–G4 ✓. **Selected** — the designated next work; this ratification is the explicit instruction the adoption requires.
- **O3 — Push to origin.** G1–G4 ✓. Not selected — premature on a dirty tree; separate authorization and a fresh device flow in any case.
- **O4 — Frame K1 Q3** (production repo-handle holder) as a design matter. G1–G4 ✓. Not selected — second; the simulation is adopted and waiting.
- **O5 — Defer.** G1–G4 ✓. Not selected — strands. **O6 — Decide nothing.** The null. Not selected.

No STOP kills.

## Decision

**Ratified O2** — build the scenario simulation as specified (DR-CMD-041), executed immediately (this turn).

## Consequences (G4)

1. Build: `core/package/scenario_sim.py` (briefs, scenario specs, manifest-provisioned sandboxes, I-21–I-24, hardening pipeline) + I-22 enforcement in the K1 accretion writer + `core/package/scenario_sim_golden_run.py` (spec acceptances A1–A6).
2. G6 carried to build (DR-CMD-041): Q1 standing-disposition classes enumerated before first use; Q2 manifest fidelity cited upstream (installer-spec); Q3 coverage stays flow-scoped in v1.
3. No records written by the NBA run itself (records follow disposition — this file).

## Checkability (G5)

Binding. Checkable: the module and golden run exist; the scenario-sim golden run passes; the spec converges to built.

## Premises

- `/pb-decide` next-best-action analysis, 2026-09-21 chat.
- DR-CMD-041 (adoption; the build's normative source).

## Uncertainties (G6)

- O1's commit still pending — the operator's call; does not block O2.
