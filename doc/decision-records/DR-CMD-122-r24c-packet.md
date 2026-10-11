# DR-CMD-122 — R24(c): per-year 1040-X entry packet builder

- Status: adopted (built)
- Date: 2026-10-11
- Selector: Peter (R24 O1, landing order (a)+(d) -> (b) -> (c)); Operator
  directed via bus to parallelize (c) alongside the (a)+(d) bank.

## Matter

R24 build request (`msg_1600621718eb`), part (c): `taxprep packet` —
per-year 1040-X entry packets from the (a)+(b) packets tree. Column-A
sheet (1040-X lines 1–23 via `column_a.COLUMN_A_LINES`, PER COMPUTER
variant used and marked where variants differ); change lines
(Schedule D lines 6/14 carry-in, derived 7/15/16/21, Form 1040 line 7)
with expected column-C direction; Part II explanation template; CA
Schedule X mapping; Form 8814 note; definition-of-done checklist.
Outputs per year: `packet.md` + `packet.json` (values in files; stdout
counts only).

## Outcome

Built 2026-10-11 on `build/half1` (commit recorded below):
`taxprep/packet.py` + `tests/test_r24_packet.py` (13 tests), `packet`
subcommand wiring in `taxprep/cli.py`. Full suite deterministic
(`-p no:randomly`): all green, zero regressions. Local-only: batched
push with (a)+(d)+(b) per the 2026-10-11 batch rule; push is Peter's
separate explicit call.

What it does:

- Reads `packets/<year>/diagnostic.json` (+ `packets/chain.json`) from
  (a) and, for the column-A sheet, re-scans the Operator's format-v2
  transcript CSVs with (a)'s own machinery (`chain._discover`,
  `_YearScan`, `_scan_file`) — the column-A values come from the same
  scan (a) used, never a parallel implementation.
- Change lines derived strictly from the frozen engine's line concepts
  (`compute_year`: line7 = st_current − st_carry_in, line15 likewise,
  line16 = sum, line 21 = allowable loss deduction): as-filed (A) from
  the diagnostic's as-filed nets, correct (C) from the chain's
  carry-ins/inputs/worksheet L2, change (B) = C − A, signed direction
  per line. As-filed 1040 line 7 is derived = as-filed Sch D L21
  (return construction), stated in the packet.
- Column-A variant rule per spec: PER COMPUTER wins and is marked
  wherever as-entered vs PER COMPUTER differ; missing/unscoped lines
  marked, never guessed.
- 2022 gets a seed-diagnostic packet only — no 1040-X. Reading
  confirmed against the spec + pivot: 2022 is the seed year; the
  amendments are 2023–2025.
- Part II template filled with carryover facts (years, ST/LT amounts,
  direction), Operator-editable brackets for prose. CA Schedule X
  always marked Operator-filled (no CA transcript exists in the packet
  inputs). Form 8814 note emitted iff the year's diagnostic lists
  f8814 (no action; software recompute covers it).
- Affected 1040-X lines: L1 moves 1:1 with the 1040-L7 change (all
  else equal); L5 by the diagnostic's taxable-income delta; L6/L11 tax
  is explicitly software-recomputed — the packet never derives tax.
- Blind-safe throughout (values to files only; asserted by a
  stdout-scan test). 0700 dirs, 0600 files. stdlib-only at module load:
  `packet` added to the import-blocker subprocess coverage.

Deliberate scope boundaries and deviations from the bus spec:

- `--csv-dir` is accepted (same meaning as in (a)) for the column-A
  sheet; without it the sheet is marked unavailable and the packet
  records a blocker (fail loud, exit 1) rather than silently omitting.
- As-filed 1040 line 7 is not a transcript label in (a)'s vocabulary;
  it is derived = as-filed Sch D L21 and labeled as derived.
- The packet does not recompute tax/total tax (L6/L11): no tax tables
  in the package; the DoD checklist requires the software recompute.

G6 note (standing): the push to origin is Peter's separate explicit
call via the device flow; this landing batches per the 2026-10-11
batch rule, with per-part `code_landed` broadcasts.
