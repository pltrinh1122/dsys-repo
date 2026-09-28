# DR-CMD-097 — `triager` profile adopted; second clerk member authored (as-built deviation)

- **Status:** adopted (with as-built deviation — same class as DR-CMD-096)
- **Date:** 2026-09-27 ~18:17 PDT
- **Matter:** "Building the triager as a clerk member is the right next
  step to populate the clerk archetype."
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "adopt 'triager' profile" (~18:17 PDT 2026-09-27),
closing the populate-clerk /pb-decide ('monitor' vs. 'registrar' vs.
'triager'; KEEP was O1 registrar then O2 triager, O3 monitor declined).
The triager is adopted as the second clerk member — a new profile, the
monitor's clerk-shaped downstream. No existing profile is modified.

## Background

- DR-CMD-094: clerk admitted (CL1–CL6), `members=()`. DR-CMD-095: name
  confirmed. DR-CMD-096: registrar_clerk adopted with load-bearing
  as-built deviation (compile refused at routing — no contracted tool
  writes the artifact registry).
- The /pb-decide dialectic: the monitor fails clerk on four of six
  invariants (CL1, CL4, CL5, CL6) — its identity *is* the honest
  world-watch (J-E, world_wins_ties). The coherent clerk-shaped watcher
  is triager-shaped. The composition: **field monitor detects and
  stages** (staff+field — corroborated change → staged alert proposal)
  → **triager reads the staged items and acts** on standing operator
  disposition. Detection is field work; triage is office work.
- CL4 resolution (the router/dispatcher falsification): triage runs
  **on schedule** — the schedule is the operator's standing trigger.
  Arrivals never trigger it, so D6 ⊆ {OPERATOR} holds for an
  arrival-driven kind.

## Profile spec

| Dim | triager (new, `core/package/authored/triager.py`) |
|---|---|
| D1 | **0.5**, per_event_disposition=False, standing_dispositions=["triage-staged-standing"] (CL1) |
| D2 | principal_wins_ties — the commissioned triage criteria bind; presented bytes (e.g. self-asserted severity) never win ties (CL6) |
| D3 | 0.0, deterministic_execution=True, replay_supported=True |
| D4 | 1.0, records events/intents/verifications (CL2) |
| D5 | **0.15**, write_scope=["quarantine", "escalation-queue", "archive"] — bounded, three declared channels, all reversible (CL3; see deviation) |
| D6 | {OPERATOR} only — scheduled operation (CL4) |
| D7 | 0.75, intent/event/trigger verified, world_target=False, fail_closed (CL5) |

