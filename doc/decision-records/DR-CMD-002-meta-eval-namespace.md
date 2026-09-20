# DR-CMD-002: Rename `/pb-eval` to `/meta-eval`; ratify `meta-*` instrument namespace

- **Matter:** The `/pb-eval` command is validator-shaped, not
  playbook-shaped (established: evaluation is not decision;
  Branch 1 runs per-dimension checks like the Architecture's
  validators, I-1…I-17 — judges aren't contestants). `pb-`
  therefore miscategorizes it. Rename target: `/ds-eval` vs
  `/meta-eval`. Decided via `/pb-decide`, 2026-09-20.
- **Disposition mode:** ratify. **Proposer:** Architect.
  **Disposer / selector:** Peter (ratified 2026-09-20,
  "adopt '/meta-eval' renaming").
- **Framing:** "The evaluation command takes `/meta-eval`,
  establishing the `meta-*` instrument namespace for ambient
  instruments operating meta to the playbook family."
- **G5:** binding on the in-repo command definition
  (`doc/slash-commands/meta-eval.md`) and in-chat invocation.
  Checkable: the definition file names `/meta-eval`; its
  Family line defines `meta-*` and cites this record.

## Options and gate trails

- **O1 — `/ds-eval`.** G1–G4 pass. **Killed.** Discrimination
  failure: `ds-` (of dsys) applies equally to every ambient
  command, so it cannot mark the instrument/playbook
  distinction the rename exists to mark; novel abbreviation
  against the architecture's full-`dsys` token (zero standing,
  verified); product/project ambiguity unanswered. Dominated
  by O2 on the discriminating feature.
- **O2 — `/meta-eval`.** G1–G4 pass. **Selected.** Self-defining
  token (no abbreviation, no new undefined term — "meta" is
  the operator's own gloss); encodes the discriminating
  feature — meta-level operation on the `pb-` family; no
  collisions (verified).
- **O3 — keep `/pb-eval`.** **Killed.** Confirmed category
  error: `pb-` is the playbook-command namespace and the
  command is validator-shaped. Keeping it preserves a
  confirmed miscategorization.
- **O4 — Decide nothing.** G1, G4 pass. Not selected.

## Consequences

- Definition file renamed to `doc/slash-commands/meta-eval.md`;
  Family line redefined to the `meta-*` instrument namespace;
  in-chat invocation is `/meta-eval <matter>` for the window.
- Namespace design (two namespaces, principled):
  `pb-*` = playbook commands (procedures you follow;
  DR-CMD-001 stands), `meta-*` = ambient instruments operating
  meta to the playbook family (evaluators/validators).
- `/meta-eval` is the first `meta-*` member.

## Uncertainties (G6)

- `meta-*` starts as a single-member namespace; further
  members are prospective, not evidenced.
- Branch 2 (general matters) isn't meta in the strict sense —
  the name foregrounds the distinguishing function (Branch 1
  playbook/run-book validation), which is the honest naming
  rule applied.
