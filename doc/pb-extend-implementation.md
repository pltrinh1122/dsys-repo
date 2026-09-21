# Implementation: `/pb-extend` execution procedure

**Status:** ratified 2026-09-20 (DR-CMD-018; O3 — contract amended, then ratified). Implements the staging-and-evaluation routine declared in `doc/slash-commands/pb-extend.md`. The normative playbook it runs is `doc/feature-expansion-playbook-spec.md` (DRAFT — pending adoption via disposition; until adopted the command runs it in rehearsal, §0). Design counterpart: `doc/pb-extend-design.md` (ratified with this doc, DR-CMD-018; provenance and reasoning live there, per DR-CMD-010).

## 0. Execution model

`/pb-extend` is executed by the ambient agent in the invoking chat session. "Execution" means the agent performs this procedure: parse, resolve, admit, stage (START), scope, per-conditional evaluation (KEEP), draft verdict, report. Steps marked `[mechanical]` are exact operations. Steps marked `[judgment]` require the agent's reasoning, reported with reasons and cited evidence, never bare verdicts. Steps marked `[mechanical format, judgment content]` have a mechanical format — the template is followed exactly — and judgment content — every finding carries reasons and citations, never bare verdicts. The agent never writes to the candidate, the repo, or any record store during execution. Findings are reported, never repaired: rework is the proposer's act (re-enter START reframed).

**Rehearsal vs governed.** The bound playbook is DRAFT and unadopted, so the command runs in **rehearsal** mode: it stages the matter, assigns scope, evaluates the adoption conditionals, and drafts the verdict — as an exercise. It does not gate (STOP kills are reported as would-kill findings, not enforced), does not decide, and writes no records. When the playbook is adopted via disposition, the command runs **governed**: STOP kills enforced, the KEEP verdict feeds the shared disposition machinery. The report's mode line (§8) always states which regime ran; the regime is a fact about the playbook's adoption state, never the agent's choice.

## 1. Parse the invocation `[mechanical]`

Input line: `/pb-extend {matter}`.

1. Empty matter → refuse back with the usage line, no report: `usage: /pb-extend {matter}` — where `{matter}` is a feature-expansion matter as chat text: a proposed requirement, feature, or mutation to dsys itself.
2. Non-empty matter → MATTER = the matter text, trimmed. The contract declares no pointer grammar (`/name`, paths); the matter is chat text, recorded as `inline`.

## 2. Resolve the matter `[mechanical]`

Record the source as `inline` with the received text. No file resolution is performed — the matter is the operator's words, not a document. (If the operator pastes a path or reference inside the text, it is treated as prior-art citation at START S4, not as a pointer to resolve.)

## 3. Admission `[judgment]`

The agent verifies, not classifies: is the matter actually a feature-expansion matter?

Comparability threshold: the matter must propose an **addition to what dsys is** — a new capability, mechanism, or surface dsys should gain. Markers: "dsys should gain X", "X is required to …", a named new thing with a stated purpose.

Below the threshold → refuse back with redirect, no report:
- a mutation of an existing rung (not an addition) → the dsys-mutation playbook (no slash-command binding; the operator routes directly);
- a general decision → `/pb-decide`;
- a playbook-shaped candidate → `/eval-pb`;
- a general claim or falsification target → `/eval-meta`.

A vague matter (no falsifiable claim statable) → refused back for reframing per START S1; this is input shaping, not a verdict.

## 4. Staging — START `[judgment]`

All four entry conditionals must hold before evaluation opens (spec §§2–3):

- **S1 — falsifiable claim.** Frame the expansion as "dsys should gain X such that Y". Vague matters refused back for reframing.
- **S2 — scope assigned.** Apply the discriminating test (§5): does the change alter what the machine guarantees? Yes → runtime; no → package. Dual-scope matters decomposed into two scoped matters at START.
- **S3 — proposer named.** Proposer ≠ disposer; the ambient never proposes on its own authority for its own expansions.
- **S4 — prior art cited.** The existing spec section (or "none" declared), the seed matter if relevant, related falsifications.

**DoD (START complete):** claim framed, scope assigned, proposer named, prior art cited. Nothing evaluated yet. In rehearsal, staging shortfalls are reported as findings, not enforced as gates.

## 5. Scope assignment `[judgment]`

The discriminating test, stated as the agent applies it:

