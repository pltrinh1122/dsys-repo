# DR-CMD-069 — agent archetype adopted as authoring-reliability construct

> **Label rename (DR-CMD-071, 2026-09-26):** staging-agent → staff,
> world-facing → field, harness-internal-reader → office. Old labels
> retired, no aliases. Body below preserves the original labels as
> decided.

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~09:08 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *the agent archetype* — a named set of facet invariants plus
  declared parameter points plus a conformance predicate, adopted as a
  **constraint on authoring** (not a generative pipeline stage), to improve
  authoring reliability for factory-built agent profiles.

## Background

The six ratified profiles (DR-CMD-068) were built with judgment calls
J-A through J-F living in docstrings. The schema's own validators
(couplings C1–C7) catch incoherent profiles but not unwise-but-coherent
ones: nothing mechanical stopped an author from granting a research-type
agent a write scope, claiming world corroboration for an agent that never
touches the world, or leaving a world trigger unauthenticated. Peter
adopted the archetype to mechanize those invariants — enforced once, not
re-derived per profile.

The adoption followed a falsification chain the same day: "six profiles
are archetypes" falsified (profiles are instances; the schema is the
archetype level); "archetypes improve efficiency and reliability of
factory output" split — efficiency false at current scale, output
reliability already at ceiling via per-profile verification — with the
survivor "archetypes improve *authoring* reliability," which is what is
adopted here.

## Decision

**ADOPTED — the agent archetype as an authoring-time constraint.**
Definition and set per `doc/d1-d7-archetypes.md`; implementation in
`core/package/factory_archetypes.py`, wired into
`core/package/factory_profile_set_001.py` (`PROFILE_ARCHETYPES` +
authoring gate in `run_agent`, before compile).

Archetype set (admission: invariants shared by ≥2 profiles or guarding a
critical risk):

| archetype | members | core invariants |
|-----------|---------|-----------------|
| staging-agent | analyst, advisor, author, monitor, coordinator | D1 0.0 (per-event, no standing, no self-correction/planning); D5 empty write_scope; D4 1.0 full instrumentation; all D6 authorizations stage-only |
| world-facing | analyst, monitor, executor | D7 1.0 all four trust boundaries verified; world trigger gate authenticated |
| harness-internal-reader | advisor, author, coordinator | D7 0.75: intent/event/trigger verified, world_target False |

Declined: a single-member "acting-agent" archetype for the executor's
D1/D5 shape — the data does not earn it; C7 plus world-facing cover the
critical core.

## Scope (load-bearing)

- **Authoring reliability only.** The efficiency/volume thesis was argued
  and explicitly deferred — not adopted.
- **No generative stage.** There is no archetype+parameters → profile
  instantiation machinery. Profiles are still authored in full; the
  archetype only checks.
- **DR-CMD-066 not amended.** The compiler's input contract is unchanged
  (validated profile in); the gate runs before compile, in the authoring
  harness. The compiler never sees an archetype.

## Verification evidence

- `python3 -m core.package.factory_archetypes` (2026-09-26): all six
  exemplars conform (0 violations each); synthetic write_scope violation
  refuses at `[staging-agent/S2]` with explicit reason; unknown archetype
  name raises `ValueError`. Gate self-test: ok.
- `python3 -m core.package.factory_profile_set_001` with the gate wired
  in: all six reach **`verified`** / operable, zero warnings, zero
  advisories.
- `python3 -m core.package.factory_golden_run`: **ok: true**,
  45 passed, 0 violations (regression check — archetype work touched no
  compiler/verifier logic).
- No profile facet was altered to fit an archetype; conformance was
  verified against the ratified profiles as built.

## Consequences (per G4)

- New profiles declare archetype(s) in `PROFILE_ARCHETYPES`; violations
  refuse at authoring time with explicit reasons (archetype, invariant
  id, reason) before compile is reached.
- Judgment calls J-A…J-F remain documented as the *rationale* behind the
  invariants; the invariants are now also mechanically enforced.
- `doc/d1-d7-archetypes.md` is the standing definition (what an
  archetype is and is not, the set, the authoring flow, worked
  conformance, explicit non-adoptions, glossary).

## Uncertainties (G6)

- Whether profile volume will ever justify a generative instantiation
  stage (deferred; would need its own spec and ratification).
- Whether new archetypes will be earned as future profiles are built
  (admission rule in `doc/d1-d7-archetypes.md` §3 governs).
- The executor's acting shape (J-C) remains judgment-call territory,
  not archetype law.

## Identifier discipline

- DR-CMD-069 consumed by this record. DR-CMD-059 remains earmarked for
  the PVB Definition of Done — **not consumed**.
- Next disposition identifier: **DR-CMD-070**.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the matter
only): this record; `core/package/factory_archetypes.py` (new);
`core/package/factory_profile_set_001.py` (`PROFILE_ARCHETYPES` +
gate); `doc/d1-d7-archetypes.md` (new). Commit and push return as
follow-on dispositions.
