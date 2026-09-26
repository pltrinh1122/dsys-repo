# DR-CMD-072 — six-actor verification ensemble adopted for step 6

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~10:55 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (adopt)
- **Matter:** *step-6 verification scope* — item 6 of the factory step-7
  run-through (2026-09-26). Peter disposed: "instead of three profiles,
  adopt the six profiles (or actors) {analyst, advisor, author, executor,
  monitor, coordinator}".

## Disposition

The step-6 verification ensemble is the six exemplar profiles — analyst,
advisor, author, executor, monitor, coordinator — each run through the
full pipeline: declare archetype (staff/field/office) → author profile →
archetype gate → bind_personalization (test principal) → compile → verify.
The legacy three-profile cases (dsys, thermostat-corner,
high-autonomy-interior, plus the fail-open agent) are KEPT as regression:
they exercise dsys-adjacent behavior the six actors don't (the dsys
self-profile's `contracted-tools-only` alias → workflow routing, the
thermostat corner's minimalism, the high-autonomy interior's advisories,
the fail-open P-D7 branch). The ensemble is six actors PLUS the legacy
fixtures, not a replacement of the cases.

Terminology note: Peter parenthetically called the six "actors". This is
recorded as usage, not adopted as a rename — the ratified term remains
"profile" (DR-CMD-068). No rename was performed.

## What changed in the suite

`core/package/factory_golden_run.py` gains the C-* battery
(`actor_cases`, with `_actor_shared`, `_actor_actuation`,
`_actor_adversarial`), importing the builders and archetype declarations
from `factory_profile_set_001.py` and the gate from
`factory_archetypes.py`. No facet value changes to the six profiles; no
invariant changes; synthetic adversarial variants are rebuilt in-memory
via `model_validate` on mutated dicts (the AGENTS.md `model_copy` lesson
is honored — the one pre-existing `model_copy(update=)` use in the
archetype self-test remains flagged, unchanged).

Case counts (observed 2026-09-26, two consecutive runs):

| Battery | Passed (before) | Passed (after) | Refusals (after) |
|---|---|---|---|
| A (compiler, legacy) | 45 total | 45 | 4 (A2a–A2d) |
| B (verifier, legacy) | — | — | — |
| C (six actors, new) | — | 67 | 1 (C-analyst-c6) |
| **Total** | **45** | **112** | **5** |

Zero violations. Determinism: per-actor repeat bind+compile is
byte-identical (C-*-deterministic), and the full suite result is stable
across runs.

### Per-actor coverage (C-*)

Shared battery per actor (47 checks): authoring gate green on the generic
profile for each declared archetype (staff/field/office as applicable);
bind → compile → verify → `verified` + operable with the static+probe
matrix green; deterministic repeat; disclosed re-binding to a second
principal (manifest records the new principal, a new build is minted, the
re-bound build verifies).

Actuation shape (7 checks): the five staff actors compile to an empty
write allowlist (J-A); the executor's 4 write channels + 2 standing
dispositions all route `direct`, each binding exactly its named registered
tool (J-C).

Adversarial (14 checks): a write_scope grant refuses at `[staff/S2]` for
all six actors — for the five staff members their own archetype refusing;
for the executor the boundary proof that it is not staff. Actor-specific:
analyst C6 conflict_rule/position boundary (expected refusal) + world-gate
authentication (field W2); advisor self-source stage-only (J-D); author
world_target claim refused at `[office/H1]`; monitor world_target drop
refused at `[field/W1]` + D3 determinism; coordinator may-act refused at
`[staff/S4]` + sources exactly {operator, self} (the F1 gap, mechanical).

## Verification evidence

- `factory_golden_run`: ok=true, 112 passed, 0 violations, 5 expected refusals
- `factory_profile_set_001`: 6 verified, 0 warnings
- `factory_archetypes` self-test: ok
- Regression suites: agent_behavior, bridge, updater, drive_contract,
  acquisition, pvb_workflow, scenario_sim, playbook — all PASS
- Tree uncommitted; no git operations performed

## Consequences

- Step 6 of the factory plan (DR-CMD-061) is now discharged by the
  six-actor ensemble + legacy fixtures, pending Peter's acceptance of the
  evidence above. This closes run-through item 6's open coverage question
  as framed: the honest gaps named in the run-through (coordinator
  multi-agent flows unexercised; the personalization stage's adversarial
  surface only partly covered) are narrowed — coordinator routing is now
  covered per-actor (C-coordinator-*) and the personalization stage has
  bind/re-bind/disclosed-mutation coverage — but multi-agent *flows*
  (coordinator arbitrating live staged proposals from other actors)
  remain unexercised by any suite. That is a standing gap, not a
  regression.
- Next free identifier: **DR-CMD-073** (DR-CMD-059 still earmarked for
  the PVB Definition of Done).

## Glossary

- **Step-6 verification ensemble:** the profile set against which the
  factory's step-6 verification battery runs; since this DR, the six
  exemplar profiles plus the legacy fixture profiles.
- **Legacy fixtures:** the dsys self-profile, the thermostat-like minimal
  agent, the high-autonomy agent, and the fail-open agent — the
  pre-DR-CMD-072 golden-run profiles, kept as regression.
- **Disclosed re-binding:** binding a new principal via
  `bind_personalization()` — a new build that re-mints and re-verifies;
  the opposite of undisclosed manifest mutation (refused at ingest).
