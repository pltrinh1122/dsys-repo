# Design: `/eval-rb` — run-book validation against the Architecture's normative definition

**Status: ratified** — DR-CMD-017 (2026-09-20). Design reasoning for the `/eval-rb` validation routine. The normative procedure is `doc/eval-rb-implementation.md`; the operator-facing contract is `doc/slash-commands/eval-rb.md`. Per the standing principle, provenance and reasoning live here, not in the implementation doc.

## 1. What is being validated

The candidate is a *procedure claiming the run-book form*. The norm is not an exemplar document but the Architecture's definition: `doc/glossary.md` "Run-book" → the RunBook entity (`schema.py`) → `doc/automaton-executor-spec.md`. This is why `/eval-rb` is semantic where `/eval-sc` is comparative: there is no standing exemplar run-book to diff against, only the definition's requirements. The division of labor between the three evaluators is deliberate: `/eval-sc` checks that a definition *binds* a procedure; `/eval-pb` and `/eval-rb` check the *bound thing* against the playbook and run-book definitions respectively. None validates the others' work.

## 2. The ten dimensions — design rationale

Dimensions 1–6 check *form*: the candidate must be strictly sequential steps, not conditionals (the v1 decision: run-books are strictly sequential — the mirror image of the playbook's "not a sequence"); each step an AST-allowlisted expression compiled once; zero inference inside execution (the automaton's hardest boundary — all inference outside as step-changes); every step invoking a declared tool; pinned to a shipped release by `release_version`; one run-book per `AutomatonRun`. Each dimension exists because its absence is a known failure mode of would-be run-books: gated flows that can't replay, unallowlisted logic, inference smuggled into execution, unbound actions, unpinned tools, multi-run-book runs.

Dimensions 7–10 check *declared evidence*, applying the DR-CMD-009 regime by pattern (DR-CMD-009 was ratified for `/eval-pb`; the regime is about procedures generally, not playbooks specifically — flagged in §7, not smuggled): exercise declared, trigger declared, output format specified, and the adapted fourth — failure routing at G1 precision, the run-book analog of the playbook's kill gates (a failure policy no failure could trigger is decoration, exactly as a gate no matter could fail is). The rationale is the same three-tier decomposition as `/eval-pb`: (a) form — dimensions 1–6; (b) declared evidence — dimensions 7–10, presence-checked only; (c) evidence-quality judgment — reserved to disposition (G5), never the validator's. The same residual risk is accepted: a candidate may cite a vacuous run and pass dimension 7. Closing it would turn the validator into an auditor, which is a different instrument.

The finding scale needs three values, not two, because the candidate may be run-book-adjacent: *undefined-against* records "this dimension does not apply to this candidate's kind" so inapplicable dimensions are stated, never silently skipped and never penalized.

## 3. Admission — why verify, not classify

Admission verifies the matter is actually a run-book candidate; it never classifies the matter into a taxonomy. The comparability threshold — a procedure claiming the run-book form (automaton-plane, sequential, tool-invoking, zero-inference, release-pinned) — is deliberately high-resolution on one point: **sequentiality alone does not pass**. A judgment-stepped ambient-agent procedure (this command family included) is sequential but not automaton-plane, and the threshold refuses it. This is the precise form of the concern recorded against `/eval-meta`'s §2 redirect phrasing ("sequential procedure" taken literally would over-admit): `/eval-rb`'s threshold is the definition the redirect points at, and the redirect's shorthand is read as this threshold, not as bare sequentiality (see G6). Below the threshold, the redirect table (`/eval-pb` for playbooks, `/eval-meta` for general matters) routes the matter to the instrument that can actually see it. A run-book-adjacent non-run-book is admitted but can only receive "not evaluable against the definition" — the honest verdict for incomplete shape, and the reason the overall scale has three values.

## 4. Report design

Per-dimension findings, each carrying one line of reasoning and at least one normative citation, because a bare verdict from a validator is uncheckable — the report must show its work or it is decoration. Deviations are reported, never repaired: repair is a mutation matter for `/pb-decide`, and a validator that rewrites its candidate has stopped validating. The byte-exact template exists so reports are comparable across runs; the pre-delivery checklist exists so the agent cannot ship a report with a missing dimension or an uncited deviation.

## 5. Character of the routine

