# DR-CMD-001: Label for the decision-making playbook's slash-command

- **Matter:** What label should the decision-making playbook's
  custom slash-command carry, and what naming pattern should the
  playbook-command family follow? Decided via `/decide-pb`
  (itself relabeled by this decision), 2026-09-20, in two runs:
  (1) `/decide-pb` vs `/decision-pb` — no disposition,
  superseded by reframe; (2) `/decision-pb` vs `/pb-decision`
  vs `/pb-decide` — disposition below.
- **Disposition mode:** ratify. **Proposer:** Architect.
  **Disposer / selector:** Peter (ratified 2026-09-20).
- **Framing:** "The command label should be `/pb-decide`,
  establishing the `/pb-<verb>` family pattern."
- **G5:** binding on the in-repo command definition
  (`doc/slash-commands/pb-decide.md`), the glossary term, and
  in-chat invocation. Checkable: the definition file names
  `/pb-decide`; the glossary cites it.

## Options and gate trails

- **O1 — `/decision-pb`** (noun, distinctive-first). G1–G4
  pass. **Survivor, not selected.** Draft lean in run (2);
  lost to the family-namespace argument.
- **O2 — `/pb-decision`** (namespace-first, noun). G1–G4 pass.
  **Survivor, not selected.**
- **O3 — `/pb-decide`** (namespace-first, verb). G1–G4 pass.
  **Selected.** Verb form matches slash-command convention
  (commands do things); namespace-first clusters the
  playbook-command family in the client's command list.
- **O4 — Decide nothing.** G1, G4 pass. Not selected.
- (`/decide-pb`, the run-(1) incumbent, was not carried into
  run (2) per the operator's reframing; never ratified.)

No kills: no option failed a gate or an exclusion. The
separating argument was prospective family membership, not a
falsifier — tagged, not hidden.

## Consequences

- Definition file renamed to `doc/slash-commands/pb-decide.md`;
  glossary cites `/pb-decide`; in-chat invocation is
  `/pb-decide <matter>` for the window.
- Family pattern ratified: playbook commands take `/pb-<verb>`
  form. `/pb-extend` (feature-expansion playbook: updater
  automaton for dsys release updates/upgrades, matter raised
  2026-09-20 13:08 PDT) is anticipated under this pattern.

## Uncertainties (G6)

- The family is prospective: `/pb-extend` is not yet defined;
  if it never materializes, the namespace-first choice bought
  clustering for one command at 4 chars of prefix overhead.
- Single-operator usage: no coordination evidence either way;
  decided on convention and stated intent.
