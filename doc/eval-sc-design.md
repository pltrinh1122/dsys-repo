# Design: `/eval-sc` — slash-command definition comparison against an exemplar

**Status: DRAFT** — proposed 2026-09-20. Not evaluated, not
disposed. Family membership in `eval-*` is proposed, not
ratified (candidate DR-CMD-006 belongs to `/pb-decide`).

## 1. Argument forms

The matter is a POINTER to a target slash-command
definition — a document providing instructions/guidance
for agent execution:

- Form A: `/eval-sc {pointer}` — target compared against
  the standing exemplar (§2).
- Form B: `/eval-sc {pointer} :: {exemplar-pointer}` —
  target compared against an explicitly named exemplar.
  `::` is the conventional delimiter, shared with
  `/eval-meta`.

Pointer grammar (mechanical, §2 of the implementation
doc):

- `/name` → `doc/slash-commands/<name>.md` in the local
  dsys-repo checkout (leading slash stripped);
- repo-relative path, e.g.
  `doc/slash-commands/pb-extend.md`;
- `<path>@<commit>` → that path at that commit
  (`git show <commit>:<path>`).

Anything else is not a pointer — refused back with the
grammar, no report.

## 2. The exemplar

The standing exemplar is the pair — contract: the
`/eval-sc` definition itself
(`doc/slash-commands/eval-sc.md`); procedure:
`doc/eval-sc-implementation.md` (the procedure this
design specifies). The command is self-referential —
the definition that specifies slash-command
well-formedness, together with the procedure that
executes the comparison, is the standard against which
future slash-command definitions are compared. The
choice is grounded in the command's own anatomy: the
definition carries every S1 section (Kind, Lineage,
Family, Description, Trigger, Support, Exemplar,
Function/Procedure, Output contract, Boundaries,
Placement), so it exemplifies the form it
specifies; the procedure exemplifies the execution the
Function/Procedure section binds. Together the pair
exemplifies S5 form discipline: literals quoted as
data, byte-exact regions fenced, boundaries
declarative, procedure imperative.

The exemplar is the standard, never the subject:
`/eval-sc` never evaluates the exemplar. A target
resolving to either exemplar document is refused back
as vacuous self-comparison (admission gate 3) — so
`/eval-sc /eval-sc` produces no report. A Form B
exemplar overrides the contract exemplar only (it must
itself resolve to a slash-command definition); the
procedure exemplar remains this procedure. Otherwise
the requested comparison cannot be performed — refused
back, no report.

## 3. Admission (pre-report gates)

1. Empty matter → refuse back with the usage line, no
   report.
2. Target pointer unresolvable → refuse back (defect:
   unresolvable pointer), no report.
3. Target resolves to the same document as the exemplar
   → refuse back (defect: vacuous self-comparison — a
   command compared against itself tells the operator
   nothing), no report.
4. Target is not definition-shaped — it does not provide
   instructions/guidance for agent execution (a spec, a
   transcript, a general claim) → refuse back with
   redirect (`/eval-meta` for general matters), no
   report. Invocation is the operator's branch
   declaration; the agent verifies, not classifies —
   the same posture as `/eval-pb`.

Admission failure produces refusal text, never a report.

## 4. Structural comparison (target ↔ exemplar)

Form against form. Largely mechanical (section presence,
declared grammar), with judgment where headings differ
but roles match — reported with reasons.

- **S1 — Section anatomy.** Map the target's sections
  onto the exemplar's section set: Kind, Lineage,
  Family, Description, Trigger, Support, Exemplar,
  Function/Procedure, Output contract, Boundaries,
  Placement. Per section: **conforms**
  (present, same role) / **deviates** (present but
  different role or scope — cited) / **absent**. Extra
  target sections are listed, never penalized.
- **S2 — Trigger/argument grammar.** Does the target
  declare how it is invoked and what it takes —
  required argument marked, bare-invocation refusal,
  argument forms — with the exemplar's explicitness?
  conforms / deviates / absent.
- **S3 — Output contract.** Does the target declare its
  output shape — named report segments or output kinds,
  verdict vocabulary? conforms / deviates / absent.
- **S4 — Boundary form.** A numbered boundary list in
  the exemplar's shape: ambient-only execution, the
  read-only / no-decision posture. conforms / deviates /
  absent.
