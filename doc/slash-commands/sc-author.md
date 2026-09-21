# Custom slash-command: `/sc-author`

- **Kind:** custom slash-command (operator-invoked routine of the
  ambient agent).
- **Lineage:** new 2026-09-20 — created per operator direction.
  Codifies the triplet-completion routine exercised 2026-09-20
  for `/eval-rb` and `/pb-extend` (contract + implementation +
  design, DR-CMD-006 / DR-CMD-010 schema).
- **Family:** `sc-*` — slash-command authoring. First member.
- **Description:** complete a slash command's
  design/contract/implementation triplet — stage the artifacts
  as DRAFTs for disposition. The operator deploys.
- **Trigger:** the operator invokes `/sc-author {matter}` in
  chat. `{matter}` is either an existing command as `/name`
  (e.g. `/sc-author /pb-extend`) needing its triplet
  completed, or a new-command proposal as chat text stating:
  proposed name, family, one-line purpose, and the normative
  source (the procedure or spec to bind or operationalize, or
  a behavior statement). Braces denote a required argument:
  a bare `/sc-author` with no matter is refused back. Matters
  too vague to frame are refused back for reframing, naming
  what is missing.
- **Support:** agent recognition, for the chat window. Same
  standing as `/pb-decide`: not a platform hook, not a client
  slash-command, not a Muse skill. The binding is performed by
  the ambient agent's recognition, not by platform machinery.
- **Function:** **triplet completion.** For the matter command:
  author or remediate the contract (the 11-section exemplar
  set), author the implementation doc (the command's execution
  procedure, operationalized from the normative source), and
  author the design doc (rationale, provenance, G6, glossary).
  Structure is completed; substance comes from the matter —
  normative substance is never invented (gaps are flagged
  explicitly, never silently bridged).
- **Procedure (normative):** `doc/sc-author-implementation.md`.
  This file binds the command to the procedure; it does not
  restate it.

## Output

The completed triplet artifacts, staged in the working tree
as DRAFTs ("DRAFT — authored <date> for operator disposition"):
new or remediated `doc/slash-commands/<name>.md`, new
`doc/<name>-implementation.md`, new `doc/<name>-design.md`;
plus a staging report (what was staged, the `/eval-sc`
verification result on the contract, gaps flagged).
Staged is not deployed: the artifacts require operator
disposition before the command can be deployed and used.

## Boundaries

1. The command executes in the ambient layer only. It is never
   installed, never on the dsys CLI tree, never invokable by
   the automaton executor.
2. Authoring is not disposition and not deployment:
   `/sc-author` never ratifies, never disposes, never writes
   DecisionRecords, never pushes. It never ratifies its own
   output — that would be self-disposition, voiding
   proposer≠disposer. Disposition and deployment are the
   operator's acts.
3. Substance comes from the matter. Where the matter
   under-specifies the procedure, the triplet is staged with
   the gaps explicitly flagged — mechanisms are never
   invented, semantics never silently bridged.
4. The command writes only the staged triplet files. It does
   not mutate the matter command's normative sources, the
   dsys runtime, installed trees, or live instance state.

## Placement

Versioned in dsys-repo under `doc/slash-commands/`, outside the
installed runtime tree (`install.sh` does not converge `doc/`).
Part of the dsys *project* (ambient tooling around dsys), not
the dsys *product* (the runtime).
