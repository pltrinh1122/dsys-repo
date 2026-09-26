# DR-CMD-060 — D1–D7 ADOPTED as reference architecture

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~07:20 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *D1–D7 as reference architecture* — the step-0 foundation fork of the ratified D1–D7 agent factory plan (DR-CMD-061), resolved in favor of grounding the factory's authority in the ratified reference architecture (not factory-as-exploration).

## Decision

**ADOPTED** — "Seven Dimensions of Agent Behavior" (D1–D7) is adopted as a **reference architecture**: architecture *of the design space*. The qualifier "reference" is load-bearing — D1–D7 delimits and directs at its level (the facet structure tells designers what to decide: trigger sources and their gates, verification targets at trust boundaries, separated read/write scope) but does not determine construction the way a system architecture does. No one builds *from* D1–D7 alone.

- **dsys as instantiation:** dsys is recognized as one instantiation of the reference architecture — and as the standpoint from which the dimensions were derived (the home poles are dsys's positions). The reference architecture locates system architectures such as dsys; it does not replace them.
- **Sequence note:** DR-CMD-061 (factory plan ratification, 2026-09-26) explicitly stated its ratification did **not** cover the reference architecture itself. This record closes that gap.

## Preserved as OPEN (not silently settled by adoption)

Per the 2026-09-26 adopt-with-amendments evaluation, adoption does **not** settle:

- **The execution-plane scope boundary question** — what "execution" covers, stated without evading "world completeness."
- **The forces/bounds/outcomes classification question** — whether resource use, latency, availability/liveness, correctness, safety/security, ambient inference, and belief representation are dimensions, forces, feasibility bounds, outcomes, or internal parameters.

These remain open matters for future disposition.

## Consequences (what changes, per G4)

- Factory plan step 0 is resolved: the factory's authority derives from the ratified reference architecture; the exploration fork is closed.
- The next concrete work is factory plan step 1 (construction-semantics table), now proceeding under the ratified plan with a ratified foundation.
- This adoption does **not** ratify: the machine-native schema (`core/package/agent_behavior.py` remains built-but-unratified), the C1–C5 couplings (still proposed, not law), the scalar representation (provisional until step 1 disposes its fate), or either remaining factory-plan fork (step-2 substrate).

## Uncertainties (G6)

- **U1 — Scope boundary:** the execution-plane scope question, open per above.
- **U2 — Classification:** the forces/bounds/outcomes classification question, open per above.
- **U3 — Scalar fate:** factory plan step 1 may calibrate the 0.0–1.0 scalars or replace them with ordinals; the schema's scalar representation is provisional until then. Now before Peter as step-1 judgment work.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not consumed**.
- Next disposition identifier: DR-CMD-062.

## State

**The tree is UNCOMMITTED at disposition** (Peter adopted the reference architecture only): this record. No spec, code, or matter-doc changes authorized by this disposition. Commit and push return as follow-on dispositions.
