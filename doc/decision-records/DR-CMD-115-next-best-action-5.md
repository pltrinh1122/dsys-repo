# DR-CMD-115 — /pb-decide next-best-action: O1 adopted (bank Arc B, then Arc C)

- Status: adopted
- Date: 2026-10-03
- Selector: Peter (rendered "O1", ~23:43 PDT)

## Matter

The next best action on 2026-10-03 (third invocation that day;
DR-CMD-114's O2 is fully consumed — Batch B + the five audit findings
banked as `00cc314`, the `addresses` tag on `code_landed` broadcasts as
`41ca53c`, broadcast `3008ab6` carrying the re-install gate addresses).
Context: Arc B (R16/R16a medallion ingestion + duplicate taxonomy +
conflicts) is built and verified at 565 passed / 5 skipped,
uncommitted and ready to bank; Arc C (R13 state machine, R15 provenance,
R19/R19a evidence pane, R12 console) is queued per the approved DAG.
The dsys front is quiet — the tranche-2 trigger unfired, PVB DoD
(DR-CMD-059) reserved, Half-2 inference-service docs deferred with no
new trigger.

## The /pb-decide (condensed)

Gates: G1 well-formed, G2 legitimate source, G3 non-redundant,
G4 actionable.

- **O1 — bank Arc B now, then build Arc C. Adopt.** G1–G4 pass: the
  medallion is a storage-layer migration (JSONL → SQLite, new identity
  scheme) and the workstation audits each head per the gate protocol —
  it should audit this head before the console piles on top. Gets the
  E2 double-count fix and gold gating into its hands fastest. No
  G-flags.
- **O2 — build Arc C first, then bank B+C together. Defer.** G1–G3
  pass; G4 passes but G-flag on sequencing: Arc C is the biggest arc
  yet (state machine + provenance + geometry + console UI), and holding
  the bank delays the medallion audit and the re-install procedure by
  the whole build.
- **O3 — bank Arc B and defer Arc C. Defer.** Legitimate on substance
  (nothing in Arc C blocks the re-install), but not recommended —
  R19/R19a is the Operator's specified requirement and the console is
  the Operator's operating surface; deferring leaves the review UI
  behind the new storage model.
- **O4 — dsys matters (tranche-2, PVB DoD, Half-2 docs). Defer.** Gates
  pass, but they block nothing and have waited without cost.
- **G6 note:** the push to origin is not a playbook matter — Peter's
  separate explicit call (device flow), flagged not recommended.

## Disposition

Peter's selection: "O1" — Arc B banks now; Arc C builds next.

## Consequences

- **O1 taken up immediately:** Arc B commits on `build/half1` (this
  record + the medallion work); the push + broadcast follow on Peter's
  banking call.
- **Arc C builds next** per the approved DAG: R13 (lifecycle state
  machine, local transition table), R15 (field provenance), R19/R19a
  (source-evidence pane — per-field provenance links, cell crop within
  row + full-page highlight, geometry-keyed), R12 (Operator console).
- Nothing else in the working tree changes from this disposition.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-116.

## State

**Commit, no push.** This disposition records the Arc B commit; the
push remains Peter's separate explicit call.
