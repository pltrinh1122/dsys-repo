# Design: `/eval-pb` — playbook validation against the Architecture's normative definition

**Status: ratified** — DR-CMD-015, 2026-09-20. Design reasoning for the `/eval-pb` validation routine. The normative procedure is `doc/eval-pb-implementation.md`; the operator-facing contract is `doc/slash-commands/eval-pb.md`. Per the standing principle, provenance and reasoning live here, not in the implementation doc.

## 1. What is being validated

The candidate is a *procedure claiming the playbook form*. The norm is not an exemplar document but the Architecture's definition: `doc/glossary.md` "Playbook (decision-making)" → `doc/dyad-architecture-doc.md` §8.2 (and §8.3 for records). This is why `/eval-pb` is semantic where `/eval-sc` is comparative: there is no standing exemplar playbook to diff against, only the definition's requirements. The division of labor between the two evaluators is deliberate: `/eval-sc` checks that a definition *binds* a procedure; `/eval-pb` checks the *bound thing* against the playbook definition. Neither validates the other's work.

## 2. The ten dimensions — design rationale

Dimensions 1–6 check *form*: the candidate must be definition-of-done conditionals, not a sequence (the operator's constraint: a playbook isn't a sequence but a set of definition-of-done conditionals); it must name admission and kill gates with failure routing; enumerate its disposition modes each with a DoD; separate proposer from disposer; write records only on disposition; and stay on its plane (a procedure the operator follows, sequencing left to run-books). Each dimension exists because its absence is a known failure mode of would-be playbooks: sequences that can't re-enter, gates that can't kill, modes without done-ness, self-disposition, mid-deliberation records, command-nodes.

Dimensions 7–10 check *declared evidence* (DR-CMD-009): exercise declared, trigger declared, output format specified, gates at G1 precision. The rationale is a decomposition of "reliable runtime execution" into three tiers: (a) form — dimensions 1–6; (b) declared evidence — dimensions 7–10, presence-checked only; (c) evidence-quality judgment — reserved to disposition (G5), never the validator's. The validator must not become an auditor: checking *that* a run is cited is mechanical enough to be honest; judging *whether the run was good* is disposition's work. The explicit residual risk: a candidate may cite a vacuous run and pass dimension 7. That risk is accepted, not closed — closing it would turn the validator into an integrity auditor, which is a different instrument.

The finding scale needs three values, not two, because the candidate may be playbook-adjacent: *undefined-against* records "this dimension does not apply to this candidate's kind" so inapplicable dimensions are stated, never silently skipped and never penalized.

## 3. Admission — why verify, not classify

Admission verifies the matter is actually a playbook candidate; it never classifies the matter into a taxonomy. The comparability threshold — a procedure claiming the playbook form, i.e. decision machinery (framing, options, gates, disposition) — is deliberately low-resolution: it is a gate, not a judgment. Below it, the redirect table (`/eval-rb` for run-books, `/eval-meta` for general matters) routes the matter to the instrument that can actually see it, rather than producing a vacuous report. A playbook-adjacent non-playbook is admitted but can only receive "not evaluable against the definition" — the honest verdict for incomplete shape, and the reason the overall scale has three values.

## 4. Report design

Per-dimension findings, each carrying one line of reasoning and at least one normative citation, because a bare verdict from a validator is uncheckable — the report must show its work or it is decoration. Deviations are reported, never repaired: repair is a mutation matter for `/pb-decide`, and a validator that rewrites its candidate has stopped validating. The byte-exact template exists so reports are comparable across runs; the pre-delivery checklist exists so the agent cannot ship a report with a missing dimension or an uncited deviation.

## 5. Character of the routine

`/eval-pb` is an evaluator, not a decider: it produces no disposition, writes no records, and its verdicts bind nothing. Deterministic replay holds in the weak sense — same candidate bytes, same procedure → same findings, modulo the judgment content, which is why every judgment carries its reasons and citations. The routine is sequential (parse → resolve → admit → validate → report) by design; that it would itself fail dimension 1 is not a defect but the point — it is not a playbook and does not claim the form.

## 6. Boundaries (retained)

From the contract: evaluation is not decision — no ratification, disposal, or recording; the disposition machinery is absent by declared design, which is why the worked self-evaluation (2026-09-20, in-chat) correctly returned "not evaluable against the definition". That run predates DR-CMD-009; dimensions 7–10 did not exist for it. The contract's Function section binds the implementation doc as of ratification (DR-CMD-015).

## 7. Provenance

Migrated from `doc/eval-pb-implementation.md` §8 (durable bullets only; the draft-state bullets — "written for operator disposition", the open binding item — are spent at disposition and die there):

- 2026-09-20 (authoring): the §1 usage line and the §2 `/name`-and-path resolution rule were newly specified in the implementation doc — the contract declares no pointer grammar — mirroring `/eval-sc`'s grammar. Flagged at authoring, not smuggled.
- 2026-09-20 (authoring): §4 operationalizes the contract's ten Check dimensions into per-dimension verdict rules, including DR-CMD-009's four declaration-presence dimensions as presence-only checks.
- 2026-09-20 (DR-CMD-010, ratified): the implementation→design reference edge is schema; this document is the counterpart the implementation doc names.

Note: the implementation doc's §8 remove-or-leave matter was disposed by DR-CMD-014 (section deleted); this section stands as the provenance home.

## G6 / open

- The Architecture's own §8.2 decision-making playbook cites no executed runs: under the ratified dimensions it fails dimension 7 (exercise declared) as it stands.
- Vacuous-run citation under dimension 7: accepted residual risk (see §2); unclosable without turning the validator into an auditor.
- Whether "not evaluable" verdicts should carry advisory repair hints: currently no — repair is mutation, routed to `/pb-decide`. Revisit if operators find the verdict unusable without hints.
- Worked examples are thin (one in-chat run); the implementation doc's example set should grow with real executions.
- ~~2026-09-20 (in-chat self-run `/eval-pb '/eval-pb'`): the implementation §2's blanket self-admission sentence ("/eval-pb's own documents are playbook-shaped") is falsified~~ — struck at ratification (DR-CMD-015): the cited sentence does not exist in the implementation doc; the agent misremembered the text. §3 as authored is well-formed, and the in-chat run's "refused" verdict was corrected per the §7 worked example (contract is playbook-adjacent → admitted → "not evaluable against the definition"). Kept as a struck record so the error is not reintroduced.

## Glossary

- **playbook form** — the Architecture's normative shape: definition-of-done conditionals (entry trigger + exit condition, condition-triggered, re-entrant), not ordered steps (glossary "Playbook (decision-making)", §8.2, I-4).
- **normative definition** — the cited requirement a dimension is checked against: the glossary playbook entry, `doc/dyad-architecture-doc.md` §8.2/§8.3, or a ratified DecisionRecord.
- **declaration-presence** — the DR-CMD-009 check regime: the validator checks that a declaration exists and is cited, never its quality. Quality is disposition's judgment.
- **comparability threshold** — the admission bar: a procedure claiming the playbook form (decision machinery). Below it, redirect; it is a gate, not a judgment.
- **candidate**, **dimension**, **admission**, **conforms / deviates / undefined-against** — operational terms defined in the implementation doc's glossary (`doc/eval-pb-implementation.md`, Glossary); used here in the same sense, not restated.
