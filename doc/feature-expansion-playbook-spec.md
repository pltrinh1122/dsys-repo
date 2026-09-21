# Feature-expansion playbook

**Status:** adopted 2026-09-21 (DR-CMD-027) — designed 2026-09-20
per operator direction ("design `/pb-extend`"); remediated
2026-09-21 per the DR-CMD-026 rehearsal (five-item fix list,
§12); amended 2026-09-21 per operator direction ("pattern
covered in general"): conditional-matter type (§1, S1–S3, §6,
§7); amended 2026-09-21 per operator direction (motivation):
S5 motivation-stated, because-Z claim form, §7 motivation-fit
lens; amended 2026-09-21 per operator direction (Z bites hardest):
S5 load-bearing (the because-Z is the claim's identity), §7
misplaced-Z invalid terminal (distinct from killed; returns only
as a new matter). Applied governed via `/pb-extend` (see §10 Bootstrap).
Invoked in chat via `/pb-extend`; bound at
`doc/slash-commands/pb-extend.md`.

**Kind:** decision-making playbook following the §8.2 pattern —
a *set* of DoD conditionals (START / STOP / KEEP, gates), not a
sequence. A procedure you *follow*, not a node you command.
Sibling: the dsys-mutation playbook (second playbook on the
same pattern). Proposer ≠ disposer holds throughout:
the ambient proposes, the operator disposes.

## 1. Matter

A **feature expansion** is a proposed new capability, mechanism,
or surface for dsys — something dsys should *gain*. (Seed
matter, 2026-09-20 13:08 PDT: "an 'updater' automaton is
required to monitor and manage release updates and upgrades to
dsys" — proposed only, never evaluated, never disposed.)

An expansion is not a mutation of an existing rung (that's the
mutation playbook's domain) and not a general decision (that's
`/pb-decide`). It is an *addition* to what dsys is.

### Conditional matters

A **conditional expansion** is an expansion whose existence is
undisposed — the operator has not disposed it into existence, or the
standing disposition is negative — but whose governed *shape* is worth
designing now. The typical source is a falsification's repair
direction ("*if* X is ever wanted, it needs Y"). The claim takes the
conditional form: "*if* disposed, dsys should gain X such that Y, because Z."
The matter designs the map, not the road: every conditional below
runs against the hypothetical, and adopting the design is never
adopting the expansion. A conditional matter whose Z is misplaced
is invalid in full — the map is of a road to nowhere. The existential disposition stays with the
operator, separate from the matter, before and after. (First
instance: K3, the governed check-now path, 2026-09-21.)

## 2. Scope differentiation

Every expansion matter is assigned **exactly one scope** at
START. The scope determines which adoption conditionals apply
(§4) and what evidence is required. The discriminating test:

> **Does the change alter what the machine guarantees?**
> Yes → runtime scope. No → package scope.

- **Package scope (dsys-repo):** the project — the CLI surface,
  `install.sh`, roles, scenarios, docs/specs (including this
  playbook), packaging, release binding. The delivery vehicle
  and the operator surface. Changes here must not alter the
  deterministic core's semantics.
- **Runtime scope (core of the Architecture):** the
  deterministic core — schema entities, validators, the
  automaton executor, the golden run, session sync, disclosure
  views, trust boundaries, the machine-native package. Changes
  here alter what the system *guarantees*: deterministic
  replay, zero inference, hermeticity, checkability.

**Why the split is load-bearing:** the core's guarantees are
the load-bearing walls; the package is scaffolding and
surface. Package-level convenience must not smuggle
runtime-level risk. (Precedent: the CLI falsification —
surface reach vs downstream inertness; the mutation playbook's
trust-boundary declaration.)

**Decomposition rule:** a matter touching both scopes is
decomposed at START into two scoped matters (one package, one
runtime). They proceed independently; **adoption is
conjunctive** — neither is adopted until both are.

**Scope creep** (a package matter growing runtime tendrils
mid-matter, or vice versa) → STOP: decompose or kill.

## 3. START — open an expansion matter

Entry conditionals (all hold before the matter opens):

- **S1 — falsifiable claim.** The expansion is stated as a
  falsifiable claim ("dsys should gain X such that Y"), not a
  vibe. The such-that clause should anticipate A5 — name the
  checkable procedure or acceptance signal, not just the
  capability. Vague matters are refused back for reframing.
  *Conditional matters:* the claim takes the conditional form
  ("*if* disposed, dsys should gain X such that Y"); the
  such-that clause is checkable against the hypothetical.
- **S2 — scope assigned.** Package or runtime, by the
  discriminating test. Dual-scope matters decomposed per §2.
  *Conditional matters:* the discriminating test runs on the
  hypothetical change. Scope assignment governs the design;
  conjunctive adoption applies to the design, never to a build.
- **S3 — proposer named.** Proposer ≠ disposer; the ambient
  never proposes on its own authority for its own expansions.
  *Conditional matters:* no proposer is required. Instead the
  **source of the conditional** is named (a kill's repair
  direction, an operator-directed design, or equivalent), and the
  existential disposition is recorded as open or
  standing-negative. The ambient may draft the conditional design
  at the operator's direction; drafting is not proposing.
- **S4 — prior art cited.** The existing spec section (or
  "none" declared), the seed matter if relevant, related
  falsifications.
- **S5 — motivation stated.** The world problem or capability
  gap, as a concrete scenario: who is failed by the current
  system, and how. One to two sentences, held to S1's anti-vibe
  bar — "it would be nice" or "the operator wants it" is not a
  gap. A matter without a statable gap is refused back for
  reframing, same as a vague claim. With S5, the S1 claim reads
  in full: "dsys should gain X such that Y, because Z" —
  conditional matters: "*if* disposed, dsys should gain X such
  that Y, because Z." S5 is load-bearing, not one gate among
  five: the because-Z is the matter's foundation. The claim's
  identity includes its Z — a new Z is a new matter, not a
  reframing. A matter whose Z is later found misplaced is invalid
  in full; see §7.

**DoD (START complete):** claim framed, scope assigned,
proposer named, prior art cited, motivation stated. Nothing evaluated yet.

## 4. Adoption conditionals

KEEP *evaluates* these conditionals against cited evidence. A
conditional **holds** only with evidence cited; without
evidence it is **unevaluated** (the matter may be staged with
unevaluated conditionals — the playbook tracks what is
evidenced, and unevidenced is not held).

**Shared (both scopes):**

- **A1 — falsification survived.** The claim was submitted to
  falsification (`falsify`, or `/eval-meta`); no
  refuted sub-claim survives in the proposal. The operator may
  waive falsification with reason recorded — waiver is
  declared, not hidden.
- **A2 — ontology justified.** Every new term, entity, or
  command justified against the existing ontology (glossary);
  no synonym proliferation; new namespace tokens defined
  before use.
- **A3 — plane discipline.** The expansion respects
  ambient/automaton plane boundaries: no inference smuggled
  into the automaton plane; no automaton reach claimed for
  ambient commands; sequencing belongs to run-books.
- **A4 — spec before build.** The expansion is specified (spec
  section or file) before implementation. Implementation
  presented without a spec is refused — the playbook
  evaluates specifications, not code drops.
- **A5 — evidence, not assertion.** Acceptance criteria stated
  as checkable sequences: validators, golden runs, CLI
  transcripts, pass/fail. "Trust me" is not evidence.

**Package-scope additions:**

- **P1 — interface consistency.** CLI changes conform to
  DR-CLI-001 (`family, operation, flags`); no third token
  level; new commands compose with the existing tree.
- **P2 — hermeticity preserved.** The per-command hermeticity
  story is stated and updated; no new network touch without
  declaration; offline install still holds.
- **P3 — docs converge.** The governing spec is updated in the
  same change; docs do not lag the code.
- **P4 — installability.** `install.sh` converges the new
  surface; `doctor` covers it; the operator's idempotency
  sequences still hold.

**Runtime-scope additions:**

- **R1 — deterministic replay preserved.** Existing
  transcripts still validate; new behavior is replayable by
  construction (transcript re-validation, never behavioral
  re-execution).
- **R2 — golden run extended.** New golden-run cases cover the
  expansion, *including refusal cases*; full chain PASS, 0
  violations.
- **R3 — validators for new invariants.** Every new invariant
  the expansion introduces gets a validator (I-N); validators
  are predicates, not procedures.
- **R4 — zero inference in execution.** No inference inside
  automaton execution; inferencing stays outside with
  human-in-the-loop, reaching the core only as discrete
  step-changes.
- **R5 — trust declared.** New trust assumptions declared
  (declared trust), trust boundaries named — not smuggled.

## 5. Gates

G1–G4 inherited from §8.2 (well-formed, legitimate source,
non-redundant, actionable), plus domain gates:

- **X1 — scope kill.** A matter that cannot be assigned a
  single scope after a decomposition attempt is refused back
  for reframing. Scope ambiguity is the failure mode.
- **X2 — core-risk kill.** A runtime-scope matter whose replay
  story (R1) evaluates to fails at KEEP is refused. No replay
  story, no runtime change. (Moved from START 2026-09-21, DR-CMD-026
  rehearsal: S1–S4 do not require a replay story at START, so firing
  at START killed every runtime seed matter; R1 is evaluated at KEEP.)
- **X3 — spec-first kill.** Implementation without a spec
  (A4) is refused at any point it appears.
- **X4 — duplicate-merge (G3 routing).** An expansion matter that
  duplicates the guarantees of a standing mechanism (prior art, S4)
  without naming its delta is refused back: narrow the claim to the
  delta and re-enter START; fold the expansion into the existing
  mechanism's spec as an amendment (merge — record the alias, the
  expansion matter closes merged); or, if the expansion genuinely
  supersedes the standing mechanism, record "superseded by" per the
  canonical supersession branch (the original stands as valid history,
  not as error). In rehearsal: would-fire.

G5/G6 operate at KEEP (§7).

## 6. STOP — kill the expansion

- A refuted sub-claim the proposer won't remove → kill (or
  narrow the claim and re-enter START).
