# Design: `/eval-meta` — claim/evidence evaluation with accretion-repo grounding

**Status: ratified** — DR-CMD-025 (2026-09-21). Member of the `eval-*` validator family (DR-CMD-004/005 lineage).

## 1. Argument forms

The matter is parsed into CLAIM (required) and CITATIONS
(optional list):

- Form A: `/eval-meta {claim}` — bare claim.
- Form B: `/eval-meta {claim} :: {citations}` — claim plus
  cited evidence. `::` is the conventional delimiter; a
  natural-language "Evidence:" list is accepted as the same
  form.

A citation is a *resolvable* reference: record ID, label,
accreted path, `<path>@<commit>`, or blob SHA. Freeform
prose ("the doctor output") is not a citation — refused
back with the citation grammar.

## 2. Scope determination (step 0)

Does the claim's truth depend on instance state (installed
tree, accreted history, runtime behavior)?

- Yes → full pipeline (checks 1–5).
- No → checks 1–2 plus adversarial reasoning; checks 3–5
  marked N/A with the reason stated. A claim about the
  architecture's definitions, for example, does not ground
  in the accretion-repo.

## 3. Check 1 — Falsifiability of the claim

Admissible iff there exists at least one observable state
whose observation would refute the claim. Otherwise refused
back for reframing, with the defect named:

- **tautological** — true by definition, not a claim;
- **vague** — terms without referents;
- **normative-unoperationalized** — "should" with no
  observable criterion;
- **untestable-in-principle** — no observation could bear
  on it.

Falsifiability is about form, not truth: a
false-but-falsifiable claim is admissible — that is the
point. Check 1 is a pre-report gate: failure produces no
report — the claim is refused back with the defect named.
The report's two sections (§8) cover dimensions 2–5 only.

## 4. Check 2 — Logical coherence, claim ↔ cited evidence (Form B)

On the cited evidence *as cited* — face value, before any
repo is touched:

- **relevance** — does it bear on the claim's truth
  conditions?
- **non-circularity** — it must not restate or assume the
  claim;
- **internal consistency** — the cited set must not
  contradict itself;
- **sufficiency-in-form** — *if* the cited evidence were
  true, would it actually move the needle, or is there a
  non-sequitur gap?

Failure → the report is still produced: D2 failed, D3–D5
marked not-run, and the synthesis delivers the refusal
(reframe and resubmit). Purely logical; the repo is not
touched at this step.

## 5. Check 3 — Grounding in the instance/accretion-repo

Each citation is resolved to bytes in the instance's
accretion-repo:

- **resolution** — citation → git object. `<path>@<commit>`
  preferred (pinned). Unpinned paths resolve to the latest
  accreted commit, flagged as unpinned (declared trust).
- **source discipline** — ground against the
  accretion-repo (the git dir), never the live tree alone.
  The live tree is mutable under the declared-mutation
  rule; the repo is the durable, history-bearing record.
- **instance binding** — default is the operator's
  instance; the accretion path is read from the instance's
  config (`accretion.path`). Accretion disabled → checks
  3–5 are unevaluable, the gap named.
- **ungrounded** — an unresolvable citation yields the
  per-citation finding `ungrounded`. Not a refutation: a
  named gap. Evaluation proceeds on the grounded subset.

Form A asymmetry: with no cited evidence, the evaluator
*may* seek refuting or confirming observations in the
accretion-repo adversarially — that is the falsification
posture — but nothing is required to ground.

## 6. Check 4 — Consistency, grounded evidence vs cited evidence

For each grounded citation: does what the repo actually
contains match what the citation *claimed* it contains?

- quoted text vs actual bytes; claimed values vs actual
  values;
- mismatch → `inconsistent`: misquotation, stale pin (the
  repo moved on), or selective excerpt — an accurate quote
  whose surrounding context reverses it, flagged as
  excerpt-risk.

This separates "the evidence is real" from "the evidence
says what you said it says."

## 7. Check 5 — Coherence, grounded evidence ↔ claim

With grounded, consistent evidence: does it support,
refute, or stay neutral on the claim?

- findings: **confirmed / refuted / decomposed**
  (standing taxonomy), plus **unevaluable** — admissible
  claim, insufficient grounded evidence, gaps named.
- decomposition is the expected common case: the claim
  splits into a surviving sub-claim and a
  refuted-or-ungrounded remainder.

## 8. Report structure

Two sections, always in this order:

