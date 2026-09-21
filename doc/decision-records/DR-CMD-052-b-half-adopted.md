# DR-CMD-052 — (b)-half (handle acquisition + lifetime) ADOPTED (narrowed)

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~13:29 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held; the playbook's evaluation ran undiminished)
- **Disposition mode:** ratify
- **Matter:** *k1-q3b-handle-acquisition* — "dsys should define how the production drive's bearer acquires the repository handle at drive start (resolution mechanics) and how handles rotate and revoke, such that the drive contract's bearer comes to hold a D3-verifiable handle within the drive-bounded lifetime, because the adopted drive contract names the bearer and bounds the handle's lifetime to the drive but does not say how the bearer comes to hold the handle — and without acquisition the drive cannot run against the real accretion repo."

## Verdict trail (falsification pipeline, this session)

- **Lineage:** K1's G6 Q3 → DR-CMD-039 → K1 Q3 (DR-CMD-045/046/047; (a)-half adopted, spec'd, built) → DR-CMD-046 F4 (the (b)-half refused not-ready; "returns as a follow-on matter once the production driver is framed") → the production driver framed (DR-CMD-048), adopted (DR-CMD-049), spec'd and spec-adopted (DR-CMD-050), built and committed (`8b61695`) → the (b)-half framed 2026-09-21 (NBA O3, DR-CMD-051), evaluated the same turn (NBA O1; draft verdict: adopt-with-conditions, narrowed).
- **S5 motivation-fit:** holds — the Z is a checkable world-claim ("no acquisition design exists anywhere in the design"), true on cited evidence (DR-CMD-046; the drive-contract spec's G6 residuals; the binding spec's D4 "Rotation is not defined"). Not misplaced, not fit-failing. Not INVALID.
- **Falsifiers:** **F1** ("the installer's path config is enough") narrowed — resolution is reading `accretion.path` at initiation; the survivor is the failure-mode contract. **F2** ("rotation is YAGNI") killed the rotation/revocation half as designed operations — no trigger in the adopted threat model (the (a)-half's F3 killed the adversary framing), and in tension with the binding spec's D5 ("minted once at install, immutable thereafter"); the survivor is the lifetime *statement*. **F3** ("implementation, not design") narrowed sharply. **F4** ("a new K3 surface") killed — the resolver reads operator-owned config; the tripwire holds, reaffirmed as a constraint. **F5** ("not a matter") narrowed, survives.
- **Conditionals holding (on the narrowed matter):** A1 (this evaluation; no refuted sub-claim survives — rotation/revocation removed); A2 (no new entity — the survivor is a contract); A3 (plane discipline — mechanical resolution); A5 (the narrowed Y is checkable); R4 (zero inference); R5 (trust declared — the install config, the manifest). A4/R1/R2/R3 are spec-stage gates, noted not failed.

## Decision

**ADOPTED (narrowed, with conditions)** — the acquisition *contract*:
- resolution via the installer's `accretion.path` at initiation (the CLI surface, process side — part of D5's one-time read);
- the failure-mode contract: absent path → the drive refuses before starting (initiation's duty, composing with the I-26/D6 gates); repo present but identity mismatch → D3 fails closed (built);
- the lifetime *statement*: identity lifetime = installation lifetime; new identities come only from fresh installs (the installer mints, D1).
The adopted-now Y: *the bearer resolves the handle via accretion.path at initiation; absent path refuses; the identity lives as long as the installation.*

**Not adopted:** rotation/revocation as designed operations (F2); a handle-manager entity (A2).

**Spec-stage conditions:** A4 (spec before build); settle fail-fast vs fail-at-write for the identity check at resolution (recommended: fail fast *and* keep D3 as the backstop — the same I-25 predicate applied earlier, no new machinery); R3 (I-N validator for acquisition — predicates, not procedures); R2 (golden-run cases: absent-path refusal, wrong-identity-at-resolution); R1 (resolution must not enter the committed payload); R5 (trust in the install config declared).

**The K1 Q3 line is fully disposed:** the (a)-half (binding) adopted/spec'd/built; the production driver framed/adopted/spec'd/spec-adopted/built; the (b)-half (acquisition) adopted narrowed here.

Adopted bytes: `doc/k1-q3b-handle-acquisition-matter.md` sha256 `2041987fc5c16af723cbe329ed0d332a406b111feabc1cd99d91a74971b99b70` (framed + evaluated + adopted; working tree, uncommitted at disposition). Next disposition identifier: DR-CMD-053.

**Build authorization:** not granted by this record. The spec and build follow on the operator's separate direction.
