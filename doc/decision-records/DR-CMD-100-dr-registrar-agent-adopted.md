# DR-CMD-100 — `dr_registrar` agent adopted; the dog-food clerk (as-built deviation)

- **Status:** adopted (with as-built deviation — same class as DR-CMD-096/097)
- **Date:** 2026-09-27 ~18:29 PDT
- **Matter:** "Proceed with the decision-record registrar agent."
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "proceed with `decision-record registrar` agent"
(~18:29 PDT 2026-09-27), adopting the suggested exemplar clerk: a
clerk-shaped agent that governs Decision Records themselves — the
D1-D7 architecture's own governance memory. Working name
`dr_registrar`, flagged provisional-in-name-only; final naming is
Peter's disposition. No existing profile is modified.

## Background

- DR-CMD-094: clerk admitted (CL1–CL6). DR-CMD-095: name confirmed.
  DR-CMD-096/097: registrar_clerk and triager adopted, both with the
  load-bearing compile-at-routing deviation (no contracted tool backs
  their write channels; J1 closed registry not amended, nothing
  silently substituted).
- DR-CMD-099 (O3, scope-don't-build): no new registrar for the
  Architecture schema; the adopted registrar_clerk covers schema
  artifacts under five commissioned mechanical vetting criteria, in
  the existing artifact registry.
- The suggestion (accepted): the exemplar clerk the architecture's
  own design/authoring/build work needs is a **decision-record
  registrar**. Ninety-nine DRs in, the next-free identifier chain is
  still hand-maintained in every record; the failure modes are real,
  frequent, and mechanical — duplicate identifiers, skipped numbers,
  malformed records, dangling premise links, addenda applied to
  nonexistent records.
- Why this agent and not the alternatives: profile-conformance is
  already gated mechanically inside every set run (no judgment left
  for an agent); spec/glossary linting is script territory (no
  agency). The DR registrar exercises bounded judgment — sequence
  integrity, reference resolution — that is genuinely office work, at
  the highest frequency of anything the authoring loop does, and its
  failure mode (a broken decision chain) damages governance directly.

## Profile spec

| Dim | dr_registrar (new, `core/package/authored/dr_registrar.py`) |
|---|---|
| D1 | **0.5**, per_event_disposition=False, standing_dispositions=["vet-and-register-dr-drafts-standing"] (CL1) |
| D2 | principal_wins_ties — the commissioned vetting criteria bind; presented bytes never win ties (CL6) |
| D3 | 0.0, deterministic_execution=True, replay_supported=True |
| D4 | 1.0, records events/intents/verifications (CL2) |
| D5 | **0.15**, write_scope=["decision-record-registry"] — bounded, one declared channel (CL3; see deviation) |
| D6 | {OPERATOR} only — scheduled sweep of the staging area; arrivals never trigger (CL4) |
| D7 | 0.75, intent/event/trigger verified, world_target=False, fail_closed (CL5) |

Role: on the operator's schedule, sweep staged DR drafts; vet each
against the mechanical criteria — (1) identifier well-formed
`DR-CMD-###`; (2) next-in-sequence vs the registry tip (no gaps, no
duplicates, honoring reservations e.g. DR-CMD-059); (3) required
sections present (status, date, matter, premises, next-free);
(4) cited premise refs resolve against the registry; (5) supersedes /
addendum targets exist; (6) content-hash not already registered.
**Record** the well-formed append-only; **defer** the malformed for
operator disposition (proposer != disposer preserved). Pure total
decision function `dr_record_decision(draft, tip)` → ("record" |
"defer", reasons) — every draft maps to exactly one outcome, never
silent. Reads staged drafts plus the existing
`doc/decision-records/` directory as presented material (no new
infrastructure needed for reading); never investigates the world.

## Verification

- **Validate:** green. Constructs with zero warnings; D positions
  0.5/0.0/1.0/0.15/0.75 as specified.
- **Clerk gate:** `check_profile(dr_registrar_profile(), ("clerk",))`
  → zero violations, CL1–CL6 all pass, including on the
  `bind_personalization` fixture-bound profile.
- **Negative controls:** vs ("staff",) refused with S1+S2+S4; vs
  ("field",) refused with W1 — the right reasons. Vs ("office",)
  *conforms* — expected by design (CL5 reuses H1; the profile
  declares ("clerk",) only, the stronger claim). The staff+field
  **monitor** vs ("clerk",) refused with CL1+CL3+CL4+CL5+CL6.
- **Diagnostics:** D-DR-1..D-DR-5 pass (may-act shape,
  operator-only triggers, office reading, bounded write scope,
  principal-wins). D-DR-6..D-DR-14 pass — clean next-in-sequence
  records; duplicate identifier, skipped number, reserved-number
  misuse (DR-CMD-059), missing sections, dangling premise ref,
  addendum-to-nonexistent, duplicate content-hash, and malformed
  identifier all defer with explicit reasons. D-DR-15 (artifact
  fidelity) needs a compiled artifact — blocked, see deviation.
- **No regressions:** set-001 run `ok: true` (7/7); set-002 run `ok:
  true` (wright + registrar); archetype self-test green (9
  exemplars, 0 violations); factory golden run 192 passed.
- **Determinism:** canonical hash stable across constructions
  (`42abe29060b69a22…`). Full validate→compile→verify replay is
  blocked, see deviation.

## As-built deviation (load-bearing; same class as DR-CMD-096/097)

`write_scope=["decision-record-registry"]` names the true effect
channel, but the factory compiler's closed contracted-tool registry
(J1, DR-CMD-055/057) resolves write channels only against
AGENT_TOOL_IDS / CHANNEL_ALIASES — and **no contracted tool backs
decision-record registration today**. Compile therefore refuses at
the **routing** stage, mechanically confirmed (fixture-bound
profile):

> `CompileRefused: compile refused at routing: write-scope channel
> 'decision-record-registry' names no registered contracted tool or
> alias (B-3 analog)`

Separately, the DR registry does not exist as a contracted structure
(`doc/decision-records/` is a directory). Reading it as presented
material needs no new infrastructure; a registry structure is
explicit follow-on work — not built in this task, per the build
brief.

Consequences, all deliberate, none silent:

1. The profile is authored
   (`core/package/authored/dr_registrar.py`), validates, and passes
   the clerk gate — but is **not registered** in `PROFILE_SET_002` /
   `PROFILE_ARCHETYPES_002` (registering it would break the set-002
   run). Nothing existing was modified.
2. `CLERK.members` stays `()` — no built clerk member is runnable
   yet, so the population claim is not made.
3. The populate trigger (≥2 built profiles) is **not yet satisfied**
   in the runnable sense: three clerk-shaped profiles are now
   authored and gate-verified (registrar_clerk, triager,
   dr_registrar), none registered.

The channel disposition now covers three profiles with one decision
for Peter:

- **(a)** Authorize building contracted tools per the DR-CMD-055
  tool discipline — `tool-register-artifact` (DR-CMD-096), the
  triage channel tools (DR-CMD-097), and a decision-record
  registration channel (this record) — then all three profiles
  compile, verify, and register as specified. The honest
  completion path.
- **(b)** Re-scope the effect channels to existing tool ids — none
  is semantically right; not recommended.
- **(c)** Amend the closed-registry discipline — J1 is load-bearing;
  not recommended.

No channel was silently substituted, no tool was added to the
pinned registry, the closed-registry discipline was not amended,
and no registry structure was built.

## Consequences

- Third clerk member authored and gate-verified; the dog-food loop
  now exists as specified code — the architecture's governance
  memory has a registrar waiting on its channel.
- The populate trigger's *shape* requirement is met three times
  over; the *runnable* requirement awaits the channel disposition
  (a) above.
- Follow-on work explicitly queued (not started): the DR registry
  as a contracted structure; the decision-record registration tool
  channel.

## Uncertainties (G6)

- The channel disposition (a/b/c above) gates factory registration
  of all three clerk members. Until it lands, all three are
  adopted-but-unregistered: specified, gate-verified, unrunnable
  through the pipeline.
- Final naming of `dr_registrar` is Peter's disposition
  (provisional-in-name-only).

## Premises

DR-CMD-069 (archetype as checked constraint), DR-CMD-077 (D2 binary
enum), DR-CMD-094 (clerk admission; CL1–CL6; populate trigger),
DR-CMD-095 (name confirmed), DR-CMD-096/097 (adoption + deviation
class precedent), DR-CMD-098 (population-tracking exemplar battery),
DR-CMD-099 (O3 scope-don't-build; five vetting criteria),
`core/package/factory_archetypes.py` (CLERK),
`core/package/factory_compiler.py` (J1 closed registry; routing
refusal), `core/package/authored/dr_registrar.py` (new).

Next free identifier: DR-CMD-101 (DR-CMD-059 still reserved for PVB DoD).
