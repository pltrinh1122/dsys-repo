# Implementation: `/eval-sc` execution procedure

**Status: DRAFT** — proposed 2026-09-20. Implements
`doc/eval-sc-design.md` (DRAFT). Not evaluated, not
disposed.

## 0. Execution model

`/eval-sc` is executed by the ambient agent in the
invoking chat session. "Execution" means the agent
performs this procedure: parse, resolve, admit, the two
comparisons, and the three-section report. Steps marked
`[mechanical]` are exact operations. Steps marked
`[judgment]` require the agent's reasoning, reported
with reasons, never bare verdicts. Steps marked
`[mechanical + judgment]` combine both regimes: what is
exact is performed exactly; what requires matching or
classification requires reasoning, stated in one line.
A section marked `[mechanical format, judgment
content]` has a mechanical format — its template is
followed exactly — and judgment content — every
finding carries reasons and citations, never bare
verdicts. The agent never
writes to the compared definitions, the repo, or any
record store during execution.

## 1. Parse the invocation `[mechanical]`

Input line: `/eval-sc {matter}`.

1. Empty matter → refuse back with the usage line, no
   report:
   `usage: /eval-sc {/name | <path> | <path>@<commit>} [:: {/name | <path> | <path>@<commit>}]`
2. Form B iff the matter contains a `::` delimiter.
   TARGET = text before it, trimmed. EXEMPLAR-PTR =
   text after it, trimmed. Form A: the exemplar is the
   pair — contract `/eval-sc`
   (`doc/slash-commands/eval-sc.md`) and procedure
   `doc/eval-sc-implementation.md` (this document).
   Form B: EXEMPLAR-PTR overrides the contract exemplar
   only; the procedure exemplar remains this document.
3. Anything that is not a pointer per the grammar
   (design §1) → refuse back with the grammar, no
   report.

## 2. Resolve pointers `[mechanical]`

Resolution root: the local dsys-repo checkout (the
working tree the ambient agent operates in).

- `/name` → `doc/slash-commands/<name>.md`
  (leading slash stripped); read the file.
- `<path>` → read `<path>` relative to the repo root.
- `<path>@<commit>` → `git show <commit>:<path>`
  in the repo.

Record per pointer: the resolved path and the commit
the bytes came from (`git rev-parse HEAD` for working-
tree reads — flagged as working-tree). A failed read →
refuse back (`unresolvable pointer: <pointer>`), no
report. An explicit exemplar pointer that resolves to
something not definition-shaped → refuse back, no
report. Target resolving to either exemplar document
(contract or procedure) → refuse back
(`vacuous self-comparison`), no report.

## 3. Admission — definition-shape verification `[judgment]`

Does the target provide instructions/guidance for
agent execution? Markers: a named command, a trigger,
a procedure or function the agent is to perform.
A spec, a transcript, or a general claim is not
definition-shaped → refuse back with redirect
(`/eval-pb` for playbook matters, `/eval-rb` for
run-book matters, `/eval-meta` for general matters),
no report. The agent verifies the operator's branch
declaration; it does not classify.

## 4. Structural comparison `[mechanical + judgment]`

Map the target's sections onto the contract exemplar's
set —
Kind, Lineage, Trigger, Support, Function/Procedure,
Output contract, Boundaries, Placement. Presence is
mechanical; matching a differently-headed section to
its role is judgment, stated in one line.

Per dimension, one finding with the exemplar section
cited:

- **S1** section anatomy: per exemplar section,
  conforms / deviates: <note> / absent. Extra target
  sections listed, never penalized.
- **S2** trigger/argument grammar: conforms /
  deviates: <note> / absent.
- **S3** output contract: conforms / deviates: <note> /
  absent.
- **S4** boundary form: conforms / deviates: <note> /
  absent.
- **S5** form discipline: format–layer fit
  (human-readable prose for the contract layer;
  TOML/YAML deviate — the uncanny valley, neither
  human-optimal nor machine-native), quoting
  discipline (literals the agent must reproduce or
  match marked as data in code spans; byte-exact
  regions fenced; no agent-actionable meaning carried
  by rendering-only syntax), form–role fit
  (declarative prose for invariants/constraints,
  imperative for procedure, fenced blocks for exact
  outputs): conforms / deviates: <note> / N/A:
  <reason>.