**Section 1 — Synthesis.** The verdict and the compressed
reasoning chain: confirmed / refuted / decomposed /
unevaluable — what the dimensions jointly establish (what
survived, what was refuted, what was ungrounded). A
one-line admission note ("claim admitted as falsifiable")
may open it; check 1 is not a dimension.

**Section 2 — Dimension assessment (2–5).** A stable
four-dimension structure. A dimension that does not apply
is marked N/A with the reason, never silently omitted:

- **D2** — claim↔cited-evidence coherence: pass / fail /
  N/A (Form A carries no cited evidence).
- **D3** — grounding: per citation grounded / ungrounded,
  with pins.
- **D4** — consistency: per citation consistent /
  inconsistent, with diffs.
- **D5** — grounded-evidence↔claim coherence: supports /
  refutes / neutral / unevaluable, with reasons.

Short-circuit: check 1 fails → no report (refusal with
the defect). D2 fails → report produced, D3–D5 marked
not-run, synthesis delivers the refusal. Ungrounded
citations never stop the pipeline; they are named gaps in
D3. Out-of-scope claims (step 0 = No): D3–D5 marked N/A
with the reason.

## 9. Character of the pipeline

Checks 3–4 are mechanical (git resolution, byte
comparison): deterministic and re-checkable. Checks 1, 2,
5 involve judgment: reported with reasons, never bare
verdicts. The pipeline is *structured*, not fully
mechanical — honest about which parts are which.

## 10. Boundaries (retained)

Read-only over the accretion-repo: git reads, never
writes, never mutates. Evaluation is not decision: never
ratifies, never disposes, never writes DecisionRecords.
Findings are delivered in chat; files are written only on
operator direction.

## G6 / open

- multi-instance qualification (default: operator's
  instance);
- citation grammar for non-file records (transcript
  turns, dialog requests);
- GC'd context: accretion excludes cache by construction —
  claims about cached state are ungroundable, not merely
  ungrounded.

## Glossary

Self-containment rule: every acronym and specialized term
used in this document is defined here. Citations point to
the official definition; the inline definition stands
alone — no other document need be opened.

- **accretion-repo** — a git repository serving as the
  durable store of a dsys installation's accreted state
  (`etc/` + `var/`, minus cache directories). Canonical
  label (ratified 2026-09-19; `git-store` is an alias).
- **check 1..5** — the five pipeline checks: 1
  falsifiability (§3), 2 claim↔cited-evidence logical
  coherence (§4), 3 grounding (§5), 4 grounded-vs-cited
  consistency (§6), 5 grounded-evidence↔claim coherence
  (§7).
- **D2–D5** — the four report dimensions (§8): D2
  claim↔cited-evidence coherence, D3 grounding, D4
  consistency, D5 grounded-evidence↔claim coherence.
- **declared-mutation rule** — dsys's own files may be
  mutated; undisclosed mutation is the failure mode
  (doctor distinguishes pristine from mutated).
- **declared trust** — the architecture's trust posture:
  properties that are author-declared rather than
  mechanically enforced (e.g. unpinned citations resolving
  to the latest accreted commit).
- **DRAFT** — proposed; not evaluated, not disposed.
- **DR** — DecisionRecord: the architecture's
  decision-recording entity.
- **falsifiable** — there exists at least one observable
  state whose observation would refute the claim (§3).
- **Form A / Form B** — the two argument forms (§1): bare
  `{claim}`, or `{claim} :: {citations}`.
- **G6** — gate 6 of the decision-making playbook
  (architecture §8.2): the open-questions slot —
  deferred items, revisit triggers, unconsidered
  alternatives. A G6 list records known gaps, not
  oversights.
- **GC'd** — garbage-collected. Cache directories are
  excluded from the accreted set by construction, so
  claims about cached state are ungroundable in
  principle, not merely ungrounded in this evaluation.
- **instance** — an installed dsys instantiation. The
  operator's instance is the default binding (§5).
- **N/A** — not applicable; always accompanied by the
  reason, never silent (§8).
- **refuse back** — explicit refusal with a redirect or a
  reframing instruction, as opposed to silent
  wrong-branch handling.
- **SHA** — content hash identifying a git object (blob,
  commit).
- **standing taxonomy** — the falsification posture's
  finding set: confirmed / refuted / decomposed.
- **step 0** — scope determination (§2): whether the
  claim's truth depends on instance state.
- **synthesis** — report section 1 (§8): verdict plus the
  compressed reasoning chain.
- **unevaluable** — finding: an admissible claim with
  insufficient grounded evidence; gaps named.