> Does the change alter what the machine guarantees — deterministic replay, zero inference in execution, hermeticity, checkability? If yes, runtime scope (the deterministic core: schema entities, validators, the automaton executor, the golden run, session sync, disclosure views, trust boundaries, the machine-native package). If no, package scope (dsys-repo: CLI surface, `install.sh`, roles, scenarios, docs/specs, packaging, release binding).

**Decomposition rule:** a matter touching both scopes is decomposed at START into two scoped matters (one package, one runtime); they proceed independently through §§6–7, and adoption is **conjunctive** — neither adopted until both are. **Scope creep** (a package matter growing runtime tendrils mid-matter, or vice versa) → STOP: in governed mode the matter is killed or decomposed; in rehearsal it is reported as a would-kill finding.

## 6. Per-conditional evaluation — KEEP `[judgment]`

For each applicable adoption conditional, produce one finding: **holds** (evidence cited) / **fails** (evidence cited) / **unevaluated** (no evidence; stated, never silent). Unevaluated is not held. Every finding carries one line of reasoning and at least one cited evidence source. Never bare verdicts.

**Shared (both scopes):**
1. **A1 — falsification survived.** The claim was submitted to falsification (`falsify`, or `/eval-meta`); no refuted sub-claim survives. A declared operator waiver (reason recorded) satisfies A1 as waived-with-reason, not as held.
2. **A2 — ontology justified.** Every new term, entity, or command justified against the existing ontology (glossary); no synonym proliferation; new namespace tokens defined before use.
3. **A3 — plane discipline.** No inference smuggled into the automaton plane; no automaton reach claimed for ambient commands; sequencing belongs to run-books.
4. **A4 — spec before build.** The expansion is specified (spec section or file) before implementation. Implementation presented without a spec → refused at any point it appears (X3).
5. **A5 — evidence, not assertion.** Acceptance criteria stated as checkable sequences: validators, golden runs, CLI transcripts, pass/fail.

**Package-scope additions:**
6. **P1 — interface consistency.** CLI changes conform to DR-CLI-001 (`family, operation, flags`); no third token level; composes with the existing tree.
7. **P2 — hermeticity preserved.** Per-command hermeticity stated and updated; no new network touch without declaration; offline install holds.
8. **P3 — docs converge.** The governing spec updated in the same change; docs do not lag the code.
9. **P4 — installability.** `install.sh` converges the new surface; `doctor` covers it; the operator's idempotency sequences hold.

**Runtime-scope additions:**
6. **R1 — deterministic replay preserved.** Existing transcripts still validate; new behavior replayable by construction (transcript re-validation, never behavioral re-execution). A runtime matter whose replay story (R1) fails at KEEP → refused in governed mode (X2); would-refuse in rehearsal. (X2 fires at KEEP, not START — spec §5, remediated 2026-09-21 per DR-CMD-026.)
7. **R2 — golden run extended.** New golden-run cases cover the expansion, including refusal cases; full chain PASS, 0 violations.
8. **R3 — validators for new invariants.** Every new invariant gets a validator (I-N); validators are predicates, not procedures.
9. **R4 — zero inference in execution.** No inference inside automaton execution; inference stays outside with human-in-the-loop, reaching the core only as discrete step-changes.
10. **R5 — trust declared.** New trust assumptions declared (declared trust); trust boundaries named, not smuggled.

Dual-scope matters evaluate both sets independently; the draft verdict is conjunctive (§7).

Domain gates (spec §5): **X1** scope kill (unassignable scope after decomposition attempt → refused back for reframing); **X2** core-risk kill (replay story fails at KEEP → refused); **X3** spec-first kill (implementation without spec → refused wherever it appears); **X4** duplicate-merge (duplicates a standing mechanism without naming the delta → refused back for narrowing/merging/superseding). In rehearsal, fired gates are reported as would-kill findings with the gate cited.

## 7. Draft verdict `[judgment]`

- **adopt** — all applicable conditionals hold.
- **adopt-with-conditions** — all hold except remediable evidence gaps; conditions stated as checkable and finite.
- **refuse** — any conditional fails, or an X-gate fires (in rehearsal: would refuse).

The verdict is a **recommendation, never an adoption**. Disposition is the operator's act through the shared disposition machinery; the DecisionRecord carries playbook discriminator `feature-expansion`. No parallel disposition modes are defined for this playbook (spec §7, reasoned: a second mode table would split the authority record). For dual-scope matters the verdict is conjunctive: neither matter is adoptable until both are.

