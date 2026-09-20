# DR-CMD-006: Keep `/eval-sc` definition and implementation doc separate

- **Matter:** "Consolidate `doc/slash-commands/eval-sc.md` +
  `doc/eval-sc-implementation.md` into a single file, or
  keep them separate." Scope: the definition/implementation
  pair only; `doc/eval-sc-design.md` untouched either way.
- **Disposition mode:** ratify. **Proposer:** Architect
  (enumerated, gated, drafted per `/pb-decide`).
  **Disposer / selector:** Peter (ratified 2026-
  09-20: "ratify O2").
- **Framing:** "Bind, don't restate: the definition is the
  invocation contract (human-verifiable, minimum
  attention); the implementation doc is the execution
  detail."
- **G5:** binding on the file pair. Checkable: the two
  files remain separate; the definition's Procedure
  section binds `doc/eval-sc-implementation.md` without
  restating it.

## Options and gate trails

- **O1 — Consolidate** (single ~350-line file). G1–G4
  pass. Not selected. Strongest case: drift between the
  files becomes impossible (the M1–M4/M1–M5 drift fixed
  2026-09-20 is exhibit A); one file, one pin. Killed on
  substance: breaks the family's load-bearing
  bind-don't-restate pattern; bloats the definition
  against M5 (the exemplar of "minimum attention
  expenditure" must itself be minimal); forces the
  exemplar's own S1 Function/Procedure section into a
  shape no other command uses, weakening its
  self-exemplification.
- **O2 — Keep separate** (status quo, ratified). G1–G4
  pass. **Selected.** Preserves the family pattern;
  definition stays 63 lines — M5 exemplar par
  excellence; separation of concerns (invocation
  contract vs execution detail); the design-doc
  self-containment rule already answers the
  two-file objection.
- **O3 — Decide nothing.** Killed at G4: adopting it
  changes no commitment, state, or behavior; the matter
  was ripe.

## Consequences

- The eval-sc pair stays as two files; no consolidation
  work.
- Bind-don't-restate is now the ratified standing
  file-organization principle for slash-command
  definitions (previously a de facto pattern).
- Numbering note: DR-CMD-006 had been named as the
  candidate number for `/eval-sc` family-membership
  ratification (`doc/eval-sc-design.md` G6); that
  candidacy moves to DR-CMD-007.

## Uncertainties (G6)

- Drift risk between the pair remains (it already bit
  once); mitigation is discipline, not structure: grep
  the dimension enumerations when editing either file.
- Whether the principle should be enforced mechanically
  (e.g. a validator) is unconsidered.