- Scope creep → decompose or kill (§2).
- Evidence failure (golden run red, validator missing,
  hermeticity broken) → kill; may re-enter START with new
  evidence. A kill is not a verdict on the idea's worth —
  killed matters may return reframed.
- *Conditional matters:* STOP kills the design, not the idea.
  The existential disposition is the operator's and is
  unaffected by the kill; a killed conditional design may return
  reframed, and the standing-negative (or open) existential is
  unchanged.

## 7. KEEP — deliver the adoption verdict

**DoD:** per-conditional findings (holds / fails /
unevaluated), each citing its evidence; overall draft verdict:

- **adopt** — all applicable conditionals hold.
- **adopt-with-conditions** — all hold except remediable
  evidence gaps; conditions stated as checkable and finite,
  recorded in the DecisionRecord. (Lapse mechanics — what
  happens if conditions are never met — tagged G6.)
- **refuse** — any conditional fails, or an X-gate fires. The
  verdict cites its flavor: `not-ready` (evidence gaps /
  unevaluated conditionals — reframe and re-enter START) or
  `killed` (a conditional fails or an X-gate fires —
  substantive).

**Motivation-fit.** KEEP checks one relation that is not a
conditional: does the evaluated design serve the stated Z (S5)?
Two tiers:

- *Fit failure* — the Z is real but the design does not serve
  it. Refused back as `not-ready`: reframe the design or restate
  the motivation. The conditionals verify the mechanism; fit
  verifies the point.
