# DR-CMD-047 — K1 Q3(a) identity-binding spec ADOPTED

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~08:58 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *k1-q3-repo-handle*, (a)-half (minting + provenance + the identity check as a contract)

## Verdict trail

- **Lineage:** the narrowed K1 Q3 adoption (DR-CMD-046, 2026-09-21) carried spec-stage conditions; the spec (`doc/k1-q3-binding-spec.md`, DRAFT) was written against them the same turn and adopted without further evaluation rounds — the conditions below are the check.
- **Spec-stage conditions (all met in-spec):**
  - **A4** — the spec precedes the build; nothing is implemented.
  - **R3** — I-25 *identity-binding*: a predicate over (manifest, handle) — the committing tool writes only to a handle whose `dsys.repo-id` equals the manifest-recorded `accretion_repo.identity`. Predicates, not procedures.
  - **R2** — golden-run cases specified as five checkable acceptances, including the wrong-identity refusal, the missing-key refusal, and the unchanged D5a not-a-repo refusal.
  - **R1** — replay story: the identity check precedes payload construction, payloads are byte-identical to K1's, the identity never enters the payload; existing transcripts validate unmodified.
  - **R5** — trust declared: installer-as-minter and manifest integrity trusted (compromise declared, not solved); the UUID is identity, not a secret.
  - **Manifest field design home settled** — D5: the contract (field `accretion_repo.identity`, UUIDv4, minted-once semantics) specified here; implementation in the installer-spec (cited, not redesigned).
- **Key design decisions adopted:** D1 the installer mints (UUIDv4 → `dsys.repo-id` in repo git config + `accretion_repo.identity` in manifest); D2 identity-is-UUID (path-only considered and rejected — rebindable, fails F2's identity requirement); D3 the check extends D5a (pre-write, fail closed, abort-not-retry per D4a); D4 trust declared.

## Decision

**ADOPTED** — the K1 Q3(a) identity-binding spec as specified.

**Not adopted here:** the (b)-half (acquisition + lifetime) — already refused not-ready under DR-CMD-046; still returns as a follow-on once the production driver is framed.

**Not authorized:** the build. Implementation follows on the operator's separate direction.

Adopted bytes: `doc/k1-q3-binding-spec.md` sha256 `860ca9091f9485e21f85da387a3010983ae57f62b61005313093bbe554ed98bc` (adopted header; working tree, uncommitted at disposition). Next disposition identifier: DR-CMD-048.