## 8. Report `[mechanical format, judgment content]`

Byte-exact template. Refused matters get no report (§3); the mode line always states the regime.

```text
/pb-extend report
Mode: <rehearsal — playbook DRAFT, unadopted | governed — playbook adopted <record-ref>>
Matter: <text> (inline)
Staging (START): claim <framed>; scope <package | runtime | decomposed: package + runtime>; proposer <named>; prior art <cited>
Scope test: <one-line discriminating-test reasoning>
Conditionals:
  A1 falsification survived: <holds | fails | unevaluated> — <evidence cited>
  A2 ontology justified: <...> — <...>
  A3 plane discipline: <...> — <...>
  A4 spec before build: <...> — <...>
  A5 evidence, not assertion: <...> — <...>
  P1 interface consistency: <...> — <...>   (package only)
  P2 hermeticity preserved: <...> — <...>
  P3 docs converge: <...> — <...>
  P4 installability: <...> — <...>
  R1 deterministic replay: <...> — <...>   (runtime only)
  R2 golden run extended: <...> — <...>
  R3 validators for invariants: <...> — <...>
  R4 zero inference in execution: <...> — <...>
  R5 trust declared: <...> — <...>
Gates: X1 <clear | fired | would-fire (rehearsal)>; X2 <...>; X3 <...>; X4 <...>
Draft verdict: <adopt | adopt-with-conditions: <conditions> | refuse> — <one-line reason>
Disposition: the operator's act (shared machinery; DecisionRecord discriminator `feature-expansion`)
```

Pre-delivery checklist: mode line present; staging complete per S1–S4 (shortfalls reported, never silently skipped); every applicable conditional carries a finding with evidence cited or an explicit unevaluated; every fails/would-fire cites its conditional or gate; draft verdict present with its reason; no records written; findings reported, never repaired.

## 9. Worked example (illustration only)

2026-09-20: staged in-chat by the ambient agent — the seed matter ("an 'updater' automaton is required to monitor and manage release updates and upgrades to dsys", 2026-09-20 13:08 PDT). Staging: claim framed ("dsys should gain an updater mechanism such that release updates and upgrades are monitored and managed"); scope decomposed at START — *release acquisition, checksum verification, release binding, installer integration* → package (alters the delivery vehicle, not the machine's guarantees); *an automaton managing upgrades* → runtime (execution semantics, new run-books, upgrade as step-change, self-modification trust). Adoption conjunctive. This is a staging illustration, **not** an evaluation: the seed matter remains proposed, never evaluated, never disposed — a chat message is not authority.

## Glossary

- **matter** — the feature-expansion matter supplied to `/pb-extend` in chat; recorded as `inline`.
- **feature expansion** — a proposed addition to what dsys is: a new capability, mechanism, or surface dsys should gain (spec §1). Not a rung mutation, not a general decision.
- **scope** — package (dsys-repo: the delivery vehicle and operator surface) or runtime (the deterministic core: what the machine guarantees), assigned by the discriminating test.
- **discriminating test** — "does the change alter what the machine guarantees?" Yes → runtime; no → package.
- **decomposition** — splitting a dual-scope matter at START into two scoped matters proceeding independently.
- **conjunctive adoption** — neither decomposed matter adopted until both are.
- **staging** — the START entry work: claim framed, scope assigned, proposer named, prior art cited (S1–S4).
- **conditional** — one adoption check (A1–A5 shared; P1–P4 package; R1–R5 runtime).
- **holds / fails / unevaluated** — the finding scale: holds and fails cite evidence; unevaluated means no evidence (stated, never held).
- **rehearsal** — the current regime: the playbook is DRAFT and unadopted, so the command exercises it (stage, scope, evaluate, draft) without gating, deciding, or recording.
- **governed** — the regime after the playbook's adoption via disposition: STOP kills enforced, the KEEP verdict feeds disposition.
- **would-kill** — a rehearsal finding: the gate or failure that would kill in governed mode, reported with its citation, not enforced.
- **draft verdict** — adopt / adopt-with-conditions / refuse: a recommendation; disposition is the operator's act.
- **proposer** — the named source of the expansion; proposer ≠ disposer always.