- *Misplaced Z* — the gap does not exist, or the request is
  solution-first with a post-hoc Z. The **complete request is
  invalid**: terminal, and distinct from `killed`. A killed
  matter may return reframed (§6); an invalid matter returns
  only as a **new** matter — new S1–S5, new lineage — because the
  because-Z is part of the claim's identity. The DecisionRecord
  records the invalidity and the evidence, so the future matter
  can cite it as prior art.

The Z makes a world-claim, and world-claims are checkable: KEEP
judges misplacement on cited evidence (the Z asserts operators
have no recourse; the recourse is exhibited). The operator may
also find misplacement at disposition — that is `reject`, with
the reason recorded.

**The verdict is a recommendation, not an adoption.**
Disposition is the operator's act, through the shared
disposition machinery, recorded in a DecisionRecord with
playbook discriminator `feature-expansion`. Applicable shared
modes (DR-2 subset): **ratify** — the operator selects among
the KEEP draft verdicts (adopt / adopt-with-conditions /
refuse); this is the normal disposition. **overrule** —
available when a standing veto blocks adoption (a prior
ratified refusal of this expansion, or a standing policy such
as a v1 scope freeze); the veto's reason is absorbed per E7.
`authorize`, `set_standing`, and `triage` do not apply to
expansion matters — adoption is a selection among verdicts,
not a permitted action, a policy establishment, or a
disclosure disposal. No parallel disposition modes are
defined — the single disposition machinery is not forked for
this playbook (reasoned: expansion adoption is a species of
decision; a second mode table would split the authority
record).

**Refuse vs reject.** `refuse` is the draft's verdict — a
recommendation, in either flavor above. `reject` is the
operator's disposition outcome: the operator ratifies a
refuse verdict, and the DecisionRecord records the expansion
as rejected — terminal, though §6 allows return reframed.
The draft never rejects; the operator never refuses — the
draft recommends, the operator disposes. (Per E5, the
operator's silence is NO_DECISION: an unratified adopt verdict
leaves the matter open; it does not reject it.)

**Conditional-matter verdicts.** KEEP evaluates the *design*
against the conditionals exactly as for a live matter, but the
verdicts attach to the design, never to the expansion:

- **adopt-the-design** — the governed shape is sound; the road
  stays undisposed.
- **adopt-the-design-with-conditions** — as above, with
  remediable evidence gaps stated as checkable and finite.
- **refuse** — the design fails; the natural terminal is
  **refuse-with-a-map**: the expansion is refused *and* the
  governed shape is recorded for a future disposition.

