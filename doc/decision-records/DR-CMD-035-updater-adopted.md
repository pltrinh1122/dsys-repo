# DR-CMD-035 — Updater (release-monitor) expansion ADOPTED with conditions

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~06:11 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the feature-expansion playbook's §7 normal mode for expansion matters; authorize/set_standing/triage excluded)
- **Discriminator:** feature-expansion (shared machinery)
- **Matter:** the narrowed updater claim — "dsys should gain a release-monitor automaton such that it watches dsys releases and, on a new release, drives an upgrade by invoking `install.sh --release` (existing), recording the step-change via the promotion bridge, honoring accretion-repo tree discipline, and executing as a FlowRun via the DR-CMD-030 bridge — the monitor/trigger logic being the new delta, the perform step composed, not duplicated."

## Verdict trail (governed `/pb-extend` evaluation, DR-CMD-034)

- **Gates:** X1 clear (scope decomposed, conjunctive); X2 clear (R1 holds); X3 clear (no implementation presented); X4 clear (delta named — the question DR-CMD-031's refuse-back asked is answered).
- **Conditionals holding:** A1–A5 (both scopes — F1/F2 ambient-run, recorded, survived); P1 (no new CLI; composes `install.sh --release`); P2 (sole network touch confined, hashed into the event log); R1 (replay by re-derivation, hash-equality assertion); R2 (§7 golden-run sequences); R4 (mechanical loop, zero inference); R5 (standing policy + bump scope; operator-only policy changes; promotion + accretion preconditions of `done`).
- **Conditionals unevaluated (build-time):** P3 (docs converge), P4 (installability), R3 (flow-table validators).
- **Draft verdict:** adopt-with-conditions.

## Decision

**ADOPTED** — the operator's "adopt as conditions": adoption under the verdict's three conditions.

### Conditions (must hold before the implementation is accepted)

1. **P3** — the implementation's docs converge with the standing docs (no contradictions with installer-spec, the architecture doc, the promotion bridge, accretion-repo).
2. **P4** — installability demonstrated (the expansion installs cleanly under the installer's rules).
3. **R3** — flow-table validators provided: totality (I-14) and determinism (I-15) checked mechanically, not by inspection.

## Consequences (G4)

1. The updater expansion is adopted. `doc/updater-spec.md` is the adopted basis for the build (status flipped from DRAFT); changes during build must keep the evaluated conditionals holding.
2. Unblocked: framing the bridge expansion matter (DR-CMD-030's source→core bridge — the updater is now its settled first consumer) and authoring the five run-books (`release-check`, `release-verify`, `policy-gate`, `release-drive`, `release-verify-installed`).
3. The build itself is not yet directed — the next action is a new matter (proposed, not presumed).

## Checkability (G5)

Binding. Checkable: this record exists; the spec carries the adoption status; the three conditions are discharged (or not) at build acceptance.

## Premises

- Governed `/pb-extend` evaluation report (DR-CMD-034 run), 2026-09-21.
- `doc/updater-spec.md` (the A4 artifact); DR-CMD-028/029/030 (machinery); DR-CMD-031/032 (X4 refuse-back and narrowing).

## Uncertainties (G6)

- The mermaid diagram still awaits the pydantic→mermaid generator (future governed expansion matter).
- Run-book bodies and the bridge are build work under this adoption, subject to the three conditions.
- Numbering: this disposition takes **DR-CMD-035**. Next identifier: **DR-CMD-036**.
