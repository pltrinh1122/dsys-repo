# DR-CMD-104 — registrar_clerk registered; CLERK has its first member

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "Register registrar_clerk", ~18:58 PDT)

## Matter

Whether to register the `registrar_clerk` profile (adopted DR-CMD-096 with
load-bearing as-built deviation) now that tranche 1 of the tool-channel
disposition has landed (`tool-register-artifact` built and verified,
DR-CMD-103) and the profile compiles green.

## Disposition

Register. `registrar_clerk` added to `PROFILE_SET_002` and
`PROFILE_ARCHETYPES_002` (archetypes `("clerk",)`); `CLERK.members` goes
from `()` to `("registrar_clerk",)`. Per DR-CMD-098's population rule the
profile joins the exemplar battery automatically on registration — no
further disposition required for joining.

## Verification

- Set-002 run: 3/3 green — wright, registrar, registrar_clerk all
  `verified`, `operable=True`.
- Archetype self-test: 10 exemplars, zero violations (was 9).
- Negative controls unchanged (staff/executor still refuse clerk for the
  right reasons).

## Consequences

- The Tetrad's fourth cell is now populated: CLERK has its first runnable
  member. The DR-CMD-094 populate trigger is satisfied in the single-profile
  instance; DR-CMD-098's population rule governs further joining.
- `triager` and `dr_registrar` remain correctly excluded (compile-refused,
  tranche 2 not authorized); they join on registration with green set runs.
- The working name `registrar_clerk` remains provisional-in-name-only; final
  naming is Peter's disposition (DR-CMD-096 flag carried forward).

Next free identifier: DR-CMD-105 (DR-CMD-059 still reserved for PVB DoD).
