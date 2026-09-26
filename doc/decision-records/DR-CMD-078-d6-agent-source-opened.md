# DR-CMD-078 — D6 `agent` source: OPEN NOW (ratified)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~11:55 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (selection among /pb-decide variants)
- **Matter:** Item 9, D6 `agent` source gap (F1) — defer vs. open now.

## Dialectic trail

1. **Standing position (defer):** F1 was confirmed mechanically (C-coordinator-f1)
   and in-flow (M6): D6's source enum `{operator, world, self}` cannot name
   inter-agent afferents; the coordinator's upstream-agent afferent rides
   `self` (staging-area sweeps) + `operator` (commissioned routing rules).
   The defer recommendation treated this as a schema-design matter, not a
   localized defect repair.
2. **/pb-decide elicitation (defer vs. open now), three examples:**
   - *Coordinator sweep honesty.* Analyst stages proposal P (author=analyst);
     coordinator's cadence fires (self); it sweeps, finds P, routes per
     commissioned rules (operator). What *activated* the coordinator is its
     cadence — `self:staging-sweep` is a true citation of the activation.
     The analyst's authorship lives in P's author field — D4/records, not
     D6. D6 tracks *activation*; provenance tracks *authorship*. The
     self+operator citation factors the causal chain across two dimensions;
     it does not distort it.
   - *What `agent` would actually name.* A hypothetical dispatcher that
     *directly triggers* the executor ("execute this now"). The executor's
     activation source would be neither operator, world, nor self. No built
     agent does this. dsys coordinates **stigmergically** — agents stage into
     shared media (staging area, world state); others discover on their own
     cadence. Nobody triggers anybody directly. A direct trigger would route
     around the staging area — the place where proposer≠disposer is
     enforced — so it is not merely unneeded; it is architecturally wrong
     here.
   - *The audit test.* "Why did the coordinator route P?" Record:
     self-triggered sweep + operator-commissioned rules + P authored by
     analyst. Complete, undistorted. The tripwire (must *distort*
     provenance) had not fired and could not fire under stigmergy.
3. **Refined reading offered:** F1 mechanically confirmed the enum cannot
   name inter-agent *triggers* — but dsys has no inter-agent triggers. The
   "gap" was reference-level (the design space includes message-passing
   systems), not a dsys defect. The enum was complete for activation in
   this architecture.
4. **Peter's selection — OPEN NOW.** Grounding reason (his words):
   *"coordinator needs to be able to operate autonomously upon state
   changes."* That is a real capability need the refined reading missed:
   **event-driven reactivity to other agents' staging actions**, not just
   cadence-driven sweeps. The coordinator must *wake* when staging state
   changes — the state change is authored by another agent, so the wake
   source is honestly `agent`, even though the trigger rides *through*
   staging (never around it).

## Decision

**OPEN NOW** — design and build the D6 `agent` source, bound by Peter's
grounding and the stigmergic constraint:

- The trigger rides **through** staging, never around it: the state change
  IS a staging record, so proposer≠disposer is untouched. The coordinator's
  authorization stays stage-only (staff); the new source changes WHEN it
  wakes, not WHAT it may do.
- Gating is **authenticated-agent**: admitted only if the staging record's
  hash chain verifies AND the author id names a verified built agent.
- Scope: the coordinator binds `agent` now; the source exists schema-wide
  for other profiles to bind later (mirroring the D5 write_scope treatment).
- The scheduler cadence stays as reconciliation backstop (missed events,
  crash recovery) — a J-call recorded in the spec.

## F1 gloss reframe (supersedes the DR-CMD-073/074 framing)

F1 is no longer "reference-level open / correct absence." It is now an
**opened dsys design matter**, resolved by this disposition: the enum gains
`agent`; the coordinator binds it with authenticated-agent gating; the
stigmergic-trigger theory (triggers through staging, never around it) is
recorded in `doc/d1-d7-d6-agent-source-spec.md`. The mechanical F1 finding
(the old enum could not name the afferent) is preserved as history; its
"finding, not a defect" status is retired — it is now implemented.

## Consequences (what changes, per G4)

- **Schema:** `TriggerSource` gains `AGENT = "agent"`;
  SCHEMA_VERSION 1.1 → 1.2 (no documented bump rule exists — recorded
  as-built, same discipline gap noted under DR-CMD-077).
- **Coordinator profile:** binds `agent` (gate: authenticated-agent staging
  event; authorization: stage-only). SELF cadence retained as backstop.
- **Substrate:** new `StagingEventListener` — the staging-event feed the
  agent trigger subscribes to; attestation pre-computed at the listener
  (chain verifies + author in verified-built-agent registry), fail-closed.
- **Compiler:** `_LISTENERS` gains `"agent": "staging-event-feed"`.
- **Verifier:** no change — the `authenticated` gate keyword already drives
  the P-D6-trigger fixtures.
- **Golden runs:** new A-* agent-source cases (admit on authenticated
  staging event; refuse spoofed author; refuse broken chain; arbitration
  staged on agent trigger with may-act still refused at [staff/S4]); M6
  updated (coordinator now binds agent).
- **Docs:** new spec `doc/d1-d7-d6-agent-source-spec.md` (Glossary +
  J-calls); F1 notes in `doc/factory-profile-set-001.md` and
  `doc/d1-d7-archetypes.md` amended; coordinator artifact hash recomputed
  with supersession note.
- **Reference level:** D6's reference description gains the `agent` source
  and the stigmergic-trigger theory (in the new spec doc; the machine-native
  reference is `agent_behavior.py`'s D6 text).

## Uncertainties (G6)

- None new. The orphan-triage policy (Item 5b) and the remaining Item 9
  items (REFERENCE validation, D4 `records_*`, `model_copy`) are untouched
  by this disposition.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next disposition identifier: DR-CMD-079.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed "open now"
only): this record. Design + implementation of the agent source (schema,
substrate, profile, compiler, verifier fixtures, golden runs, docs) was
authorized as a follow-on build under the ambient's hand and returns for
verification. Commit and push return as follow-on dispositions.
