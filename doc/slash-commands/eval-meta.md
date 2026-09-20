# Custom slash-command: `/eval-meta`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Renamed** 2026-09-20: `/pb-eval` → `/meta-eval` (ratified,
  DR-CMD-002); **renamed** 2026-09-20: `/meta-eval` →
  `/eval-meta` (ratified, DR-CMD-005). Playbook/run-book
  validation split off to `/eval-pb` and `/eval-rb`
  (DR-CMD-003, renamed DR-CMD-004). This command is the
  broad open-text evaluator. No `meta-*` commands remain;
  DR-CMD-002's namespace clause is superseded.
- **Family:** `eval-*` — evaluators (DR-CMD-004, DR-CMD-005).
  Suffix marks the target: `-pb` playbooks, `-rb`
  run-books, `-meta` the untyped/open case (matters as
  falsifiable claims, no type declared — the falsification
  posture, which stands outside the claim, including claims
  *about* validations).
- **Trigger:** the operator invokes `/eval-meta {matter}` in chat.
  Braces denote a required argument: a bare `/eval-meta` with no
  matter is refused back. The matter may be inline text, a repo
  path, or a named artifact.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill.
- **Function:** structured evaluation of the matter as a
  falsifiable claim, in the standing falsification posture:
  adversarial test of the named claim, findings reported as
  confirmed / refuted / decomposed, survivors spec'd not
  decided. Vague matters are refused back for reframing.
  Evaluation is not decision: `/eval-meta` never ratifies,
  never disposes, never writes DecisionRecords. If the matter
  calls for a decision, the operator invokes `/pb-decide`.

## Redirect

This command no longer validates playbooks or run-books. A
playbook-shaped matter is refused back with redirect to
`/eval-pb`; a run-book-shaped matter to `/eval-rb`.
Explicit refusal, not silent wrong-branch evaluation:
invocation is the operator's branch declaration, and the
agent does not second-guess it.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor.
2. The report is delivered in chat; files are written only on
   operator direction.
3. Evaluation findings are advisory to the operator. If the
   matter calls for a decision, that is disposition, and
   belongs to `/pb-decide`.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project*, not the dsys *product*.
