# Custom slash-command: `/eval-rb`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Derived** 2026-09-20: decomposed from `/meta-eval`
  (DR-CMD-003). **Renamed** 2026-09-20: `/meta-eval-rb` →
  `/eval-rb` (ratified, DR-CMD-004) — the `meta-eval-`
  prefix was a vestige of the carve-out that misdescribed
  siblings as modes.
- **Family:** `eval-*` — evaluators (DR-CMD-004, DR-CMD-005).
  Suffix marks the target: `-pb` playbooks, `-rb`
  run-books, `-meta` the untyped/open case.
- **Trigger:** the operator invokes `/eval-rb {matter}` in
  chat, supplying a run-book candidate — a procedure claiming
  the run-book form. Braces denote a required argument: a bare
  `/eval-rb` with no matter is refused back. Invocation
  *is* the branch declaration: there is no detection dispatch.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill.
- **Function:** **semantic validation** of the candidate
  against the Architecture's normative definition of a
  run-book — cited, not restated: `doc/glossary.md`
  "Run-book", normative in the RunBook entity (`schema.py`)
  and `doc/automaton-executor-spec.md`.

## Check dimensions

- Strictly sequential steps.
- Each step deterministic (AST-allowlisted expression,
  compiled once).
- Zero inference inside.
- Steps invoke tools.
- Pinned to a shipped release (`release_version`).
- One run-book per `AutomatonRun`.

## Admission

The agent verifies, not classifies: is the matter actually a
run-book candidate? A playbook, a general claim, or a
non-sequential procedure is **not admitted** — refused back
with redirect (`/eval-pb` for playbooks, `/eval-meta`
for general matters).

## Output

A validation report — per-dimension conforms / deviates /
undefined-against findings, each citing the normative clause;
overall: conforms, deviates (cited), or not evaluable against
the definition. Deviations are reported, never repaired:
repair is a mutation matter, not an evaluation.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor. (It validates run-books; it does
   not execute them — judges aren't contestants, across
   planes too.)
2. Normative sources are read, never rewritten, by validation.
   The report is delivered in chat; files are written only on
   operator direction.
3. Validation findings are advisory to the operator. A
   "deviates" finding does not deprecate, void, or rewrite the
   candidate — that is disposition, and belongs to `/pb-decide`.
4. Evaluation is not decision: `/eval-rb` never ratifies,
   never disposes, never writes DecisionRecords.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project*, not the dsys *product*.
