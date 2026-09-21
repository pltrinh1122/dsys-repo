# DR-CMD-023 — `/pb-extend` name kept (O1)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:24 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Keep the `/pb-extend` command name, or rename it?

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — keep `/pb-extend`:** survived; recommended; selected. No churn:
  the name is referenced in the DR-CMD-001 lineage (`/pb-<verb>` family
  pattern), DR-CMD-018 (triplet ratified), the contract's Trigger
  (`/pb-extend {matter}`), and the Family line (`pb-*`, sibling
  `/pb-decide`). G1 ✓, G4 ✓ (the name is the command's identity),
  G5 ✓ (checkable: contract filename + trigger line).
- **O2 — rename to `/pb-expand`:** survived; not selected. Lost on
  churn: the rename buys nothing semantically and breaks every existing
  reference (lineage, DRs, contract, Family declarations).
- **O3 — rename to `/pb-scope`:** killed in the earlier deliberation.

## Decision

**Ratified O1.** The command stays `/pb-extend`. No file changes
required — the name is already uniform across contract, design,
implementation, and records.

## Consequences (G4)

The naming question is closed. (The command itself remains
rehearsal-only until its feature-expansion playbook is remediated and
disposed — separate matter, still open.)

## Checkability (G5)

Binding. Checkable: `doc/slash-commands/pb-extend.md` Trigger reads
`/pb-extend {matter}` (or not).

## Uncertainties (G6)

- None blocking. Revisit trigger: none foreseen — the name is settled.
- Numbering (disposition order): this ratification takes **DR-CMD-023**.
