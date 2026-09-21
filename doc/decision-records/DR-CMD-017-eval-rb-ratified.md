# DR-CMD-017 — ratify `/eval-rb` triplets (implementation + design + contract binding)

- **Status:** ratified
- **Date:** 2026-09-20 ~19:15 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Ratification of the `/eval-rb` triplets — `doc/eval-rb-implementation.md`, `doc/eval-rb-design.md`, and the contract binding in `doc/slash-commands/eval-rb.md` — completing DR-CMD-012 step 3.

## What was ratified

The triplets as authored 2026-09-20 on the ratified `/eval-pb` pattern:

1. **Ten check dimensions** — the contract's six form dimensions (strictly sequential steps; step determinism; zero inference inside; steps invoke tools; release pinning; one run-book per `AutomatonRun`) plus dimensions 7–10 (exercise declared; trigger declared; output format specified; failure routing at G1 precision) applying the DR-CMD-009 declaration-presence regime. **The pattern application is ratified by this decision** — the design's G6 question on whether applying DR-CMD-009 by pattern needed its own ratification is thereby closed.
2. **The admission threshold** — a procedure claiming the run-book form (automaton-plane, sequential, tool-invoking, zero-inference, release-pinned); sequentiality alone does not pass. This is the precise form of the concern recorded against `/eval-meta` §2's redirect wording.
3. **The three-valued finding scale** (conforms / deviates / undefined-against) and the run-book-adjacent "not evaluable against the definition" branch, with the worked self-example (contract → admitted as adjacent → not evaluable).
4. **The DR-CMD-006 / DR-CMD-010 schema edges** — contract binds the implementation without restating it; implementation names its design counterpart header-adjacent.

## Changes applied at ratification

- `DRAFT` removed from both docs; stale status lines fixed ("not evaluated, not disposed", "for operator disposition" — gone).
- Implementation header now records the DR-CMD-009 pattern application as ratified in this record.
- Design §7 gained the ratification provenance note; design G6's DR-CMD-009 bullet removed from the open list (resolved, recorded in provenance).
- Contract unchanged — already bound, no DRAFT, no stale language.

## Consequences (G4)

The triplets are normative: `/eval-rb` is now a usable instrument (no longer rehearsal — it was never draft-gated, but its drafts are now disposed). DR-CMD-012 step 3 is complete; the DR-CMD-012 sequence is fully complete.

## Checkability (G5) — binding

No `DRAFT` remains in either doc (grep-verified); contract→implementation binding present; implementation→design reference present with status explicit; this record exists.

## Uncertainties (G6)

- `/eval-meta` §2's redirect phrasing ("sequential procedure") vs `/eval-rb` §3's threshold: `/eval-rb` reads the shorthand as the threshold; tightening `/eval-meta`'s wording is `/eval-meta`'s own matter, not this record's. Carried open.
- Vacuous-run citation under dimension 7: accepted residual risk (closing it turns the validator into an auditor). Carried open.
- Whether "not evaluable" verdicts should carry advisory repair hints: currently no (repair is mutation, `/pb-decide`); the two eval commands should answer it the same way. Carried open.
- Worked examples thin (one in-chat self-run); no shipped run-book exists yet — the first real candidate will exercise dimensions 1–6 against genuine automaton-plane material. Carried open.
- Numbering (disposition order): this ratification takes **DR-CMD-017**. Projected: any future ratification touching the `/pb-decide` contract remediation → DR-CMD-018; the `/eval-sc` family-membership candidacy → DR-CMD-019.
