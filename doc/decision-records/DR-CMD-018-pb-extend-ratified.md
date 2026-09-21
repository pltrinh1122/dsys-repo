# DR-CMD-018 — `/pb-extend` triplet ratified (O3: amend, then ratify)

- **Date:** 2026-09-20
- **Matter:** next steps per the `/eval-sc` report on `/pb-extend`
  (verdict: conforms both axes; one observation — the bound
  implementation doc's authored-as-DRAFT-for-disposition status
  was not declared in the contract alongside the playbook spec's
  DRAFT; behaviorally identical either way).
- **Options:**
  - O1 — ratify the triplet as-is (observation immaterial;
    implementation status visible via the binding).
  - O2 — also adopt the feature-expansion playbook spec.
    **Killed:** the report evaluates the contract, not the
    playbook spec; adoption is a separate disposition with its
    own evidence bar. Conflates the two dispositions the
    triplet work explicitly separated.
  - O3 — amend the contract's Procedure bullet (one line:
    declare the implementation doc's DRAFT-for-disposition
    history), then ratify.
  - O4 — decide nothing (null; DRAFTs stay staged).
- **Selector:** Peter — "ratify O3".
- **Disposition:** O3 ratified.
- **Applied:**
  - `doc/slash-commands/pb-extend.md` — Procedure bullet
    amended: implementation doc's authored-as-DRAFT history
    declared alongside the playbook spec's still-pending
    DRAFT; ratification recorded.
  - `doc/pb-extend-implementation.md` — DRAFT removed; status
    ratified 2026-09-20 (DR-CMD-018); design-counterpart
    reference updated.
  - `doc/pb-extend-design.md` — DRAFT removed; status ratified
    2026-09-20 (DR-CMD-018); ratification provenance appended
    (§7).
- **Not disposed:** `doc/feature-expansion-playbook-spec.md`
  remains DRAFT — its adoption is a separate disposition
  (spec §10 bootstrap). `/pb-extend` runs in rehearsal until
  then.
- **Verification (post-ratification):**
  - Contract binds the implementation doc (DR-CMD-006).
  - Implementation names its design counterpart
    header-adjacent, status explicit (DR-CMD-010).
  - No active DRAFT status remains in the triplet; remaining
    "DRAFT" mentions are factual (the playbook spec's pending
    state; the implementation's authored-as-DRAFT history).
  - The O3 amendment is disposition-recording and
    dimension-neutral: it changes no S1–S5 / M1–M5 basis, so
    the `/eval-sc` conforms verdict stands without re-run.

**Numbering:** next actual disposition takes DR-CMD-019
(`/pb-decide` remediation ratification, if ever, was projected
here — it moves to 019; `/eval-sc` family membership moves
to 020).
