# DR-CMD-096 — clerk-variant `registrar` profile adopted; first clerk member authored

- **Status:** adopted (with as-built deviation — see below)
- **Date:** 2026-09-27 ~18:15 PDT
- **Matter:** "Building the clerk-variant registrar as a clerk member is
  the right next step to populate the clerk archetype."
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "adopt 'registrar' profile" (~18:15 PDT 2026-09-27),
closing the populate-clerk /pb-decide ('monitor' vs. 'registrar' vs.
'triager'; KEEP was O1 registrar then O2 triager, O3 monitor declined).
The clerk-variant registrar is adopted as the first clerk member. The
existing set-002 staff registrar ("registrar", staff+office, DR-CMD-083)
is untouched — this is a second profile, the minimal pair across the
acting axis. Working name `registrar_clerk` (provisional-in-name-only;
final naming is the Operator's disposition).

## Background

- DR-CMD-094: clerk admitted (CL1–CL6), `members=()`.
- DR-CMD-095: name `clerk` confirmed.
- The populate trigger (DR-CMD-094, repurposed from DR-CMD-093) requires
  ≥2 built profiles sharing the clerk shape. This record is the first.
- The /pb-decide dialectic: the monitor fails clerk on four of six
  invariants (CL1, CL4, CL5, CL6) — its identity *is* the honest
  world-watch (J-E); the coherent clerk-shaped watcher is triager-shaped.
  The registrar is already office (D7 0.75) — its clerk variant flips
  exactly one axis.

## Variant spec (deltas vs. the staff registrar)

| Dim | staff registrar (set-002, untouched) | registrar_clerk (new) |
|---|---|---|
| D1 | 0.0, per-event, no standing | **0.5**, per_event_disposition=False, standing_dispositions=["register-artifact-standing"] (CL1) |
| D2 | principal_wins_ties | principal_wins_ties (CL6) |
| D3 | 0.5, non-deterministic | **0.0**, deterministic_execution=True, replay_supported=True |
| D4 | 1.0 | 1.0 (CL2) |
| D5 | 0.0, write_scope=[] | **0.15**, write_scope=["artifact-registry"] (CL3; see deviation) |
| D6 | {OPERATOR, SELF} | **{OPERATOR} only** (CL4; scheduled operation — arrivals never trigger) |
| D7 | 0.75, office | 0.75, office (CL5; unchanged) |

Role: on the operator's schedule, sweep the staged area for verified
build notices and adopted customization proposals; validate against
office criteria (well-formed, attested, chain verifies — never
investigate the world); record survivors into the content-addressed
append-only artifact registry (the customization bridge's registry,
DR-CMD-091); refuse the rest with reasons. The real need: today
`adopt-proposal` requires per-event operator disposition; the
standing-disposition registrar is the coherent may-act form.

## Verification

- **Validate:** green. Pydantic derived-position checks pass at
  construction: D1=0.5, D2=principal_wins_ties, D3=0.0, D4=1.0,
  D5=0.15, D7=0.75 (positions derived per DR-CMD-062, never hand-set).
- **Clerk gate:** `check_profile(registrar_clerk_profile(), ("clerk",))`
  → zero violations. CL1–CL6 all pass, including on the
  `bind_personalization` fixture-bound profile.
- **Negative controls:** staff registrar vs ("clerk",) refused with
  CL1+CL3+CL4 (D1 0.0, empty write_scope, SELF trigger — the right
  reasons); new variant vs ("staff",) refused with S1+S2+S4; vs
  ("field",) refused with W1. New variant *conforms* to ("office",) —
  expected by design: CL5 reuses H1, office reading is a subset of
  clerk; the profile declares ("clerk",) only, the stronger claim.
- **Diagnostics:** RC-D1..RC-D7 pass (may-act shape, operator-only
  triggers, office reading, bounded write scope, principal-wins,
  refuse-unverified, record-verified). RC-D8 (artifact fidelity) needs
  a compiled artifact — blocked, see deviation.
- **No regressions:** set-002 run green (`ok: true`, wright + registrar
  verified); archetype self-test green; factory golden run 192 passed.
- **Determinism:** profile construction deterministic (canonical hash
  stable across constructions: `a07a61ec405e8d94…`). Full
  validate→compile→verify replay is blocked, see deviation.

## As-built deviation (load-bearing)

`write_scope=["artifact-registry"]` names the true effect channel, but
the factory compiler's closed contracted-tool registry (J1,
DR-CMD-055/057) resolves write channels only against AGENT_TOOL_IDS /
CHANNEL_ALIASES — and **no contracted tool writes the artifact
registry today**: `adopt-proposal` writes via direct `reg.register()`
calls, ambient-side (`core/package/author_channels.py:414`). Compile
therefore refuses at the **routing** stage, mechanically confirmed:

> `CompileRefused: stage=routing — write-scope channel
> 'artifact-registry' names no registered contracted tool or alias
> (B-3 analog)`

Consequences, all deliberate, none silent:

1. The profile is authored (`core/package/authored/registrar_clerk.py`),
   validates, and passes the clerk gate — but is **not yet registered**
   in `PROFILE_SET_002` / `PROFILE_ARCHETYPES_002` (registering it
   would break the set-002 run). Nothing existing was modified.
2. `CLERK.members` stays `()` in `factory_archetypes.py` — no built
   clerk member is runnable yet, so the population claim is not made.
3. The populate trigger (≥2 built profiles) is **not yet satisfied**.

The channel question is now a clean, separate disposition for Peter:

- **(a)** Authorize building a new contracted production tool
  `tool-register-artifact` (spec per the DR-CMD-055 discipline, registry
  pin update, verifier stub) — then this profile compiles, verifies,
  and registers as specified. This is the honest completion path.
- **(b)** Re-scope the effect channel to an existing tool id — none is
  semantically right (the eight tools cover the updater flow, not the
  artifact registry); not recommended.
- **(c)** Amend the closed-registry discipline — J1 is load-bearing;
  not recommended.

No channel was silently substituted and no tool was added to the
pinned registry: both would have misrepresented what was built.

## Consequences

- First clerk member authored and gate-verified; the minimal pair
  (staff registrar / clerk registrar) now exists as specified code,
  demonstrating the acting axis of the two-axis model.
- Working name `registrar_clerk` flagged provisional-in-name-only —
  final naming is Peter's disposition.
- Next build in the populate sequence per the /pb-decide KEEP: O2
  **triager** (new build; the monitor's clerk-shaped downstream).

## Uncertainties (G6)

- The channel disposition (a/b/c above) gates factory registration.
  Until it lands, the profile is adopted-but-unregistered: specified,
  verified at the gate, unrunnable through the pipeline.

## Premises

DR-CMD-069 (archetype as checked constraint), DR-CMD-077 (D2 binary
enum), DR-CMD-091 (customization bridge; artifact registry),
DR-CMD-094 (clerk admission; CL1–CL6; populate trigger), DR-CMD-095
(name confirmed), `core/package/factory_archetypes.py` (CLERK),
`core/package/factory_compiler.py` (J1 closed registry),
`core/package/authored/registrar.py` (staff registrar, untouched),
`core/package/authored/registrar_clerk.py` (new).

Next free identifier: DR-CMD-097 (DR-CMD-059 still reserved for PVB DoD).
