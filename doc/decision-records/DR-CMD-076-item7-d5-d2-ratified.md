# DR-CMD-076 — Item 7 closed: factory self-profile ratified (D5, D2 readings)

**Date:** 2026-09-26
**Disposer:** Peter
**Status:** ratified

## Disposition

Peter ratified "as recommended" on the two remaining Item-7 open questions
(the D6 self-source and D7 corroboration questions having been disposed in
DR-CMD-075):

### D5 — keep 0.0

D5 is read over contracted tool channels: the factory binds none, so the
derived position stands at 0.0. The factory's accretion writes (staged
proposals, verdict records) are pipeline-internal operations on its own
substrate (DR-CMD-065), not tool-mediated effect scope. "Writes to its own
workbench" is not "may affect the world through tools"; conflating them
would weaken the dimension. The alternative — a factory-specific channel
(e.g. `staging-write`) raising D5 above 0.0 — is declined.

### D2 — keep the stipulation

Intent = ratified spec, world = presented profile bytes; on conflict the
factory refuses (conflict rule `intent_wins_ties`, C6 bound satisfied). The
alternative reading (world = deployment environment) is declined: the
factory never reads the deployment environment, so no competing claim from
that direction can ever reach the conflict rule — the rule would go
vacuous.

## Consequence

With these two, plus DR-CMD-075 (D6: flow transitions are not a `self`
source — continuation ≠ activation, D6 stays {operator}; D7: no
external-ground-truth corroboration, `world_target` stays false, deferred as
G6 with revisit trigger "revisit if a built agent's failure traces to a
false registry claim that attestation would have caught"), **Item 7 is now
closed**.

The factory self-profile is **RATIFIED** at:

- D1 0.0 (per-event disposition, no standing dispositions)
- D2 0.0 (declared, `intent_wins_ties`; intent = ratified spec, world = presented bytes)
- D3 0.0 (deterministic by construction)
- D4 1.0 (events, intents, verifications; operator + auditor; forever)
- D5 0.0 (zero contracted-tool write scope)
- D6 structural (single source: operator, authenticated-session gate, may-act on disposition)
- D7 0.75 (intent, event, trigger verified; `world_target` false; fail_closed)

The profile remains machine-valid: all seven dimensions validate, all
couplings C1–C7 hold, `warnings()` returns none. The factory's self-run
(`compile_profile` + `verify` → verified/operable on its own profile) stands
as conformance evidence.

## Standing notes

- The factory is not `staff`: its D6 authorization is "may-act on
  disposition" (it compiles and verifies — it acts), so staff S4 would
  refuse it. It is office-shaped (D7 0.75, no `world_target`), but the
  archetypes constrain built agents, not the builder; no archetype
  membership is claimed.
- `doc/d1-d7-factory-self-profile.md` updated to RATIFIED status with all
  four step-7 open questions marked decided.

## Still open

- Item 9: five defect dispositions (/pb-decide framed, awaiting Peter).
- Item 10: final factory ratify.

## Identifier discipline

- This record: DR-CMD-076.
- DR-CMD-059 remains earmarked for the PVB Definition of Done.
- Next free identifier: DR-CMD-077.
