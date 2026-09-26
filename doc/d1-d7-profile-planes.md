# D1–D7 Profile Planes — personalization, customization, configuration reconciled

Status: **ratified** 2026-09-26 (Peter), DR-CMD-070. Implements the
reconciliation of *personalization*, *customization*, and *configuration*
as three disposition planes, segmented at the factory gate.

## 1. The claim this document settles

"Personalization, customization, configuration — all operate on the same
plane" was **falsified** 2026-09-26: they bind at different lifecycle
stages, are disposed by different parties, verify on different schedules,
and diverge in the multi-principal case (one configuration, many
personalizations). In the pre-DR-CMD-070 schema they were *represented*
on one plane — every configurable facet a bare field on
`AgentBehaviorProfile` — and that flattening was the defect: from a build
artifact you could not tell which facets were shared machine
configuration and which were one principal's personalization.
Re-personalizing required re-profiling, and one principal's binding was
indistinguishable from machine configuration.

This document makes the planes explicit in the schema. Nothing about the
dimensions changes: DR-CMD-062 (positions derived from facets) and
DR-CMD-066 (compiler contract) are untouched — see §6.

## 2. The plane enum

`Plane` (`core/package/agent_behavior.py`):

| Plane | Disposer | Binds | Shared across principals? |
|---|---|---|---|
| `FACTORY_CONFIG` | machine governor | pre-factory | yes — it *is* the machine |
| `PROFILE_CUSTOM` | profile author | at authoring; **closes at the factory gate** (immutable post-build by hash coverage) | yes — role-shaping |
| `PRINCIPAL_PERSONAL` | the principal served | at the personalization stage, or accretes at standing | **no** — this is the point |

Every configurable facet field carries exactly one tag in `PLANE_TAGS:
dict[(facet, field) -> Plane]`. Derived positions are not configurable
(they are computed); they live in `DERIVED_FIELDS`. An untagged
configurable field is an implementation bug — asserted at import
(`_assert_plane_coverage()`).

Archetypes (DR-CMD-069) may only constrain `FACTORY_CONFIG` and
`PROFILE_CUSTOM` fields, plus derived fields. A definition-time check in
`factory_archetypes.py` rejects any invariant touching a
`PRINCIPAL_PERSONAL` field — the line from DR-CMD-069, now mechanical.

## 3. Field → plane table

Facet keys are the profile attribute names; `profile` covers the
profile's own leaf fields. One-line rationale is given where the tagging
is not obvious.

### D1 Authority

| field | plane | rationale |
|---|---|---|
| position | *derived* | computed from facets (DR-CMD-062) |
| per_event_disposition | PROFILE_CUSTOM | role shape; staff S1 |
| standing_dispositions | PRINCIPAL_PERSONAL / BUILD | the principal's pre-authorizations; moves D1, hence behavior guarantees |
| self_correction | PROFILE_CUSTOM | role capability |
| self_planning | PROFILE_CUSTOM | role capability |

### D2 Fidelity

| field | plane | rationale |
|---|---|---|
| conflict_rule | PROFILE_CUSTOM | **the D2 value itself**: the binary enum {principal_wins_ties, world_wins_ties} — whose claims prevail at ties (DR-CMD-077). Declared by the *author*, not the principal. No scalar position (retired with C6). |
| principal_precedence | PRINCIPAL_PERSONAL / BUILD | who the principal is; feeds conflict-resolution guarantees |
| interaction_preferences | PRINCIPAL_PERSONAL / REFERENCE | the principal's interaction posture (challenge/clarify style); declared slots, filled by the principal |

### D3 Reproducibility

| field | plane | rationale |
|---|---|---|
| position | *derived* | entropy budget |
| deterministic_execution | PROFILE_CUSTOM | role's execution contract |
| replay_supported | PROFILE_CUSTOM | role's execution contract |

### D4 Observability

| field | plane | rationale |
|---|---|---|
| position | *derived* | instrumentation fraction |
| records_events | FACTORY_CONFIG | audit instrumentation is a machine-governor guarantee: factory agents are fully instrumented *by policy*, not by role choice |
| records_intents | FACTORY_CONFIG | as above |
| records_verifications | FACTORY_CONFIG | as above |
| inspectors | PROFILE_CUSTOM | which *roles* may inspect ("operator" = the principal role, principal-agnostic) |
| retention | FACTORY_CONFIG | storage policy belongs to the machine governor |

### D5 Scope

| field | plane | rationale |
|---|---|---|
| position | *derived* | write-scope breadth bands |
| read_scope | PROFILE_CUSTOM | role-shaping |
| write_scope | PROFILE_CUSTOM | role-shaping; staff S2 |

### D6 Initiative

| field | plane | rationale |
|---|---|---|
| sources | PROFILE_CUSTOM | role's activation surface (C5) |
| gating | PROFILE_CUSTOM | per-source gate *choice* is role-shaping; the gate *vocabulary* is pinned in the factory version (semantics table) |
| authorization | PROFILE_CUSTOM | the authorization *rule text* is role-level (staff S4); its *exercise* references the principal at runtime |

