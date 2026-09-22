# DR-CMD-054 — automaton executor spec ADOPTED (with conditions C1–C6)

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~17:00 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *automaton-executor* — the automaton-plane runtime design (`doc/automaton-executor-spec.md`, specified 2026-09-20). Evaluated 2026-09-21 under the draft feature-expansion playbook (falsification submission = that evaluation; no refuted sub-claim survives).

## Verdict trail

- **Lineage:** the flow-drive CLI surface built and committed (`e899b6b`) with `advance --flow-run` honestly refusing (executor step semantics unbuilt) → the installer-mint gap closed (`27f3575`) → the executor spec (specified 2026-09-20, not implemented) evaluated 2026-09-21 → **this disposition**.
- **S5 motivation-fit:** holds — the Z is a checkable world-claim (the executor is the machinery behind `advance`'s honest refusal; the next stage of the automaton line), true on cited evidence. Not misplaced, not fit-failing. Not INVALID.
- **Falsifiers:** run at evaluation. F-E1–F-E5 (pre-registered) survive as declared trust. New probes: the §4 "wrapper-driven (cron)" convention vs the drive contract's D4 K3 tripwire — **no conflict** (D4 governs *initiation*; the spec's wrapper only *drives* via `advance`; driving ≠ initiation). AX2's "deterministic walker that advances automaton flows" is the executor; the wrapper is the scheduler both disown. The §6→§§4–7 duty mapping (D1) verified complete against `doc/automaton-flow-spec.md` §6. No refutation.
- **Conditionals:** A1 (this evaluation; no refuted sub-claim survives), A2 (ontology justified — quiescence, wrapper, step_parked, idempotency key; §11 rejects node-addressing and freeform input with reasons), A3 (plane discipline — zero-inference structural; `--external` recorded as bytes; F-E5 declares trigger authenticity), A4 (spec before build — satisfied), A5 (staged — the §14.5 golden run is the evidence, on the build), P1 (DR-CLI-001 conformance), R1 (deterministic replay — §9 transcript re-validation, no tool reinvocation; existing flow transcripts untouched), R2 (staged — golden run acceptances), R3 (conditions C3 below), R4 (zero inference — structural, no code path), R5 (trust declared — F-E1–F-E5, §3, §8). X1/X2/X3/X4 do not fire.

## Decision

**ADOPTED WITH CONDITIONS C1–C6.** The operator selected "O1: adopt
with conditions (C1–C6), then amend + build." The spec is adopted as
the automaton-plane runtime design; the build follows this record on
the operator's direction in the same disposition ("then amend +
build").

**C1 — malformed tool result.** §5/§8: a tool-result contract
deviation (exception, missing keys, non-JSON `ctx_delta`) reads as
*tool failure* → the declared failure policy applies; the log records
a normalized failure record so replay re-validates. (Without this the
builder invents semantics.)

**C2 — dangling `step_started` in replay.** §9: a trailing
`step_started` with no outcome event is a *valid* transcript (crash
recovery pending, F-E3), not a violation.

**C3 — name the new invariants (R3).** I-28 (step_failed is always
followed by its policy consequence); I-29 (quiescence stickiness — no
event after a terminal/`step_parked` event without intervening input);
I-30 (init idempotency — the content-hash key returns the existing
open run, never duplicates).

**C4 — name the state store.** §10: runs live at
`var/runs/<run_id>.json` under the install home (the O3 surface's
established layout); the OS file lock is on the state file.

**C5 — anchor the driving discipline.** §4 cites the drive contract's
D4 K3 tripwire (ambient-established initiating wrappers are K3
revived) and states the AX2 mapping explicitly: the executor *is*
AX2's deterministic walker; the wrapper is the scheduler, outside the
architecture.

**C6 — glossary.** The spec gains a Glossary (design-doc rule):
automaton-executor, quiescence, wrapper, step_parked, idempotency key,
automaton-exception; the closed trigger enum is listed once:
{timer, external, run_completed, run_aborted}.

## Residuals (recorded, not blocking)

- **Driving-wrapper establishment authority** is ungoverned ("outside
  the architecture"); D4 covers initiating wrappers only. Belongs to a
  future production-operations matter, not this spec.
- Deterministically-lying tools are declared trust (§9 cites F-E1's
  class; the citation is approximate — the substance, declared trust,
  is correct).
- `--external` on a closed run is a silent no-op (closed is terminal).
- Run-level `init` idempotency (closed → new run) vs flow-level
  `init-flow` idempotency (binding, returns the closed run): different
  semantics by design (creation vs binding).

## Build decisions (recorded, not silent)

- **Unknown tool name at `init`:** fail fast (exit 1, config error).
  The spec assumes tools resolve; inventing a policy-time meaning for
  an unresolvable name would bridge undefined semantics.
- The flow driver (§7) lifts `advance --flow-run`'s honest refusal:
  the refusal was conditioned on unbuilt step semantics; the build
  supplies them.

Adopted bytes: `doc/automaton-executor-spec.md` as amended with
C1–C6 (amendment follows this record; build follows the amendment).
Next disposition identifier: DR-CMD-055.
