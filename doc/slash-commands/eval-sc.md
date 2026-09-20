# Custom slash-command: `/eval-sc`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Authored** 2026-09-20 on operator direction. Design:
  `doc/eval-sc-design.md` (DRAFT); execution procedure:
  `doc/eval-sc-implementation.md` (DRAFT). Family membership
  in `eval-*` proposed, not ratified (candidate DR-CMD-006
  belongs to `/pb-decide`).
- **Family:** `eval-*` — evaluators. Suffix marks the target:
  `-sc` slash-command definitions.
- **Description:** Compare a target slash-command definition
  against the exemplar definition — structurally (section
  anatomy, trigger grammar, output contract, boundary form)
  and semantically (terminology, authority, guidance,
  intent–procedure coherence). Use when the operator invokes
  `/eval-sc` with a pointer to a target definition.
- **Trigger:** the operator invokes `/eval-sc {pointer}` in
  chat, where `{pointer}` is `/name`, a repo-relative path,
  or `<path>@<commit>`. Form B — `/eval-sc {pointer} ::
  {exemplar}` — names an explicit exemplar. Braces denote
  required arguments: a bare `/eval-sc` is refused back.
  Invocation is the operator's branch declaration — the
  matter is a slash-command definition; the agent verifies,
  not classifies.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill. The binding is performed
  by the ambient agent's recognition, not by platform
  machinery.
- **Exemplar:** the `/pb-decide` definition
  (`doc/slash-commands/pb-decide.md`) unless Form B names
  another. The exemplar is the standard, never the subject.
- **Procedure (normative):**
  `doc/eval-sc-implementation.md` — parse, resolve pointers,
  admit (definition-shape verification), structural
  comparison S1–S4, semantic comparison M1–M5, and the
  three-section report (Synthesis, Structural comparison,
  Semantic comparison). This file binds the command to the
  procedure; it does not restate it.
- **Output:** the three-section report, delivered in chat.
  Verdicts: conforms / deviates (cited) / not evaluable as a
  slash-command definition. Deviations are reported, never
  repaired — repair is a mutation matter for `/pb-decide`.
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

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project* (ambient tooling around dsys), not
the dsys *product* (the runtime).
