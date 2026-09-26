# DR-CMD-071 — archetype labels adopted: staff / field / office

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~10:50 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (adopt)
- **Matter:** *alternative labels for the three agent archetypes* — the
  ambient proposed three thematically coherent candidate sets; Peter
  disposed "adopt {staff, field, office}" via the decide matter
  `/fb-decide` on 2026-09-26.

## Background

DR-CMD-069 adopted three archetypes as authoring-reliability constraints
with working labels: staging-agent, world-facing, harness-internal-reader.
The working labels were thematically mixed (one efferent posture — what
the agent emits — plus two afferent postures — what it reads) and the
third was clunky. Peter asked for thematically coherent alternatives;
the ambient proposed three candidate sets and a recommendation with
ordered alternatives; Peter adopted the recommended set.

## The decide matter

Candidates, with recorded defects:

1. **{staff, field, office}** (org-posture theme; ambient recommendation)
   — *Defect:* "field" collides with schema-field vocabulary (the 26
   plane-tagged fields, DR-CMD-070). Mitigated via glossary
   disambiguation: "field agent" always means the archetype; "schema
   field" always means a configurable profile field.
2. **{chat, world, harness}** (locus/medium theme) — *Defect:* names the
   locus but misses the defining invariant. The staff archetype's raison
   d'être is "never commits" (mechanized J-A); "chat" doesn't say it. A
   label that misses the archetype's defining invariant is a bad label,
   however pithy.
3. **{commit-free, world-verified, harness-verified}** (trust-boundary
   theme) — *Defect:* "commit" is overloaded in dsys (accretion-commit).
   A "commit-free agent" reads as one that never accretes — false and
   confusing. Most precise on the invariants, but the defect is in the
   label itself, which no glossary fixes.
4. **{aphemeral, live, ground}** (ontological-status theme) — *Defect:*
   "ground" is ambiguous (noun or clipped adjective) and sits badly
   against D7's "ground truths," which the office archetype is precisely
   the one that does *not* verify against the world.

The ambient's recommendation: {staff, field, office} — the only set where
the archetype boundary falls out of the label's meaning, and the only
set coherent with the ratified profile labels' organization-function
theme (DR-CMD-068). Peter's disposition: **adopt {staff, field, office}**.

## Rationale (recorded)

The staff/line distinction is classical organization theory: staff
proposes, line disposes. All five staff members (analyst, advisor,
author, monitor, coordinator) stage proposals and never commit; the
executor alone is line. The archetype boundary coincides with the
staff/line boundary — the label teaches the architecture rather than
merely tagging it. Field and office name where the agent works: against
the world, or against the harness-interior record.

## Rename mapping (clean rename; old labels retired, no aliases)

| old label | new label | members |
|-----------|-----------|---------|
| staging-agent | **staff** | analyst, advisor, author, monitor, coordinator |
| world-facing | **field** | analyst, monitor, executor |
| harness-internal-reader | **office** | advisor, author, coordinator |

Refusal codes follow the rename: `[staff/S2]`, `[field/W1]`,
`[office/H1]`. Invariant ids (S1–S4, W1–W2, H1) are unchanged.

## What changed (rename only)

- `core/package/factory_archetypes.py`: archetype names, constant names
  (`STAGING_AGENT`→`STAFF`, `WORLD_FACING`→`FIELD`,
  `HARNESS_INTERNAL_READER`→`OFFICE`), gate refusal strings, self-test
  expectations, docstrings.
- `core/package/factory_profile_set_001.py`: the six profiles' declared
  archetype names.
- `doc/d1-d7-archetypes.md`: renamed throughout; §3 gains the
  staff/line rationale and the rename mapping; glossary entries
  rewritten (staff; field with the field-agent/schema-field
  disambiguation; new office entry).
- `doc/d1-d7-profile-planes.md`: invariant cross-references renamed
  (staff S1/S2/S4).
- DR-CMD-069 and DR-CMD-070: rename notes added at the top; bodies
  preserved as historical record (a ratified decision record is a
  transcript — it is not rewritten).

No invariant changed. The DR-CMD-070 S1 amendment stands.

## Verification (observed 2026-09-26)

- `python3 -m core.package.factory_archetypes` → gate self-test: ok
  (six exemplars 0 violations; negative control refuses at `[staff/S2]`;
  unknown archetype rejected)
- `python3 -m core.package.factory_profile_set_001` → 6 verified,
  0 warnings; repeat runs byte-identical
- `python3 -m core.package.factory_golden_run` → 45 passed, 0 violations,
  4 expected refusals
- Other regression suites (agent_behavior, bridge, updater,
  drive_contract, acquisition, pvb_workflow, scenario_sim, playbook)
  → green

## Consequences

- Authoring flow, compiler contract (DR-CMD-066), verifier, and plane
  tags (DR-CMD-070) are untouched.
- The glossary disambiguation (field agent vs schema field) is the
  standing mitigation for the one recorded defect; revisit if confusion
  is observed in practice.

## G6 (uncertainties)

- Whether "field" proves confusing in practice despite the glossary
  note — the revisit trigger is observed confusion, not speculation.
- Next free identifier: **DR-CMD-072** (DR-CMD-059 still earmarked for
  the PVB Definition of Done).
