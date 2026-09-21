# Design: `/pb-extend` — feature-expansion staging and evaluation

**Status:** ratified 2026-09-20 (DR-CMD-018; O3 — contract amended, then ratified). Design reasoning for the `/pb-extend` staging-and-evaluation routine. The normative procedure is `doc/pb-extend-implementation.md`; the operator-facing contract is `doc/slash-commands/pb-extend.md`; the playbook the procedure runs is `doc/feature-expansion-playbook-spec.md` (DRAFT — pending adoption). Per the standing principle, provenance and reasoning live here, not in the implementation doc.

## 1. What is being staged

The candidate is a *proposed addition to what dsys is* — a capability, mechanism, or surface dsys should gain. The division of labor is deliberate: `/pb-decide` handles general decisions through §8.2; the dsys-mutation playbook handles mutations of existing rungs (ladder configure|role|scenario|wrap|patch|fork); `/pb-extend` handles *additions*. An expansion is none of the other two: it is not a decision about existing things, and it is not a change to a rung — it is a new thing. The admission threshold (§3 of the implementation) exists because these three get confused in practice: a "new CLI flag" is a rung mutation wearing an expansion's clothes, and a "should we adopt X" is a general decision. The redirect table routes each to the instrument that can actually see it; the agent verifies the branch, never classifies the matter into a taxonomy.

## 2. The scope discriminator — design rationale

The load-bearing design decision is the scope split, and the split's test: *does the change alter what the machine guarantees?* The core's guarantees — deterministic replay, zero inference in execution, hermeticity, checkability — are the load-bearing walls; the package (dsys-repo: CLI surface, installer, roles, docs, packaging) is scaffolding and surface. The test is deliberately about *guarantees*, not about *files touched*: a `doc/` change that redefines replay semantics is runtime-scope by this test even though it lives in the repo, and the pre-registered falsifier F-E2 exists precisely because a package change (an installer default, a config default) can alter runtime behavior — the P/R split marks risk domains, not a firewall. That is why A3 (plane discipline) applies to both scopes: the split organizes scrutiny, it does not exempt the package side from core-risk thinking.

Decomposition with conjunctive adoption (§2 of the spec) is the honest answer to dual-scope matters: the "updater" seed matter is the standing example — release acquisition and installer integration are package work, while an upgrade-managing automaton is runtime work with self-modification trust implications. Letting either half adopt alone would let delivery-vehicle convenience pull core-risk changes through the weaker gate set. Scope creep → STOP exists because the most dangerous expansions are the ones that start package and grow runtime tendrils mid-matter.

## 3. The adoption conditionals — design rationale