- **S5 — Form discipline.** The artifact's textual
  forms fit their roles (falsification survivor,
  2026-09-20). Format–layer fit: human-readable prose
  (`.md`) for the contract layer; machine-parseable
  formats (TOML/YAML) are the uncanny valley — neither
  human-optimal nor machine-native — and deviate.
  Quoting discipline: literal strings the agent must
  reproduce or match (command names, delimiters,
  grammar tokens) marked as data (code spans);
  byte-exact regions (usage lines, report templates)
  fenced; no meaning the agent must act on carried by
  rendering-only syntax (`#`, `**` are conveniences —
  the raw text is fully actionable). Form–role fit:
  declarative prose for invariants/constraints
  (Boundaries: what must hold, checkable); imperative
  for procedure (what to do, executable with minimum
  inference); fenced blocks for exact outputs. conforms
  / deviates (cited) / N/A (with the reason).

## 5. Semantic comparison (target ↔ exemplar)

Meaning against meaning. Judgment throughout, always
with reasons and citations.

- **M1 — Terminological coherence.** Shared terms
  (matter, disposition, ambient agent, operator,
  playbook, run-book, …) used per the architecture
  glossary and family usage; no private redefinition
  contradicting a normative definition. conforms /
  deviates (cited) / N/A.
- **M2 — Authority coherence.** The target must not
  arrogate dispositional authority: proposer≠disposer
  held, evaluation≠decision where it evaluates, no
  self-authorized writes, a chat response is not
  authority. conforms / deviates (cited) / N/A.
- **M3 — Guidance non-contradiction.** Where target and
  exemplar guide the same situation (trigger form,
  support/binding, refusal behavior, record-writing),
  the guidance must not conflict. Declared, reasoned
  qualifications (e.g. rehearsal-until-adoption) are
  recorded, not penalized. conforms / deviates (cited)
  / N/A.
- **M4 — Intent–procedure coherence.** The stated
  function must be deliverable by the stated procedure:
  every promised output has procedural basis; no
  procedure that cannot produce the promise. conforms /
  deviates (cited) / N/A.
- **M5 — Single-concern human verifiability.** The
  target addresses a single concern, and a human can
  verify and validate its conformance quickly and
  easily, with minimum attention expenditure. A target
  whose verification requires extensive execution —
  especially Python-driven mechanical
  verification/validation — deviates: that machinery is
  the Architecture's domain, an `sc-author` harness
  with a corresponding automaton, not a slash-command.
  conforms / deviates (cited) / N/A.

There is no short-circuit between the axes: a
structurally deviant definition is still semantically
assessable on what is present. A dimension that cannot
be assessed is marked N/A with the reason, never
silently omitted.

## 6. Report structure

Three sections, always in this order:

**Section 1 — Synthesis.** The verdict and the
compressed reasoning chain: **conforms** (both axes
conform) / **deviates** (deviating dimensions cited) /
**not evaluable as a slash-command definition** (the
target is definition-shaped but declares neither
Trigger nor Function/Procedure — below the
comparability threshold; the structural section shows
the absences, the semantic section is N/A with the
reason). Per-axis verdicts are stated before the
overall.

**Section 2 — Structural comparison.** Per-dimension
findings S1–S5 (S5: N/A with reason rather than
absent): conforms / deviates (cited) / absent,
each with the exemplar section cited.

**Section 3 — Semantic comparison.** Per-dimension
findings M1–M5: conforms / deviates (cited) / N/A
(with the reason).

The report records the target pin and the exemplar pin
(resolved path + commit) so a comparison is replayable.

## 7. Character of the pipeline

Pointer resolution and section mapping are mechanical
and re-checkable. Definition-shape verification, role
matching under differing headings, and all of the
semantic axis require judgment: reported with reasons,
never bare verdicts. The pipeline is *structured*, not
fully mechanical — honest about which parts are which.

## 8. Boundaries (retained)

1. The command executes in the ambient layer only. It
   is never installed, never on the dsys CLI tree,
   never invokable by the automaton executor.
2. The compared definitions are read, never rewritten.
   The report is delivered in chat; files are written
   only on operator direction.
3. Evaluation is not decision: `/eval-sc` never
   ratifies, never disposes, never writes
   DecisionRecords. A "deviates" finding does not
   deprecate, void, or rewrite the target — deviation
   is reported, never repaired. Repair is a mutation
   matter, and belongs to `/pb-decide`.
4. `/eval-sc` does not validate either document against
   the architecture's normative definitions — that is
   `/eval-pb` / `/eval-rb` / `/eval-meta` territory.
5. The slash-command layer is the simple,
   human-verifiable layer. Extensive execution —
   especially Python-driven mechanical verification and
   validation — is the Architecture's domain: an
   `sc-author` harness with a corresponding automaton.
   M5 is where this layer principle bites on the
   target.

## G6 / open

- Pointer grammar for non-file definitions (definitions
  held outside the repo tree).
- Whether the standing exemplar should be pinned to a
  commit or track the working tree.
