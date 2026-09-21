# Custom slash-command: `/eval-sc`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Lineage:** authored 2026-09-20 on operator direction.
- **Family:** `eval-*` — evaluators; membership proposed,
  not ratified (candidate DR-CMD-009 belongs to
  `/pb-decide`).
- **Description:** Compare a target slash-command definition
  against the exemplar pair — structurally and semantically.
- **Trigger:** the operator invokes `/eval-sc {pointer}` in
  chat, where `{pointer}` is `/name`, a repo-relative path,
  or `<path>@<commit>`. Form B — `/eval-sc {pointer} ::
  {exemplar-pointer}` (see Exemplar). Braces denote
  required arguments: a bare `/eval-sc` is refused back.
  Example: `/eval-sc /pb-extend`. Invocation is the
  operator's branch declaration — the matter is a
  slash-command definition; the agent verifies,
  not classifies.
- **Support:** agent recognition, for the chat window — same
  standing as `/pb-decide`.
- **Exemplar:** the pair — contract: this definition
  (`doc/slash-commands/eval-sc.md`); procedure:
  `doc/eval-sc-implementation.md` — unless Form B names
  another contract exemplar. The exemplar is the
  standard, never the subject: a target resolving to
  either exemplar document is refused back as vacuous
  self-comparison.
- **Function/Procedure (normative):**
  `doc/eval-sc-implementation.md`. This file binds the
  command to the procedure; it does not restate it.
- **Output contract:** the three-section report, delivered
  in chat. Verdicts: conforms / deviates (cited) / not
  evaluable as a slash-command definition. Deviations are
  reported, never repaired — repair is a mutation matter
  for `/pb-decide`.
- **Boundaries:**
  1. The command executes in the ambient layer only. It is
     never installed, never on the dsys CLI tree, never
     invokable by the automaton executor.
  2. The compared definitions are read, never rewritten.
     Files are written only on operator direction.
  3. Evaluation is not decision: `/eval-sc` never ratifies,
     never disposes, never writes DecisionRecords. A
     "deviates" finding does not deprecate, void, or rewrite
     the target.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside
the installed runtime tree (`install.sh` does not converge
`doc/`) — project (ambient tooling), not product (runtime).