`/eval-rb` is an evaluator, not a decider: it produces no disposition, writes no records, and its verdicts bind nothing. Deterministic replay holds in the weak sense — same candidate bytes, same procedure → same findings, modulo the judgment content, which is why every judgment carries its reasons and citations. The routine is sequential (parse → resolve → admit → validate → report) by design; that it would itself fail dimensions 1–5 is not a defect but the point — it is not a run-book and does not claim the form. It lives in the ambient layer by declared design (contract Boundaries 1): judges aren't contestants, across planes too.

## 6. Boundaries (retained)

From the contract: the command executes in the ambient layer only — never installed, never on the dsys CLI tree, never invokable by the automaton executor; normative sources are read, never rewritten, by validation; validation findings are advisory to the operator — a "deviates" finding does not deprecate, void, or rewrite the candidate (that is disposition, `/pb-decide`); evaluation is not decision — no ratification, disposal, or recording. The disposition machinery is absent by declared design, which is why the worked self-evaluation (2026-09-20, in-chat) correctly returned "not evaluable against the definition".

## 7. Provenance

Authoring notes (durable):

- 2026-09-20 (authoring): the §1 usage line and the §2 `/name`-and-path resolution rule were newly specified in the implementation doc — the contract declares no pointer grammar — mirroring `/eval-pb` §§1–2. Flagged at authoring, not smuggled.
- 2026-09-20 (authoring): §4 operationalizes the contract's six Check dimensions into per-dimension verdict rules, and adds dimensions 7–10 on the DR-CMD-009 declaration-presence pattern (dimension 10 adapted: kill gates → failure routing, the run-book analog). The pattern application was proposed in the draft, subject to operator disposition.
- 2026-09-20 (authoring): the run-book-adjacent second admission branch mirrors `/eval-pb`'s §3 second branch; the threshold's "sequentiality alone does not pass" clause is the precise form of the concern recorded against `/eval-meta` §2.
- 2026-09-20 (DR-CMD-010, ratified): the implementation→design reference edge is schema; this document is the counterpart the implementation doc names.
- 2026-09-20 (ratification, DR-CMD-017): DRAFT removed from both docs; the DR-CMD-009 pattern application for dimensions 7–10 ratified (the design's G6 question on whether the pattern application itself needed ratification is thereby closed); DR-CMD-012 step 3 complete.

## G6 / open

- `/eval-meta` §2's redirect phrasing ("sequential procedure — glossary 'Run-book'") vs `/eval-rb` §3's threshold ("a procedure claiming the run-book form"): should the redirect wording be tightened so the shorthand cannot be read as bare sequentiality? `/eval-rb` reads it as the threshold; the `/eval-meta` text is `/eval-meta`'s own remediation matter, not this draft's.
- Vacuous-run citation under dimension 7: accepted residual risk (see §2); unclosable without turning the validator into an auditor.
- Whether "not evaluable" verdicts should carry advisory repair hints: currently no — repair is mutation, routed to `/pb-decide`. Same open question as `/eval-pb`; the two commands should answer it the same way.
- Worked examples are thin (one in-chat self-run); the implementation doc's example set should grow with real executions. No shipped run-book exists yet to validate against (the executor spec is specified, not implemented) — the first real candidate will exercise dimensions 1–6 against genuine automaton-plane material.

## Glossary

- **run-book form** — the Architecture's normative shape: strictly sequential steps, each an AST-allowlisted expression compiled once, invoking declared tools, zero inference inside, pinned to a shipped release, one run-book per `AutomatonRun` (glossary "Run-book", RunBook entity, `doc/automaton-executor-spec.md`).
- **normative definition** — the cited requirement a dimension is checked against: the glossary run-book entry, the RunBook entity (`schema.py`), `doc/automaton-executor-spec.md`, or a ratified DecisionRecord.
- **declaration-presence** — the DR-CMD-009 check regime, applied by pattern: the validator checks that a declaration exists and is cited, never its quality. Quality is disposition's judgment.
- **comparability threshold** — the admission bar: a procedure claiming the run-book form. Sequentiality alone does not pass. Below it, redirect; it is a gate, not a judgment.
- **candidate**, **dimension**, **admission**, **conforms / deviates / undefined-against** — operational terms defined in the implementation doc's glossary (`doc/eval-rb-implementation.md`, Glossary); used here in the same sense, not restated.
