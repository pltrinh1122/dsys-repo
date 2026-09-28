# DR-CMD-102 — tool-channel disposition: O1 adopted, tranched

- **Status:** adopted
- **Date:** 2026-09-27 ~18:52 PDT
- **Matter:** "Which option to land to resolve the three clerk profiles'
  compile refusals."
  Separator: Peter (operator default, designated at START; /pb-decide
  recommendation below; Peter's disposition rendered on it).

## Disposition

Peter rendered "proceed as recommended" (~18:52 PDT 2026-09-27) on the
/pb-decide below:

- **O1 adopted with conditions, tranched** — tranche 1 now
  (`tool-register-artifact` per DR-CMD-055 tool discipline); tranche 2
  conditional (triage channels + decision-record registration channel).
- **O2 refused** — re-scope to existing tools.
- **O3 refused** — amend the J1 closed-registry discipline.

## Background: the state this lands on

Three adopted clerk profiles are gate-green but compile-refused at
routing, all for the same deviation class (DR-CMD-096/097/100):

- `registrar_clerk` (DR-CMD-096) — `write_scope=["artifact-registry"]`.
- `triager` (DR-CMD-097) — `write_scope=["quarantine",
  "escalation-queue", "archive"]`.
- `dr_registrar` (DR-CMD-100) — `write_scope=["decision-record-registry"]`.

Each refused because its write-scope channel names no contracted tool
under the compiler's closed registry (J1, which resolves only the 8
production tools). The refusals were recorded, not worked around:
nothing registered, `CLERK.members` still `()`, profiles excluded from
the exemplar battery. `rb-profile-build` B-1..B-3 regression-pin the
refusals byte-equal to the direct-compile oracle (DR-CMD-101).

## The /pb-decide recommendation (condensed)

**O2 — re-scope.** Thesis: cheapest, zero new trusted surface.
Antithesis: no semantically honest channel exists among the 8
production tools — the exact substitution the three deviations refused.
Routing "quarantine" through a generic write tool corrupts D5
semantics: the scope would *say* one thing while the tool *does*
another. KEEP: **refuse**.

**O3 — amend J1.** Thesis: the closed registry is the blocker; loosen
it. Antithesis: J1 is load-bearing — it is what *produced* the honest
refusals. Amendment does not create the missing tools; it manufactures
a compiler-level false backing — profiles compiling against channels
backed by nothing, with the system claiming contracted support. KEEP:
**refuse**.

**O1 — build the contracted tools.** Thesis: resolves the deviation at
its root; DR-CMD-055/057 precedent (8 production tools, 73-case golden
run) works; unblocks all three plus the DR-CMD-099 schema path; B-1..B-3
flip mechanically. Antithesis: (a) cost — 5+ tools plus a
registry-structure design, all new trusted surface; (b) inversion risk —
tools are commissioned from operational need, not to unblock profiles;
letting blocked profiles commission tools inverts the J1 direction;
(c) **G3 conditional** — the DR-registration channel forces the
DR-registry-structure design, which is undisposed (channel before store
is backwards); (d) **G5 speculative** — no triage volume exists (the
triager has never run); building quarantine/escalation/archive channels
now is speculative tooling.

**Synthesis — adopt O1 with conditions, tranched:**

- **Tranche 1 (now): `tool-register-artifact`.** The artifact registry
  exists as a contracted structure (content-addressed, append-only,
  DR-CMD-091) with no contracted write path — adopt-proposal uses
  direct ambient-side `reg.register()` calls. A genuine operational gap
  independent of the profiles, needed by both registrar_clerk and
  DR-CMD-099. Not speculative.
- **Tranche 2 (conditional):** triage channels + decision-record
  registration channel, conditional on (i) the DR-registry-structure
  disposition landing first, and (ii) demonstrated operational need.
  Until then the profiles stay honestly refused — the refusal correctly
  reports "not yet needed."

## Consequences

- Tranche-1 build commissioned: `tool-register-artifact` per DR-CMD-055
  tool discipline (contract, build, golden run) — commissioned by this
  disposition, not yet built.
- On landing, rb-profile-build B-1 is expected to flip mechanically
  from refused-at-COMPILE to staged; B-2/B-3 stay honestly refused
  (their channels remain unbuilt).
- `registrar_clerk` registration becomes a *pending disposition* once
  tranche 1 compiles green — staged by the run-book, never
  self-executed.
- Tranche 2 stays conditional; the triager and dr_registrar remain
  adopted-but-unregistered, gate-green, compile-refused.
- Nothing in this disposition amends J1, substitutes a channel, or
  invents a registry structure — the DR-registry-structure design is
  explicitly still undisposed.

## Uncertainties (G6)

- Triage tool granularity (one bounded tool vs three channel-tools) —
  for the tranche-2 design, when commissioned.
- The DR registry structure design (precondition for the DR
  registration channel) — undisposed.
- Tools go through DR-CMD-055's tool discipline, not rb-profile-build
  (that run-book is for profiles).

## Premises

- DR-CMD-055/057 (production-tools discipline + 8-tool build),
  DR-CMD-091 (customization bridge; artifact registry, append-only),
  DR-CMD-096/097/100 (the three routing refusals, verbatim),
  DR-CMD-098 (population-tracking exemplar set — profiles join the
  battery on registration),
  DR-CMD-099 (schema-artifact criteria; the registrar_clerk scope),
  DR-CMD-101 (rb-profile-build; B-1..B-3 regression pins).

Next free identifier: DR-CMD-103 (DR-CMD-059 still reserved for PVB DoD).
