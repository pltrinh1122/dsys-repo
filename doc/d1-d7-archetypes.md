# D1–D7 Agent Archetypes — authoring-reliability constraints

**Status:** adopted by Peter 2026-09-26 (DR-CMD-069). Labels renamed
staff / field / office by Peter 2026-09-26 (DR-CMD-071; old labels
staging-agent, world-facing, harness-internal-reader retired, no aliases).
Implementation: `core/package/factory_archetypes.py`; wired into
`core/package/factory_profile_set_001.py`.

An **archetype** (in this document: a named set of checkable facet
invariants plus declared parameter points, with a conformance predicate)
is a *constraint on authoring*, not a generative pipeline stage. It
answers "what must every profile of this kind get right?" at authoring
time, before the profile ever reaches the factory compiler. There is
deliberately no archetype-plus-parameters → profile instantiation
machinery: the compiler's input contract is unchanged (it takes a
validated profile; the ratified compiler spec, DR-CMD-066, is not amended
by this work).

## 1. Why archetypes

The six ratified profiles (`doc/factory-profile-set-001.md`) were built
with judgment calls J-A through J-F living in docstrings — tribal
knowledge. Each new profile re-derives the same decisions by hand, and
nothing mechanical stops an author from drifting: granting a
research-type agent a write scope, claiming world corroboration for an
agent that never touches the world, or leaving a world trigger
unauthenticated. The schema's own validators (couplings C1–C5, C7 — C6 retired, DR-CMD-077 — in
`core/package/agent_behavior.py`) catch *incoherence*; they do not catch
*unwise-but-coherent* profiles. Archetypes close that gap: they mechanize
the invariants the six exemplars already share, so the seventh profile
inherits them structurally instead of rediscovering them.

Scope of the claim (per the adoption disposition): archetypes improve
**authoring reliability** — invariants enforced once, not per profile.
They do not improve the verified reliability of factory output beyond
what per-profile verification already delivers (every profile is still
fully compiled and verified), and the efficiency thesis (payoff at
profile volume) is explicitly deferred, not adopted.

## 2. What an archetype is and is not

**Is.** A named, versioned bundle of:
- **facet invariants** — checkable predicates over an
  `AgentBehaviorProfile` (each returns *None* when it holds, otherwise a
  human-readable reason);
- **parameter points** — documented degrees of freedom the author
  decides within schema bounds (e.g. D2 conflict rule, D7 failure
  policy);
- **a conformance predicate** — `conforms(profile, archetype)` returning
  the list of violations (empty = conforms).

**Is not.**
- Not a generator: no instantiation step, no parameters-to-profile
  compilation. A profile is still authored in full; the archetype only
  *checks* it.
- Not a profile: profiles are instances (the six exemplars conform to
  archetypes; archetypes do not conform to anything).
- Not a compiler change: the authoring gate runs *before* compile, in
  the authoring harness. `compile_profile` never sees an archetype.
- Not a disposition: archetype conformance never authorizes anything.
  Proposer ≠ disposer is untouched.

## 3. The archetype set

The Tetrad (DR-CMD-094, 2026-09-27; "Triad" deprecated). Staff, field,
and office derived from the seven profiles' shared invariants.
Admission rule: an archetype is adopted only if it captures invariants
shared by ≥2 profiles or guards a critical authoring risk — the bar
stands for future admissions. Clerk (may-act × office) was admitted by
operator disposition (DR-CMD-094), superseding DR-CMD-093's deferral
and the evidentiary bar for this instance; it has no built profiles
yet. A single-member "acting-agent" for the executor's field may-act
D1/D5 shape remains declined — the data does not earn it, and coupling
C7 plus the field archetype already cover its critical core.

Names (DR-CMD-071; clerk confirmed, DR-CMD-095): **staff**,
**field**, **office**, **clerk** — a single coherent theme of
organizational posture, matching the profile labels'
organization-function theme (DR-CMD-068). *Staff* is the classical
staff/line distinction: staff proposes, line disposes. *Clerk* is the
office counterpart of acting: it acts on standing operator disposition
while reading staged material only — the label confirmed by operator
disposition (DR-CMD-095). 'Line' is reserved for the may-act pole if a
pole-renaming redesign is ever disposed. All six staff
members (analyst, advisor, author, monitor, coordinator, customizer)
stage proposals and never commit; the executor alone is line. The
archetype boundary coincides with the staff/line boundary — the label
teaches the architecture. *Field* and *office* name where the agent
works: against the world, or against the harness-interior record.
*Clerk* names the acting posture inside the office: the inbox-organizer
shape (acts on the mailbox, reads presented mail only). Old labels
(staging-agent, world-facing, harness-internal-reader) are retired with
no aliases; refusal codes now read e.g. `[staff/S2]`, `[field/W1]`,
`[office/H1]`, `[clerk/CL3]`.