Role: on the operator's schedule, sweep the staged area; assess each
staged item against the commissioned triage criteria (office criteria
only — well-formed, attested, chain verifies, kind/severity against the
commission's bands; never investigate the world); **quarantine** the
unverified, **escalate** the urgent, **archive** the routine, **defer**
the ambiguous (defer = stage for operator disposition — the staff-like
residue: the standing disposition pre-authorizes the clear action
classes, not per-event outcomes; proposer != disposer holds for the
ambiguous middle). Pure decision rule `triage_decision(item, criteria)`
— total: every item maps to exactly one action, never silent.

## Verification

- **Validate:** green. Pydantic derived-position checks pass at
  construction: D1=0.5, D2=principal_wins_ties, D3=0.0, D4=1.0,
  D5=0.15, D7=0.75 (positions derived per DR-CMD-062, never hand-set);
  zero warnings.
- **Clerk gate:** `check_profile(triager_profile(), ("clerk",))` →
  zero violations, CL1–CL6 all pass, including on the
  `bind_personalization` fixture-bound profile.
- **Negative controls:** vs ("staff",) refused with S1+S2+S4; vs
  ("field",) refused with W1 — the right reasons. Vs ("office",)
  *conforms* — expected by design: CL5 reuses H1, office reading is a
  subset of clerk; the profile declares ("clerk",) only, the stronger
  claim. The staff+field **monitor** vs ("clerk",) refused with
  CL1+CL3+CL4+CL5+CL6 — the /pb-decide's O3 decline, mechanically
  confirmed.
- **Diagnostics:** T-D1..T-D7 pass (may-act shape, operator-only
  triggers, office reading, bounded write scope, principal-wins,
  quarantine-on-unverified, escalate/archive/defer routing). T-D8
  (artifact fidelity) needs a compiled artifact — blocked, see
  deviation.
- **No regressions:** set-002 run green (`ok: true`, wright + registrar
  verified); archetype self-test green; factory golden run 192 passed.
- **Determinism:** profile construction deterministic (canonical hash
  stable across constructions: `2baf016fa9009711…`). Full
  validate→compile→verify replay is blocked, see deviation.

## As-built deviation (load-bearing; same class as DR-CMD-096)

`write_scope=["quarantine", "escalation-queue", "archive"]` names the
true effect channels, but the factory compiler's closed contracted-tool
registry (J1, DR-CMD-055/057) resolves write channels only against
AGENT_TOOL_IDS / CHANNEL_ALIASES — and **no contracted tool backs
quarantine, escalation, or archival today**. Compile therefore refuses
at the **routing** stage, mechanically confirmed (fixture-bound
profile):

> `CompileRefused: compile refused at routing: write-scope channel
> 'quarantine' names no registered contracted tool or alias (B-3 analog)`

Consequences, all deliberate, none silent:

1. The profile is authored (`core/package/authored/triager.py`),
   validates, and passes the clerk gate — but is **not registered** in
   `PROFILE_SET_002` / `PROFILE_ARCHETYPES_002` (registering it would
   break the set-002 run). Nothing existing was modified.
2. `CLERK.members` stays `()` in `factory_archetypes.py` — no built
   clerk member is runnable yet, so the population claim is not made.
3. The populate trigger (≥2 built profiles) is **not yet satisfied** in
   the runnable sense: two clerk-shaped profiles are now authored and
   gate-verified (registrar_clerk + triager), neither registered.

The channel question now covers both profiles with one disposition for
Peter:

- **(a)** Authorize building contracted tools per the DR-CMD-055 tool
  discipline — `tool-register-artifact` (DR-CMD-096) and the triage
  channel tools (quarantine / escalation-queue / archive) — then both
  profiles compile, verify, and register as specified. The honest
  completion path.
- **(b)** Re-scope the effect channels to existing tool ids — none is
  semantically right (the eight tools cover the updater flow, not
  triage); not recommended.
- **(c)** Amend the closed-registry discipline — J1 is load-bearing;
  not recommended.

No channel was silently substituted, no tool was added to the pinned
registry, and the closed-registry discipline was not amended.

## Consequences

- Second clerk member authored and gate-verified; the monitor→triager
  composition (field detect/stage → office assess/act) now exists as
  specified code.
- The populate trigger's *shape* requirement is met twice over
  (registrar_clerk, triager — both clerk-gate green); the *runnable*
  requirement awaits the channel disposition (a) above.
- Next matter in the sequence: the tool-channel disposition, which
  unblocks both profiles at once.

## Uncertainties (G6)

- The channel disposition (a/b/c above) gates factory registration of
  both clerk members. Until it lands, both profiles are
  adopted-but-unregistered: specified, gate-verified, unrunnable
  through the pipeline.

## Premises

DR-CMD-069 (archetype as checked constraint), DR-CMD-077 (D2 binary
enum), DR-CMD-094 (clerk admission; CL1–CL6; populate trigger),
DR-CMD-095 (name confirmed), DR-CMD-096 (registrar_clerk adoption;
deviation class precedent), `core/package/factory_archetypes.py`
(CLERK), `core/package/factory_compiler.py` (J1 closed registry;
routing refusal), `core/package/authored/triager.py` (new).

Next free identifier: DR-CMD-098 (DR-CMD-059 still reserved for PVB DoD).