### D7 Verification

| field | plane | rationale |
|---|---|---|
| position | *derived* | trust-boundary fraction |
| intent_target | PROFILE_CUSTOM | role's trust boundaries |
| event_target | PROFILE_CUSTOM | role's trust boundaries |
| world_target | PROFILE_CUSTOM | role's trust boundaries |
| trigger_target | PROFILE_CUSTOM | role's trust boundaries |
| on_failure | PROFILE_CUSTOM | role's failure policy |

### Profile identity

| field | plane | rationale |
|---|---|---|
| agent | PROFILE_CUSTOM | authoring label |
| version | PROFILE_CUSTOM | authoring label |
| personalization | PRINCIPAL_PERSONAL / BUILD | the binding record itself; hash-covered in the manifest |

## 4. Bind-time semantics

`PRINCIPAL_PERSONAL` fields carry a `BindTime`:

- **BUILD** — bound pre-verify, in the manifest's declared personalization
  section, re-verified per binding. Fields: `d1.standing_dispositions`,
  `d2.principal_precedence` (both move the position vector or the
  behavior guarantees), and the `profile.personalization` record itself.
- **REFERENCE** — accreted as `var/` material at standing, validated at
  reference time, never part of the build hash. Fields:
  `d2.interaction_preferences`.

The separator is mechanical: if it changes the position vector or a
behavior guarantee, it is BUILD (new binding = new build = re-verify);
if it is data the agent reads at reference time, it is REFERENCE
(accretion, no rebuild).

## 5. The personalization flow

`bind_personalization(profile, principal_id, bindings, disposition_ref,
gate=None)` (`agent_behavior.py`):

1. **Target check.** Every `(facet, field)` in `bindings` must be a
   bindable `PRINCIPAL_PERSONAL`/`BUILD` field; anything else is a loud
   `ValueError`. The binding record itself is set by the binder, never
   by bindings.
2. **Apply + recompute.** Bindings overlay the role defaults on a copy
   (the input is untouched); derived positions are recomputed from the
   bound facets — DR-CMD-062 holds inside the binder, positions are never
   hand-set.
3. **Validate.** Full schema validation runs (C1–C5, C7 — C6 retired, DR-CMD-077 — + derivation checks).
4. **Gate.** When a `gate` callable is supplied (the archetype gate), it
   re-checks conformance on the *bound* profile. A binding that breaks
   an archetype invariant — e.g. granting a staff agent a standing
   disposition moves D1 to 0.25 against S1 — **refuses the binding, not
   the profile**.
