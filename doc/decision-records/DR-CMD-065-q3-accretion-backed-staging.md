# DR-CMD-065 — Q3 RESOLVED: accretion-backed staging-area durability

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:38 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *Q3 — staging-area durability* (open in DR-CMD-064, carried
  as an undecided parameter through the step-3 compiler and step-4
  verifier specs): where a factory-built agent's proposed actions wait
  with their verification evidence until disposed — ephemeral or
  accretion-backed.

## Decision

**ADOPTED — accretion-backed.** Every staged proposal (actions +
verification evidence) is committed to the accretion repo. Pending
proposals survive restarts and stay auditable — including proposals
never disposed.

**Rationale (recorded):** D4-consistency — the dsys profile sits at
D4=1.0, and pending proposals vanishing silently would be an
observability hole; crash-durability of the pending queue (a crash
must not lose the queue silently).

**Cost (recorded):** write amplification, storage growth, and the
accretion-writer machinery — new machinery, specified in the compiler
spec, built in step 5.

**Defeated alternative — ephemeral:** lighter and simpler, but a crash
loses the pending queue silently and undisposed proposals leave no
trace. Defeated on selection, recorded explicitly.

## Consequences (per G4)

- The `staging.durability` parameter in the compiler spec
  (`doc/d1-d7-compiler-spec.md`) and verifier spec
  (`doc/d1-d7-verifier-spec.md`) is **pinned** to `accretion-backed` —
  fixed, no longer a parameter (see State).
- The step-5 build implements the staging accretion writer as new
  machinery.
- Steps 3+4 remain DRAFT and unratified as wholes; this decision pins
  one parameter inside them, nothing more.

## Uncertainties (G6)

- **Q1 — Backend binding interface:** which model backend(s) and how the
  binding is declared; deferred to step 5. Open.
- **Probe-suite versioning authority:** who versions and disposes
  probe-suite changes (to be settled at step 5). Open.
- **Reflexivity** (DR-CMD-061): the factory itself must be profiled in
  D1–D7 and published — due at step 5/7. Open.
- U1 (scope boundary) and U2 (classification), carried from DR-CMD-060:
  still open. U3 closed (DR-CMD-062). U4 closed (DR-CMD-063). Q2 closed
  (DR-CMD-064). Q3 closed by this record.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- Next disposition identifier: DR-CMD-066.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed only):
this record; `staging.durability` pinned to `accretion-backed` in the
compiler spec (§3 model, §7, §8 A8, §11) and the verifier spec (§4,
§6 B7, §9); substrate spec §7 Q3 marked RESOLVED. Commit and push
return as follow-on dispositions.