The conditionals decompose into three tiers with the same presence-only discipline as DR-CMD-009 (the validator checks that the declaration exists and is cited; quality is disposition's judgment):

- **Shared (A1–A5)** — the expansion-independent bar: falsification survived (A1; waivable by the operator with reason recorded — waiver declared, not hidden, because silent waivers are how guarantees die); ontology justified (A2; synonym proliferation is the slow rot of a growing system); plane discipline (A3; the automaton's hardest boundary, restated at every gate); spec before build (A4; the playbook evaluates specifications, not code drops — X3 refuses implementations that arrive without one); evidence, not assertion (A5; acceptance as checkable sequences — validators, golden runs, transcripts).
- **Package (P1–P4)** — the surface bar: interface consistency against DR-CLI-001 (P1; the CLI tree's shape is a decided matter, not a per-expansion choice); hermeticity preserved (P2; offline install is a property, not a hope); docs converge (P3; docs lagging code is how the project and the product diverge); installability (P4; `install.sh` converges the surface, `doctor` covers it, idempotency sequences hold).
- **Runtime (R1–R5)** — the core bar, ordered by severity: deterministic replay preserved (R1; a runtime matter that cannot state its replay story is killed at START — X2 — because no replay story means no runtime change, full stop); golden run extended *including refusal cases* (R2; expansions must prove they refuse, not just that they work); validators for new invariants (R3; predicates, not procedures); zero inference in execution (R4; the v1 hard requirement, restated); trust declared (R5; declared trust, boundaries named — smuggled trust is the failure mode).

The same residual risk as the eval commands is accepted: a matter may cite thin evidence and pass a conditional's presence check. Closing it would turn the staging routine into an auditor, which is a different instrument.

## 4. Rehearsal vs governed — design rationale

The playbook is DRAFT and unadopted, but the command exists and is invoked — so the implementation defines two regimes, and the report always states which ran. Rehearsal is not a weaker playbook; it is the *same* procedure with enforcement suspended: stage, scope, evaluate, draft — reported, never gated, decided, or recorded. The would-kill finding is the mechanism that keeps rehearsal honest: a gate that would fire in governed mode is named with its citation, so the rehearsal report shows exactly where the governed run would have stopped. This is why the mode line is byte-exact in the template — a report without its regime stated is uncheckable.

The bootstrap circle (spec §10) is real and is broken the only way it can be: the operator's adoption disposition. The playbook's own adoption is a package-scope matter; its START, falsification (`/eval-pb`), and disposition are the rehearsal the draft prescribes for itself. A chat response is not authority, and neither is a draft citing itself.

## 5. Character of the routine

`/pb-extend` is a playbook command, not an evaluator and not a decider: it stages and evaluates against the playbook's conditionals, drafts a verdict, and stops. It produces no disposition, writes no records, and its verdicts bind nothing — adoption is the operator's act through the shared disposition machinery (one machinery, not forked: spec §7's reasoned answer to the earlier `/meta-eval` deviation about a local disposition-mode table — expansion adoption is a species of decision, and a second mode table would split the authority record). Deterministic replay holds in the weak sense — same matter bytes, same procedure → same findings, modulo the judgment content, which is why every judgment carries its reasons and cited evidence. The routine lives in the ambient layer by declared design (contract Boundaries): it stages expansions; it does not execute them.

## 6. Boundaries (retained)

From the contract: the command executes in the ambient layer only — never installed, never on the dsys CLI tree, never invokable by the automaton executor; until the playbook is adopted, rehearsal only (staging, scoping, conditional evaluation, draft verdicts — no gating, deciding, or recording); proposer ≠ disposer holds throughout — the ambient never proposes an expansion on its own authority, and never records one; evaluation is not decision.

## 7. Provenance

Authoring notes (durable; draft-state notes die at disposition):

- 2026-09-20 (authoring): the triplet was completed on the ratified `/eval-pb`→`/eval-rb` pattern at operator direction ("complete design, contract, and implementation of slash-command '/pb-extend'"). Implementation (`doc/pb-extend-implementation.md`) and design (this doc) authored as DRAFTs for disposition; contract rebound from the playbook spec to the implementation doc per DR-CMD-006 (bind-don't-restate), keeping the spec as the normative playbook the procedure runs.
- 2026-09-20 (authoring): the rehearsal/governed regime split and the would-kill finding were newly specified in the implementation doc — the contract declares rehearsal behavior but no regime mechanics. Flagged at authoring, not smuggled.
- 2026-09-20 (authoring): §2 of the implementation declares no pointer grammar (`/name`, paths) — the contract's trigger supplies the matter as chat text, and the implementation does not invent resolution machinery the contract doesn't declare. Flagged, not smuggled.
- 2026-09-20 (authoring): the worked staging example (seed matter, spec §8 illustration) is carried as illustration only — proposed, never evaluated, never disposed.
- 2026-09-20 (DR-CMD-010, ratified): the implementation→design reference edge is schema; this document is the counterpart the implementation doc names.
- 2026-09-20 (ratification, DR-CMD-018): O3 ratified — the contract's Procedure bullet was amended to declare the implementation doc's authored-as-DRAFT-for-disposition history alongside the playbook spec's still-pending DRAFT, then the triplet (contract, implementation, design) was ratified. The playbook spec's adoption remains a separate disposition (spec §10 bootstrap); the command runs in rehearsal until then.

## G6 / open

- The earlier `/meta-eval` deviation (no local disposition-mode table vs §8.2's per-decision mode-specific DoD): answered in spec §7 (reasoned: no fork — expansion adoption is a species of decision; a second mode table would split the authority record). Whether the answer satisfies is the operator's judgment at the spec's adoption disposition — carried open until then.
- Pre-registered falsifiers F-E1–F-E4 (spec §11): carried — scope decomposition always possible; package changes can't break determinism; the conditional set is complete; every matter assigns cleanly to package|runtime. Each has its falsifier stated.
- No expansion has run the procedure yet (the worked example is a staging illustration, not an evaluation) — the first real matter will exercise the conditional set against genuine material.
- Rehearsal would-kill vs refuse: in rehearsal, fired gates are reported, not enforced. If the operator wants rehearsal to refuse malformed matters outright (closer to governed), that is a disposition-level change to the regime, not an agent judgment call.
- The spec itself remains DRAFT pending adoption — the regime the command runs under. These two docs are the command's triplet; the playbook's adoption is a separate disposition (spec §10 bootstrap).

## Glossary

- **feature expansion** — a proposed addition to what dsys is: a new capability, mechanism, or surface dsys should gain. Not a rung mutation, not a general decision.
- **scope** — package (dsys-repo: the delivery vehicle and operator surface) or runtime (the deterministic core: what the machine guarantees).
- **discriminating test** — "does the change alter what the machine guarantees?" Yes → runtime; no → package.
- **decomposition** — splitting a dual-scope matter at START into two scoped matters proceeding independently.
- **conjunctive adoption** — neither decomposed matter adopted until both are.
- **staging** — the START entry work: claim framed, scope assigned, proposer named, prior art cited (S1–S4).
- **adoption conditional** — one check the KEEP evaluation runs: A1–A5 shared, P1–P4 package-scope, R1–R5 runtime-scope.
- **holds / fails / unevaluated** — the finding scale: holds and fails cite evidence; unevaluated means no evidence was cited (stated, never held).
- **rehearsal** — the current regime: the playbook is DRAFT and unadopted, so the command exercises it (stage, scope, evaluate, draft) without gating, deciding, or recording.
- **governed** — the regime after the playbook's adoption via disposition: STOP kills enforced, the KEEP verdict feeds the shared disposition machinery.
- **would-kill** — a rehearsal finding naming the gate or failure that would kill in governed mode, cited, not enforced.
- **draft verdict** — adopt / adopt-with-conditions / refuse: a recommendation; disposition is the operator's act.
- **X1 / X2 / X3** — the domain gates: scope kill, core-risk kill (no replay story), spec-first kill.
- **bootstrap circle** — the playbook's own adoption must run its own START, falsification, and disposition; broken only by the operator's adoption act.
