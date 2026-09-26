# DR-CMD-066 — compiler + verifier specs ratified as drafted

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:39 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *the D1–D7 agent factory steps 3 and 4 specifications* —
  the compiler spec (`doc/d1-d7-compiler-spec.md`) and the conformance
  verifier spec (`doc/d1-d7-verifier-spec.md`), each DRAFT, presented for
  ratify-or-amend.

## Decision

**ADOPTED — both specs ratified as drafted.** No amendments.

- `doc/d1-d7-compiler-spec.md` — step 3: deterministic, total, closed
  compiler: profile → build plan → agent.
- `doc/d1-d7-verifier-spec.md` — step 4: conformance verifier:
  build → probe → check.

"As drafted" expressly includes:

1. The **Q3 pin** (DR-CMD-065): `staging.durability` = accretion-backed
   in both specs.
2. The **finalized Q2 discriminator edge wording** (G6 carried from
   DR-CMD-064, disposed by step 3's authorship): "bound at disposition
   time" means bound from the disposition record ∪ (standing rule +
   trigger event), with no dependence on any prior tool result and no
   inter-step guard; the discriminator counts *effects*
   (`write_scope` invocations), not reads. A standing disposition never
   pre-authorizes an unseen flow source — drafted and staged, never
   executed.
3. The **shared interfaces** reconciled between the two specs: the
   `AgentBuildPlan` schema defined once (compiler spec §3), consumed
   embedded in the agent artifact `{plan, manifest}`; Q2 routing at
   `actuation.routing`; the five-part `FactoryVersion` determinism
   scope; both factory pipelines specified as automaton flows with
   named states/inputs/outputs/guards (DR-CMD-064 Decision 2), to be
   authored as pydantic sources per DR-CMD-058.

## Consequences (per G4)

- Both specs move DRAFT → **ratified**.
- **Step 5 unblocks and is now in progress under the ambient's hand:**
  build the compiler, the verifier, and the substrate. (The factory's
  own build pipeline runs as automaton flows per DR-CMD-064.)
- Step 6 (cross-space golden suite) and step 7 (Peter's run-through
  and disposition) follow in plan order.
- This ratification covers the specs only — **not** the step-5
  implementation, which must be verified by golden runs before step 7.

## Uncertainties (G6)

- **Q1 — backend binding interface:** step 5 defines the interface;
  the concrete facility binding is marked stub. Open.
- **Probe-suite versioning authority:** open.
- **Factory reflexivity profile:** the factory's own D1–D7 profile
  publication (DR-CMD-061 requirement) — due step 5/7. Open.
- U1 (execution-plane scope boundary) and U2 (forces/bounds/outcomes
  classification), carried from DR-CMD-060: still open. U3 closed
  (DR-CMD-062), U4 closed (DR-CMD-063), Q2 closed (DR-CMD-064),
  Q3 closed (DR-CMD-065).
- The profile schema as a whole and couplings C1–C5 remain
  built-but-unratified; this ratification does not extend to them.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done —
  **not consumed**.
- Next disposition identifier: **DR-CMD-067**.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the matter
only): this record; both spec docs' §0 status headers updated to
ratified. Commit and push return as follow-on dispositions.
