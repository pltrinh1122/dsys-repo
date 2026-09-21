# DR-CMD-008: No Glossary in the `/eval-sc` contract

- **Matter:** "Should `doc/slash-commands/eval-sc.md`
  include a Glossary?" Scope: the contract file only;
  the implementation doc's glossary untouched.
- **Disposition mode:** ratify. **Proposer:** Architect
  (enumerated, gated, drafted per `/pb-decide`).
  **Disposer / selector:** Peter (ratified 2026-
  09-20: "ratify O2").
- **Framing:** the contract is the M5 exemplar —
  minimum attention expenditure. Its specialized terms
  (`pointer`, Form B, `branch declaration`, `vacuous
  self-comparison`, `ambient agent`, `mutation matter`)
  are defined exactly once, in the bound implementation
  doc's glossary; bind-don't-restate covers terms too.
- **G5:** binding on the contract file. Checkable: no
  glossary section appears in
  `doc/slash-commands/eval-sc.md`; every specialized
  term it uses resolves to the glossary in
  `doc/eval-sc-implementation.md`, reached through the
  existing Function/Procedure binding.

## Options and gate trails

- **O1 — Include a Glossary.** G1–G4 pass. Not
  selected. Strongest case: the self-containment
  rationale — no other document need be opened; M5
  penalizes cross-document term lookup. Killed on
  substance: ~30% bloat of the 50-line M5 exemplar for
  a reader the file doesn't have (the contract's
  readers — invoking operator, executing agent — both
  travel contract → implementation); duplication of
  the implementation glossary with its drift surface;
  the self-containment rule's letter says "design
  document" and "acronyms" — the contract is neither,
  and its terms aren't acronyms.
- **O2 — Not include** (status quo, ratified). G1–G4
  pass. **Selected.** Terms defined once; the existing
  binding already carries the glossary; the contract
  stays the lean invocation contract.
- **O3 — Decide nothing.** Killed at G4: adopting it
  changes no commitment, state, or behavior; the matter
  was ripe.

## Consequences

- No glossary is added to the contract; its term load
  stays as-is.
- Bind-don't-restate now explicitly covers terms: the
  contract binds the implementation glossary, never
  duplicates it.
- A one-line terms-pointer was considered and rejected
  as redundant with the Function/Procedure binding.
- Numbering note: DR-CMD-008 had been named as the
  candidate number for `/eval-sc` family-membership
  ratification (`doc/eval-sc-design.md` G6); that
  candidacy moves to DR-CMD-009.

## Uncertainties (G6)

- Whether first-time standalone readers of
  `doc/slash-commands/` ever materialize in enough
  number to revisit; trigger would be observed
  lookup-cost complaints, none so far.
