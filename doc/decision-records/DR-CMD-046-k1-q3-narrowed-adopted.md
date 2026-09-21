# DR-CMD-046 — K1 Q3 (production repository-handle binding) ADOPTED (narrowed)

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~08:52 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held; the playbook's evaluation ran undiminished)
- **Disposition mode:** ratify
- **Matter:** *k1-q3-repo-handle* — "dsys should define the production repository-handle holder for the updater's accretion writer such that the committing tool's repository handle is a declared, authorized binding — with a named minter, recorded provenance, and a bounded lifetime — because K1 verified the committing logic against a fixture, and without a bound handle the writer is undeployable."

## Verdict trail (falsification pipeline, this session)

- **Lineage:** K1's G6 Q3 ("the production repo-handle holder — composes with K3 (D7); this spec does not design it"), framed 2026-09-21 under DR-CMD-045 (NBA O2), evaluated the same turn (NBA O2).
- **S5 motivation-fit:** holds — the Z is a checkable world-claim ("no production handle exists anywhere in the design"), true on cited evidence (DR-CMD-039; k1-repair-spec D7). Not misplaced, not fit-failing. Not INVALID.
- **Falsifiers:** **F1** ("no holder needed") narrowed — holder-as-entity refused under A2 (no new entity; the GoalClassification precedent); the survivor is the *binding*, not a holder. **F2** ("D5a covers it") narrowed — liveness ceded to D5a; the matter's core is the **identity binding** (D5a's check gains an identity conjunct: the handle must resolve to the manifest-recorded identity, else fail closed). **F3** (confused-deputy melodrama) killed — the failure mode is misconfiguration, not adversary. **F4** (premature: acquisition needs the unframed production driver) survived as staging — the matter decomposes into (a) minting + provenance + identity-check as contract (adoptable now) and (b) acquisition + lifetime (refused not-ready).
- **Conditionals holding (on the narrowed matter):** A1 (this evaluation; no refuted sub-claim survives — holder-as-entity removed, liveness ceded); A2 (no new entity); A3 (plane discipline — no inference in execution); A5 (the narrowed Y is checkable); R4 (zero inference); R5 (trust declared — installer as minter, manifest integrity). A4/R1/R2/R3 are spec-stage gates, noted not failed.

## Decision

**ADOPTED (narrowed, with conditions)** — the (a)-half: the production repository-handle *binding* — minting + provenance via the installation manifest, and the identity check as a contract the committing tool enforces (extending D5a's fail-closed). The adopted-now Y: *named minter, recorded provenance, identity verified before write.*

**Not adopted:** the (b)-half (acquisition + lifetime) — refused (not-ready); returns as a follow-on matter once the production driver is framed (F4).

**Spec-stage conditions:** A4 (spec before build); R3 (I-N validator for the identity binding — predicates, not procedures); R2 (golden-run cases including the wrong-identity refusal); R1 (replay-identity constraint if the identity enters the committed payload); settle the manifest field's design home (contract specified here for the installer to implement, vs designed in the installer-spec).

Adopted bytes: `doc/k1-q3-repo-handle-matter.md` sha256 `0267f5b8c5415d6eb0a0d6760d150ac16f9c70007b79b882ea12762375ec2c7f` (framed + evaluated; working tree, uncommitted at disposition). Next disposition identifier: DR-CMD-047.
