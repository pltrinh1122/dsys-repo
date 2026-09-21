# DR-CMD-050 — Production-drive contract spec ADOPTED

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~13:16 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held; the spec stage ran undiminished)
- **Disposition mode:** ratify
- **Matter:** *production-driver* — the production-drive *contract* (adopted narrowed with conditions under DR-CMD-049), now specified in `doc/production-drive-contract-spec.md`.

## Verdict trail (this session)

- **Lineage:** framed DR-CMD-048 (NBA O2) → evaluated (draft verdict: adopt-with-conditions, narrowed) → disposed DR-CMD-049 (adopted narrowed with conditions: named initiator, authorized principal, Harness invocation, verified handle, the K3 tripwire, the bearer's duties; spec-stage conditions A4, initiation contract + principal binding, R3, R2, R1, R5, settle the (b)-half boundary) → spec written DRAFT (NBA O2) → disposed here.
- **Spec-stage conditions check (DR-CMD-049):** A4 — the spec exists before build. Initiation contract + principal binding — D1–D3. R3 — I-26 (authorized-initiation predicate, predicates not procedures). R2 — five checkable acceptances incl. the ambient-initiation refusal (golden-run cases at build). R1 — initiation metadata in the transcript envelope, wall-clock excluded, replay-identity unchanged. R5 — trust declared (the operator as initiator; the manifest's integrity; the Harness strapping; the ambient explicitly not trusted with initiation). The (b)-half boundary — settled: the contract names the bearer and bounds the handle's lifetime to the drive (step-function model — no long-lived bearer); acquisition mechanics + rotation are the (b)-half's.

## Decision

**ADOPTED** — the production-drive contract spec (`doc/production-drive-contract-spec.md`): D1 the initiator is the operator (human, or the ambient on explicit instruction); D2 invocation through the CLI's flow-drive surface (`automaton init-flow` / `advance --flow-run`) strapping a Harness (AX1/AX2); D3 principal binding (dyad-or-human, agents excluded); D4 the K3 tripwire; D5 manifest read once at initiation (process side), the tool's D3 check a pure per-write comparison (governed side); D6 full profile only; D7 after fail-closed (no retry, record, surface; new initiation required).

**Not adopted:** nothing refused — the spec is adopted whole. Residuals carry: the executor spec is specified-not-disposed (neighboring thread); no scheduler exists; the CLI flow-drive surface is specified-not-implemented.

Adopted bytes: `doc/production-drive-contract-spec.md` sha256 `ae55cda8fca174f69b868a2d0e55215b2b41e59300a6b940aded372b0a48c35a` (working tree, uncommitted at disposition). Next disposition identifier: DR-CMD-051.

**Build authorization:** not granted by this record. The build follows on the operator's separate direction — implementation of I-26, the golden-run cases (incl. the ambient-initiation refusal), and transcript verification.
