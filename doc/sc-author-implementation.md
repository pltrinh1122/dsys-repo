# Implementation: `/sc-author` execution procedure

**Status: ratified** — DR-CMD-024 (2026-09-21). Implements the triplet-completion routine declared in `doc/slash-commands/sc-author.md`. Design counterpart: `doc/sc-author-design.md` (ratified, DR-CMD-024).

## 0. Execution model

`/sc-author` is executed by the ambient agent in the invoking chat session. "Execution" means the agent performs this procedure: parse, resolve, admit, inventory, author the contract, author the implementation doc, author the design doc, verify, stage. Steps marked `[mechanical]` are exact operations. Steps marked `[judgment]` require the agent's reasoning, reported with reasons, never bare verdicts. The agent writes only the staged triplet files; it never disposes, never deploys, never ratifies (its own output least of all), never writes DecisionRecords, never pushes. Gaps in the matter's substance are flagged explicitly in the staged artifacts — never silently bridged, never invented.

## 1. Parse the invocation `[mechanical]`

Input line: `/sc-author {matter}`.

1. Empty matter → refuse back with the usage line, no report: `usage: /sc-author {matter}` — where `{matter}` is `/name` (an existing command needing its triplet completed) or a new-command proposal as chat text (proposed name, family, one-line purpose, normative source).
2. Non-empty matter → MATTER = the matter text, trimmed.

## 2. Resolve the matter `[mechanical]`

Two forms:

- **Existing command** — MATTER is a `/name` (starts with `/`, contains no spaces): resolve to `doc/slash-commands/<name>.md` and read it. **Inventory** the triplet: contract exists? implementation doc (`doc/<name>-implementation.md`) exists? design doc (`doc/<name>-design.md`) exists? contract binds the implementation (DR-CMD-006)? implementation names its design counterpart header-adjacent with status explicit (DR-CMD-010)? Record each as present/absent. A failed read → refuse back (`unresolvable command: <matter>`), no staging.
- **New-command proposal** — otherwise MATTER is chat text: it must state the proposed name, the family, a one-line purpose, and the normative source (the procedure or spec the command binds or operationalizes, or a behavior statement precise enough to proceduralize). Missing elements → refuse back for reframing, naming exactly what is missing. Vague matters (no framable command) → refused back for reframing.

## 3. Admission `[judgment]`

The agent verifies, not classifies: does the matter concern a slash command — a named operator-invoked routine of the ambient agent? Markers: a command name, an operator trigger, a purpose the agent would perform.

Below the threshold → refuse back with redirect, no staging: playbook matters → `/pb-decide`; run-book matters → `/eval-rb`; playbook-shaped candidates → `/eval-pb`; general matters → `/eval-meta`.

## 4. Author or remediate the contract `[judgment]`

Map the contract onto the 11-section exemplar set (the standing contract `doc/slash-commands/eval-sc.md`): Kind, Lineage, Family, Description, Trigger, Support, Exemplar, Function/Procedure, Output contract, Boundaries, Placement.

- **Existing contract:** remediate the gaps — add missing Family / Description; harden the Trigger to brace grammar (`/<name> {matter}`, bare refused, matter forms declared); add the normative Procedure binding per DR-CMD-006 if missing. (This is the 2026-09-20 `/pb-decide` / `/pb-extend` remediation pattern.)
- **New contract:** author the full set. Lineage records "new <date>" (plus rename history if the proposal renames). Exemplar: included only for evaluator-family commands; otherwise absent as principled (not an evaluator). Boundaries carry the standing: ambient layer only; never installed/CLI/automaton; the command's own authority posture (evaluation≠decision for evaluators; proposer≠disposer for playbook commands; authoring≠deploying where the command stages artifacts).

## 5. Author the implementation doc `[judgment]`

The command's execution procedure, operationalized from the normative source — never invented. Required sections:

1. Status header (DRAFT for disposition) naming the design counterpart header-adjacent per DR-CMD-010.
2. §0 Execution model: ambient agent, chat session; the step sequence; `[mechanical]`/`[judgment]` marking; write discipline (what the command may and may not write); deviations/gaps reported, never repaired or silently bridged.
3. Parse / resolve / admit sections per the command's own trigger grammar and threshold (§§1–3 of this procedure, adapted).
4. The command-specific body: the procedure's steps operationalized from the normative source — dimensions with verdict rules for evaluators; staging/conditionals/verdict for playbook commands; whatever the source specifies, cited per step.
5. Report template (byte-exact) if the command reports, with a pre-delivery checklist.
6. Worked example, labeled (illustration vs executed run — never describe a simulation as an executed run).
7. Glossary: every operational term defined.

**Substance limit:** where the normative source under-specifies the procedure, author the structural sections and flag the substantive gaps explicitly in the draft (marked `GAP:`), never bridging them with invented semantics. A command whose procedure cannot be framed from the matter is refused back at §2, not staged half-invented.

## 6. Author the design doc `[judgment]`

Rationale, provenance, and open questions — per the standing principle, all reasoning lives here, not in the implementation doc. Required sections: what the command is for (and what it is not); design rationale per major decision; character of the routine (evaluator / playbook command / authoring instrument — and its authority posture); boundaries retained; provenance (authoring notes, durable); G6/open (residual risks, falsifiers where the command pre-registers them, known thin spots); glossary (every acronym and specialized term defined inline — a reader never opens another document to understand it).

## 7. Verify `[mechanical + judgment]`

Before staging, check the triplet's file-state evidence:

1. Contract binds the implementation doc (DR-CMD-006) — mechanical grep.
2. Implementation names its design counterpart header-adjacent, status explicit (DR-CMD-010) — mechanical grep.
3. No stale DRAFT language beyond the intentional status headers — mechanical grep.
4. Every specialized term used in the design appears in its glossary — judgment, reported.
5. Run `/eval-sc` on the authored/remediated contract per its procedure; the result is reported in the staging report, not auto-repaired — deviations in the staged triplet are the operator's disposition input.

## 8. Stage `[mechanical]`

Write the files: new or remediated `doc/slash-commands/<name>.md`; new `doc/<name>-implementation.md`; new `doc/<name>-design.md`. New docs carry `**Status: DRAFT** — authored <date> for operator disposition`. Then deliver the staging report: what was staged (paths), the inventory delta for existing commands, the `/eval-sc` verification result, and gaps flagged (`GAP:` items). Staged is not deployed: state explicitly that the artifacts require operator disposition before the command can be deployed and used. Never mark final, never push, never write a DecisionRecord.

## Glossary

- **matter** — the text supplied to `/sc-author`: a `/name` or a new-command proposal.
- **triplet** — the three artifacts: contract (`doc/slash-commands/<name>.md`), implementation (`doc/<name>-implementation.md`), design (`doc/<name>-design.md`).
- **inventory** — the §2 check of which triplet members exist and whether the schema edges hold.
- **exemplar set** — the 11-section contract anatomy the standing exemplar defines (Kind, Lineage, Family, Description, Trigger, Support, Exemplar, Function/Procedure, Output contract, Boundaries, Placement).
- **normative source** — the procedure or spec the matter command binds or operationalizes; substance comes from here, never invented.
- **staging** — writing the triplet artifacts as DRAFTs for disposition.
- **deployment** — the operator's act adopting the staged artifacts; `/sc-author` never performs it.
- **`GAP:`** — an explicit flag in a staged draft marking under-specified procedure substance the matter did not supply.
