# DR-CMD-099 — Architecture-schema registrar: scope, don't build (O3)

- **Status:** adopted
- **Date:** 2026-09-27 ~18:28 PDT
- **Matter:** "It is feasible and valuable to have a clerk-shaped
  `registrar` for the Architecture schema to ensure proper vetting and
  registration." (Peter's framing: "feasible and valuable to have a
  `registrar` for the Architecture schema to ensure proper vetting and
  registration".)
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "adopt O3" (~18:28 PDT 2026-09-27) on the /pb-decide
('dedicated Architecture-schema registrar' vs. 'don't build' vs.
'scope, don't build'; KEEP was O3).

## Dialectic (trail)

- **Thesis (for a registrar):** schemas are the load-bearing contracts of
  the whole system — every profile, golden run, and Decision Record leans
  on them. An unregistered schema change is an unaccountable change.
  The clerk shape is already built and gate-green (registrar_clerk,
  DR-CMD-096): mechanical vetting (validates, version-bumps,
  changelog-present, supersedes-chain intact) plus append-only
  registration on standing disposition, deferring ambiguity to the
  operator. Schema drift becomes impossible to do quietly. That is proper
  vetting, and it is feasible today.
- **Antithesis (against a new build):** three problems. (1) "The
  Architecture schema" as a single registry is not an established thing —
  the architecture has many schemas; a registrar needs a *specific*
  registry, and that scoping disposition has not been rendered. (2) No
  demonstrated need: no drift incident, no near-miss, no G6 trigger —
  the existing machinery (staff registrar staging verified builds, the
  content-addressed artifact registry, operator-disposed adoptions) has
  not failed. Building a third registry and a new profile for an
  unbitten problem is speculative machinery. (3) "Proper vetting"
  smuggles discretion: real schema vetting — *is this change sound?* — is
  staff-plus-operator work. The clerk can only check commissioned
  mechanical criteria. Without those criteria commissioned, the
  registrar is a recorder wearing a vetter's title — and we already have
  recorders.
- **Synthesis:** the valuable core is real but narrower than a new build.
  Do not build a new registrar — **scope the adopted one.**
  registrar_clerk's write_scope is already `["artifact-registry"]`, and
  Architecture schema versions are exactly the kind of content-addressed
  artifact that registry holds (DR-CMD-090/091). What is actually missing
  is not a profile — it is (a) the contracted tool channel (the
  DR-CMD-096/097 disposition) and (b) a *commissioned* mechanical
  vetting criteria set for schema artifacts, which is operator work no
  profile can do. If schema drift ever becomes a live problem, a
  dedicated schema registrar is the escalation — with the incident as its
  trigger.

## Options and gate trails

- **O1 — build a dedicated Architecture-schema registrar** (new clerk
  profile + schema registry + tool): G1 pass (spec-able); G2 pass
  (factory pipeline); **G3 conditional** — "the Architecture schema" as
  one registry needs a scoping disposition first, undisposed; G4: new
  profile + new registry + new tool — multiplies registries; **G5
  speculative** — no drift incident or near-miss on record; G6: which
  schema, exactly? what criteria? Draft: **refuse as premature**.
- **O2 — don't build** (existing machinery suffices): G1–G6 pass (status
  quo). Draft: sustain. Cost: the "proper vetting" stays uncommissioned
  and unclaimed.
- **O3 — scope, don't build**: no new profile; registrar_clerk covers
  schema artifacts under commissioned mechanical vetting criteria
  (below). G1 pass; G2 pass (profile built, gate-green; channel = the
  pending tool-register-artifact disposition); G3 pass (artifact registry
  exists; no new scoping); G4: two acts — commission the criteria
  (operator), build the tool channel (pending); G5: captures the value
  with no new machinery; G6: the criteria content itself (Peter's).
  Draft: **adopt**.

**Selected: O3.**

## Commissioned mechanical vetting criteria (schema artifacts)

Adopted as the criteria set; content ratifiable-or-amendable by Peter.
A presented schema artifact is registered iff all of:

1. The artifact **validates against its schema** (mechanical parse +
   schema check — no discretion).
2. Its **version bumps per rule** (monotonic increment over the
   registered tip for that artifact line; no skips, no repeats).
3. The **supersedes-chain is intact** vs the registry tip (the new
   version's supersession claim resolves to the currently registered
   head — no forks, no dangling claims).
4. **Required metadata is present**, including a Decision Record
   reference authorizing the change (no anonymous schema changes).
5. **No duplicate content-hash** already registered (the registry is
   content-addressed; re-registration of identical bytes is refused).

**Ambiguous → defer:** any artifact failing a criterion, or presenting a
case the criteria do not cover, is staged for operator disposition —
never registered, never silently dropped. Proposer ≠ disposer holds for
the ambiguous middle (triager precedent, DR-CMD-097).

## Dependent acts still pending

O3 is adopted but not yet operable. Two acts remain, both explicitly
**not** discharged by this record:

- **(a) The tool-channel disposition** — build contracted
  `tool-register-artifact` per the DR-CMD-055 tool discipline. This is
  the same pending (a) from DR-CMD-096/097; O3 depends on it identically.
  Until the channel exists, registrar_clerk cannot compile, cannot
  register, and cannot vet or record schema artifacts. (Alternatives
  (b)/(c) from DR-CMD-096/097 stand as recorded: re-scope — none
  semantically right, not recommended; amend J1 — load-bearing, not
  recommended.)
- **(b) Peter's ratification-or-amendment of the five criteria above.**
  The set is adopted; the *content* is his. Amendments re-enter without
  prejudice.

## Relationship to standing records

- **DR-CMD-096/097** (registrar_clerk / triager adopted with compile
  deviation): same channel blocker. This record adds no new blocker and
  removes none — it scopes the already-adopted registrar_clerk to schema
  artifacts rather than authorizing new machinery.
- **DR-CMD-090/091** (customizer admitted; customization bridge
  ratified): the artifact registry O3 relies on — content-addressed,
  append-only — is the bridge's registry. No new registry is created.
- **DR-CMD-094** (Tetrad; clerk `members=()`): unchanged. Schema
  artifacts, once the channel exists, become registrar_clerk's first
  real workload — the dog-food use case Peter named: the clerk
  archetype's first member vets and registers the Architecture's own
  schemas.

## G6 uncertainties

The criteria content (b above) and the tool-channel disposition (a
above). No other material uncertainty: the profile shape is built and
gate-green, the registry exists, the defer rule is pinned.

---
Next free identifier: **DR-CMD-100** (DR-CMD-059 still reserved for PVB DoD).
