# DR-CMD-114 — /pb-decide next-best-action: O2 adopted (build five findings, then bank)

- Status: adopted
- Date: 2026-10-03
- Selector: Peter (rendered "O2", ~18:56 PDT)

## Matter

The next best action on 2026-10-03 (second invocation that day;
DR-CMD-113's O1 is fully consumed — the R1–R8 arc banked as `8497c72`,
Arc A as `44e9886`). Context: Batch B (X1/R17/R18/G1/T1) is built and
verified at 460 passed / 5 skipped, uncommitted and ready to bank; the
workstation's audit of `44e9886` surfaced five new findings
(D5/F1b/G2/B1F/V1) awaiting disposition; Arc B (R16/R16a medallion) is
queued per the approved DAG; R19a adopted into Arc C scope alongside
R19/R15. The dsys front is quiet — the tranche-2 trigger unfired, PVB
DoD (DR-CMD-059) reserved, Half-2 inference-service docs deferred with
no new trigger.

## The /pb-decide (condensed)

Gates: G1 well-formed, G2 legitimate source, G3 non-redundant,
G4 actionable.

- **O1 — bank Batch B now, then build the five findings. Defer.** G1–G4
  pass, but G-flag: the workstation re-install would ship known
  silent-omission (F1b/G2 — `carryforward_ready` passes while lots are
  excluded for unknown term) and wrong-figure (B1F — box 1f counted as
  withholding credit) defects for a window. Unblocking the re-install
  does not justify banking known wrong-figure defects.
- **O2 — build the five findings first, then bank Batch B + fixes
  together. Adopt.** G1–G4 pass: the findings are small and adjacent to
  Batch B files (`transcript.py`, `extractors.py`, `verify.py`,
  `carryforward.py`); one clean re-install with no known silent defects
  is worth the short delay. No G-flags.
- **O3 — bank Batch B and park the five findings for Arc B/C. Refused
  on substance.** Silent omissions and wrong-figure tax logic on the
  core path do not park.
- **O4 — dsys matters (tranche-2, PVB DoD, Half-2 docs). Defer.** Gates
  pass, but they block nothing and have waited without cost.
- **G6 note:** the push to origin is not a playbook matter — Peter's
  separate explicit call (device flow), flagged not recommended.

## Disposition

Peter's selection: "O2" — the five findings are built now; banking of
Batch B + the fixes follows as a single push.

## Consequences

- **O2 taken up immediately:** the D5/F1b/G2/B1F/V1 build proceeds now
  (separate workstream); the combined Batch B + fixes bank as one
  `build/half1` push plus broadcast, on Peter's banking call.
- **R19a adopted into Arc C scope** alongside R19 (evidence pane) and
  R15 (provenance): per-field provenance links (cell crop within row +
  full-page highlight, geometry-keyed); computed fields show lineage;
  edited fields show original evidence + edit record.
- **Arc B (R16/R16a medallion + duplicate taxonomy)** remains queued
  per the approved DAG, after the combined bank.
- Nothing in the working tree changes from this disposition.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-115.

## State

**No commit, no push.** This disposition is a record only; the O2
build proceeds from here.
