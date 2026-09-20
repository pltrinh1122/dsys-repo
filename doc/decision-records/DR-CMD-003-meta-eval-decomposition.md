# DR-CMD-003: Decompose `/meta-eval` into `/meta-eval-pb` and `/meta-eval-rb`

- **Matter:** Branch 1 of `/meta-eval` (playbook/run-book
  validation) carried the softest clause in the definition —
  "playbook-shaped" detection as guidance, not a decision
  procedure (recorded in the `/meta-eval` self-evaluation).
  Falsification of the single-split proposal
  (`/meta-eval-pb` alone) decomposed it: run-books were left
  homeless, and the "no conditional loops" claim was refuted
  (the dispatch relocates inward, it isn't removed). Widened
  form adopted: two dedicated commands.
- **Disposition mode:** ratify. **Proposer:** Architect
  (widened form after falsification). **Disposer / selector:**
  Peter (directed "decompose into two: '/meta-eval-pb' and
  '/meta-eval-rb'", 2026-09-20).
- **Framing:** "Playbook validation and run-book validation
  become dedicated `meta-*` commands; `/meta-eval` retains
  general claim evaluation. Invocation is the operator's
  branch declaration; the agent verifies (admission), not
  classifies."
- **G5:** binding on the three definition files and in-chat
  invocation. Checkable: `doc/slash-commands/meta-eval-pb.md`
  and `meta-eval-rb.md` exist with their check dimensions;
  `meta-eval.md` carries the redirect rule.

## Options and gate trails

- **O1 — decompose into `/meta-eval-pb` + `/meta-eval-rb`.**
  G1–G4 pass. **Selected.** Resolves the run-book
  homelessness of the single-split proposal; operator
  declares by invocation; misinvocation refuses with
  redirect (explicit, not silent wrong-branch evaluation).
- **O2 — keep unified `/meta-eval`.** Not selected. The
  detection clause was recorded as the softest clause and
  the operator chose remediation over tolerance.
- **O3 — declaration-only Branch 1 (no new commands).**
  G1–G4 pass. **Survivor, not selected.** Same clarity at
  lower cost; the operator preferred explicit commands.

## Consequences

- New: `doc/slash-commands/meta-eval-pb.md` (playbook
  validation; dimensions: DoD conditionals, gates,
  disposition modes, proposer≠disposer, records on
  disposition, plane discipline), `doc/slash-commands/
  meta-eval-rb.md` (run-book validation; dimensions:
  sequential steps, deterministic AST-allowlisted steps,
  zero inference, tool invocation, release pinning, one
  run-book per AutomatonRun).
- Rewritten: `doc/slash-commands/meta-eval.md` — Branch 2
  only, plus hard redirect (playbook-shaped →
  `/meta-eval-pb`, run-book-shaped → `/meta-eval-rb`).
- Updated: `doc/feature-expansion-playbook-spec.md` §§A1,
  9, 10 references.
- `meta-*` now has three members.

## Uncertainties (G6)

- Rump identity: `/meta-eval` (general claim evaluation
  only) retains the `meta-` name on the weak "family
  instrument" reading — Branch 1 was the strong
  justification (DR-CMD-002). If it ever misleads, rename
  to `/eval`.
- Classification burden moved to the operator at
  invocation; misinvocation now refuses (with redirect)
  where the unified command degraded gracefully.
- The playbook-vs-run-book conditional survives inside the
  admission checks; decomposition relocated the dispatch,
  it didn't remove conditionals (falsification finding,
  kept honest).
