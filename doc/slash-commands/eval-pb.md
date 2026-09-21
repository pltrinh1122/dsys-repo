# Custom slash-command: `/eval-pb`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Derived** 2026-09-20: decomposed from `/meta-eval`
  (DR-CMD-003). **Renamed** 2026-09-20: `/meta-eval-pb` →
  `/eval-pb` (ratified, DR-CMD-004) — the `meta-eval-`
  prefix was a vestige of the carve-out that misdescribed
  siblings as modes.
- **Family:** `eval-*` — evaluators (DR-CMD-004, DR-CMD-005).
  Suffix marks the target: `-pb` playbooks, `-rb`
  run-books, `-meta` the untyped/open case.
- **Trigger:** the operator invokes `/eval-pb {matter}` in
  chat, supplying a playbook candidate — a procedure claiming
  the playbook form. Braces denote a required argument: a bare
  `/eval-pb` with no matter is refused back. Invocation
  *is* the branch declaration: there is no detection dispatch.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill.
- **Function:** **semantic validation** of the candidate
  against the Architecture's normative definition of a
  playbook — cited, not restated: `doc/glossary.md` "Playbook
  (decision-making)", normative in
  `doc/dyad-architecture-doc.md` §8.2. Worked reference
  (consultative only): `doc/dsys-mutation-playbook-spec.md`
  — a ratified instance, never a comparative axis; validation
  stays definition-anchored per DR-CMD-011 (DR-CMD-020).
- **Procedure (normative):** `doc/eval-pb-implementation.md`.
  This file binds the command to the procedure; it does not
  restate it.

## Check dimensions

- DoD conditionals, not sequences (START/STOP/KEEP or
  equivalent).
- Explicit admission/kill gates.
- Disposition modes each with their own DoD.
- Proposer ≠ disposer.
- Records writable only on disposition.
- Plane discipline: a procedure you follow, not a node you
  command — sequencing belongs to run-books.
- Exercise declared: the candidate cites at least one
  executed run (transcript or record ref) exercising the
  admit and kill paths. Presence checked, never
  quality-judged — quality is disposition's job (G5).
- Trigger declared: states when the playbook applies and
  the non-trigger cases where it does not.
- Output format specified: the record/report shape the
  playbook produces is defined (template or schema
  cited), not left to per-run invention.
- Gates at G1 precision: admission/kill gates stated
  precisely enough to fail — a gate no matter could
  fail is decoration.

## Admission

The agent verifies, not classifies: is the matter actually a
playbook candidate? A binding without a procedure, a
run-book, or a general claim is **not admitted** — refused
back with redirect (`/eval-rb` for run-books,
`/eval-meta` for general matters). A playbook-adjacent
non-playbook (procedure undefined, shape incomplete) is
admitted to the verdict "not evaluable against the
definition" rather than validated.

## Output

A validation report — per-dimension conforms / deviates /
undefined-against findings, each citing the normative clause;
overall: conforms, deviates (cited), or not evaluable against
the definition. Deviations are reported, never repaired:
repair is a mutation matter, not an evaluation.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor.
2. Normative sources are read, never rewritten, by validation.
   The report is delivered in chat; files are written only on
   operator direction.
3. Validation findings are advisory to the operator. A
   "deviates" finding does not deprecate, void, or rewrite the
   candidate — that is disposition, and belongs to `/pb-decide`.
4. Evaluation is not decision: `/eval-pb` never ratifies,
   never disposes, never writes DecisionRecords.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project*, not the dsys *product*.
