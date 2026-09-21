# DR-CMD-022 — Decision-making playbook consolidation ratified

- **Status:** ratified
- **Date:** 2026-09-21 ~05:24 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Ratify the consolidated `doc/decision-making-playbook-spec.md`
  as the canonical decision-making playbook text.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — ratify as-is:** survived; selected. The consolidation is faithful:
  canonical §8.2/§8.3 text, DR-1..DR-4, E1–E5/E7 with the stale
  "Spec-only" header corrected (implemented in
  `core/package/{schema,validators,golden_run}.py` under DR-4), new §1
  Applicability (trigger + non-trigger cases), new §2 Exercise (executed
  golden run 2026-09-21: ok=True, 0 violations, 37 refusals), Glossary.
  `/eval-pb` re-run on the consolidated bytes: conforms 10/10. G1 ✓
  (genuine matter), G2 ✓ (performed at the operator's direction; the
  Architecture cites the file as canonical, so the question is live),
  G3 ✓ (DR-1..DR-4 ratified the machinery, not the consolidation act —
  no duplicate), G4 ✓, G5 ✓ (file exists; Architecture pointers exist).
- **O2 — ratify with amendments:** survived as a variant. No amendments
  named — not selected.
- **O3 — decline / remand:** survived as the null. Not selected: the
  Architecture already cites the file as "Canonical text"; leaving it
  unratified would leave a standing contradiction between the
  Architecture's citation and the file's standing.

## Decision

**Ratified O1.** `doc/decision-making-playbook-spec.md` is the canonical
decision-making playbook. No file changes required — the consolidation,
the Architecture pointers (§8.2 canonical text, §8.3 canonical records),
and the inventory line (DR-CMD-021) are already in place.

## Consequences (G4)

The canonical-text question is closed. Future playbook amendments go
through the playbook's own machinery (START/STOP/KEEP, disposition,
record).

## Checkability (G5)

Binding. Checkable: the file exists at
`doc/decision-making-playbook-spec.md` with the consolidated sections
(or not); the Architecture §8.2/§8.3 pointers resolve to it (or not).

## Uncertainties (G6)

- None blocking. Revisit trigger: a substantive amendment to the
  playbook's machinery, which re-enters START under its own rules.
- Numbering (disposition order): this ratification takes **DR-CMD-022**.
