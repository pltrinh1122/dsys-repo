# DR-CMD-012 — refactoring sequence for incomplete slash commands (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~18:28 PDT
- **Selector:** Peter (operator; framer and disposer the same person — explicitly recorded self-ratification per the playbook's Boundary clause)
- **Disposition mode:** ratify
- **Matter:** In what order (ordered matters, each with its DoD) should the incomplete slash commands be refactored to the ratified family schema (DR-CMD-006 separate files; DR-CMD-010 implementation→design reference)?

## Inventory (G2 evidence, observed 2026-09-20)

| Command | Contract | Implementation | Design | Contract binds impl | Verdict |
|---|---|---|---|---|---|
| /eval-sc | ✓ | ✓ | ✓ | ✓ | complete per schema (DRAFTs) |
| /eval-pb | ✓ | ✓ DRAFT | ✓ DRAFT | ✗ missing | incomplete: binding + undisposed drafts + §8 open |
| /eval-meta | ✓ | ✓ DRAFT | ✓ DRAFT | ✗ missing | incomplete: binding; coherence unverified |
| /eval-rb | ✓ | ✗ | ✗ | ✗ | incomplete: no implementation, no design, no binding |
| /pb-decide | ✓ | n/a (binds §8.2) | n/a | ✓ | complete per kind — out of scope |
| /pb-extend | ✓ | n/a (binds spec DRAFT) | n/a | ✓ | complete per kind — out of scope |

## Options and gate trails

**O1 — Command-complete, dependency order (selected).** Close /eval-pb fully → /eval-meta (coherence check, then bind) → /eval-rb (author docs on the ratified pattern, then bind).
- G1: pass — statable as ordered matters with DoDs and dependencies. G2: pass — dependency logic (can't bind what doesn't exist; don't replicate an unratified pattern) + pattern-validation: /eval-pb is furthest along, closing it first proves the pattern /eval-rb copies. G3: pass — no standing sequencing decision. G4: pass — creates the work plan.

**O2 — Bindings first (not selected).** G1/G3/G4 pass; G2 weak — "cheap first" is a heuristic with no domain source; front-loads the least valuable work, unblocks nothing, and /eval-rb can't be bound yet anyway.

**O3 — Biggest gap first (not selected).** G1/G3/G4 pass; G2 weak — "hardest first" heuristic; replicates the /eval-pb pattern before its disposition settles it → rework risk for no dependency reason.

**O4 — Defer all refactoring until sc-author (not selected).** G1/G3/G4 pass; G2 weak — DR-CMD-007's letter covers machine-readable front matter only; the work at issue is prose structure, not the machine contract it protected.

**O0 — Decide nothing: killed at G4**, per precedent.

## Decision

**O1 ratified.** The sequence, each step with its DoD:

1. **Close /eval-pb.** DoD: §8 matter disposed → implementation draft disposed (final content) → design draft disposed → contract Function gains the binding line (may ride the disposition package, DR-CMD-010 precedent).
2. **/eval-meta.** DoD: coherence check (contract ↔ implementation — is the implementation doc actually its procedure?) → binding line added on pass; mismatches become their own matter.
3. **/eval-rb.** DoD: implementation + design authored *on the ratified /eval-pb pattern* → contract binding added → drafts disposed.

## Consequences (G4)

The family's incomplete set drains in an order where each step's output is the next step's validated input. Step 1 is operator-gated throughout (dispositions); step 2's check is agent work, its binding conditional on a clean pass; step 3 is blocked until step 1's pattern is ratified.

## Checkability (G5) — binding

Every DoD is a file/state check: §8 present/absent per disposition; drafts' status lines; contract Function contains the binding line; /eval-rb docs exist.

## Uncertainties (G6)

- The /eval-meta coherence check may surface deeper mismatches (unknown) — tagged, not blocking step 1.
- /eval-rb authoring may surface schema questions (unknown) — tagged, blocked behind step 1 by design.
- Numbering note (supersedes the projection in DR-CMD-011's G6): this matter takes DR-CMD-012 in disposition order. The still-open `/pb-decide` remediation matter (from the `/eval-sc` report) moves to DR-CMD-013 on ratification; the `/eval-sc` family-membership candidacy moves to DR-CMD-014.

## Completion log

- 2026-09-20: step 1 complete — `/eval-pb` §8 matter disposed (DR-CMD-014), both drafts disposed (DR-CMD-015), contract binding added. Step 3 unblocked.
- 2026-09-20: step 2 complete — `/eval-meta` coherence check surfaced two material gaps → remediated (DR-CMD-013, union expansion: redirect step + Form B), contract binding added. No new DR for the remediation act.
- 2026-09-20: step 3 complete — `/eval-rb` implementation + design authored on the ratified `/eval-pb` pattern, contract binding added, drafts disposed (DR-CMD-017). **Sequence complete.**
