# DR-CMD-075 — Item-7 /pb-decide ratifications: D6 self-source and D7 corroboration

**Date:** 2026-09-26
**Matter:** D1–D7 agent factory, step-7 run-through (DR-CMD-061) — factory
self-profile (`doc/d1-d7-factory-self-profile.md`), open questions 3 and 4.
**Selector:** Peter. **Disposition:** ratify both as recommended (2026-09-26).

## 1. Do the factory's own AutomatonFlow transitions count as a D6 `self` source?

**Decided: NO.**

The factory's pipelines run as AutomatonFlows (DR-CMD-064):

- Compiler flow (`agent-compiler-flow`): ingesting → validating → deriving →
  planning → routing → materializing → attesting → done/failed.
- Verifier flow: ingesting → static_checking → probing → checking →
  attesting → verified/refused/failed.

Every mid-flow transition fires on `run_completed` (with a payload guard,
e.g. `violation_count == 0`, `hashes_match == True`) or `run_aborted` →
failed. The only entry trigger is `external` at "ingesting", injected by the
operator's disposition (DR-CMD-061 authorized step 5 as one run, not as a
standing permission).

**Rationale recorded.** Continuation ≠ activation. Each transition is the
pipeline continuing downstream of the single operator-injected entry event;
nothing *decides* to begin a new step, and nothing wakes the factory
unprompted — no cadence, no sweep, no wake-up. The abort edges are
termination, not activation. Counting transitions as sources would make
every multi-step AutomatonFlow self-sourced and collapse the source enum's
discrimination ("woke itself up" vs "kept working" would become
indistinguishable). The flow's `run_completed`/`run_aborted`/`external`
triggers are control-plane signals, not D6 trigger sources — conflating the
two vocabularies was identified as the trap and rejected.

**Consequence.** D6 stays `{operator}`, gate `authenticated-session`,
authorization "may-act on disposition". The doc's open question 3 is closed;
no `self` source is added to the factory self-profile.

## 2. Corroboration against external ground truth — should `world_target` become true?

**Decided: AGAINST, for now.**

The factory will not corroborate profiles against external ground truth:
no registry attestation (signed tool contracts verified against a trust
root), no independent recompilation across factory instances, no
tool-behavior attestation. `world_target` stays false; D7 stays 0.75.

**Rationale recorded.**

- **Category.** The factory's claim is "this profile conforms to the
  ratified spec" — the spec is the ground truth, and it is internal
  (intent), exactly what D2's `intent_wins_ties` encodes. Treating
  spec-conformance as an empirical claim is a category error.
- **Trust import.** Corroboration makes the verdict depend on something
  outside the ratified spec. On attestation-service outage the factory
  would have to fail closed (halt all builds) or fail open (build anyway)
  — neither is named by the spec, and either changes the factory's
  character.
- **Regress.** Who attests the attester? The trust root needs its own
  verification — D7 all the way down, no natural floor.
- **Determinism.** External corroboration injects network/time dependence
  into a D3 0.0 pipeline: a build verifying today might not verify
  tomorrow, breaking byte-identical reproducibility (A4).

**Deferred as G6.** Revisit trigger: *revisit if a built agent's failure
traces to a false registry claim that attestation would have caught.*
Corroboration remains an operating-time concern (is this tool actually safe
in the world); the factory's jurisdiction is build-time spec-conformance.
The doc's open question 4 is closed with this deferral.

## Still open

- **Item 7 (continued):** the D5 accretion-writes reading (zero
  contracted-tool write scope vs a factory-specific write-scope channel —
  the least comfortable reflexive fit) and the D2 world-reading stipulation
  ("world = presented profile bytes" vs the deployment environment). Both
  with Peter now.
- **Item 9:** /pb-decide on the five defect dispositions.
- **Item 10:** final ratify of the factory implementation as built.

Already disposed in this run-through: DR-CMD-074 (Item 6 coverage, Item 5a
chain head, Item 5b staged-unmatched-triggers); orphan-triage policy timing
still with Peter.

## Identifier discipline

DR-CMD-075 is this record. DR-CMD-059 remains earmarked for the PVB
Definition of Done. Next free identifier: **DR-CMD-076**.
