# Manual W-2 record format (v1)

Operator-keyed W-2 entry. The machine does not extract W-2s; the Operator
types them. One CSV file per W-2 (one employer, one tax year), using the
R23 Operator CSV v2 syntax (`taxprep/operator_csv.py`): UTF-8, header row
exactly `label,value`, standard CSV quoting.

## File

- Name: `w2-manual-YYYY-slug.csv` — e.g. `w2-manual-2024-acme.csv`.
  The slug is yours; document identity comes from the content hash (R4).
- The file itself is the Bronze source (exact bytes + hash, idempotent).
  Re-editing it supersedes the earlier version for the same
  (tax_year, employer_ein); old bytes stay for audit.
- Available v2 prefixes: `# ` headings, `% ` boilerplate (ignored),
  `! ` source-error audit notes (kept, never fields), `\` escape for a
  literal prefix-leading label. `@page` has no meaning here (no PDF) —
  leave it out.
- Ingested as form_type `W-2`, text_source `manual`, status
  `needs_review` — it goes through the review UI before Gold like every
  other source. Do not also ingest the same W-2's PDF; the two would not
  auto-resolve.

## Labels

Labels match case-insensitively with whitespace collapsed; the spellings
below are canonical. Unknown labels fail loud — never silently dropped.

| Label | Field key | Kind / rule |
|---|---|---|
| `tax_year` | (document attribute) | required, `YYYY` |
| `employer_name` | `employer_name` | required |
| `employer_ein` | `employer_ein` | required, `NN-NNNNNNN` |
| `1 Wages tips other compensation` | `1` | money |
| `2 Federal income tax withheld` | `2` | money |
| `3 Social security wages` | `3` | money |
| `4 Social security tax withheld` | `4` | money |
| `5 Medicare wages and tips` | `5` | money |
| `6 Medicare tax withheld` | `6` | money |
| `12a` … `12d` | `12a` … `12d` | `CODE AMOUNT`, e.g. `D 19500.00`; repeat as needed, omit unused |
| `13 Statutory employee` | `13_statutory` | `X` if checked, omit row if unchecked |
| `13 Retirement plan` | `13_retirement` | `X` if checked, omit row if unchecked |
| `13 Third-party sick pay` | `13_sick` | `X` if checked, omit row if unchecked |
| `14` | `14`, `14_2`, … | free text; repeatable, one row per item |
| `15 State` | `15_state` | optional, e.g. `CA` |
| `16 State wages` | `16` | money, optional |
| `17 State income tax` | `17` | money, optional |

## Value rules

- Money: `^\d+\.\d{2}$` — digits, one decimal point, exactly two
  decimals. No `$`, no commas, no parentheses. W-2 boxes are never
  negative. Anything else fails loud.
- Box 12: `^[A-Z]{1,2} \d+\.\d{2}$` — code, one space, amount.
- EIN: `^\d{2}-\d{7}$`.
- Omit any row whose box is blank on the form. Omit means blank;
  `0.00` means a printed zero — they are different.
- Box 12 letters follow the paper (`12a`–`12d` top to bottom).

## Example (synthetic values)

```csv
label,value
# W-2 2024 — Acme Corp,
tax_year,2024
employer_name,Acme Corp
employer_ein,12-3456789
1 Wages tips other compensation,52345.67
2 Federal income tax withheld,4321.00
3 Social security wages,52345.67
4 Social security tax withheld,3245.43
5 Medicare wages and tips,52345.67
6 Medicare tax withheld,758.99
12a,D 19500.00
12b,W 2500.00
13 Retirement plan,X
14,CA SDI 612.34
15 State,CA
16 State wages,52345.67
17 State income tax,2100.00
```

Field keys `1`–`6` are exactly what `verify.py` and transcript
reconciliation expect, so the manual record participates in coverage and
corroboration unchanged. Box 2 (federal withholding) flows to the 1040
total-withholding line through the normal path.
