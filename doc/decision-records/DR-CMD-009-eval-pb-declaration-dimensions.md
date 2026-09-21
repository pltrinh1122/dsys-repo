# DR-CMD-009: `/eval-pb` gains declaration-presence dimensions

- **Matter:** "Should `/eval-pb` be extended beyond form
  validation — and what is necessary for reliable runtime
  execution of a playbook candidate?"
- **Disposition mode:** ratify. **Proposer:** Architect
  (enumerated, gated, drafted per `/pb-decide`).
  **Disposer / selector:** Peter (ratified 2026-
  09-20: "ratify O3").
- **Framing:** `/eval-pb`'s six dimensions validate
  *form* against the Architecture's playbook definition
  (§8.2). Cross-checked against the skill-creator
  SKILL.md authoring discipline
  (`doc/exemplars/skill-creator-repo/SKILL.md`), five
  maturity gaps: exercise evidence, trigger/non-trigger
  declaration, output format specification, integrity
  (lack of surprise), iteration/stop conditions. A
  never-executed playbook passes all six dimensions
  silently. The question is which of these belong in
  the validator vs. at disposition vs. in falsification.
- **G5:** binding on `doc/slash-commands/eval-pb.md`.
  Checkable: its Check dimensions include the four
  declaration-presence checks below; each is
  presence-checked (cited), never quality-judged.

## Options and gate trails

- **O1 — Full maturity extension** (judged dimensions:
  exercise quality, trigger calibration, output-format
  adequacy, integrity, iteration sufficiency). G1–G4
  pass. Not selected. Strongest case: form-valid
  artifacts fail in use — SKILL.md's whole loop exists
  for this; playbooks *dispose*, so the cost of an
  unreliable one is the system's highest. Killed on
  substance: quality judgment is decision-shaped and
  collapses evaluation≠decision; M5 — the validator
  becomes a heavyweight audit, no longer quickly
  verifiable; evidence judgment needs protocols that
  don't exist.
- **O2 — Form-only; maturity at disposition**
  (`/pb-decide` G2/G5, no `/eval-pb` change). G1–G4
  pass. Not selected. Strongest case: cleanest division
  of labor, zero new machinery. Killed on substance:
  the never-run playbook still *passes* `/eval-pb`
  silently — the pass reads as broader endorsement
  than form.
- **O3 — Declaration-presence dimensions**
  (selected). G1–G4 pass. **Selected.** `/eval-pb`
  checks that the candidate *declares* maturity
  evidence — exercise cited, trigger/non-trigger
  stated, output format specified, gates at G1
  precision — presence only, never quality. "Cited,
  not restated" is already the validator's posture;
  the checks stay text-checkable (M5 holds);
  evaluation≠decision intact. Maturity *judgment*
  stays at disposition (G5: checkable → binding, else
  provisional) and in falsification.
- **O4 — Decide nothing.** Killed at G4: ripe,
  explicitly invoked; adopting it changes nothing.

## Consequences

- `doc/slash-commands/eval-pb.md` Check dimensions
  gain four declaration-presence checks: exercise
  declared (run cited exercising admit and kill
  paths), trigger declared (applies / does-not-apply
  cases named), output format specified (record/report
  shape defined, not per-run invention), gates at G1
  precision (stated precisely enough to fail — a gate
  no matter could fail is decoration).
- Reliable runtime execution now decomposes into
  three layers: (1) form — the six dimensions;
  (2) declared evidence — the four new checks, making
  absence visible instead of silent; (3) judgment on
  the evidence — `/pb-decide` disposition and
  falsification.
- Numbering note: DR-CMD-009 had been named as the
  candidate number for `/eval-sc` family-membership
  ratification (`doc/eval-sc-design.md` G6); that
  candidacy moves to DR-CMD-010.

## Uncertainties (G6)

- Presence-vs-quality theater: a candidate can cite a
  vacuous run and pass the letter. Mitigation is
  disposition discipline (G5), not more validator.
- Integrity — the deceptive-but-form-valid candidate —
  cannot be closed by any validator dimension without
  turning it into an auditor. Residual risk owned by
  falsification ("falsify this playbook's gates") and
  operator judgment, explicitly not by `/eval-pb`.
- Whether `/pb-decide` disposers will actually pick up
  maturity judgment at G2/G5, or whether the
  declaration checks arrive too vaguely to act on.
