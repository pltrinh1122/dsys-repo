# Custom slash-command: `/pb-extend`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Renamed** 2026-09-20: `/feature-expansion-playbook` →
  `/pb-extend`, per the `/pb-<verb>` family pattern (DR-CMD-001).
  "Extend" is the verb form of "expansion".
- **Trigger:** the operator invokes `/pb-extend` in chat,
  supplying a feature-expansion matter — a proposed
  requirement, feature, or mutation to dsys itself.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill. The binding is performed by
  the ambient agent's recognition, not by platform machinery.
- **Procedure:** `doc/feature-expansion-playbook-spec.md`
  (DRAFT, 2026-09-20 — designed per operator direction;
  pending adoption via disposition). Until adopted, the
  command runs the draft in rehearsal: it stages the matter,
  evaluates the adoption conditionals, and drafts the verdict.
  It does not gate, decide, or record — disposition remains
  the operator's act.

## Originating matter (sole evidence)

2026-09-20 13:08 PDT, via `/feature-expansion-playbook`:

> "an 'updater' automaton is required to monitor and manage
> release updates and upgrades to dsys"

Status: proposed only — never evaluated, never disposed. It is
recorded here as the seed matter, not as an accepted
requirement. A chat message is not authority.

## Inputs / outputs

- **In:** a feature-expansion matter, ideally framed as a
  falsifiable requirement claim ("X is required to ...").
  Vague matters are refused back for reframing.
- **Out:** the staged matter with scope assigned
  (package | runtime, decomposed if dual), per-conditional
  adoption findings (holds / fails / unevaluated, evidence
  cited), and a draft verdict (adopt / adopt-with-conditions /
  refuse). The verdict is a recommendation; the operator
  disposes.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor.
2. Until the procedure is adopted, the command runs it in
   rehearsal: staging, scoping, conditional evaluation, and
   draft verdicts only. It does not gate, decide, or record —
   records are written only on adoption of the procedure.
3. Proposer ≠ disposer holds throughout: the ambient proposes;
   the operator disposes. The command never records a
   requirement on its own authority.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Fulfills the `/pb-extend` anticipation in DR-CMD-001. Part of
the dsys *project* (ambient tooling around dsys), not the dsys
*product* (the runtime).
