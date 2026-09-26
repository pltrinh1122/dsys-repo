# DR-CMD-070 — profile planes ratified: personalization / customization / configuration reconciled

> **Label rename (DR-CMD-071, 2026-09-26):** staging-agent → staff,
> world-facing → field, harness-internal-reader → office. Old labels
> retired, no aliases. Body below preserves the original labels as
> decided.

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~10:38 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *the updated profile schema* — plane tags
  (`FACTORY_CONFIG` / `PROFILE_CUSTOM` / `PRINCIPAL_PERSONAL`) on every
  configurable facet field, `bind_time` (`BUILD` / `REFERENCE`) on
  `PRINCIPAL_PERSONAL` fields, the explicit personalization lifecycle
  stage (`bind_personalization()`), and the declared personalization
  section in the build manifest — as proposed by the ambient the same
  morning.

## Background

The morning's dialectic ran: "personalization, customization,
configuration — all operate on the same plane" was **falsified**
(different bind times, different disposers, different verification
schedules, multi-principal divergence), with the survivor that they were
*represented* on one plane in the schema — a latent defect: from a build
artifact you could not tell shared machine configuration from one
principal's personalization. The ambient proposed the reconciliation
(segmented pre-factory / post-factory) and the schema deltas; Peter
disposed **ratify**.