## 5. Semantic comparison `[judgment]`

Meaning against meaning, each dimension with reasons
and citations to the exact target/exemplar lines:

- **M1** terminological coherence: shared terms per
  the glossary and family usage; no private
  redefinition contradicting a normative definition.
- **M2** authority coherence: proposer≠disposer held;
  evaluation≠decision where it evaluates; no
  self-authorized writes; a chat response is not
  authority.
- **M3** guidance non-contradiction: no conflict where
  both guide the same situation. Declared, reasoned
  qualifications are recorded, not penalized.
- **M4** intent–procedure coherence: every promised
  output has procedural basis; no procedure that
  cannot produce the promise.
- **M5** single-concern human verifiability: the target
  addresses a single concern, and a human can verify
  and validate its conformance quickly and easily,
  with minimum attention expenditure. Verification
  requiring extensive execution — especially
  Python-driven mechanical verification/validation —
  deviates: that machinery belongs to an `sc-author`
  harness with a corresponding automaton, not to a
  slash-command.

Findings: conforms / deviates: <cite> / N/A: <reason>.
No short-circuit between the axes; N/A is never
silent.

## 6. Report `[mechanical format, judgment content]`

```text
/eval-sc report
Target: <pointer> -> <resolved path> @ <commit>
Exemplar (contract): <pointer> -> <resolved path> @ <commit>
Exemplar (procedure): doc/eval-sc-implementation.md @ <commit>

1. Synthesis
Verdict: <conforms | deviates | not evaluable as a slash-command definition>
<per-axis verdicts; compressed reasoning: what conforms, what deviates, cited>

2. Structural comparison
S1 - section anatomy:
  - Kind: <conforms | deviates: <note> | absent>
  - Lineage: <...>
  - Trigger: <...>
  - Support: <...>
  - Function/Procedure: <...>
  - Output contract: <...>
  - Boundaries: <...>
  - Placement: <...>
  - (extra sections: <list>)
S2 - trigger/argument grammar: <conforms | deviates: <note> | absent>
S3 - output contract: <conforms | deviates: <note> | absent>
S4 - boundary form: <conforms | deviates: <note> | absent>

3. Semantic comparison
M1 - terminological coherence: <conforms | deviates: <cite> | N/A: <reason>>
M2 - authority coherence: <conforms | deviates: <cite> | N/A: <reason>>
M3 - guidance non-contradiction: <conforms | deviates: <cite> | N/A: <reason>>
M4 - intent-procedure coherence: <conforms | deviates: <cite> | N/A: <reason>>
M5 - single-concern human verifiability: <conforms | deviates: <cite> | N/A: <reason>>
```

Before delivering, verify: three sections present;
every S/M finding carries a verdict; every
"deviates" carries a citation; no bare verdicts;
neither axis short-circuited. A failed check is
repaired in the report, never waived.

## 7. Worked example

### Historical — pre-pair exemplar (2026-09-20)

Test-drive 2026-09-20 (this procedure, executed for
real — §8). Invocation:

```text
/eval-sc /pb-extend
```

Resolution: target → `doc/slash-commands/pb-extend.md`
@ working tree (49e2546, clean); exemplar default →
`doc/slash-commands/pb-decide.md` @ working tree.
Admission: definition-shaped (named command, trigger,
procedure binding, output contract); not
self-comparison.

Report (abridged):

