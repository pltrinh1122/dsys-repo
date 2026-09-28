# DR-CMD-098 — exemplar set is population-tracking; wright + registrar join the battery

- **Status:** adopted
- **Date:** 2026-09-27 ~18:20 PDT
- **Matter:** "The archetype gate self-test's exemplar set should include
  the set-002 profiles wright and registrar."
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "adopt as recommended" (~18:20 PDT 2026-09-27) on the
/pb-decide ('wright+registrar inclusion' vs. 'keep seven' vs.
'population-tracking'; KEEP was O3 with O1 as first instance).

## The ground fact that reshaped the matter

The set-002 run **already gates every profile through `check_profile`**
against its declared archetypes (it is the `gate=` argument in
`bind_personalization`). Wright and registrar are therefore
conformance-checked on every set-002 run today. The self-test's exemplar
loop is *defense in depth* plus the definition-level negative controls —
not the sole conformance check. The dialectic turned on this: the
dispute was never seven-vs-nine but **fixed list vs population-tracking**.

## Dialectic (trail)

- **Thesis (O1 — include wright+registrar):** the battery should reflect
  the built population; "exemplars must conform" covering seven of nine
  built profiles is a silently narrowing claim; a future archetype edit
  that breaks only wright's or registrar's dimension values would go
  uncaught by the gate's own self-test. Two lines, pure gain.
- **Antithesis (O2 — keep seven):** at the definition level the battery's
  value is *shape coverage*, not headcount — and per-profile conformance
  is already enforced by the set runs. Wright and registrar are both
  staff+office, a shape already covered 4× (advisor, author, coordinator,
  customizer): depth, not coverage. The battery's real gap is the
  uncovered shape — clerk, members=(). Motion without coverage.
- **Synthesis (O3 — population-tracking):** fixed lists silently drift;
  this exact request would recur for registrar_clerk and triager on
  registration. The honest rule: **the exemplar set IS the registered
  built population, automatically.** "Registered" = present in a
  PROFILE_SET_00X + PROFILE_ARCHETYPES_00X registry with its set run
  green. Registration is the admission act, so the normative worry
  dissolves: only registered profiles count.

## Options and gate trails

- **O1 — include wright+registrar (one-off):** G1 pass; G2 pass (iterate
  the set-002 registry); G3 pass (no DR fixes the battery at seven —
  "seven exemplars" was a code comment, not a decision); G4 pass;
  G5 modest (per-run gates already enforce their conformance, so
  marginal). Draft: adopt.
- **O2 — keep seven:** G1–G6 pass (status quo). Draft: sustain. Cost: the
  battery silently narrows with every new profile; the conversation
  recurs per profile.
- **O3 — population-tracking battery:** G1 pass; G2 pass (self-test
  iterates every PROFILE_SET_00X registry via an explicit tuple of
  (PROFILE_SET, PROFILE_ARCHETYPES) pairs — one line per set, so a future
  set-003 joins with one line; explicit preferred over dynamic
  discovery); G3 pass; G4 pass ("seven exemplars" comment rewritten as
  the population rule); G5 highest (no drift, no per-profile
  dispositions, single-command whole-population assertion); G6:
  "registered" defined precisely above. Draft: adopt.

**Selected: O3, with O1 as its first instance.** Wright and registrar
join the battery now (both registered, verified, green); the rule, not
the list, is what is adopted.

## Implementation (as-built)

`core/package/factory_archetypes.py`:

- The `__main__` exemplar loop now iterates `PROFILE_SET_PAIRS`, an
  explicit tuple of `(PROFILE_SET_00X, PROFILE_ARCHETYPES_00X)` pairs
  (set-001, set-002). A future set-003 joins with one line.
- The module docstring's "seven exemplars" sentence is rewritten as the
  population rule.
- Negative controls kept exactly as-is: synthetic write-scope violation
  must refuse; unknown archetype name must raise ValueError; staff vs
  clerk and executor vs clerk refusals unchanged.
- `registrar_clerk` and `triager` are **not** registered (compile-refused,
  DR-CMD-096/097) and correctly do not join the battery yet — noted in a
  code comment. They join on registration with green set runs, with **no
  further disposition required**.

## Verification (2026-09-27)

- Archetype gate self-test: **9 exemplars, 0 violations** — analyst,
  advisor, author, executor, monitor, coordinator, customizer (set-001) +
  wright, registrar (set-002). Assertion passes.
- Negative controls: synthetic write-scope violation refused (S2);
  unknown archetype raises ValueError. Unchanged behavior.
- set-001 run: **7/7 verified, ok: true**. set-002 run: **2/2 verified
  (wright, registrar), ok: true**.

## Consequences

- The exemplar battery can never silently narrow relative to the built
  population again. New profiles in existing sets join automatically; new
  sets join with one line in `PROFILE_SET_PAIRS`.
- registrar_clerk and triager join the battery on registration (pending
  the tool-channel disposition, DR-CMD-096/097) — no further disposition
  needed per profile.
- No existing profile was modified; no archetype definition changed.

## Premises

DR-CMD-069 (archetype = checked constraint), DR-CMD-090 (customizer
seventh member), DR-CMD-094 (Tetrad; clerk `members=()`), DR-CMD-096/097
(registrar_clerk / triager adopted with compile deviation),
`core/package/factory_archetypes.py`, `core/package/factory_profile_set_001.py`,
`core/package/factory_profile_set_002.py`.

## G6 uncertainties

None material. The "registered" definition is pinned above; the
tool-channel disposition (DR-CMD-096/097) is the only open item touching
future battery membership.

---
Next free identifier: **DR-CMD-099** (DR-CMD-059 still reserved for PVB DoD).
