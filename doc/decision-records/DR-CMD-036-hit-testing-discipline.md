# DR-CMD-036 — Human-in-the-loop testing discipline for automata

- **Disposition:** ratify. **Selector:** Peter. **Date:** 2026-09-21 (~06:40 PDT).
- **Matter (framed at START):** "The testing discipline for automata should put the human in the *testing* loop — designing attacks and judging outcomes — while execution stays inference-free and deterministic (hard constraint, unchanged). Which design best does that?"

## Options and gate trails (START)

- **O1 — Chat falsification (status quo).** Operator tags claims "falsify"; ambient attacks; survivors specified. G1 ✓ (precisely describable current practice). G2 ✓ (three falsifications executed 2026-09-21 ~06:31–06:37). G3 ✓ (no standing testing-discipline decision). G4 ✓. Survived.
- **O2 — Scenario-driven testing.** Declarative scenarios (actors/turns/expectations, driver-interpreted, replay by transcript re-validation), cli-interface-spec §3.4.1. G1 ✓ G2 ✓ G3 ✓ G4 ✓. Survived.
- **O3 — Harness-mediated testing.** Guided turns aimed at DoD conditions; interaction preferences control challenge posture. G1 ✓ G2 ✓ G3 ✓ G4 ✓. Survived with G6 weight (runnable-Harness status uncertain; sc-author harness fenced behind operator's build direction).
- **O4 — Golden-run + negative validators (the updater pattern).** Every automaton ships a golden run over success/defer/failure/replay paths plus negative cases proving validators bite; transcripts + path hashes as evidence; human reviews transcripts and attacks the run's claims. G1 ✓ G2 ✓ (updater golden run executed 2026-09-21 ~06:25: PASS, replay hash equality `1369c22a51bf`, I-14/I-15 negative cases fire) G3 ✓ G4 ✓. Survived — strongest G2 in the set.
- **O5 — Decide nothing (explicit null).** G1–G4 pass trivially. Survived as the null.

No kills at START; nothing failed G1–G4. Not dialectic (choice among options, not truth-apt); no separator designated.

## Selected

**O4 as the mechanical substrate + O1 as the human layer** (the proposer's draft verdict, ratified as-is). O2 is the named growth path for repeatability; O3 waits on the runnable-Harness question and the operator's build fence.

## Consequences (G4)

- Every automaton ships the O4 shape: golden run (success/defer/failure/replay) + negative validator cases + transcript/hash evidence. The updater build is the exemplar.
- Operator testing proceeds via O1: "falsify"-tagged claims in chat; kills specified, survivors recorded.
- When a defect class recurs across chat probes, it graduates to O2 (a scenario), not to more chat.

## Checkability (G5)

Binding. Verifiable afterward: (a) each automaton has a golden run with negative cases in the tree; (b) falsification exchanges leave specified survivors or recorded kills. If (a) lapses, the decision is not holding.

## Uncertainties (G6)

- Scenario-driver runnable status unverified (specified, "shipped," not executed in this tree).
- Harness runnable status unverified; sc-author harness build remains fenced behind explicit operator direction.
- O4's adversarial-imagination bottleneck: golden runs prove what they are written to prove; O1 is the mitigation, not the cure.
- O1's trail decay: chat + memory degrade under compaction; DecisionRecords are the durable trail.

## Standing

Ratified; holds until falsified or superseded. Next identifier: DR-CMD-037.
