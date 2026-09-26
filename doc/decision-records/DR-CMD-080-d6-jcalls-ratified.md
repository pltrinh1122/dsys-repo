# DR-CMD-080 — D6 `agent` source: judgment calls ratified (J-G, J-H, J-I)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~14:15 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (selection among variants as framed in the
  2026-09-26 ~12:01 disposition message)
- **Matter:** DR-CMD-078's open loop — the three judgment calls in the D6
  `agent`-source design spec (`doc/d1-d7-d6-agent-source-spec.md`),
  returned for Peter's disposition at build time.

## Selections

Peter: **"ratify YES as recommended"** — all three as the ambient proposed:

1. **J-G — retain the SELF cadence as reconciliation backstop: YES.**
   The staging-event feed can miss (crash between write and wake); the
   sweep is idempotent, so the backstop is free. Pure event-driven would
   leave a missed event sitting forever. The coordinator therefore binds
   `agent` for event-driven waking AND keeps its self cadence for
   reconciliation.

2. **J-H — `agent` in the schema-wide D6 enum, coordinator-only binding:
   YES.** The source exists for all profiles (mirroring the D5
   `write_scope` treatment); only the coordinator binds it now. No other
   agent has the autonomous-arbitration role; binding everywhere would be
   premature.

3. **J-I — attestation pre-computed at the StagingEventListener: YES.**
   The listener (which holds the writer + registry) pre-computes the
   authenticated flag; the existing `authenticated` gate keyword admits on
   it — zero gate-semantics change. Gate-side attestation would widen the
   gate's authority for no gain.

## State

This closes the D6 matter's open loop from DR-CMD-078. What remains is
**Item 10**: ratification of the factory implementation as built/amended
(including the D6 agent-source build, the DR-CMD-077 D2 enum, and the
DR-CMD-079 Item-9 remediations) — a separate follow-on disposition.
Nothing in this record ratifies the build itself.

## Mechanical consequence recorded here (not a silent amendment)

As a direct mechanical consequence of the already-ratified DR-CMD-078
(the enum gained `agent`), `doc/d1-d7-factory-self-profile.md` — a
**ratified** document (DR-CMD-076) — gains one explicit line in its D6
section: the D6 source enum now carries four members
{operator, world, self, agent}, while the factory's own D6 binding remains
{operator}. DR-CMD-075 (no self source for the factory) is unchanged and
unamended. This edit is flagged here precisely so no ratified document is
amended silently.

## Uncertainties (G6)

- None new. The SCHEMA_VERSION bump-rule discipline gap (1.1 → 1.2, no
  documented rule — noted in DR-CMD-078 as a second occurrence of the
  DR-CMD-077 pattern) remains an open G6 candidate for Item 10.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next disposition identifier: DR-CMD-081.
