# DR-CMD-007: Defer machine-readable metadata header to `sc-author`

- **Matter:** "Add YAML front-matter (machine-readable
  metadata) to slash-command definitions now, or defer
  until the `sc-author` harness is specified." Scope: all
  files under `doc/slash-commands/`; format and field set
  unconsidered either way.
- **Disposition mode:** ratify. **Proposer:** Architect
  (enumerated, gated, drafted per `/pb-decide`).
  **Disposer / selector:** Peter (ratified 2026-
  09-20: "rastify: O2").
- **Framing:** the header fields *are* the harness's parse
  contract; specifying them now designs the harness by
  stealth, against the standing directive that `sc-author`
  is not designed until Peter directs it.
- **G5:** binding on the corpus. Checkable: no
  front-matter appears in `doc/slash-commands/*.md`; the
  deferred requirement stands recorded as a G6 item in
  `doc/eval-sc-design.md`; it fires when `sc-author`
  specification begins.

## Options and gate trails

- **O1 — Add now** (specify fields, front-matter the
  definitions). G1–G4 pass. Not selected. Strongest
  case: the shape is nearly forced (SKILL.md's
  `name`/`description` as existence proof); a file format
  is not the harness; the corpus would be parseable from
  day one with no retrofit. Killed on substance: the
  fields are the harness's input contract — fixing them
  now preempts Peter's reserved design freedom; no
  consumer exists today (agent recognition keys on the
  literal token); premature standardization risks later
  migration churn; and a half-migrated corpus is worse
  than none.
- **O2 — Defer until `sc-author`** (status quo, ratified).
  G1–G4 pass. **Selected.** Harness and its contracts are
  specified together, by Peter, when ready; the deferral
  is recorded and checkable (design-doc G6, trigger
  named); one migration, once, with actual consumer needs
  known. Retrofit cost is small (half-dozen files,
  mechanical).
- **O3 — Decide nothing.** Killed at G4: adopting it
  changes no commitment, state, or behavior; the matter
  was ripe and the G6 item's status would stay ambiguous.

## Consequences

- No front-matter is added now; prose headers stand.
- The design-doc G6 item ("Machine-readable header
  (deferred)") stands under a ratified deferral, not a
  provisional note.
- Numbering note: DR-CMD-007 had been named as the
  candidate number for `/eval-sc` family-membership
  ratification (`doc/eval-sc-design.md` G6); that
  candidacy moves to DR-CMD-009.

## Uncertainties (G6)

- Whether the header format will be YAML front-matter
  (the SKILL.md shape, and the likely candidate) or
  another format — genuinely open until the harness is
  specified.
- The exact field set (name, family, version, status are
  guesses, not decisions).
- Whether the header applies to all slash-command
  definitions or only some.