Invariant: **adopting the design is never adopting the
expansion.** A DecisionRecord on a conditional matter records the
map and the still-open (or standing-negative) existential
disposition; it authorizes no build. If the operator later
disposes the existential affirmatively, the expansion re-enters
as a live matter at START — the recorded design is prior art
(S4), not a pre-adoption.

G5 binds the DecisionRecord; G6 tags uncertainties.

## 8. Worked scoping example (illustration only)

Seed matter: "an 'updater' automaton is required to monitor
and manage release updates and upgrades to dsys."

Scoping, by the discriminating test:

- *Release acquisition, checksum verification, release
  binding, installer integration* — alters the delivery
  vehicle, not the machine's guarantees → **package scope**
  (installer-spec, release binding).
- *An automaton that manages upgrades* — execution semantics,
  new run-books, upgrade as step-change, trust around
  self-modification → **runtime scope**.

→ Decompose into two matters at START; adoption conjunctive.
This is a scoping illustration, **not** an evaluation: the
seed matter remains proposed, never evaluated, never
disposed.

## 9. Relations

- **`/pb-decide`** (general): the operator may route an
  expansion matter through `/pb-decide` directly; this
  playbook is the specialized procedure for expansion
  matters invoked via `/pb-extend`.
- **`/eval-pb`**: validates playbook-shaped
  candidates against the Architecture's playbook definition —
  the instrument for the A1 falsification of this draft and
  of future expansion specs. **`/eval-meta`** is the
  falsification posture for expansion claims.

## 10. Bootstrap

Adopting this playbook is itself a **package-scope** matter
(a `doc/` change in dsys-repo). Applying it to itself before
ratification is rehearsal: the draft's own adoption should
run its START (S1–S4 above), survive falsification
(`/eval-pb`), and be disposed by the operator (mode:
set_standing — adoption establishes the playbook as standing
policy).
The operator's adoption breaks the circle — a chat response
is not authority, and neither is a draft citing itself.

## 11. Falsifiers (pre-registered)

- **F-E1:** "Scope decomposition is always possible."
  Falsifier: an expansion whose package and runtime aspects
  are inseparable (e.g., a CLI command that *is* a new
  guarantee — surface and core in one). If found, the
  conjunction rule needs revision.
- **F-E2:** "Package-scope expansions can't break
  determinism." Falsifier: a package change (installer
  default, config default) that alters runtime behavior.
  The P/R split marks *risk domains*, not a guarantee —
  P-scope matters still face A3.
- **F-E3:** "The adoption conditionals are complete."
  Falsifier: an adopted expansion that later breaks a
  guarantee no conditional covers. The set is versioned;
  incompleteness is expected and recorded, not hidden.
- **F-E4:** "Every matter assigns cleanly to package|runtime."
  Falsifier: a matter that *is* the taxonomy (amending §2)
  or an ontology change (glossary) governing both scopes.
  If found, the taxonomy needs a "governs" relation or a
  third scope.

## 12. Executed exercise (2026-09-21, DR-CMD-026)

This remediation's fix list derives from an executed
rehearsal, not from reading the spec. Two matters run through
the draft procedure in rehearsal (would-findings, no gating,
no records, no disposition):

- **Admit case** — seed matter "an 'updater' automaton is
  required to monitor and manage release updates and upgrades
  to dsys" (2026-09-20 13:08 PDT): decomposed at START
  (package: release acquisition, checksum verification,
  release binding, installer integration; runtime: upgrade
  execution semantics, new run-books, upgrade as step-change,
  self-modification trust). Staging complete per S1–S4; all
  conditionals unevaluated (no spec, no evidence cited); X2
  would-fire (no replay story stated at START). Draft verdict:
  would-refuse (not-ready) — reframe and re-enter.
- **Kill case** — "LLM-driven natural-language query interface
  inside the automaton executor, answers generated at
  execution time" (exercise-proposed): runtime scope. A3 fails
  (inference in the automaton plane, contra the ratified v1
  zero-inference decision); R1 fails (not replayable by
  construction); R4 fails (the proposal *is* inference in
  execution). Draft verdict: would-refuse (killed).

Findings (the fix list this remediation implements): (1) the
disposition-mode subset was unnamed — §7 now names
ratify (+overrule exceptional); (2) this exercise — recorded
here; (3) G3 duplicate-merge routing was missing ('updater'
overlaps `install.sh --release` binding, the AutomatonRelease
promotion bridge, and accretion-repo's installed-tree
discipline) — X4 added; (4) refuse-vs-reject conflated — §7
now distinguishes draft `refuse` (not-ready | killed,
a recommendation) from operator `reject` (the ratified
terminal decline); (5) X2 fired at START though S1–S4 require
no replay story at START — X2 moved to KEEP; (6) S1
such-that clauses should anticipate A5 — staging guidance
added.

Full reports: 2026-09-21 chat record (rehearsal regime,
per `/pb-extend` §8).
