# DR-CMD-015 — ratify the `/eval-pb` drafts and bind the contract (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~18:57 PDT
- **Selector:** Peter (operator; framer and disposer the same person — explicitly recorded self-ratification per the playbook's Boundary clause)
- **Disposition mode:** ratify
- **Matter:** Dispose the two `/eval-pb` drafts — `doc/eval-pb-implementation.md` and `doc/eval-pb-design.md` — adopting them as ratified, and add the contract→implementation binding to `doc/slash-commands/eval-pb.md`. Completes step 1 of DR-CMD-012's sequence.

## Decision

**Ratified as follows**, 2026-09-20:

1. `doc/eval-pb-implementation.md` — DRAFT removed; status now ratified under this record. Stale DR-CMD-010 status line corrected (the design counterpart is authored and ratified in the same package, not "not yet authored"). Content otherwise unchanged: §§0–7 + Glossary, §8 deleted per DR-CMD-014.
2. `doc/eval-pb-design.md` — DRAFT removed; status now ratified under this record. Two stale notes updated (§6: contract binding now bound; §7: §8 matter disposed by DR-CMD-014).
3. `doc/slash-commands/eval-pb.md` — binding line added to Function: "**Procedure (normative):** `doc/eval-pb-implementation.md`. This file binds the command to the procedure; it does not restate it." (DR-CMD-006 pattern.)

## Consistency corrections at ratification

- A G6 bullet added in-chat on 2026-09-20 cited a nonexistent "blanket self-admission sentence" in the implementation's admission section and drew a false conclusion from it. The agent misremembered the text; §3 as authored is well-formed (comparability threshold, refuse-with-redirect below it, admit-but-not-evaluable for playbook-adjacent). The bullet was **struck**, kept as a struck record so the error is not reintroduced. The in-chat self-run's "refused" verdict was likewise corrected per the implementation's own §7 worked example: the contract is playbook-adjacent → admitted → "not evaluable against the definition."
- Verified: the `/eval-meta` redirect's citation (`doc/eval-pb-implementation.md` §3) points at the Admission section — correct, no repair needed.

## Consequences (G4)

Step 1 of DR-CMD-012 is complete: `/eval-pb` is closed — contract, procedure, and design all ratified and bound. Step 3 (`/eval-rb` authoring on the ratified pattern) is unblocked.

## Checkability (G5) — binding

No DRAFT status in either doc; binding line present in the contract; §3 verified well-formed.

## Uncertainties (G6)

- Carried open items (design doc G6): the Architecture's §8.2 playbook fails dimension 7 as it stands; vacuous-run citation accepted as residual risk; whether "not evaluable" verdicts should carry advisory repair hints; thin worked examples.
- Numbering note (supersedes the projection in DR-CMD-014's G6): this ratification takes DR-CMD-015 in disposition order. The still-open `/pb-decide` remediation matter (from the `/eval-sc` report on `/pb-decide`) moves to DR-CMD-016 on ratification; the `/eval-sc` family-membership candidacy moves to DR-CMD-017.