- `doc/slash-commands/eval-sc.md`: the definition file
  itself — authored 2026-09-20 on operator direction
  ("write doc/slash-commands/eval-sc.md"). The design is now
  self-applied: `/eval-sc /eval-sc` conforms on both axes
  against the exemplar (test-driven 2026-09-20 — against
  the then-standing `/pb-decide` exemplar; under the
  self-referential exemplar this invocation is refused
  back as vacuous self-comparison).
- Family membership ratification (candidate DR-CMD-009)
  via `/pb-decide`.
- Machine-readable header (deferred): a future `sc-author`
  harness with mechanical verification will need a
  parseable metadata header on slash-command definitions
  (name, family, version, status — shape TBD with the
  harness). Until the harness is specified, prose headers
  stand.

## Glossary

Self-containment rule: every acronym and specialized
term used in this document is defined here. Citations
point to the official definition; the inline definition
stands alone — no other document need be opened.

- **absent** — structural finding: the exemplar's
  section (or declared contract) has no counterpart in
  the target (§4).
- **admission** — the pre-report gates (§3). Failure
  produces refusal text, never a report.
- **ambient agent** — the agent executing in the chat
  session; the executor of slash-commands.
- **ambient layer** — the chat-side execution plane,
  outside the installed dsys runtime and the automaton
  executor.
- **attention expenditure** — the human cost of
  verifying and validating a slash-command; M5
  requires it to be minimal (§5).
- **branch declaration** — the `/eval-pb` posture,
  adopted here: invocation declares what the matter
  is; the agent verifies the declaration instead of
  classifying the matter itself (§3).
- **comparability threshold** — the minimum for a
  comparable definition: a declared Trigger and a
  declared Function/Procedure. Below it the synthesis
  verdict is "not evaluable as a slash-command
  definition" (§6).
- **conforms / deviates** — per-dimension findings:
  the target matches the exemplar on the dimension, or
  departs from it (departures always cited).
- **definition-shaped** — the target provides
  instructions/guidance for agent execution, whatever
  its completeness (§3).
- **disposition** — the operator's decision act (select
  among survivors, authorize, ratify, …). Proposer ≠
  disposer: the ambient proposes, the operator
  disposes.
- **DRAFT** — proposed; not evaluated, not disposed.
- **DR-CMD-001..005** — ratified decision records
  naming and scoping the slash-command family
  (see `doc/decision-records/`).
- **eval-*** — the evaluator command family: `-pb`
  playbooks, `-rb` run-books, `-meta` the open/untyped
  case, `-sc` (proposed) slash-command definitions.
- **exemplar** — the standard of comparison, a pair:
  contract `doc/slash-commands/eval-sc.md` and procedure
  `doc/eval-sc-implementation.md`; Form B names another
  contract exemplar only (§2). Never the subject of
  evaluation.
- **form discipline** — the S5 structural dimension:
  format–layer fit, quoting discipline, form–role fit
  (§4).
- **Form A / Form B** — `{pointer}` / `{pointer} ::
  {exemplar-pointer}` (§1).
- **G6** — gate 6 of the decision-making playbook: the
  open-questions slot — deferred items, revisit
  triggers, unconsidered alternatives.
- **N/A** — not applicable; always accompanied by the
  reason, never silent (§5).
- **not evaluable as a slash-command definition** —
  synthesis verdict: admitted as definition-shaped but
  below the comparability threshold (§6).
- **output contract** — the target's declared output
  shape: named segments or output kinds plus verdict
  vocabulary (S3).
- **pointer** — a resolvable reference to a definition:
  `/name`, repo-relative path, or `<path>@<commit>`
  (§1).
- **refuse back** — explicit refusal with usage, the
  grammar, a reframing instruction, or a redirect —
  never silent, never a report.
- **sc-author** — proposed, not built: the harness plus
  its corresponding automaton that would provide
  mechanical verification and validation of
  slash-command authoring. Extensive execution,
  especially Python-driven, belongs to it — not to the
  slash-command layer (§8).
- **section anatomy** — the S1 mapping of target
  sections onto the exemplar's section set (§4).
- **self-comparison** — target resolving to either
  exemplar document (contract or procedure): vacuous,
  refused back (§3).
- **semantic comparison** — report section 3 (§5):
  meaning-against-meaning, dimensions M1–M5.
- **single concern** — the target does one thing; a
  bundled multi-concern command fails M5 (§5).
- **structural comparison** — report section 2 (§4):
  form-against-form, dimensions S1–S5.
- **synthesis** — report section 1 (§6): per-axis
  verdicts plus the overall verdict with the
  compressed reasoning chain.
- **target** — the slash-command definition under
  evaluation, named by the pointer.
- **trigger grammar** — the S2 declaration of how the
  command is invoked and what argument it takes (§4).
- **vacuous** — a comparison that cannot inform: the
  self-comparison refusal (§3).
