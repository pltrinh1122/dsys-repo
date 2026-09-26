# DR-CMD-062 — Derived scalars ADOPTED (U3 scalar fate resolved)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:21 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *U3 — scalar fate* (open in DR-CMD-060 and DR-CMD-061): whether the D1–D7 0.0–1.0 scalar positions are calibrated as declared inputs, replaced with ordinals, or resolved another way. Resolved in favor of the ambient's proposed third path: **derive the scalars** rather than calibrate-or-ordinal.

## Decision

**ADOPTED** — scalar positions are **computed from each dimension's facet configuration by a documented, deterministic derivation function**. Calibration by construction: two profilers configuring the same facets get the same numbers. This addresses the false-precision objection (raised in the "D1–D7 has a schema" falsification) structurally rather than by convention — the scalar is a summary of the facets, not an independent uncalibrated input.

- **D2 is the honest exception:** intent-vs-world position remains declared (no facet configuration derives it from), but declared-*but-bounded*: the new `D2.conflict_rule` bounds the position (`intent_wins_ties` ⇒ position ≤ 0.5; `world_wins_ties` ⇒ position ≥ 0.5) and makes it auditable — anyone can check whether the agent resolves ties as its position claims.
- **D6 has no scalar** (unchanged — structural: trigger sources plus gates).

Derivation sketches (to be formalized as documented functions in the schema revision): D1 position := share of the agent's action classes executable under standing disposition; D3 := entropy budget (T=0/seeds/pinned ⇒ 0.0; unseeded sampling ⇒ 1.0); D4 := fraction of instrumentation streams enabled (events/intents/verifications); D5 := write-scope breadth in bands (contracted-tools-only ≤ 0.2; bounded named set 0.2–0.6; open-ended > 0.6); D7 := verification-target coverage (enabled targets / 4), capped by failure policy.

## Schema consequences (being implemented by the ambient)

- **New field** `D2.conflict_rule` ∈ {`intent_wins_ties`, `world_wins_ties`, `principal_decides`} — recovers the dropped D2 conflict content named in the falsification.
- **New field** `D6.authorization` — per-source authorization, splitting **activation** (may the trigger fire?) from **authorization** (may the agent act on it?); built as a two-stage trigger pipeline. Recovers the dropped D6 activation-vs-authorization distinction.
- **New coupling C6** (conflict-rule/position consistency): `intent_wins_ties` ⇒ position ≤ 0.5; `world_wins_ties` ⇒ position ≥ 0.5.
- **New coupling C7** (fail-open cap): `on_failure=fail_open` with derived verification position > 0.5 refused — promotes advisory warning W3 to a coupling.
- **C4 extended:** every enabled trigger source requires an explicit gate **and** an explicit authorization (was: gate only).

## Consequences (what changes, per G4)

- The false-precision objection is addressed structurally: scalars can no longer drift between profilers for identical configurations.
- Profiler UX: declare a position, which is **checked against** the derived value (mismatch refused or flagged — to be specified in the schema revision); positions remain human-readable in `position_vector()`.
- U3 is **closed**.
- This disposition does **not** ratify: the machine-native schema as a whole (remains built-but-unratified; the revision implementing this decision is in progress), the C1–C5 couplings (still proposed), or the step-2 substrate fork (pending).

## Uncertainties (G6)

- **U1 — Scope boundary:** the execution-plane scope question, open (carried from DR-CMD-060).
- **U2 — Classification:** the forces/bounds/outcomes classification question, open (carried from DR-CMD-060).
- **U3 — Scalar fate:** **closed** by this record.
- **U4 — Step-2 substrate fork:** dsys-harness-native only vs. substrate-neutral with dsys adapter (carried from DR-CMD-061); Peter's call, unresolved.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- Next disposition identifier: DR-CMD-063.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the scalar-fate fork only): this record. Schema revision (derived-scalar functions, new fields, C6/C7, extended C4) is in progress under the ambient's hand and returns for verification. Commit and push return as follow-on dispositions.

## Amendment note (DR-CMD-077, 2026-09-26) — historical text above preserved

The "honest exception" for D2 (declared-but-bounded scalar position, C6)
is **superseded**. Run-through as-built evidence showed the scalar's
gradations were mechanically idle — the only consumer was C6's hemisphere
bound — and the posture content they encoded already lived in role prose.
D2's schema value is now the binary enum {principal_wins_ties,
world_wins_ties} (DR-CMD-077); the scalar position retired; C6 retired
(incoherent posture declarations are unrepresentable by construction, which
is stronger than the bound). U3 remains closed; this amendment narrows,
not reopens, its resolution.
