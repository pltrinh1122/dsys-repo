# DR-CMD-014 — remove §8 "Remediation history" from `eval-pb-implementation.md` (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~18:33 PDT
- **Selector:** Peter (operator; framer and disposer the same person — explicitly recorded self-ratification per the playbook's Boundary clause)
- **Disposition mode:** ratify
- **Matter:** Should §8 "Remediation history" be removed from the draft `doc/eval-pb-implementation.md`, with provenance/reasoning living in `doc/eval-pb-design.md` — or left as-is? (Peter's principle: all provenance and reasoning belongs in the design document.)

## Options and gate trails

**O1 — Remove (selected).** Delete §8; durable provenance already migrated to the design doc.
- G1–G4: pass — precisely statable; sourced in Peter's principle + the family pattern (`eval-sc-design.md` holds reasoning; `eval-sc-implementation.md` holds procedure + execution evidence); no standing decision; changes the file.
- At disposition time the case strengthened: `eval-pb-design.md` §7 already holds both durable bullets (newly-specified pointer grammar; §4 operationalization) and §6 the open-binding bullet — deletion loses nothing; the draft-state bullets are spent at disposition.

**O2 — Leave (not selected).** G1/G3/G4 pass; G2 weakened past the point of viability — with the design doc's §7 in place, leaving §8 sustains *duplication* of the same provenance in two homes, against the family's defined-once principle (DR-CMD-008's spirit).

**O3 — Stub (not selected).** Survived gates, but its rationale evaporated: DR-CMD-010's status line already is the pointer to the design doc — a stub §8 would be a pointer to a pointer.

**O0 — Decide nothing: killed at G4**, per precedent.

## Decision

**O1 ratified.** §8 deleted from `doc/eval-pb-implementation.md` 2026-09-20. No migration needed (design §7 already holds the durable content); the draft-state bullets die at disposition.

## Consequences (G4)

One section deletion. The implementation doc now runs §§0–7 + Glossary, with provenance/reasoning solely in `doc/eval-pb-design.md` per the ratified principle and DR-CMD-010's reference edge.

## Checkability (G5) — binding

§8 absent from `doc/eval-pb-implementation.md`; design §7 present.

## Uncertainties (G6)

- Numbering note (superseded by DR-CMD-015's G6): the `/eval-pb` ratification took DR-CMD-015 in disposition order. The still-open `/pb-decide` remediation matter (from the `/eval-sc` report on `/pb-decide`) moves to DR-CMD-016 on ratification; the `/eval-sc` family-membership candidacy moves to DR-CMD-017.
- Step 1 of DR-CMD-012's sequence continues: implementation draft disposition and design draft disposition remain the operator's; the contract binding line rides that package.