5. **Record.** `PersonalizationState{principal_id, disposition_ref,
   bindings_hash}` is attached, where `bindings_hash` covers the
   *effective* `PRINCIPAL_PERSONAL`/`BUILD` values (single source:
   `personalization_bindings_hash()`; the verifier's S6 recomputes it).

The author-agent flow around the function: the **author agent drafts**
the bindings and stages them (D1 0.0, stage-only — it cannot bind);
the **principal disposes**; `disposition_ref` records that disposition
(never invented); the binder executes; the compiler compiles; the
verifier re-verifies. Pure function: no timestamps, no wall-clock, no
randomness — identical inputs bind byte-identically.

A disclosed re-binding is a **new build** (new hashes, re-verified). An
*undisclosed* mutation of the manifest's personalization section breaks
`artifact_hash` → the verifier refuses at ingest; a section/profile skew
with an honestly re-minted hash fails S6 → refused. Personalization can
never silently alter a verified build.

### 5.1 The REFERENCE read path

`reference_binding(facet, field, accreted)` (`agent_behavior.py`) is the
read path the schema's REFERENCE declaration promises
(DR-CMD-079 — implemented, was declared-but-unimplemented):

- `accreted` is the standing-time `var/` material keyed by `(facet, field)`,
  mirroring `bind_personalization`'s `bindings`.
- `(facet, field)` must be `PRINCIPAL_PERSONAL` with `BindTime.REFERENCE`
  (today: `d2_fidelity.interaction_preferences`). Reading a BUILD field
  here would bypass the build hash → refused; CUSTOM/CONFIG/derived →
  refused (not principal material).
- A dangling reference (slot never filled at standing) → refused with
  reasons. No silent fallback to the role default; a caller that wants
  the default reads the profile facet directly.
- The accreted value is validated against the field's declared schema
  (`TypeAdapter` over the facet model's annotation) → invalid values
  refused with the validation reasons.
- Pure and deterministic: no I/O, no timestamps. Reads never mutate the
  profile and never enter the build hash (`personalization_bindings_hash`
  covers BUILD fields only).

Failure mode is refuse-with-reasons (`ReferenceBindingError`): the caller
stages or escalates; nothing passes silently.

## 6. Lifecycle with the explicit personalization stage

```
archetype → profile → personalization → build → verified → standing
→ active → closed → superseded
```

- **profile**: generic — `PROFILE_CUSTOM` bound, `PRINCIPAL_PERSONAL`/`BUILD`
  unbound (role defaults), `personalization=None`.
- **personalization**: `bind_personalization()` — the stage this document
  adds. Principal-bound, disposed, archetype re-gated.
- **build**: the compiler takes the bound profile. Its validating stage
  refuses unbound profiles (`require_personalized()`); the manifest
  carries the declared `personalization{principal_id, bindings_hash,
  disposition_ref}` section, hash-covered.
- **verified**: the verifier's new **S6** (personalization integrity)
  checks section↔profile consistency, principal agreement, recomputed
  `bindings_hash`, and a non-empty `disposition_ref`.
- **standing**: `PERSONAL`/`REFERENCE` fields accrete as `var/` material,
  validated at reference time — the only plane open post-factory besides
  deployment re-configuration.
- **customization closes at the factory gate**: `PROFILE_CUSTOM` is
  immutable post-build by hash coverage. Post-factory "tuning" of a
  customized facet is a new profile, a new build, a re-verify — there are
  no knobs on a standing agent.

## 7. What is unchanged

- **DR-CMD-062**: positions are derived from facets by the documented
  functions. The binder recomputes them; it never sets them. D2 is the
  binary enum {principal_wins_ties, world_wins_ties} (DR-CMD-077 — the
  declared-but-bounded scalar retired); D6 remains structural.
- **DR-CMD-066**: the compiler contract — validated profile bytes →
  artifact, same stages — is unchanged. "Validated" now *includes*
  personalization-bound (enforced in `rb-compiler-validate`); the stages
  and their input/output shapes are untouched.
- **DR-CMD-069**: archetypes remain authoring-time constraints, not a
  pipeline stage. One amendment with recorded reason: **S1** no longer
  checks `standing_dispositions` emptiness directly (that field is
  `PRINCIPAL_PERSONAL`, untouchable by archetypes); the derived D1
  position == 0.0 check preserves S1's teeth, and the post-binding gate
  re-check refuses autonomy-granting bindings.
- The six ratified profiles (DR-CMD-068): **no facet value changes**.
  Their builders produce generic profiles; the runner binds an explicit
  test principal before compile. Position vectors are unchanged;
  artifact hashes changed (personalization section) — expected;
  determinism across repeat runs holds.

## 8. Glossary

- **archetype**: a named set of facet invariants + parameter points,
  checked at authoring time; a constraint, not a generative stage
  (DR-CMD-069).
- **authoring gate**: the archetype conformance check
  (`check_profile()`); refuses violations with explicit reasons.
- **bind time**: when a `PRINCIPAL_PERSONAL` field binds — `BUILD`
  (pre-verify, in the manifest) or `REFERENCE` (accreted at standing).
- **binding**: the mapping from `(facet, field)` to principal-specific
  values applied by `bind_personalization()`.
- **bindings_hash**: SHA-256 over the canonical form of the effective
  `PRINCIPAL_PERSONAL`/`BUILD` field values; recorded in the binding
  record and the manifest.
- **customization**: the `PROFILE_CUSTOM` plane — role-shaping disposed
  by the profile author; closes at the factory gate.
- **configuration**: the `FACTORY_CONFIG` plane (machine governor,
  pre-factory) and deployment configuration (post-factory wiring) —
  same word, two planes (§1 of the reconciliation).
- **derived field**: a position scalar computed from facets by a
  documented function (DR-CMD-062); never configured, never hand-set.
- **disposition_ref**: the recorded reference to the principal's
  disposition authorizing a personalization binding (recorded, never
  invented).
- **factory gate**: the compile boundary; `PROFILE_CUSTOM` becomes
  immutable past it (by hash coverage).
- **generic profile**: a profile with `personalization=None` —
  `PRINCIPAL_PERSONAL`/`BUILD` fields at role defaults, unbound to any
  principal. Not compilable.
- **personalization**: the `PRINCIPAL_PERSONAL` plane — principal binding
  disposed by the principal served; the lifecycle stage between profile
  and build.
- **personalization section**: the manifest's declared
  `{principal_id, bindings_hash, disposition_ref}` block, hash-covered.
- **plane**: who disposes a configurable field and when it binds
  (`FACTORY_CONFIG` / `PROFILE_CUSTOM` / `PRINCIPAL_PERSONAL`).
- **principal**: the party the agent serves; the Operator in the
  single-principal deployment.
- **S6**: the verifier's personalization-integrity static check
  (section↔profile consistency, bindings_hash recomputation).
- **`touches`**: the `(facet, field)` pairs an archetype invariant
  declares it reads; definition-time plane-checked.
- **var/ material**: accreted principal-specific data at standing
  (preferences, history), validated at reference time — the
  `REFERENCE` bind-time home.
