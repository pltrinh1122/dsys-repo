# DR-CMD-043 — AX1/AX2 architectural invariants (Harness invocation plane) RATIFIED

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~07:49 PDT
- **Selector:** Peter (operator; the premises were disposed by the operator during the K3 design work, 2026-09-21)
- **Disposition mode:** ratify (standing architectural premise)
- **Discriminator:** architecture (not feature-expansion — these are invariants of what dsys is, not additions to it)

## The invariants

- **AX1 — invocation is always through a Harness, never directly to an Automaton.** System-wide invariant: there is no ambient-callable Automaton entry point. Every automaton execution is invoked through the Harness plane — the interaction plane with its strap/unstrap gates, DR-1 coexistence, and authority precedence. The automaton plane exposes transitions to the driver; it does not expose itself to callers.
- **AX2 — the Automaton driver is a strapped Harness instance.** The deterministic walker that advances automaton flows (in production and in testing) is Harness machinery, operating under the strap. Explicit scope exclusion, per the operator's clarification: the *unittest harnesses* (assertion suites — `updater_golden_run.py` and kin) are **not** Harness instances; they remain outside the Harness, asserting on transcripts. AX2 covers the driver, not the suites.

## Provenance

Disposed by the operator as premises of the K3 conditional design (2026-09-21). When K3's extension request was found invalid (DR-CMD-040), AX1/AX2 were explicitly carved out of the invalidity — premises, not parts of the claim — so they could stand alone. This record is that standing-alone. Cited by DR-CMD-041 (scenario simulation): AX2's strapped driver is the matter's executor; AX1 is why the matter needs no new invocation authority.

## Consequences

- One invocation plane: Harness. Anything that wants an automaton to move goes through it.
- The driver inherits Harness discipline: strapped operation, transcript as the run record, replay by re-validation.
- Test-driver divergence is unrepresentable: there is no separate "test double" driver — the driver *is* the Harness instance (AX2), so tested behavior and production behavior share the invocation machinery by construction.
- Future matters invoking automata cite AX1/AX2 instead of re-arguing the plane.

Next disposition identifier: DR-CMD-044.
