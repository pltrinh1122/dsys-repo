# DR-CMD-082 — Item 10: D1–D7 agent factory implementation RATIFIED as built

- **Date:** 2026-09-26 ~14:22 PDT
- **Matter:** Item 10 of the D1–D7 agent factory plan (DR-CMD-061) — final disposition on the factory implementation as built and amended
- **Disposition:** RATIFY AS BUILT (Peter, 2026-09-26)
- **Disposition mode:** ratify (final; "do not silently ratify" — this record is the ratification)
- **Status:** ratified; implementation RATIFIED. This closes the step-7 run-through of the DR-CMD-061 plan.

## The ratification

Peter rendered **"ratify as built"** on the Item-10 disposition (~14:22 PDT
2026-09-26). The D1–D7 agent factory implementation — compiler, verifier,
substrate, profile set, archetypes, and all amendments through DR-CMD-081 —
is **RATIFIED as built**, carrying the four explicit G6s below. Nothing in
this ratification is silent: the as-built state, the verification evidence,
and the carried uncertainties are all recorded in this document.

This closes the step-7 run-through (DR-CMD-061). The factory arc's DR chain
is **DR-CMD-074 through DR-CMD-082** (DR-CMD-059 remains reserved for the
Product Vision Board Definition of Done).

## As-built state (ratified)

- **Schema v1.2.** D2 is the binary enum `{principal-wins-ties,
  world-wins-ties}`, scalar retired, C6 retired as superseded (DR-CMD-077).
  D6 sources are `{operator, world, self, agent}` (DR-CMD-078); J-G (retain
  SELF cadence as reconciliation backstop), J-H (`agent` schema-wide,
  coordinator-only binding), J-I (attestation pre-computed at the
  StagingEventListener) all ratified YES as recommended (DR-CMD-080). D1,
  D3, D4, D5 remain computed scalars; D2 is categorical; D6 has no scalar.
- **Sextet.** Six profiles — analyst, advisor, author, executor, monitor,
  coordinator — all archetype-conformant under the Triad (staff, field,
  office; DR-CMD-069/071). The coordinator binds `{operator, self, agent}`
  and stays stage-only (staff S4): the `agent` source changes WHEN it wakes
  (attested staging events from verified built agents), not WHAT it may do.
  Triggers ride *through* staging, never around it — proposer≠disposer
  holds.
- **Item-9 remediation (DR-CMD-079).** REFERENCE validation implemented at
  the read sites (`reference_binding`, refuse-with-reasons, never silent,
  reads excluded from the build hash); archetype self-test `model_copy`
  replaced with validating `model_validate`; D4 `records_*` remains
  factory-wide (deferred as G6, see below).
- **Orphan-triage structural policy (DR-CMD-081).** Coordinator holds the
  drain duty; closure by construction (append-only staging file, `triage()`
  the only exit, disposition ∈ {routed, refused, archived} with mandatory
  reasons, no removal API); orphan count + oldest-age as standing
  coordinator disclosure. Shape-specific routing rules deferred as G6 (see
  below).

## Factory self-profile (ratified DR-CMD-076, amended DR-CMD-077/080)

D1 **0.0**, D2 **principal_wins_ties** (categorical, no scalar), D3 **0.0**,
D4 **1.0**, D5 **0.0**, D6 **structural, {operator}** (no scalar; the D6
source enum now carries four members — DR-CMD-078/080 — but the factory's
own binding remains `{operator}`, DR-CMD-075 unchanged), D7 **0.75**
(intent + event + trigger verified; world not corroborated).

## Final verification evidence

- **Factory golden run: 183 passed, 0 violations, 4 expected refusals.**
  Reconciles exactly: 139 (D2 baseline: 138 + 1 converted C6 refusal) + 18
  (D6 A-* battery + M6) + 11 (REFERENCE R-* battery) + 15 (orphan O-*
  battery).
- **Agent-behavior golden run:** 0 violations, 11 expected refusals, ok=True.
- **Archetype self-test:** six profiles conform, negative control refused,
  unknown archetype rejected.
- **Bridge, updater, drive contract, acquisition, Product Vision Board
  workflow, scenario simulation, playbook suites:** green.
- **Determinism:** two consecutive factory golden runs byte-identical.
- **Artifacts:** six profile artifact hashes recomputed with supersession
  notes (bytes changed across the D2, D6, and REFERENCE amendments).

## Carried G6s (explicit, not silent)

1. **D7 corroboration (DR-CMD-075).** `world_target=false`; D7 stays 0.75.
   Revisit trigger: a built agent's failure traces to a false registry
   claim that attestation would have caught.
2. **D4 `records_*` per-profile override (DR-CMD-079).** Factory-wide
   instrumentation guarantee stands. Revisit trigger: a *concrete* profile
   genuinely needs less instrumentation (e.g., forever-retention infeasible
   at field volume).
3. **Shape-specific orphan routing rules (DR-CMD-081).** Structural policy
   is ratified; which orphan kinds route where, aging thresholds, and
   escalation ladders are deferred. Tripwire: first production orphan past
   30 days untriaged, or the first production run's retrospective, whichever
   comes first.
4. **SCHEMA_VERSION bump rule — ADOPTED after ratification (see below).**
   At the moment of ratification (~14:22 PDT) no rule had been adopted:
   the 1.0→1.1 (DR-CMD-077) and 1.1→1.2 (DR-CMD-078) bumps stood as
   recorded as-builts with comments in the compiler, and the discipline gap
   (no documented bump rule) was carried open. Moments after ratification,
   Peter adopted the candidate rule as recommended. The adoption is
   recorded in the next section so the sequence stays honest: the factory
   was ratified *with the gap open*, and the gap was closed *after*.

## Post-ratification adoption: schema versioning rule

Moments after the Item-10 ratification, Peter adopted the candidate bump
rule as recommended:

> **Minor version bump on any schema-enum or schema-field change, recorded
> in the implementing decision record.**

The rule is now stated durably at the SCHEMA_VERSION definition site
(`core/package/factory_compiler.py`, "Schema versioning rule" note).
Consistency check: the two historical bumps — 1.0→1.1 (D2 scalar retired
for the binary enum, DR-CMD-077) and 1.1→1.2 (D6 source enum gains AGENT,
DR-CMD-078) — were both enum changes, so both are consistent with the
adopted rule; no retroactive conflict. The discipline gap is closed.

## Authority boundaries

The tree remains **uncommitted** (43 changed/untracked files on branch
`main`, HEAD `2d5a234`). Commit is a separate local authority and push a
separate publication authority (single-use GitHub device flow, external
browser); neither was granted by this ratification. Ratification accepts
content; transcription records it; commit snapshots bytes locally; push is
publication.
