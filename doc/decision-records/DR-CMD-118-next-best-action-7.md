# DR-CMD-118 — /pb-decide next-best-action: O1 adopted (bank R21, then repair arc)

- Status: adopted
- Date: 2026-10-04
- Selector: Peter (rendered "O1", ~11:10 PDT)

## Matter

The next best action on 2026-10-04 (fifth /pb-decide invocation in the
tax-prep thread). Context: R21 (per-person scoping + column-A builder)
built and verified at 839/6, uncommitted and ready to bank. The
workstation's gate audit on `ee669d0`/`efc5751` (G-1/G-2 PASS, G-3
813/1/1) left a repair arc: T2 blank-fixture test failure, O1a
ineffective on real tesseract (14/50 lots), O2 broken on the force-ocr
route (`ingest.py:1159` route gate), C1 corroboration never comparing
("still_unusable" on any unparsed line). The workstation still operates
`10b13b7`. Queued behind: B1–B3 perf, R20, R21 console UI wiring.

## The /pb-decide (condensed)

Gates: G1 well-formed, G2 legitimate source, G3 non-redundant,
G4 actionable.

- **O1 — bank R21, then build the repair arc. Adopt.** G1–G4 pass:
  R21 is verified and independent of the repairs; the repairs fix
  real-engine gaps in the just-banked OCR work that will bite on real
  scans. Correctness on real data before perf.
- **O2 — build repairs first, bank together. Defer.** Delays verified,
  independent R21 for unrelated fixes.
- **O3 — bank R21, then B1–B3 perf, repairs later. Defer.** Wrong
  order — correctness before speed.
- **O4 — dsys matters. Defer.** Unchanged.

G6 note (standing): the push to origin is Peter's separate explicit
call via the device flow.

## Outcome

R21 banked 2026-10-04 as `3077040` on `build/half1` (839/6 green).
Repair arc build queued next per O1.
