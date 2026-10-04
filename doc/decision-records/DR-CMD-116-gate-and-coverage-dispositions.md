# DR-CMD-116 — /pb-decide gate-and-coverage dispositions: Matter 1 O3, Matter 2 O2 (adopted)

- Status: adopted
- Date: 2026-10-04
- Selector: Peter (rendered "Matter 1 - O3" and "Matter 2 - O2", ~07:51 PDT)

## Matter

Two gate-semantics matters from the workstation's G-2 canary on real
TY2025 transcripts (canary_report `msg_d5054258e8b7`, Operator-approved
release, shapes only). Context: the gate-fixes arc (P1/P2/P3/X2, ROA
account-section split X3, transcript float cleanup) is built and
verified at 765 passed / 5 skipped, uncommitted and ready to bank;
the canary showed `carryforward_ready` reporting "ready" while
`extraction_yield` FAILs with phantom/0-field docs present.

**Matter 1 — Should extraction-yield failures and phantom docs block the
gold gate?**

**Matter 2 — Per-transcript-type parse-coverage release criterion**
(workstation's suggestion): even correctly classified, transcript
coverage stays thin — Return ~2.5%, Account ~24%, ROA ~4% — because the
label tables (~40 entries) face hundreds of real labeled lines.

## The /pb-decide (condensed)

Gates: G1 well-formed, G2 legitimate source, G3 non-redundant,
G4 actionable.

**Matter 1**

- **O1 — all yield FAILs block the gold gate. Deferred.** G1–G4 pass,
  but fail-closed to the hilt: thin-but-correct transcripts (Return
  ~2.5% coverage even when right) would block gold on *thinness*, not
  wrongness — noisy until the label tables grow.
- **O2 — block on wrongness signals only (`zero_yield` +
  `expected_coverage`), `parse_coverage` advisory. Deferred (was
  recommended).** Targets the canary's actual gap without conflating
  "we parse little" with "we parse wrong." Peter declined: machinery
  that distinguishes coverage from error is not needed by the Operator.
- **O3 — yield failures stay advisory (reported in Checks, never
  gate-blocking). Adopt.** Peter's reason: as the user, no-coverage and
  error appear the same — both land in front of him for judgment, so a
  gate that distinguishes them is machinery he doesn't need; he stays
  the decider (consistent with the standing rule "Operator as sole
  decider of filed figures"). No G-flags.

**Matter 2**

- **O1 — set per-type targets now. Deferred.** G1–G4 pass, but no
  principled basis for the numbers before the expansion work exists —
  a target set now would be a guess.
- **O2 — measure, then set. Adopt.** A future build arc expands the
  label tables toward real transcript breadth with per-type coverage
  measured; the blocking criterion is set from measured data afterward.
  No G-flags.
- **O3 — keep parse_coverage advisory permanently. Deferred.** The
  criterion is wanted; it is just sequenced after measurement.

## Disposition

Peter's selections: Matter 1 → "O3"; Matter 2 → "O2".

## Consequences

- **Matter 1 (O3):** no code change. The current advisory behavior —
  extraction-yield failures reported in Checks, never blocking the
  gold gate — stands as the adopted behavior. Peter remains the sole
  decider; coverage gaps and errors both surface to him for judgment.
- **Matter 2 (O2):** a future build arc expands the transcript label
  tables toward real transcript breadth with per-type parse-coverage
  measured; the blocking R18 criterion is set from that measured data,
  not guessed now. Queued behind the gate-fixes bank and the
  workstation's re-install gate.
- Nothing in the working tree changes from this disposition.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-117.

## State

**No commit, no push.** This disposition is a record only.
