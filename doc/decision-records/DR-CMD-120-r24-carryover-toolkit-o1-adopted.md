# DR-CMD-120 — R24 carryover-amendment toolkit: O1 adopted (build as specified)

- Status: adopted
- Date: 2026-10-11
- Selector: Peter (rendered "O1", ~06:28 PDT)

## Matter

R24 build request (`msg_1600621718eb`, Operator-approved 2026-10-11,
following the carryover-only pivot `msg_3e0cd90159d8`): a
carryover-amendment toolkit in four parts — (a) `taxprep chain`
carryover chain + diagnostic CLI over the Operator's transcript CSVs
plus an optional 2022 seed sheet, (b) `taxprep stmt-summary` broker
consolidated-1099 summary extractor with Schedule D reconciliation,
(c) `taxprep packet` per-year 1040-X entry packets, (d) packaging /
environment. Landing order (a)+(d) -> (b) -> (c), each landing
separately with its own `code_landed` so the workstation gate-audits
and installs parts independently. This DR covers the (a)+(d) first
landing only.

## The disposition (condensed)

- **O1 — build as specified, in landing order, `code_landed` per part.
  Adopt.** The spec is precise, the blind-safety rule is explicit
  (never print a monetary or identity value; stdout carries only
  labels, counts, flags, years, file ids, check names, paths; values go
  to files under `--out`), and the per-part landing *is* the checkpoint
  mechanism.
- **O2 — build (a)+(d) first, hold (b)/(c) for a workstation checkpoint
  on the chain semantics. Defer.** Adds a gate the request already
  designed in via per-part landings.
- **O3 — defer. Defer.** R24 is the critical path under the pivot.

## Outcome

Built 2026-10-11 on `build/half1` (commit recorded below):
`taxprep/chain.py` + `tests/test_r24_chain.py` (19 tests), `chain`
subcommand wiring in `taxprep/cli.py`, packaging declaration in
`pyproject.toml`. Full suite deterministic (`-p no:randomly`): all
green, zero regressions. Local-only: push is Peter's separate explicit
call.

Deliberate scope boundaries and deviations from the bus spec:

- Worksheet line 1 is derived as AGI − deductions − QBI (never the
  floored taxable-income line). If any component is missing for a year,
  the `no_engine_fallback` check FAILS and the run exits 1 without
  calling the engine — the frozen engine's "assume enough ordinary
  income" path can never engage silently.
- "Deduction allowed" is the worksheet's L4 (what actually reduced
  taxable income), not line 21; they differ in low-income years.
- The 2022 seed-vs-filed category comparison maps 8949 boxes to
  Schedule D categories (A/B/C -> ST basis/no-basis/no-1099b,
  D/E/F -> LT equivalents); mismatches fail the run by category name.
- Filing status comes from `--filing-status`, else a transcript
  "filing status" label, else loud failure (the spec is silent; the
  frozen engine requires it). Carryover into 2022 via
  `--prior-st/--prior-lt` (default 0).
- Packaging: `requires-python = ">=3.12"` (3.12 primary, 3.14
  supported); `pdfplumber` + `pdf2image` moved to the optional `pdf`
  extra. The chain path was verified (subprocess test with an import
  blocker) to run with pdfplumber/pdf2image/pypdf unimportable.
  `pypdf`/`cryptography`/`mcp` stay hard deps (lightweight; the spec's
  bar is pdfplumber at module load).
- The spec's "original/corrected statement pair" fixture belongs to
  (b)'s duplicate handling and is deferred to that landing.

G6 note (standing): the push to origin is Peter's separate explicit
call via the device flow.
