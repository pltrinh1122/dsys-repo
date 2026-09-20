# Custom slash-command: `/pb-decide`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Renamed** 2026-09-20: `/decision-making-playbook` →
  `/decide-pb` → `/pb-decide` (ratified, DR-CMD-001).
  Playbook commands take the `/pb-<verb>` form; `/pb-extend`
  (feature-expansion playbook) anticipated.
- **Trigger:** the operator invokes `/pb-decide` in chat,
  supplying a matter.
- **Support:** agent recognition, for the chat window. This is
  not a platform hook (event-driven by construction), not a
  client slash-command (client registry is built-in-only as far
  as known), and not a Muse skill (agent-invoked by relevance,
  no user-only mode). The binding is performed by the ambient
  agent's recognition, not by platform machinery.
- **Procedure (normative):** the decision-making playbook,
  `doc/dyad-architecture-doc.md` §8.2 — START / STOP / KEEP,
  gates G1–G6, disposition modes
  ratify | authorize | set_standing | overrule | triage.
  This file binds the command to the procedure; it does not
  restate it.

## Terminology (conceded)

- First called "ambient agent hook" (2026-09-20); conceded —
  the ambient platform's hook system is event-driven (a polling
  script wakes a worker) and this is operator-invoked.
- Then claimed as "SKILL" (2026-09-20); falsified for Muse —
  this platform's skills are agent-invoked by relevance with no
  user-only mode. For Claude Code the skill container fits:
  `.claude/skills/decide-pb/SKILL.md` with
  `disable-model-invocation: true` (verified 2026-09-20).

## Inputs / outputs

- **In:** a matter, framed as a falsifiable claim (vague matters
  refused back for reframing, per START).
- **Out (evaluation):** options with gate trails, kills with
  reasons cited, survivors with draft verdicts. Draft until
  ratified — a chat response is not authority.
- **Out (on disposition):** a DecisionRecord in
  `doc/decision-records/`, written only after the operator's
  explicit disposition; selection among survivors is the
  disposition act.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor.
2. The command reads repo specs as its normative sources and
   writes DecisionRecords; it does not mutate the dsys runtime,
   installed trees, or live instance state.
3. Proposer ≠ disposer: the ambient proposes (enumerates,
   gates, drafts); the operator disposes. The command never
   records a selection on its own authority.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project* (ambient tooling around dsys), not
the dsys *product* (the runtime).