Two precursor positions, both from the same session, are mechanized
here: "personalization is an author agent acting on its own manifest"
(the author agent drafts the binding into a *declared* manifest section,
staged for the principal's disposition — never a silent tweak) and
"personalize before verify" (every binding re-verifies; a disclosed
re-binding is a new build).

## Decision

**RATIFIED — the three-plane schema.** Definition per
`doc/d1-d7-profile-planes.md`; implementation in
`core/package/agent_behavior.py` (plane registry, binder),
`core/package/factory_compiler.py` (manifest section, bound-check),
`core/package/factory_verifier.py` (S6), `core/package/factory_archetypes.py`
(definition-time plane check), wired into `core/package/factory_profile_set_001.py`
and `core/package/factory_golden_run.py` (bind-before-compile).

Schema deltas:

1. **`Plane` enum** — `FACTORY_CONFIG` (machine governor, pre-factory,
   shared), `PROFILE_CUSTOM` (profile author, binds at authoring, closes
   at the factory gate), `PRINCIPAL_PERSONAL` (the principal served).
2. **`PLANE_TAGS`** — `(facet, field) → Plane` for every configurable
   field; derived positions in `DERIVED_FIELDS`; untagged field =
   implementation bug (asserted at import).
3. **`BindTime`** on `PRINCIPAL_PERSONAL` fields — `BUILD`
   (`d1.standing_dispositions`, `d2.principal_precedence`: bound
   pre-verify, in the manifest, re-verified per binding) vs `REFERENCE`
   (`d2.interaction_preferences`, new field: accreted `var/` at standing,
   validated at reference time).
4. **Personalization stage** — `bind_personalization(profile,
   principal_id, bindings, disposition_ref, gate=None)`: target-checked,
   position-recomputed (DR-CMD-062 holds inside the binder),
   schema-validated (C1–C7), archetype re-gated on the bound profile
   (violations refuse the *binding*, not the profile), pure and
   deterministic. `disposition_ref` records the principal's disposition —
   never invented.
5. **Manifest section** — declared `personalization{principal_id,
   bindings_hash, disposition_ref}`, hash-covered. Undisclosed mutation
   breaks `artifact_hash` (refused at ingest); section/profile skew with
   an honestly re-minted hash fails S6 (refused).
6. **Archetype interplay** — invariants declare `touches`; a
   definition-time check rejects `PRINCIPAL_PERSONAL`-touching
   invariants (DR-CMD-069's line, now mechanical). **S1 amended** (see
   Scope): the direct standing-dispositions check is removed; the derived
   D1 position == 0.0 check keeps its teeth via the post-binding gate.
7. **Six exemplars** — no facet value changes. Builders produce generic
   profiles; the runner binds an explicit test principal before compile
   (bindings empty — role defaults stand — exercising the stage
   mechanically). Position vectors unchanged; artifact hashes changed
   (personalization section) — expected; determinism across repeat runs
   holds.

## Scope (load-bearing)

- **DR-CMD-062 not amended.** Positions remain derived from facets by the
  documented functions; the binder recomputes them, never sets them. D2
  stays declared-but-bounded (its position is `PROFILE_CUSTOM`, declared
  by the author); D6 stays structural.
- **DR-CMD-066 not amended.** The compiler contract — validated profile
  bytes → artifact, same stages — is unchanged. What "validated" means
  is *extended*: the profile must be personalization-bound
  (`require_personalized()`, enforced in `rb-compiler-validate`). Stages
  and input/output shapes untouched.
- **DR-CMD-069 not amended, one recorded deviation.** Archetypes remain
  authoring-time constraints, not a pipeline stage. S1's amendment is a
  deviation *with reason*, not a weakening: `standing_dispositions`
  moved to `PRINCIPAL_PERSONAL`/`BUILD`, which archetypes may not touch;
  the derived-position check plus the post-binding gate re-check enforce
  the same invariant ("no pre-authorized action in a staging role") at
  the plane where the field now lives.
- **No multi-principal machinery.** The schema is now multi-principal
  *representable* (one configuration, many personalizations), but
  principal management, binding registries, and per-principal
  disposition plumbing are not built.
- **`REFERENCE` accretion is declared, not implemented.** The bind-time
  exists, the slot (`d2.interaction_preferences`) exists, the
  validated-at-reference-time rule is stated; the harness-side
  reference-time validation is future work.

## Verification evidence

All observed 2026-09-26, uncommitted tree:

- `python3 -m core.package.factory_profile_set_001`: all six
  **verified** / operable, zero warnings, zero advisories; position
  vectors identical to the DR-CMD-068 ratification; repeat runs
  byte-identical (determinism holds across the new stage).
- `python3 -m core.package.factory_archetypes`: gate self-test **ok**
  (six exemplars 0 violations; synthetic write-scope violation refuses
  at `[staging-agent/S2]`; unknown archetype raises `ValueError`).
- `python3 -m core.package.factory_golden_run`: **ok: true**, 45 passed,
  0 violations, 4 expected refusals (A2a–A2d unchanged).
- Regression: `agent_behavior_golden_run`, `bridge_golden_run`,
  `updater_golden_run`, `scenario_sim_golden_run` (PASS),
  `drive_contract_golden_run`, `acquisition_golden_run`,
  `pvb_workflow_golden_run`, `golden_run` (decision playbook) — all
  green.
- Negative controls (new mechanics, all as designed):
  1. unbound profile → compile refused at **validating**
     ("run bind_personalization() before compile");
  2. archetype-breaking binding (standing disposition granted to
     analyst) → binding refused at `[staging-agent/S1]`
     ("D1 position must be 0.0, got 0.25") — the profile untouched;
  3. undisclosed manifest personalization mutation → **refused**
     (artifact hash mismatch at ingest);
  4. disclosed re-binding under a different principal → **verified**,
     hashes differ (new build, re-verified);
  5. personalization section dropped with honestly re-minted hash →
     **refused** via `S6-section` (the section must be truthful, not
     just hash-covered).

## Consequences (per G4)

- From any build artifact you can now read which plane each facet
  belongs to, who disposed it, and when it bound — the "same plane"
  flattening is unrepresentable in the schema.
- Customization closes at the factory gate *mechanically*
  (`PROFILE_CUSTOM` immutable post-build by hash coverage); the
  personalization stage is the only authoring-time plane that binds a
  principal, and it always precedes verify.
- `doc/d1-d7-profile-planes.md` is the standing definition (plane enum,
  full field→plane table with rationales, bind-time semantics,
  personalization flow, lifecycle, glossary).
- `doc/d1-d7-archetypes.md` §3.1 S1 text updated to the amended form.

## Uncertainties (G6)

- Whether `FACTORY_CONFIG` tagging of `d4.records_*` should ever admit
  a per-profile override (currently a machine-governor act only).
- Whether `REFERENCE` bind-time fields beyond `interaction_preferences`
  will be needed (history slots, per-principal tool preferences).
- The harness-side reference-time validation for `REFERENCE` fields is
  specified nowhere yet — a spec matter when the first consumer lands.
- Multi-principal deployment (binding registries, per-principal
  disposition plumbing) is representable but unbuilt.

## Identifier discipline

- DR-CMD-070 consumed by this record. DR-CMD-059 remains earmarked for
  the PVB Definition of Done — **not consumed**.
- Next disposition identifier: **DR-CMD-071**.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the matter
only): this record; `core/package/agent_behavior.py` (planes, binder);
`core/package/factory_compiler.py` (manifest section, bound-check);
`core/package/factory_verifier.py` (S6); `core/package/factory_archetypes.py`
(`touches` + definition-time check, S1 amendment);
`core/package/factory_profile_set_001.py` + `core/package/factory_golden_run.py`
(bind-before-compile); `doc/d1-d7-profile-planes.md` (new);
`doc/d1-d7-archetypes.md` (S1 text). Commit and push return as follow-on
dispositions.
