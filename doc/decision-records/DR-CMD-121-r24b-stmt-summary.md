# DR-CMD-121 — R24(b): broker consolidated-1099 summary extractor

- Status: adopted (built)
- Date: 2026-10-11
- Selector: Peter (R24 O1, landing order (a)+(d) -> (b) -> (c))

## Matter

R24 build request (`msg_1600621718eb`), part (b): `taxprep stmt-summary`
— parse broker consolidated-1099 PDFs at SUMMARY level (per account, per
Form 8949 box) and emit the seed-sheet CSV that `taxprep chain` (R24(a))
consumes, plus per-file statement records and a reconciliation report.
The workstation gated (b) on the label vocabulary; the blind label
census arrived (`msg_aa4c4b4d3e4b`: 23 statements, 2 layouts — Fidelity
+ second payer — 21 column headers, 6 section titles, 58 row labels,
shape-only Tier 2) and is the agreed vocabulary. Keep (b) small; land
as soon as the vocabulary is agreed.

## Outcome

Built 2026-10-11 on `build/half1` (commit recorded below):
`taxprep/stmt_summary.py` + `tests/test_r24_stmt_summary.py` (17
tests), `stmt-summary` subcommand wiring in `taxprep/cli.py`. Full suite
deterministic (`-p no:randomly`): all green, zero regressions.
Local-only: batched push with (a)+(d) per the standing batch rule; push
is Peter's separate explicit call.

What it does:

- Parses consolidated-1099 PDFs (text only, no OCR) with a
  label-anchored geometry parse on pdfplumber word boxes, using the R23
  two-column capture (`twocol.group_into_lines`, largest-gap split
  discipline) as the template. Column detection from header-word
  alignment; pdfplumber `x_tolerance=2` so adjacent table columns never
  merge.
- Layout 1 (Fidelity): summary-table rows for 8949 boxes A/B/D/E with
  Proceeds | Cost Basis | Market Discount | Wash Sales Disallowed |
  Gain/Loss | Income Tax Withheld columns. Per-row net check:
  printed Gain/Loss vs proceeds − cost + wash, cent-exact, mismatch
  flagged loud (printed value kept as authoritative).
- Layout 2 (second payer): 'Box <A–F> <Short|Long>-Term Realized
  Gain/Loss' rows netted to gain − loss (proceeds/cost absent by
  construction, flagged `proceeds_only_box`); 'Box B or Box E'
  ambiguous rows reported by label text, never guessed; total rows
  skipped, never seeded.
- Per file: payer EIN, account → opaque id `sha256(EIN + number)[:8]`
  (never the number), tax year, recipient → person-N via `--persons-file`
  (never printed), corrected flag, 1099-DIV boxes 1a/1b/2a/2b/2c/2d/2e/2f/3/5/7,
  1099-INT boxes 1/3/8, federal withholding. Money as Decimal-safe
  strings, never floats.
- Duplicates keyed (EIN, acct id, period): corrected wins, else richest,
  else first-seen (stable); pairs reported by file id.
- Reconciliation per year (pass/fail + counts on stdout, diffs to
  file): per-box sums vs as-filed Schedule D per-category lines parsed
  from the Return Transcript CSVs with chain.py's own label vocabulary
  (basis + basis_no_adj both roll into the 8949 box), cent-exact;
  per-year totals vs the W&I partial sum (same proceeds rule as (a)).
- Outputs: `packets/<year>/statements.json`,
  `packets/<year>/seed-sheet.csv` (exact (a) schema, verified by parsing
  it with `chain._parse_seed_sheet` in tests),
  `packets/<year>/reconciliation.json`. 0700 dirs, 0600 files.
- `taxprep stmt-summary --template` writes an empty seed-sheet.csv whose
  placeholders fail loud under (a)'s reader (cf. the W-2 template).
- Blind-safe throughout: stdout carries only labels, counts, flags,
  years, file ids, check names and paths; asserted by tests that scan
  captured stdout for money values, EINs, account digits and names.

Deliberate scope boundaries and deviations from the bus spec:

- The `--labels` vocabulary file extends a built-in default seeded from
  the census (so it works out of the box); unmatched labels are
  reported by label text for blind census extension, per the census
  note's request.
- 1099-DIV/INT/withholding land in `statements.json` only, not the seed
  sheet: (a)'s seed reader accepts 8949 boxes A–F only, and changing it
  would alter the already-landed (a). The (c) packet builder can consume
  DIV capital-gain distributions from `statements.json`.
- Unknown-term rows are excluded from the seed and flagged (the term is
  genuinely unknown; guessing would corrupt the chain). The Schedule D
  reconciliation diff then surfaces them for Operator disposition —
  the system working as designed.
- `term` on seed rows is written explicitly ("st"/"lt") as well as
  being inferable from the box letter.
- pdfplumber is imported lazily inside the parse path; `taxprep.chain`
  stays stdlib-clean (its import-blocker test still passes).

G6 note (standing): the push to origin is Peter's separate explicit
call via the device flow; this landing batches with (a)+(d) per the
2026-10-11 batch rule, with per-part `code_landed` broadcasts.
