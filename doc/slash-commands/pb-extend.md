# Custom slash-command: `/pb-extend`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Renamed** 2026-09-20: `/feature-expansion-playbook` →
  `/pb-extend`, per the `/pb-<verb>` family pattern (DR-CMD-001).
  "Extend" is the verb form of "expansion".
- **Family:** `pb-*` — playbook commands (DR-CMD-001).
  Sibling: `/pb-decide` (decision-making playbook).
- **Description:** stage a feature-expansion matter — scope it,
  evaluate the adoption conditionals, draft a verdict. The
  operator disposes.
- **Trigger:** the operator invokes `/pb-extend {matter}` in chat,
  supplying a feature-expansion matter as chat text — a proposed
  requirement, feature, or mutation to dsys itself. Braces denote
  a required argument: a bare `/pb-extend` with no matter is
  refused back. Vague matters are refused back for reframing.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill. The binding is performed by
  the ambient agent's recognition, not by platform machinery.
- **Procedure (normative):** `doc/pb-extend-implementation.md`
  (ratified 2026-09-20, DR-CMD-018; authored 2026-09-20 as DRAFT
  for operator disposition). This file binds the command to the
  procedure; it does not restate it. The procedure runs the
  feature-expansion playbook, `doc/feature-expansion-playbook-spec.md`
  (adopted 2026-09-21, DR-CMD-027; remediated per the DR-CMD-026
  rehearsal). The command runs the playbook governed: it stages the
  matter, evaluates the adoption conditionals, and drafts the
  verdict; STOP kills are enforced and KEEP verdicts feed the shared
  disposition machinery — disposition remains the operator's act.

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
2. The procedure is adopted (DR-CMD-027); the command runs it
   governed: staging, scoping, conditional evaluation, draft
   verdicts, enforced STOP kills, and KEEP verdicts feeding
   disposition. It does not decide — records are written only
   on the operator's disposition.
3. Proposer ≠ disposer holds throughout: the ambient proposes;
   the operator disposes. The command never records a
   requirement on its own authority.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Fulfills the `/pb-extend` anticipation in DR-CMD-001. Part of
the dsys *project* (ambient tooling around dsys), not the dsys
*product* (the runtime).
