# DR-CMD-013 — fix the `/eval-meta` contract↔implementation gaps (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~18:32 PDT
- **Selector:** Peter (operator; framer and disposer the same person — explicitly recorded self-ratification per the playbook's Boundary clause)
- **Disposition mode:** ratify
- **Matter:** Resolve the two material coherence gaps between `doc/slash-commands/eval-meta.md` (contract) and `doc/eval-meta-implementation.md` (implementation): (1) the contract's Redirect section (playbook→`/eval-pb`, run-book→`/eval-rb`) had no implementation step; (2) the implementation's Form B (`{claim} :: {citations}`) was undeclared in the contract's Trigger.

## Options and gate trails

**O1 — Expand to the union (selected).** Add the redirect step to the implementation; declare Form B in the contract's Trigger.
- G1: pass — two specified edits. G2: pass — DR-CMD-003's standing redirect principle; `/eval-sc`'s contract Trigger as the Form B template; the implementation's worked example as evidence Form B is load-bearing. G3/G4: pass.

**O2 — Trim to the intersection (not selected).** Delete the Redirect section from the contract; remove Form B from the implementation.
- G1/G3/G4: pass; G2 weak (operator-proposed, no domain source). Defeated on the merits: trimming Redirect un-ratifies DR-CMD-003's branch-declaration principle and reintroduces the silent wrong-branch evaluation the contract explicitly forbids; trimming Form B guts the evidence pipeline (Check 2 is Form-B-only; D2–D5 run on citations).

**O0 — Decide nothing: killed at G4**, per precedent.

## Decision

**O1 ratified.** Edits applied 2026-09-20:

1. `doc/slash-commands/eval-meta.md` — Trigger declares Form B: `` `/eval-meta {claim} :: {citations}` `` (one line, in `/eval-sc`'s form).
2. `doc/eval-meta-implementation.md` — §2 renamed "Step 0 — branch redirect and scope determination": branch redirect runs first (shape before scope), with exact refusal texts citing `/eval-pb` / `/eval-rb`; shape criteria cited not restated (`doc/eval-pb-implementation.md` §3's threshold; glossary "Run-book"). §0's procedure list and the glossary's step-0 entry updated to match. No section renumbering.

## Consequences (G4)

Both material gaps closed; the contract's Redirect promise now has procedural basis, and Form B is declared at both layers.

## Checkability (G5) — binding

Redirect step present in the implementation (§2); Form B declared in the contract Trigger.

## Uncertainties (G6)

- The three minor gaps from the coherence check are untouched and out of scope: operator-side `/pb-decide` guidance (no agent detection), path/artifact matter-form resolution, the `unevaluable` verdict name.
- Numbering note (supersedes the projection in DR-CMD-012's G6): this matter takes DR-CMD-013 in disposition order. The still-open `/pb-decide` remediation matter (from the `/eval-sc` report) moves to DR-CMD-014 on ratification; the `/eval-sc` family-membership candidacy moves to DR-CMD-015.