```text
/eval-sc report
Target: /pb-extend -> doc/slash-commands/pb-extend.md @ 49e2546 (working tree)
Exemplar: /pb-decide -> doc/slash-commands/pb-decide.md @ 49e2546 (working tree)

1. Synthesis
Verdict: conforms
Structural axis: conforms (S1–S4). Semantic axis: conforms (M1–M4).
The target reproduces the exemplar's anatomy section for section,
declares its trigger, output contract, and boundaries in the
exemplar's shape, and holds the family's authority posture
(proposer≠disposer; rehearsal-only until procedure adoption,
explicitly marked temporary). One extra section ("Originating
matter") listed, not penalized. No deviations cited.

2. Structural comparison
S1 - section anatomy:
  - Kind: conforms
  - Lineage: conforms ("Renamed 2026-09-20", same role as exemplar's)
  - Trigger: conforms
  - Support: conforms (claims the exemplar's standing explicitly)
  - Function/Procedure: conforms (binds the DRAFT spec; rehearsal noted)
  - Output contract: conforms (Inputs/outputs with verdict vocabulary)
  - Boundaries: conforms (3 numbered, ambient-only)
  - Placement: conforms
  - (extra sections: Originating matter)
S2 - trigger/argument grammar: conforms (invocation + matter character
  declared: "a proposed requirement, feature, or mutation to dsys itself")
S3 - output contract: conforms (staged matter + scope, per-conditional
  findings holds/fails/unevaluated, draft verdict adopt/adopt-with-
  conditions/refuse)
S4 - boundary form: conforms (ambient-only; no record until adoption;
  proposer≠disposer)

3. Semantic comparison
M1 - terminological coherence: conforms (matter, disposition, ambient,
  operator per family usage; no redefinitions)
M2 - authority coherence: conforms ("does not gate, decide, or record";
  "A chat message is not authority")
M3 - guidance non-contradiction: conforms (same trigger form and support
  standing; record-writing guidance coheres — exemplar: on disposition;
  target: on procedure adoption — declared qualification, reasoned)
M4 - intent-procedure coherence: conforms (stage/scope/evaluate-draft/
  recommend deliverable by the drafted procedure; rehearsal status explicit)
```

### Current — pair exemplar (2026-09-20)

Test-drive 2026-09-20 (this procedure, executed for
real — §8). Invocation:

```text
/eval-sc /eval-pb
```

Resolution: target → `doc/slash-commands/eval-pb.md`
@ working tree (0fb3091, clean); exemplar contract →
`doc/slash-commands/eval-sc.md` @ working tree
(0fb3091, modified); exemplar procedure →
`doc/eval-sc-implementation.md` @ working tree
(0fb3091, modified). Admission: definition-shaped
(named command, trigger, validation function); not
self-comparison.

Report:

```text
/eval-sc report
Target: /eval-pb -> doc/slash-commands/eval-pb.md @ 0fb3091 (working tree, clean)
Exemplar (contract): /eval-sc -> doc/slash-commands/eval-sc.md @ 0fb3091 (working tree, modified)
Exemplar (procedure): doc/eval-sc-implementation.md @ 0fb3091 (working tree, modified)

1. Synthesis
Verdict: conforms
Structural axis: conforms (S1–S5). Semantic axis: conforms (M1–M5).
The target reproduces the exemplar's anatomy role for role —
named command, lineage, trigger with required-argument grammar,
agent-recognition support, declared function, output contract,
ambient-only boundaries, repo placement — and holds the family's
authority posture (proposer≠disposer; validation≠decision;
findings advisory; disposition belongs to /pb-decide). Its
redirect table (/eval-rb, /eval-meta) matches the family's
pattern. Extra sections (Family, Check dimensions, Admission)
listed, not penalized.

2. Structural comparison
S1 - section anatomy:
  - Kind: conforms (identical: operator-invoked routine of the ambient agent)
  - Lineage: conforms (Derived/Renamed bullets fill the lineage role)
  - Trigger: conforms (/eval-pb {matter}; braces required; bare refused; invocation is the branch declaration)
  - Support: conforms (agent recognition, chat window; same standing as /pb-decide)
  - Function/Procedure: conforms (semantic validation declared; normative definition cited not restated; check dimensions inline)
  - Output contract: conforms (per-dimension findings cited + overall verdict; reported never repaired)
  - Boundaries: conforms (ambient-only; read-never-rewrite; evaluation≠decision)
  - Placement: conforms (dsys-repo doc/slash-commands/; project not product)
  - (extra sections: Family, Check dimensions, Admission)
S2 - trigger/argument grammar: conforms (operator invocation in chat; matter character declared: "a procedure claiming the playbook form")
S3 - output contract: conforms (per-dimension conforms/deviates/undefined-against + overall verdict, each citing the normative clause)
S4 - boundary form: conforms (ambient-only; no install/CLI/automaton; findings advisory)
S5 - form discipline: conforms (prose contract layer; literals code-spanned; no rendering-only meaning; declarative throughout)

3. Semantic comparison
M1 - terminological coherence: conforms (matter, disposition, ambient, operator, branch declaration per family usage; "binding" mildly unclear, not contradictory)
M2 - authority coherence: conforms (validation≠decision; never ratifies/disposes/writes DecisionRecords; files only on operator direction)
M3 - guidance non-contradiction: conforms (same trigger/support form; redirect table coherent with the family pattern)
M4 - intent-procedure coherence: conforms (six check dimensions + admission rule ground every promised output)
M5 - single-concern human verifiability: conforms (one concern, ~60 lines, six-bullet dimensions; no extensive execution)
```

