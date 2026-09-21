# DR-CMD-026 — Feature-expansion playbook: exercise-then-remediate (O2)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:31 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Next best action for remediating the DRAFT
  feature-expansion playbook — four known items (applicable shared
  disposition-mode subset; executed admit/kill exercise before
  reference candidacy; G3 duplicate-merge routing; draft-verdict
  `refuse` vs operator-disposition `reject` distinction) — before it
  is a reference candidate and `/pb-extend` leaves rehearsal-only.

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — remediate, then exercise:** survived; not selected. Applies
  the four fixes now, then runs the 'updater' matter as the admit/kill
  exercise. Fastest if the list is complete. Lost on rework risk: the
  list is a hypothesis until a run tests it.
- **O2 — exercise, then remediate:** survived; selected. Rehearse the
  'updater' matter through the current draft first (rehearsal needs no
  disposition modes — findings are would-admit/would-kill), let the run
  confirm or extend the fix list, then remediate, bootstrap-evaluate,
  and present for disposition. This is how the decision-making
  playbook earned E1–E5/E7 — the fix list came from executed runs, not
  from reading the spec. Also advances the 'updater' matter,
  undisposed since 2026-09-20. G1–G5 ✓.
- **O3 — defer:** survived; not selected. Legitimate (no live consumer
  forces the issue) but strands both the playbook and the 'updater'
  matter indefinitely.
- **O4 — decide nothing:** the null. Not selected — the question is
  live and cheap to answer.

## Decision

**Ratified O2.**

## Consequences (G4)

1. Rehearsal run of the 'updater' matter (admit case) plus one
   deliberately out-of-scope matter (kill case) through the current
   draft playbook — findings would-admit/would-kill, no disposition.
2. Fix list confirmed or extended by the rehearsal.
3. Spec remediated against the confirmed list.
4. Bootstrap-evaluate; present the playbook for disposition.
5. Step 1 is gated on the operator's confirmation that 'updater' is
   still a live matter (G6) — the ratified verdict's own terms.

## Checkability (G5)

Binding. Checkable: a rehearsal transcript exists citing the draft
spec sections exercised (or not); subsequent spec edits cite
rehearsal findings (or not).

## Uncertainties (G6)

- 'updater' currency — confirm before running the rehearsal.
- Whether the four-item list survives contact with the rehearsal —
  this is precisely what O2 tests.
- Numbering (disposition order): this ratification takes **DR-CMD-026**.
