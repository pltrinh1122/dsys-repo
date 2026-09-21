# DR-CMD-019 — `/sc-author` §7 gap: record and defer (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~19:48 PDT (disposition); recording interrupted before write, resumed and recorded 2026-09-21
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Next steps per the `/eval-meta` report outcome on the claim "'/sc-author' validates completion by checking for existence of target's triplet" (verdict: *decomposed* — `/sc-author` inventories existence at §2 intake, never validates completion by it; §7 validates declaration-presence, schema edges, and the `/eval-sc` result). The report named one small gap: `/sc-author` §7 step 2's absent-file failure path is unspecified (the grep presupposes the implementation file; the procedure does not say what happens when it is absent).

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — clarify §7 now** (one line: the mechanical greps run over the in-hand texts — authored drafts, or files read at §2; §2's inventory guarantees existence before §7 for existing matters): survived G1–G4 as the near-free alternative. Not selected: amending a just-created, never-yet-run procedure for a covered case is premature polish.
- **O2 — record and defer**: survived G1–G4. Draft verdict was adopt. The gap is behaviorally covered upstream — §2's inventory records implementation/design present/absent for existing-command matters, and §§4–6 author whatever the inventory found absent — so the residual is a clarity nit, not a behavioral hole. The analysis goes into `/sc-author`'s design G6 (durable); revisit trigger is the first real `/sc-author` run.
- **O3 — decide nothing**: dominated by O2 at G4 — leaves the gap only in the chat report, which is not a durable record.

## Decision

**Ratified O2.** The gap analysis is recorded in `doc/sc-author-design.md` G6; no procedure change to `/sc-author` now. Remediation follows the standing rule: record non-blocking gaps, remediate when blocking.

## Consequences (G4)

No change to the `/sc-author` triplet. The finding is durable in the design's G6 with a named revisit trigger instead of living only in chat.

## Checkability (G5)

Checkable: the G6 entry exists (or not); the revisit trigger is observable — a first real `/sc-author` run that surfaces ambiguity in §7's grep target.

## Uncertainties (G6)

- Whether the first real run actually exercises the absent-file path (existing-command matter with a dangling binding) or only the clean paths.
- If the run shows ambiguity, the one-line §7 clarification (O1's text) remains the ready-made remediation.
- Numbering (disposition order): this ratification takes **DR-CMD-019**.