## 8. Test-drive record

2026-09-20: the worked example in §7 was executed for
real by the ambient agent in-chat: parse (Form A —
`/eval-sc /pb-extend`), pointer resolution (both
definitions read as working-tree bytes at 49e2546),
admission (definition-shaped; not self-comparison),
S1–S4 mapped against the exemplar's file bytes,
M1–M4 assessed with line citations, three-section
report produced. Verdict: conforms on both axes. No
refusal paths were exercised in this run; the
unresolvable-pointer and self-comparison refusals are
specified (§2) but not yet test-driven — recorded as a
gap, not a finding.

2026-09-20: second test-drive, executed for real by the
ambient agent in-chat: parse (Form A —
`/eval-sc /eval-pb`), pointer resolution (target
`doc/slash-commands/eval-pb.md` clean at 0fb3091;
exemplar pair as modified working-tree bytes at
0fb3091), admission (definition-shaped; not
self-comparison), S1–S5 mapped against the pair
exemplar, M1–M5 assessed with line citations,
three-section report produced under the pair-exemplar
header, pre-delivery checklist passed. Verdict:
conforms on both axes. Recorded as the current worked
example in §7; the earlier example is retained as
history (pre-pair exemplar).

## Glossary

Self-containment rule: every acronym and specialized
term used in this document is defined here. Citations
point to the official definition; the inline definition
stands alone.

- **admission** — definition-shape verification (§3):
  the target must provide instructions/guidance for
  agent execution.
- **ambient agent** — the agent executing in the chat
  session; this procedure's executor.
- **attention expenditure** — the human cost of
  verifying and validating a slash-command; M5
  requires it to be minimal (§5).
- **branch declaration** — invocation declares what
  the matter is; the agent verifies instead of
  classifying (§3).
- **comparability threshold** — declared Trigger +
  declared Function/Procedure; below it the synthesis
  verdict is "not evaluable as a slash-command
  definition".
- **DRAFT** — proposed; not evaluated, not disposed.
- **Form A / Form B** — `{pointer}` / `{pointer} ::
  {exemplar-pointer}` (§1).
- **G6** — gate 6 of the decision-making playbook: the
  open-questions slot.
- **judgment / mechanical** — step markers: agent
  reasoning reported with reasons vs exact operations
  (§0).
- **N/A** — not applicable, always with the reason.
- **pointer** — `/name`, repo-relative path, or
  `<path>@<commit>`, resolved against the local
  dsys-repo checkout (§2).
- **refuse back** — explicit refusal with usage, the
  grammar, or a redirect — never silent, never a
  report.
- **resolution root** — the local dsys-repo checkout
  that pointers resolve against (§2).
- **S1–S5 / M1–M5** — the structural (§4) and semantic
  (§5) dimensions.
- **sc-author** — proposed, not built: the harness plus
  its corresponding automaton that would provide
  mechanical verification and validation of
  slash-command authoring; extensive execution,
  especially Python-driven, belongs to it, not to the
  slash-command layer.
- **self-comparison** — target resolving to either
  exemplar document (contract or procedure): vacuous,
  refused back (§2).
- **single concern** — the target does one thing; a
  bundled multi-concern command fails M5 (§5).
- **vacuous** — a comparison that cannot inform the
  operator (§2).
- **working-tree** — pointer resolved to uncommitted
  working-tree bytes; flagged in the report pin (§2).
