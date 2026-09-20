# DR-CLI-001: CLI syntax for complex hierarchical commands

- **Matter:** Which CLI syntax should dsys adopt for complex and
  hierarchical commands? Decided via the decision-making playbook,
  2026-09-20.
- **Disposition mode:** ratify. **Proposer:** Architect.
  **Disposer / selector:** Peter (ratified 2026-09-20).
- **Framing:** "dsys should adopt syntax S for complex and
  hierarchical commands."
- **G5:** binding on the CLI surface (spec + implementation).
  Checkable: the command surface either gains a third token level
  (decision violated) or it does not; instance selection stays
  flag-based.

## Options and gate trails

- **O1 — Space-separated, N levels** (`dsys automaton advance
  --run <id>`, extendable to 3+ token levels). G1–G4 pass.
  Survivor, not selected. Incumbent: implemented in cli.py,
  documented in the CLI spec.
- **O2 — Dotted path** (`dsys automaton.advance --run <id>`).
  G1–G4 pass (G2 weak on invocation precedent; maps cleanly to
  pydantic model paths — tagged). Survivor, not selected.
  Node-addressing misreading hazard bounded: F-C5 already confines
  instances to flags; no option permits `{run-id}.advance`.
- **O3 — Verb-first** (`dsys advance run <id>`, kubectl-style).
  G1–G2 pass. **Killed:** architectural misfit + churn — dsys's
  hierarchy is plane-first (automaton/session/dialog); verb-first
  scatters planes and churns every existing command for zero
  capability gain.
- **O4 — Slash-separated** (`dsys automaton/advance`). G1 pass,
  G2 weak. **Killed:** dominated by O1 — no gain over spaces,
  adds path-confusion (reads as a file path, fights shell path
  completion).
- **O5 — Decide nothing.** Freeze the current shape; instance
  selection via flags (as the executor spec already does with
  `--run` / `--flow-run`). G1–G4 pass. **Selected.**

Alias-synthesis (`automaton advance` ≡ `automaton.advance`)
considered in STOP and rejected: two invocations for one operation
doubles the contract surface (completion, docs, tests) for zero
capability.

## Consequences

- cli-interface-spec.md §3 stays at its current token depth; new
  command families (e.g. `automaton` §3.7) select instances via
  flags, consistent with O5.
- No implementation change required: cli.py already conforms.
- O1-extension re-enters START without prejudice if a genuine
  third token level is ever needed.

## Uncertainties (G6)

- Revisit trigger: a command family that cannot be expressed
  cleanly in (family, operation, flags) form — e.g. session-sync
  or dialog surfaces demanding per-entity subcommands.
- The decision binds the token hierarchy, not flag vocabulary;
  flags may still grow.
- Assumes cli.py's 2-level argparse structure stays adequate;
  deeper subcommand needs reopen the matter.
