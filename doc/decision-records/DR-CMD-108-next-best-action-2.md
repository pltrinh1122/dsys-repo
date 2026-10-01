# DR-CMD-108 — /pb-decide next-best-action: O1 taken up, O2 queued

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "O1 then O2", ~20:46 PDT)

## Matter

The next best action after the DR-CMD-107 rename banking. Context: the
`recorder`/`chronicler` renames are banked as `ddc2ce3` (tree clean); the
09-26 factory close-out stands closed per the DR-CMD-079/081/082
correction (Item 9 disposed and remediations verified; orphan-triage
remediate-now ratified and implemented; Item 10 ratified as built —
there was no close-out left to present); tranche 2 remains conditional;
push is Peter's separate explicit call.

## The /pb-decide (condensed)

- **O1 — take up DR-CMD-099 (ratify-or-amend the five schema-artifact
  vetting criteria). Adopt.** Its blocker landed today
  (`tool-register-artifact`, DR-CMD-103), so the criteria are actionable
  for the first time; it is the smallest well-defined disposition on the
  board, and it closes the schema-artifact thread end to end (099 → tool
  → criteria). No G-flags.
- **O2 — containment for the build path. Queued behind O1.** Authored
  bytes execute in-process at stage time — the one known safety gap in
  the otherwise closed loop. But the exposure is bounded (hash-pinned,
  commission-scoped, the ambient's own process), so it is hygiene, not a
  live fire; and it is a heavier design+build arc than O1.
- **O3 — Half-2 inference-service docs (ratify/amend/refuse). Defer.**
  Different arc, blocks nothing, has waited without cost.
- **O4 — wright runtime. Defer (G5 unchanged).** Ambient labor still closes
  the loop at zero marginal cost.
- **G6 note:** the push to origin is not a playbook matter — Peter's
  separate explicit call (device flow), flagged not recommended.

## Disposition

Peter's selection: "O1 then O2" — O1 adopted as its own disposition
matter, O2 queued as the following matter, O3/O4 deferred.

## Consequences

- **O1 taken up immediately:** the five DR-CMD-099 criteria are presented
  for ratify-or-amend as their own disposition matter (this record does
  not dispose on the criteria themselves — no outcomes claimed).
- **O2 queued:** containment for the build path becomes the next matter
  after O1's disposition lands.
- Nothing in the working tree changes from this disposition.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-109.

## State

**No commit, no push.** This disposition is a record only; the O1
disposition matter proceeds from here.
