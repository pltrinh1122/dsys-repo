# DR-CMD-058 — Authoring language RATIFIED (O3)

- **Status:** ratified (disposition)
- **Date:** 2026-09-24 ~05:22 PDT (selection)
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *authoring language* — selection: **O3** — the authoring language for processes deployed into dsys instances (run-books, flows) shall be selected from {pydantic, BPMN} against conditions C0–C8 — because the criteria decide the matter (two survivors, one recommended), DR-CMD-028's updater-scoped pydantic-as-source decision needs a general-scope successor, and BPMN's status (on the table as challenger O2) needs settling rather than resurfacing. C0 = scope check: authoring the processes *deployed into* instances, not deployment configuration itself (for deployment config proper, BPMN is a category error). C1 = semantic closure (no surplus); C2 = deterministic compilation; C3 = authoring-principal fit; C4 = mechanical verifiability; C5 = diffability/accretion; C6 = expressiveness fit; C7 = hermeticity/dependency weight; C8 = interchange requirement.

## Decision

**RATIFIED (O3)** — pydantic is the authoring language for dsys-deployed processes, confirmed at general scope (extending DR-CMD-028, not superseding it); BPMN-as-source is refused as standing policy; BPMN is permitted only as derived rendering/export, never as source — with any renderer/exporter deferred until an interchange requirement (C8) materializes.

## Options with gate trails (G1 well-formed · G2 legitimate source · G3 non-redundant · G4 actionable)

- **O1 — pydantic as the authoring language: SURVIVED.** G1 ✓ (precisely stated, shipped precedent). G2 ✓ (bridge-spec B-1/B-2/B-3; bridge golden run: byte-for-byte compile equality, recompile hash equality, heartbeat→replay hash identity; updater built and verified). G3 ✓ — not a duplicate of DR-CMD-028: that decision scoped pydantic-as-source to the updater FSM machinery; this matter generalizes to all dsys-deployed processes (precedent noted, scope extended). G4 ✓ (sets the authoring standard). Criteria: C1 holds by construction (the schema *is* the mapping — zero surplus); C2 proven; C3 fits the authoring principal (operator) with no translation layer; C4 demonstrated (Python validators, golden runs, negative cases); C5 clean semantic diffs; C6 exact expressiveness fit (strictly-sequential run-books, FSM flows); C7 no new dependencies, offline-safe. C8 the bounded gap: no OMG-standard interchange — not currently a requirement.
- **O2 — BPMN as the authoring language: KILLED.** G1 ✗ — under-specified as stated: no pinned BPMN subset, no pinned execution semantics; unevaluable, and pinning them *is* the C1 refusal surface (the bulk of the work). Killed-by-falsification on **C1** (semantic surplus: ~100 BPMN constructs against sequential run-books/FSMs; most of the language unmappable — a large permanent refusal surface). Falsifying precedent cited: mermaid-as-source died on the same ground (DR-CMD-028/029/030). Supporting failures: C3 (serves analysts, not the operator principal; a translation layer = unverified machinery); C4 (XML toolchain + BPMN-semantics checker = new machinery); C5 (layout/semantics interleave → noisy diffs); C6 (concurrency/choreography surplus the machine cannot execute); C7 (new parser dependency; graphical modelers not CLI/offline-friendly). C8 the sole criterion O2 wins — insufficient against seven failures.
- **O3 — pydantic as source; BPMN as derived rendering/export only: SURVIVED (selected).** G1 ✓ (precisely stated: BPMN = derived rendering/export, never authored). G2 ✓ (precedent: mermaid-as-source died, mermaid-as-renderer survived — DR-CMD-028/029/030). G3 ✓ · G4 ✓ (commits the source/rendering distinction as standing policy). Inherits O1's C1–C7 passes; captures C8's readability/interchange value without making BPMN the source. Selected over O1 because the matter put BPMN on the table — O3 settles its status rather than leaving the question to resurface.
- **O4 — decide nothing: KILLED.** G4 ✗ — the supplied criteria decide the matter (two survivors, one recommended); deferral has no ground and would be silent sustainment without reason. Killed with reason cited, per STOP.

## Consequences (what changes, per G4)

- pydantic is confirmed as the authoring language for dsys-deployed processes at general scope — DR-CMD-028's updater-scoped decision extended, not superseded.
- BPMN-as-source is refused as standing policy: any future proposal to author dsys-deployed processes in BPMN must first re-open this matter (see U2).
- BPMN-as-rendering/export is permitted but nothing is built: no renderer/exporter is authorized by this disposition; that work is deferred until a C8 interchange requirement materializes (see U1).

## Uncertainties (G6)

- **U1** — whether external BPM interchange ever becomes a requirement: unknown; O3's export half deferred on it.
- **U2** — O2's kill is provisional against a future mandate (partner/customer requiring BPMN-native authoring); such a requirement re-opens the matter. Standing rule: holds until falsified or superseded.
- **U3** — C3 assumes operator-authors; analyst-authoring would re-weigh C3.

## State

**The tree is UNCOMMITTED at disposition** (Peter ratified the selection only): this record. No code, spec, or matter-doc changes authorized by this disposition. Commit and push return as follow-on dispositions. Next disposition identifier: DR-CMD-059.