### 3.1 staff — members: analyst, advisor, author, monitor, coordinator, customizer

Agents whose entire work product is staged proposals for operator
disposition. Mechanizes judgment call J-A.

| id | invariant | guards |
|----|-----------|--------|
| S1 | D1 0.0: per-event disposition true; no self-correction; no self-planning. Standing dispositions are excluded *via the derived position*: any grant moves D1 off 0.0 (DR-CMD-070 — standing_dispositions is PRINCIPAL_PERSONAL/BUILD, which archetypes may not touch; the position check keeps S1's teeth, and bind_personalization() re-runs this gate on the bound profile) | pre-authorized action smuggled into a staging role |
| S2 | D5 0.0: write_scope empty — output is staged proposals, not tool effects | invented write channels; the contracted-tools-only alias over-grant |
| S3 | D4 1.0: full event/intent/verification streams; inspectors include operator and auditor; retention forever | black-box staging (unstaged, unwitnessed proposals) |
| S4 | every D6 authorization is stage-only (no "may-act") | actuation authority leaking through trigger authorization |

Parameter points: D2 conflict rule + position (bounded by C6); D3 facets;
D6 source set (non-empty per C5); D7 targets + failure policy (bounded by
C7); D5 read_scope contents; agent label.

### 3.2 field — members: analyst, monitor, executor

Agents that read raw world claims or act on the world.

| id | invariant | guards |
|----|-----------|--------|
| W1 | D7 1.0: intent, event, world, and trigger targets all verified | unverified world contact (the F3 risk: world claims admitted without corroboration) |
| W2 | world trigger gate authenticates the trigger (rejects none/unauthenticated/empty) | unauthenticated world activation driving a verified agent |

Parameter points: D7 failure policy — escalate or fail_closed (fail_open
refused by C7 at this assurance level); D1/D2/D5 positions and facets;
D6 source sets and authorization rules.

### 3.3 office — members: advisor, author, coordinator, customizer

Agents that read harness-internal staged material only — never raw world
claims.

| id | invariant | guards |
|----|-----------|--------|
| H1 | D7 0.75: intent, event, trigger verified; world_target False | incoherent verification posture — claiming world corroboration the agent cannot perform |

Parameter points: D7 failure policy; D2 conflict rule + position; D3
facets; D6 source sets (stage-only per S4); D5 read_scope contents.

### 3.4 The two-axis model (DR-CMD-092; fourth cell filled DR-CMD-094)

The four archetypes are not four independent tags. They are cells on
two orthogonal axes:

- **Axis 1 — acting posture.** *staff* (propose-only: S1–S4 — D1 0.0,
  D5 0.0, D4 1.0, stage-only D6 authorizations) vs *may-act* (D1>0,
  D5>0, may-act authorizations permitted — the executor, and clerk).
- **Axis 2 — reading posture.** *office* (D7 0.75, no world_target:
  reads harness-internal staged material) vs *field* (D7 1.0,
  world_target: reads raw world claims).

Office and field are mutually exclusive (both pin D7); staff is
orthogonal to both (disjoint facet sets — staff S4 and field W2 touch
different D6 fields). The named archetypes as cells:

| | office | field |
|---|---|---|
| **staff** | advisor, author, coordinator, customizer | analyst, monitor |
| **may-act** | clerk | executor |

**Triad deprecated → Tetrad.** The set was three archetypes (staff,
field, office — DR-CMD-071). DR-CMD-094 (2026-09-27) admits the
fourth, clerk (may-act × office), by operator disposition —
superseding DR-CMD-093's deferral and the DR-CMD-069 evidentiary bar
for this instance. The set is now the **Tetrad**: staff, field,
office, clerk. "Triad" is deprecated for the archetype set; it survives
only in historical decision records, which stand as decided.

The may-act × office cell was unnamed by decision, not oversight
(DR-CMD-069 §3 admission rule: an archetype is adopted only for
invariants shared by ≥2 profiles or a critical authoring risk).
**Admission trigger — superseded for admission, retained for
populating:** DR-CMD-092 recorded that a fourth archetype is admitted
iff ≥2 built profiles share the may-act acting shape, or a critical
authoring risk is demonstrated that field + coupling C7 do not cover.
DR-CMD-094 supersedes this for admission — clerk is admitted with
members=(). The trigger now governs *populating* the archetype: the
outstanding work is building profiles in the clerk shape (candidates
vetted in DR-CMD-093's addendum: inbox-organizer, news-synthesizer-poster).

### 3.5 clerk — members: (none yet)

Agents that act on the world on standing operator disposition while
reading staged material only — may-act × office. Admitted by operator
disposition (DR-CMD-094, 2026-09-27), superseding DR-CMD-093's deferral
for this instance. Label confirmed DR-CMD-095.

| id | invariant | guards |
|----|-----------|--------|
| CL1 | D1 > 0.0: standing operator disposition, no per-event disposition gate (flipped S1 polarity; standing_dispositions excluded via the derived position per DR-CMD-070) | per-event proposal discipline where standing commitment is required |
| CL2 | D4 1.0: full instrumentation — a clerk's world actions are fully observed (mirrors staff S3's position requirement) | unobserved world action |
| CL3 | D5 > 0.0: non-empty, bounded write_scope — effect channels declared, never unbounded | undeclared or unbounded effect channels |
| CL4 | D6 OPERATOR only: no WORLD, AGENT, or SELF triggers (non-empty per C5) | non-operator-initiated acting without external corroboration |
| CL5 | D7 office reading: reuses H1 (0.75; intent, event, trigger verified; world_target False) | claiming world corroboration the agent cannot perform |
| CL6 | D2 principal_wins_ties: the principal's commission binds action parameters; presented bytes never win ties | action parameters set by uncorroborated presented bytes |

Parameter points: D1 standing disposition classes; D5 write_scope bounds;
D6 authorization rule text; D2 fixed; D7 on_failure (escalate | fail_closed).

D2 correction (DR-CMD-094): DR-CMD-093's derivation said
"commission_wins_ties"; DR-CMD-077 made D2 the binary enum
{principal_wins_ties, world_wins_ties}. Implemented as
principal_wins_ties — the commission IS the principal's standing
disposition; world_wins_ties is incoherent with office reading (no
world_target).

## 4. The authoring flow

```
declare archetype(s)          e.g. PROFILE_ARCHETYPES["analyst"]
        |
author the full profile       facets as today; archetype changes nothing here
        |
authoring gate: check_profile profile declared-archetypes
        |
  violations? --yes--> refuse with explicit reasons -> revise profile
        |
        no
        |
compile (unchanged) -> verify (unchanged)
```

The gate lives in the authoring harness (`run_agent` in
`factory_profile_set_001.py`), not in the compiler. A refusal names the
archetype, the invariant id, and the reason — e.g.
`[staff/S2] write_scope must be empty: ... got ['tool-run-doctor']`.
Refusal is an authoring event, not a verifier verdict: it never produces
`refused`/`failed` downstream because the profile never reaches compile.

A profile may declare multiple archetypes (analyst declares staff
*and* field); conformance is the conjunction. Declaring an unknown
archetype name is itself an authoring error (rejected explicitly).

## 5. Worked conformance — the six exemplars

Run 2026-09-26 (`python3 -m core.package.factory_archetypes`):

| profile | declared archetypes | violations |
|---------|--------------------|------------|
| analyst | staff, field | 0 |
| advisor | staff, office | 0 |
| author | staff, office | 0 |
| executor | field | 0 |
| monitor | staff, field | 0 |
| coordinator | staff, office | 0 |

Negative control: an analyst variant with
`write_scope=["tool-run-doctor"]` refuses at S2 with the explicit reason
above. Unknown archetype names raise `ValueError`. The six exemplars are
unchanged by this work — no facet was altered to fit; conformance was
verified against the ratified profiles as built.

Note the executor's position in the set: it is the *only* profile
outside staff (D1 0.25, D5 0.4, may-act authorizations) and the
only member of field that also acts. Its acting shape remains
judgment-call territory (J-C), not archetype law — the data earns no
single-member archetype for it.

## 6. Explicitly not adopted

- **Generative instantiation.** No archetype+parameters → profile
  machinery exists or is planned under this record. If profile volume
  ever justifies it, that is a separate matter with its own spec and
  ratification.
- **Compiler-spec changes.** DR-CMD-066 stands unamended; the compiler
  never sees archetypes.
- **The efficiency thesis.** Archetypes-as-efficiency (payoff at volume)
  was argued but explicitly deferred at adoption. This record covers
  authoring reliability only.
- **Single-member archetypes.** Declined for the executor's acting shape
  (see §3 admission rule).

## Glossary

- **archetype** — a named set of checkable facet invariants plus declared
  parameter points, with a conformance predicate; an authoring-time
  constraint, not a generator.
- **facet** — one configurable field of a D-dimension (e.g.
  `per_event_disposition` in D1, `write_scope` in D5). Positions are
  derived from facets (DR-CMD-062), never hand-set.
- **facet invariant** — a predicate over a profile's facets that must
  hold for conformance; returns a human-readable reason when violated.
- **parameter point** — a documented degree of freedom left to the
  profile author within schema bounds (not checked by the archetype, or
  checked only against schema couplings).
- **conformance predicate** — `conforms(profile, archetype)`: the
  function returning the list of invariant violations (empty = conforms).
- **authoring gate** — the check step that runs after profile authoring
  and before compilation; violations refuse with explicit reasons.
- **exemplar** — a ratified profile used to derive and validate an
  archetype; the six profiles in `doc/factory-profile-set-001.md`.
- **Sextet** — the six ratified exemplar profiles taken as a set:
  analyst, advisor, author, executor, monitor, coordinator (DR-CMD-068);
  the step-6 verification ensemble (DR-CMD-072).
- **staff** — an agent whose entire work product is staged
  proposals for operator disposition (D1 0.0, D5 0.0, stage-only
  authorizations). The name is the classical staff/line distinction from
  organization theory: staff proposes, line disposes. The executor alone
  is line — the archetype boundary coincides with the staff/line
  boundary, which is why the label teaches the architecture rather than
  merely tagging it. Cf. judgment call J-A.
- **staging (noun)** — the accretion-backed area where proposals await
  disposition (DR-CMD-065); cf. *staged proposal*.
- **staged proposal** — actions plus verification evidence committed to
  the staging area, awaiting the operator's disposition.
- **disposition** — the operator's verdict on a staged item: ratify,
  authorize, set_standing, overrule, or triage (DR-2).
- **proposer ≠ disposer** — architectural invariant: agents propose
  (stage); only the principal disposes.
- **trust boundary** — a point where a claim crosses between parties and
  must be checked: D7's four targets (intent, event, world, trigger).
- **field** — an agent that reads raw world claims or acts on the
  world (as opposed to reading harness-internal staged material).
  Disambiguation: *field agent* is the archetype; *schema field* is a
  configurable profile field (cf. the 26 plane-tagged fields, DR-CMD-070).
  In prose the two never collide — "field agent" always means the
  archetype — but the glossary records the distinction because both
  senses appear in factory documentation.
- **office** — an agent that reads harness-internal staged material only,
  never raw world claims (D7 0.75, world_target False); the interior
  counterpart of *field*.
- **Triad** — DEPRECATED for the archetype set (DR-CMD-094, 2026-09-27):
  the three archetypes taken as a set (staff, field, office — adopted
  2026-09-26, DR-CMD-071). Retained in historical decision records,
  which stand as decided; do not use for the current set.
- **Tetrad** — the four archetypes taken as a set: staff, field, office,
  clerk (DR-CMD-094). Structure is the two-axis model (§3.4): acting
  posture (staff — never commits, stages only; clerk — acts on standing
  operator disposition while reading staged material only, label confirmed
  DR-CMD-095) × reading posture (field — reads raw world claims; office —
  reads harness-internal staged material). The executor (field may-act)
  remains the only field-side acting profile.
- **clerk** — the may-act × office archetype (label confirmed DR-CMD-095):
  D1 > 0.0 on standing operator
  disposition, D4 1.0, D5 > 0.0 bounded write_scope, D6 OPERATOR only,
  D7 0.75 (office reading), D2 principal_wins_ties. No built profiles
  yet (DR-CMD-094).
- **harness** — the dsys execution plane in which factory-built agents
  reside (DR-CMD-063: harness-native agents).
- **DR-CMD-066** — the ratified compiler and verifier specs; unamended
  by this work.
- **C1–C5, C7** (C6 retired, DR-CMD-077) — cross-dimension couplings enforced as schema validators in
  `core/package/agent_behavior.py` (per-event→audit trail, D6
  completeness, D2 coherence, etc.).
- **J-A…J-F** — documented build-time judgment calls in the profile set
  (empty write_scope, D2 splits, standing-disposition tool ids,
  stage-only self sources, failure-policy choices).
- **F1-CONFIRMED** — the mechanically confirmed finding that D6's source
  enum {operator, world, self} cannot name inter-agent afferents.
  **AMENDMENT 2026-09-26 (DR-CMD-078):** resolved — the enum now carries
  `agent` and the coordinator binds it (authenticated-agent gating,
  stage-only); see `doc/d1-d7-d6-agent-source-spec.md`.
