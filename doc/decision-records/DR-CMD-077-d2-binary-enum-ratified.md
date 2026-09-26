# DR-CMD-077 — D2 binary enum RATIFIED (reconciliation)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~11:39 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** D2 reconciliation — whether D2's scalar position survives the run-through.

## Dialectic trail

1. **Claim (Peter):** "by definition, D2 has only two values (0.0, 1.0)."
2. **Falsification:** falsified as a *schema* description — D2's position was
   typed `UnitFloat`, and the ratified ensemble (DR-CMD-068) carried four
   distinct values (0.0 executor; 0.1 author; 0.2 advisor, coordinator; 0.7
   analyst, monitor), all validating/compiling/verifying green. But sustained
   at the *operational* level: the only mechanical consumer of the scalar was
   the C6 hemisphere bound (≤ 0.5 / ≥ 0.5); nothing anywhere distinguished
   0.1 from 0.2 or 0.7 from 0.9 (validators, compiler, verifier S1-D2 checked
   consistency not value, warnings, archetype gates).
3. **Root intent recovered (DR-CMD-062):** the D2 scalar was the "honest
   exception" — declared posture, with `conflict_rule` added as the auditable
   bound ("anyone can check whether the agent resolves ties as its position
   claims"). The scalar was the claim; the rule was the audit. A boolean
   records only the tie-break; two agents can share a tie-break and differ in
   posture (author 0.1 vs advisor 0.2, both `intent_wins_ties`) — the tie-break
   does not exhaust fidelity.
4. **Probabilistic-threshold proposal falsified** (scalar as P(world wins)
   against `random()`): voids the auditability DR-CMD-062 was built to
   provide (no single tie resolution checkable; verification becomes
   statistical); unaccountable action at the exact point of accountability
   (principal cannot know which side wins *this* tie; 0.5 becomes the least
   governed point); dimension collapse (entropy smuggled into D2, which is
   D3's jurisdiction); demotes `conflict_rule` from mechanism to hemisphere
   label.
5. **Reconciliation (adopted):** the talking-past-each-other resolved — the
   "two values" claim was about the dimension's *operational content*, the
   "four values" about the *position field* (a posture summary). The posture
   gradations were a redundant encoding of what role prose already says
   ("synthesizes verdicts from staged material" *is* the advisor's
   world-lean). The dimension **is** the binary enum; the scalar retires.

## Decision

**ADOPTED** — D2's schema value becomes the binary enum
**{principal-wins-ties, world-wins-ties}**; the scalar `position` retires.

- "Principal" over "intent": the question is jurisdictional (whose claims
  prevail), not hermeneutic (what was meant).
- The `-ties` qualifier is preserved and load-bearing: the enum governs the
  *conflict* limit case, not ordinary operation. Unqualified "wins" would
  overclaim against the analyst's world-leaning job.
- `conflict_rule` *is* D2 now (renamed values `principal_wins_ties` /
  `world_wins_ties`); there is no second field to cohere with, so incoherent
  posture declarations become unrepresentable by construction — stronger
  than C6's bound.

## Consequences (what changes, per G4)

- **DR-CMD-062 amended:** the "honest exception" (declared-but-bounded
  scalar) is superseded by as-built evidence from the run-through — the
  scalar's gradations proved mechanically idle. This is the run-through
  process working as designed, not a hasty reversal; the historical text is
  preserved with an amendment note appended.
- **C6 retired as superseded:** with no scalar, there is nothing to bound;
  incoherence is unrepresentable by construction.
- **Item 9 advisor/author thin-separation item recorded as MOOT** (not
  decided — dissolved): both profiles become `principal-wins-ties`; there is
  no separation left to accept or deepen.
- **DR-CMD-076 amended:** the factory self-profile's D2 entry (position 0.0,
  `intent_wins_ties`) becomes the enum value `principal-wins-ties`; the D2
  rationale is rewritten (no scalar; no C6 bound to satisfy).
- **Ensemble re-expressed:** analyst, monitor → `world-wins-ties`; advisor,
  author, coordinator, executor, factory → `principal-wins-ties`.
- **Schema consequences:** `D2Fidelity.position` removed; `position_vector()`
  D2 entry becomes the enum string; PLANE_TAGS D2 position row retired;
  verifier S1-D2 (derived-vs-declared consistency) retired; SCHEMA_VERSION
  1.0 → 1.1 (no pre-existing bump rule was found in the repo; the bump and
  its date/cause are recorded in the code comment — as-built, see the
  implementation report).
- Posture content lives in role prose (the human-facing layer), which already
  carried it; the machine-native schema no longer duplicates it.

## Uncertainties (G6)

- None new. The D2 falsification thread is closed.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next disposition identifier: DR-CMD-078.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the
reconciliation only): this record. Implementation of the reconciliation
(schema, verifier, golden runs, profiles, docs) was authorized as a
follow-on build under the ambient's hand and returns for verification.
Commit and push return as follow-on dispositions.
