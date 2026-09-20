# DR-CMD-004: Rename `/meta-eval-pb` → `/eval-pb`, `/meta-eval-rb` → `/eval-rb`

- **Matter:** "`/meta-eval-pb` is redundant; we can just have
  `/eval-pb` and `/eval-rb`." The `meta-eval-` prefix was a
  vestige of the DR-CMD-003 carve-out: it reads as *a mode
  of* `/meta-eval`, but the commands are siblings, not
  modes — the prefix misdescribes the structure.
- **Disposition mode:** ratify. **Proposer / selector:**
  Peter (proposed and ratified, 2026-09-20: "ratify:
  '/eval-meta', '/eval-pb', '/eval-rb'").
- **Framing:** "The type-targeted validators are named for
  what they do — `eval-` plus the target suffix — with no
  vestigial prefix."
- **G5:** binding on the definition files and in-chat
  invocation. Checkable: `doc/slash-commands/eval-pb.md`
  and `eval-rb.md` exist; no `meta-eval-pb`/`meta-eval-rb`
  references remain outside historical records.

## Options and gate trails

- **O1 — rename to `/eval-pb` + `/eval-rb`.** G1–G4 pass.
  **Selected.** Removes the misdescribing prefix; each
  name fully states its function.
- **O2 — keep `/meta-eval-pb` + `/meta-eval-rb`.**
  Not selected. Weakened (not killed — no gate fails):
  the names function, but the prefix misdescribes
  siblings as modes.
- **O3 — declaration-only (no new commands).** Survivor
  from DR-CMD-003, not revived, not selected.
- **O4 — decide nothing.** Not selected.

## Consequences

- Renamed: `doc/slash-commands/meta-eval-pb.md` →
  `eval-pb.md`, `meta-eval-rb.md` → `eval-rb.md`.
- `eval-*` established as the productive evaluator
  namespace: suffix marks the target (`-pb` playbooks,
  `-rb` run-books).
- Updated: `doc/feature-expansion-playbook-spec.md` §§9,
  10 references; redirect rules in the sibling
  definitions.

## Uncertainties (G6)

- Composes with DR-CMD-005 (the broad command's name);
  disposed together.
