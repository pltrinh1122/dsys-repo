# DR-CMD-112 — `eval-sc` implementation doc: test-drive material and Glossary RETAINED

- **Status:** ratified (selection among /pb-decide options)
- **Date:** 2026-09-28 ~15:20 PDT
- **Selector:** Peter (operator; rendered "O1"; proposer = ambient
  agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** "Should `doc/eval-sc-implementation.md` retain its
  §7/§8 test-drive material and its Glossary?"

## Framing

The implementation doc currently holds, after the procedure
(§§0–6): §7 worked example (~120 lines — the only instantiated
report); §8 test-drive record (two real 2026-09-20 runs — parse,
pointer resolution, admission, S1–S5/M1–M5 mapping, three-section
report — plus the 2026-09-20 remediation re-mapping, recorded as
mechanical presence plus the run's original one-line role judgments,
explicitly not a re-execution, with the refusal-path gap labeled as
a gap, not a finding); and a 17-term Glossary (self-containment
rule: every acronym and specialized term used in the document is
defined here).

DR-CMD-008 already settled the *contract* file: no glossary in
`doc/slash-commands/eval-sc.md` — the contract's terms bind the
implementation's glossary, never duplicate it. This matter concerned
the *implementation* file only; DR-CMD-008 does not dispose it.

This was a restart: the original /pb-decide run on this matter was
interrupted before disposition on 2026-09-20 and nothing from it was
decided. The doc was verified byte-identical to the interrupted
run — the run was reframed from a clean matter state on 2026-09-28.

## Options and gate trails

- **O1 — Keep both (status quo).** G1–G4 pass. **SELECTED.**
  Strongest case: the Glossary is load-bearing, not decorative —
  DR-CMD-008's ratified framing makes it the /eval-sc pair's single
  term home (bind-don't-restate covers terms), and DR-CMD-006 puts
  definitions in implementation files; §7 is the only instantiated
  report — §6's output contract is specified but never shown without
  it; §8 is honest provenance — dated, self-labeled as history, with
  its open gap stated, so it cannot mislead. The single concern holds
  by layout (procedure §§0–6, worked material §§7–8).
- **O2 — Keep the Glossary, remove §7/§8.** G1–G4 pass. Not
  selected. Strongest case: M5 single-concern human verifiability —
  the doc's concern is the execution procedure; run records are an
  audit trail, a different concern, referencing dead commits
  (49e2546, 0fb3091) that rot, and the evidentiary value of a
  2026-09-20 run decays while the stated gap (refusal paths
  untested) stays open. Lost on substance: the provenance is
  explicitly labeled history rather than live procedure, and the
  worked example is the procedure's only concrete report instance.
- **O3 — Keep §7/§8, remove the Glossary.** Killed on substance:
  orphans the contract's bound terms — bind-don't-restate with
  nothing to bind to; contradicts DR-CMD-006 and the ratified
  DR-CMD-008 framing.
- **O4 — Remove both.** Killed on substance: same term-orphaning
  as O3, plus loses the only report instance.
- **O5 — Decide nothing.** Killed at G4: adopting it changes no
  commitment, state, or behavior; the matter was ripe.

## Consequences

- No document changes — status quo kept: §7 worked example, §8
  test-drive record, and the Glossary stay in
  `doc/eval-sc-implementation.md`.
- The draft verdict from the restarted run (O1) is confirmed by
  this ratification.

## Uncertainties (G6)

- Whether the test-drive record's aging references (the 2026-09-20
  runs, the dead-commit pins) ever warrant revisiting; trigger would
  be observed confusion from a reader, none so far.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done —
  **not consumed**.
- Next free identifier: DR-CMD-113.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the
selection only): this record. Commit and push return as follow-on
dispositions.
