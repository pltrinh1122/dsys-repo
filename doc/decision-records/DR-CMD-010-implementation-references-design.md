# DR-CMD-010 — `*-implementation.md` references its `*-design.md` counterpart (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~18:20 PDT
- **Selector:** Peter (operator; framer and disposer the same person — explicitly recorded self-ratification per the playbook's Boundary clause)
- **Disposition mode:** ratify
- **Matter:** Should the family schema require every `*-implementation.md` to carry a reference to its `*-design.md` counterpart?

## Options and gate trails

**O1 — Ratify (selected).** Schema rule: every `*-implementation.md` names its bound `*-design.md` counterpart in a header-adjacent prose line, in the exemplar's form.
- G1 well-formed: pass — precisely evaluable (line exists, header-adjacent, names `doc/<name>-design.md` with status; exemplar `doc/eval-sc-implementation.md:3` is the template).
- G2 legitimate source: pass — (a) Peter's principle that provenance/reasoning lives in the design doc; (b) DR-CMD-006's bind-don't-restate pattern extended to the implementation→design edge; (c) the exemplar's own existing practice (ratifies, invents nothing).
- G3 non-redundant: pass — no standing decision mandated it. DR-CMD-006 covers contract→implementation; DR-CMD-007 deferred machine-readable front matter only, a different mechanism.
- G4 actionable: pass — records the rule; `eval-pb-implementation.md` gains the line; future implementation docs conform by construction.

**O2 — No ratify (not selected).** Schema unchanged; the reference stays convention.
- G1–G4: pass (explicit sustain; status quo already contains the reference in the exemplar; closes the matter). Not selected: convention leaves the split undiscoverable by machinery and provenance placement unenforced.

**O0 — Decide nothing: killed at G4** — adopts no commitment, state, or behavior change (precedent: earlier `/pb-decide` matter).

## Decision

**O1 ratified.** DoD: every `*-implementation.md` carries the counterpart line in the exemplar's form ("Implements `doc/<name>-design.md` (STATUS)" or equivalent naming); a nonexistent counterpart is named with its status explicit ("not yet authored"), never silently omitted.

## Consequences (G4)

- Schema rule in force for the `*-implementation.md` / `*-design.md` family edge.
- `doc/eval-pb-implementation.md` status line amended to name `doc/eval-pb-design.md` (not yet authored) as its design counterpart.
- Future implementation docs conform by construction.

## Checkability (G5) — binding

Grep per implementation file for the counterpart line: present and naming `doc/<name>-design.md` (status explicit) = holds.

## Uncertainties (G6)

- The sibling matter (remove-or-leave §8 "Remediation history" in `eval-pb-implementation.md`) is still open; if its O1 is ratified, this line becomes the load-bearing pointer for the migrated provenance. No blocking coupling.
- Disposed as one-off ratify; whether to additionally record as standing policy (`set_standing`) left to the operator.
- Numbering note: DR-CMD-010 was previously earmarked for the still-open `/pb-decide` remediation matter (from the `/eval-sc` report); assigned here in disposition order instead. On its ratification that matter takes DR-CMD-011, and the `/eval-sc` family-membership candidacy moves to DR-CMD-012.
