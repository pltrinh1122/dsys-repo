# DR-CMD-031 — Next best action: governed updater run (O2)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:47 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Next best action, given: feature-expansion playbook adopted (`/pb-extend` governed), FSM machinery decided (DR-CMD-028/029/030), 'updater' still undisposed, working tree dirty with the morning's ratified work.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — Commit the working tree locally** (all ratified work). G1–G4 ✓. Not selected — hygiene; remains the operator's trigger ("Y: commit").
- **O2 — Governed `/pb-extend` run on the 'updater' seed matter** (first governed run). G1–G4 ✓. **Selected.**
- **O3 — Frame + admit the bridge expansion matter.** G1–G4 ✓. Not selected — premature (presumes the undisposed updater; not S1–S4 framed).
- **O4 — Pin pydantic v1/v2, author first FSM models.** G1–G4 ✓. Not selected — premature (models of an unspec'd flow).
- **O5 — Defer.** G1–G4 ✓. Not selected — strands. **O6 — Decide nothing.** The null. Not selected.

No STOP kills.

## Decision

**Ratified O2.**

## Consequences (G4)

1. The governed `/pb-extend` run on 'updater' is the ratified next action — executed immediately (this turn), no further confirmation gated.
2. First governed run: `Mode: governed — playbook adopted DR-CMD-027`; STOP kills enforced; verdict feeds disposition; no records written by the run itself.
3. Outcome (recorded here for completeness): **X4 fired** — the matter duplicates `install.sh --release`'s "converge tree to release R" guarantee without naming its delta → **refused back** for narrowing (recommended: split the monitor/trigger automaton, the actual delta, from the perform step, which exists) / merging / superseding. Full report in the 2026-09-21 chat record.

## Checkability (G5)

Binding. Checkable: this record exists; the run report carries `Mode: governed` (or not).

## Premises

- `/pb-decide` next-best-action analysis, 2026-09-21 chat.
- DR-CMD-027 (playbook adopted); DR-CMD-028/029/030 (FSM machinery).

## Uncertainties (G6)

- O1's commit still pending — the operator's call; does not block O2.
- The updater's S1 such-that is thin (flagged in staging, not refused).
- Numbering: this ratification takes **DR-CMD-031**. Next identifier: **DR-CMD-032**.
