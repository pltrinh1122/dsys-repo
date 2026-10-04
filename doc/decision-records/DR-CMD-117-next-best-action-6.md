# DR-CMD-117 — /pb-decide next-best-action: O1 adopted (bank two arcs as two commits, then R21)

- Status: adopted
- Date: 2026-10-04
- Selector: Peter (rendered "go O1", ~10:15 PDT)

## Matter

The next best action on 2026-10-04 (fourth /pb-decide invocation in the
tax-prep thread). Context: two arcs sat uncommitted on `build/half1`
(23 files) — the gate-fixes arc (X2b/B4/LINEAGE-1/X4/X3b/bus-guard,
verified 796/5) and the OCR arc (O1a/O1b/O2, verified 809/6). The
workstation operates `10b13b7` on real data; X4/X3b block its
account/ROA validation. Queued behind: R21 (per-person scoping +
column-A builder, disposition open), the B1–B3 perf arc, R20.

## The /pb-decide (condensed)

Gates: G1 well-formed, G2 legitimate source, G3 non-redundant,
G4 actionable.

- **O1 — bank as two commits (gate-fixes, then OCR), then build R21.
  Adopt.** G1–G4 pass: the workstation audits each head per the gate
  protocol and validates real account/ROA docs against X4/X3b today —
  it should get those fixes fastest, with the OCR arc separable behind
  them. One push delivers both commits.
- **O2 — bank as a single commit, then R21. Defer.** G1–G4 pass;
  coarser history, no sequencing advantage.
- **O3 — build R21 first, bank everything together. Defer.** G4
  G-flag on sequencing: delays validation-blocking fixes the
  workstation needs now.
- **O4 — dsys matters. Defer.** Unchanged (tranche-2 trigger unfired,
  PVB DoD reserved, Half-2 docs deferred).

G6 note (standing): the push to origin is Peter's separate explicit
call via the device flow.

## Outcome

Banked 2026-10-04 as two commits on `build/half1` (O1's two-commit
form honored despite hunk-level interleaving across extractors.py,
ingest.py, README.md — split verified line-clean, each arc's tests
green against its commit):

- `ee669d0` — X2b/B4/LINEAGE-1/X4/X3b + bus PII guard
- `efc5751` — OCR accuracy O1+O2 (O3 parked)

Full suite at `efc5751`: 809 passed, 6 skipped (verified twice).
Broadcast to the private store followed the push per the standing
protocol. R21 build queued next, pending its disposition.
