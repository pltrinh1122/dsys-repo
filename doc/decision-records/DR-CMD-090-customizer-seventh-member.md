# DR-CMD-090 — customizer admitted as seventh member of the factory profile set

- **Status:** ratified
- **Date:** 2026-09-27 ~12:14 PDT
- **Matter:** Whether the customizer becomes a seventh member of the ratified
  six-profile factory set (DR-CMD-068). Framed by the ambient as the
  outstanding disposition after the customizer was built and verified
  standalone. Separator: Peter.

## Disposition

Peter rendered "yes, customizer is a seventh member" (~12:14 PDT
2026-09-27). The set-001 profile set is now **ratified as seven members**;
`core/package/factory_profile_set_001.py` amended accordingly (DR-CMD-068
stands, amended by this record).

## Implementation (under this record)

- `PROFILE_SET_001` gains `"customizer": customizer_profile`; archetypes
  `(staff, office)`; STAFF/OFFICE member tuples updated; header records
  the amendment.
- Verification observed 2026-09-27: archetype self-test 7/7, zero
  violations; set-001 run 7/7 verified (customizer: D1 0.0,
  D2 principal_wins_ties, D3 0.5, D4 1.0, D5 0.0, D6 None, D7 0.75);
  factory golden run 192 passed (was 183).

## Dialectic trail (same turn)

Peter's accompanying claim — *"Factory isn't included in the set because
it's the consumer of the profiles"* — was ordered falsified and
**falsified**:

1. The factory *is* profiled: DR-CMD-076 ratified the factory self-profile
   (D1 0.0, D2 0.0, D3 0.0, D4 1.0, D5 0.0, D6 {operator}, D7 0.75). The
   claim conflates being-profiled with being-a-member of the built set.
2. Every member consumes (customizer reads registry/staging, executor
   reads dispositions, monitor reads world state) — consumption
   distinguishes nothing.
3. The demonstrated line is **builder-vs-built**: that morning the factory
   built the customizer (staged → drive → verified). The set is the
   factory's build output; the factory is not its own output.
4. Peter's own admission refutes the claim: the customizer exists to feed
   the factory — the most consumer-adjacent member possible — and was
   just seated.

Survivor: the factory isn't a member because it is the builder, not the
built. Nothing about consumption.

## Consequences

- The ratified profile set is seven; "the six profiles" phrasing in
  set-001 docs is superseded.
- Set-002 (wright, registrar) is untouched by this record.
- Work remains uncommitted on `build/half1` (no push authority granted).

## Uncertainties (G6)

- Whether the seven-member set should be re-labeled (e.g. "Septet" vs the
  standing "Sextet" for the six actors) — undisposed.

Next free identifier: DR-CMD-091 (DR-CMD-059 still reserved for PVB DoD).
