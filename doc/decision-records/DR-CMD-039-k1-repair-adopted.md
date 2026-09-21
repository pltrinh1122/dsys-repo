# DR-CMD-039 — K1 repair (the updater's accretion writer) ADOPTED

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~07:44 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the feature-expansion playbook's §7 normal mode for expansion matters)
- **Discriminator:** feature-expansion (shared machinery)
- **Matter:** the K1 repair — "the updater's drive journals its inter-install event log to the accretion repository: a `committing` state after completed verification, cumulative commits via a watermark, abort-not-retry, append-only, git as a hard dependency — so the drive's own history is never silently lost."

## Verdict trail (governed `/pb-extend` evaluation, this session)

- **Gates:** X1 clear (dual-scope, decomposed at START, conjunctive); X2 clear (R1 — replay identity is canonical payload bytes, not the nondeterministic git envelope); X3 clear (pre-build); X4 clear (not K2 — K2 adopts the repo at install time; K1 writes the updater's inter-install event log; neither subsumes the other).
- **Claim:** drive order `driving → verifying → committing → done` (commit belongs to a completed-verification drive); commits cumulatively cover all events since the previous commit through a watermark; `committing` aborts rather than retries (the next drive's cumulative commit is the retry); bounded residual (drive N's terminal edge may ride drive N+1's commit); replay identity is canonical payload bytes; git is a hard dependency (absent/unusable git fails closed); append-only (no amend, no rebase).
- **Conditionals holding:** A1 (falsified twice — D2 reordered, D4 made cumulative via the F-A amendment with D4a abort / D4b residual); A2 (glossary-defined); A3 (no plane crossing — the writer is invoked by the driver, a deterministic step); A4 (spec exists); A5 (checkable acceptances); R1 (payload-canonicity story); R3 (I-18 commit-completeness, I-19 cumulative payload-canonicity, I-20 append-only — numbering provisional, no earlier claim); R4; R5 (git as declared hard dependency).
- **Draft verdict:** adopt (evaluation findings remediated pre-disposition).

## Decision

**ADOPTED** — the operator's "adopt": the K1 repair as specified, including the evaluation remediations (D2 reorder, D3 standing-authority extension, D5/D5a payload-envelope distinction + git dependency) and the F-A amendment (D4 cumulative watermark, D4a abort, D4b bounded residual).

Adopted bytes: `doc/k1-repair-spec.md` sha256 `a9bc1268a306742d7a4668f8066b2741f739986aa1d2077a189a23356eed2e74` (adopted header; working tree, uncommitted at disposition). G6 carried to build: the exact canonical serialization of payloads; the production repository-handle holder. Next disposition identifier: DR-CMD-040.
