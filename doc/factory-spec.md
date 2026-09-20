# factory — spec

Status: specified 2026-09-20; stress-test amendments 2026-09-20
(F-FACT-6–F-FACT-9) in this revision. Falsification adjudicated
2026-09-20. Not implemented. Not ratified — ratification is a
disposition for Peter.

Matter: **how an automaton is authored and built.** The `factory` is the
authoring-and-building system that produces `automaton` — concretely,
AutomatonRelease candidates (run-books, flows, conditions, config) that
enter the automaton plane only through the existing promotion bridge
(AutomatonRelease / PromotionRecord). The ambient LLM-agent is the
primary surface for Operator prompts (goals and dispositions);
conversation is never authority.

## 1. Position in the architecture

The factory lives on the harness plane (judgmental, inference allowed)
with a deterministic core (build, verify). It is the governed "outside"
the architecture already names: all inference happens outside
execution, reaching the automaton only as discrete step-changes — the
factory is the machinery that *authors* those step-changes.

```
prompt ──► AuthoringTurn ──► Draft ──► VerificationResult ──► disposition ──► BuildRun ──► VerificationResult ──► authorize ──► PromotionRecord ──► AutomatonRelease
              (ambient          (inert,        (mechanical)      (DecisionRecord,   (pure,          (mechanical)      (hash-bound)       (existing         (existing
               proposes)         content-                        playbook=factory,  deterministic)                                     bridge)            entity)
                                 addressed)                      buildability)
```

The stage transitions are **definition-of-done conditionals, never a
sequence** (the playbook pattern): each gate states its DoD, and a
matter may stall, loop back, or die at any gate.

Drafts and builds are accretion-repo material (`var/`) — the authored
state of the installation, versioned by content hash.

## 2. Data entities

**FactoryProject** — the durable authoring context. `id` (uuid4),
`label` (human-readable, per the label decision — durable references
cite `id`), `principal_ref` (dyad-or-human; the dialog §16 principal
binding applies), `goal_text` (the operator's goal statement),
`lifecycle` (drafting | buildable | released | archived). Every draft,
turn, and build hangs off a project; a project with no drafts is just
an stated intent.

**AuthoringTurn** — one exchange with the ambient. `project_ref`,
gapless `seq` per project, `prompt_text` (operator; data, never
instruction — cf. R5), typed `inference_request` (propose | classify |
triage | assess | challenge | goal, per the dialog protocol's closed
enum), `response_ref`, `context_manifest` (DR-DIALOG-001 content-
addressed pins), optional `disposition_ref` (DecisionRecord, when the
turn carries authority). Turns reuse the dialog protocol's turn
structure and are write-gated: a turn alone creates nothing durable.

**Draft** — a candidate artifact, content-addressed (`id` = hash of
bytes). `kind` (runbook | flow | condition | config | scenario |
policy), `parent_refs` (what it revises), `turn_ref` (the authoring
turn that produced it), `reason` + `reason_status` (accepted | pending
— the mutation reason classification generalizes: every authored
change states its reason; unevidenced-but-authorized is `pending`,
marked as resting on authority alone), `touches_trust_boundary`
(bool — mirrors the mutation playbook's flag; set when the draft
modifies the §8 trust base, triggering the amendment procedure).
Kinds are tagged compiled vs. carried (§7): runbook | flow |
condition are compiled; policy (standing policies, role prompts,
playbook prose) is carried; config | scenario are mixed.
Drafts are **inert by construction**: quarantine as a data property,
not a location. Nothing about a draft is trusted; everything about it
is checkable.

**BuildRun** — deterministic *derivation* (compile, seal, package)
of drafts into a release candidate. `project_ref`, input draft refs
(+ hashes), `toolchain` version, output bytes hash,
`derivation_manifest_ref`, `receipt_refs` (RunnerReceipts cited —
possibly several under diversity; see `runner-spec.md`). A pure
function: same inputs + same toolchain = same bytes. No inference
backend, no network, no clock — the hermeticity story extended to
authoring. I-F2 is a *measured* property: the receipt attests the
hermeticity conditions held (C-4), on top of the empirical
double-derive check — declared trust all the way down, never
sandbox-proven.
BuildRun is derivation, not implementation: it crosses no
representation gap requiring judgment, and an implementation in
factory terms is a Draft (glossary — falsified 2026-09-20).

**VerificationResult** — mechanical checks against a draft or a build
(see §6, the verification triad). `subject_ref` (draft or build
hash), per-check pass/fail with the refusal cases or violations
cited. Deterministic re-checking, never inference.

**FactoryDisposition** — the shared DecisionRecord with
`playbook=factory` (third playbook on the single disposition
machinery; playbooks proliferate, disposition doesn't). All five
modes available; `authorize` is hash-bound (§5). `reason` required,
same as mutation.

## 3. Process entities — and the collapsed one

F-FACT-4 falsified the need for a separate authoring-run entity.
Authoring is an exercise of dyad authority aimed at DoD conditionals —
that is a **HarnessRun under a factory standing-policy domain**, not a
new entity. "Drafts awaiting disposition" are structurally open
disclosures, so the disclosure/triage machinery transfers; the five
disposition modes transfer unchanged. Two specified deltas, no new
entity:

- (a) Authoring runs under authority-scope `governance` — no new
  scope — which serializes authoring against governance drain. This is
  consistent with the architecture's structural seriality, not a new
  restriction.
- (b) The closure bar needs an authoring analogue of I-13: no
  authoring run closes with un-dispositioned drafts, or they persist
  explicitly as project state. **Decision pending** (G6, §12).

The "session" is a view over a project's turns, not an entity.

**Promotion** is the existing PromotionRecord, unchanged — the
factory's terminal step.

## 4. Stage gates (DoD conditionals)

- **Authored.** DoD: draft exists, content-addressed, cites its turn
  and parents, states its reason. Nothing else required — a bad draft
  is allowed to exist; it is not allowed to proceed.
- **Verified (draft).** DoD: VerificationResult on the draft passes
  the triad (§6). Failure routes to STOP (revise or kill the draft).
- **Buildable.** DoD: draft-level disposition (ratify/authorize)
  permitting derivation, *and* the factory has assembled the
  hermetic input closure (DerivationManifest: every derivation input
  declared, content-addressed) with no deferred judgment —
  "to be decided at build time" is a buildability violation (C-1,
  C-2). This is permission to *derive*, not to release.
- **Built.** DoD: the runner returns a passing RunnerReceipt —
  double-derive hashes match, seal attested (R-1, R-3). A cache hit
  satisfies this gate by citing the original receipt (R-5, C-5):
  rebuilding identical inputs is idempotent by input hash.
- **Verified (build).** DoD: VerificationResult on the build bytes
  passes (validators + golden-run replay over the compiled artifact).
- **Promotable.** DoD: build-level `authorize` binding the exact build
  hash and citing the build's VerificationResult (§5).
- **Promoted.** DoD: PromotionRecord minted; AutomatonRelease enters
  the automaton plane. Terminal.

Carried artifacts (§7) take the collapsed path through these gates:
authored → built (build = identity, input hash == output hash checked
mechanically) → promotable (intent-only authorize). Syntax/behavior
layers are recorded N/A *by kind* — distinct from *abstained*, which
is a failed precondition on a compiled artifact (§6).

## 5. Two-stage authorization (from F-FACT-2)

"Authorizing a draft authorizes the release" was falsified:
draft→build is a byte-changing transformation, and drafts can be
amended after authorization. Hence:

- Draft-level dispositions govern **buildability**.
- Build-level `authorize` governs **promotability**, and must bind
  the exact build hash **and** cite the VerificationResult it relied
  on. A draft changed after draft-authorize voids buildability; a
  build changed (rebuilt) after build-authorize voids promotability
  (I-F3).

Carried artifacts pass through both gates uniformly; the build gate
is trivially satisfied (identity, hash equality checked). Pipeline
uniformity is worth more than skipping a trivial step — and I-F3
still binds the hash.

## 6. The verification triad (from F-FACT-5; amended F-FACT-6, F-FACT-7)

The ambient is never trusted to write; each layer catches what the
others can't. Applicability: compiled artifacts get the full triad;
mixed artifacts get it per grammar-bearing fragment (prose fragments
are intent-only); carried artifacts record syntax/behavior as N/A by
kind (§7).

- **Syntax** — the expression-language AST allowlist (+ compile-once):
  the artifact cannot smuggle execution-time inference past the
  grammar. Catches syntactic escape.
- **Behavior** — two sub-layers, explicitly bound (F-FACT-6):
  (i) structural validators — the package I-series (determinism,
  totality, FK integrity): universal properties no transcript replay
  can establish; (ii) golden-run replay against expected transcripts:
  the artifact does what it claims. Catches semantic wrongness the
  grammar can't see.
- **Intent** — the Operator's hash-bound authorize: the artifact is
  what was *meant*. The human judgment the other two layers
  deliberately don't encode.

**Expectation independence (F-FACT-7).** Golden expectations must be
operator-supplied or independently authored — a separate draft with
its own lineage (`turn_ref` distinct from the artifact's authoring
turn), or operator-authored directly. A behavior check run against
self-authored expectations is not run at all: the VerificationResult
records behavior=abstained (reason: self-authored expectations), and
promotion then requires the authorize disposition to explicitly
acknowledge the abstention (I-F6).

## 7. Artifact classes: compiled, carried, mixed (from F-FACT-9)

The triad and two-stage authorization assume derivation. Not all
draft kinds derive:

- **Compiled** (runbook | flow | condition) — grammar-bearing. Full
  triad, full two-stage authorization. This is the pipeline §§4–6
  describe unqualified.
- **Carried** (policy: standing policies, role prompts, playbook
  prose) — no grammar, no mechanical syntax or behavior layer. Build
  is identity. The pipeline collapses to: authored → built (hash
  equality checked) → promotable (intent-only authorize). What the
  factory still contributes over a chat log: content-addressing,
  turn lineage, reason classification, and a hash-bound authorize —
  auditability, honestly labeled, not verification.
- **Mixed** (config | scenario) — per-fragment: grammar-bearing
  fragments (expression-language guards, schema-conformant blocks)
  get the triad; prose fragments get intent-only. The
  VerificationResult records per-fragment applicability.

N/A-by-kind (carried, or prose fragments) is distinct from abstained
(§6): the former is a property of the artifact class, the latter a
failed precondition on a compiled artifact. Only abstention triggers
I-F6.

## 8. Trust boundary & amendment procedure (from F-FACT-8)

Harness specs span from content down to governance. The factory
defines its trust base explicitly — the fixed machinery the factory
itself runs on:

- the stage gates (§4) and their DoD conditionals;
- the verification triad machinery (§6): AST allowlist + compiler,
  structural validators, golden-run harness;
- the toolchain — a first-class versioned, pinnable artifact (C-3),
  not just a version string;
- the runner — the derivation executor, in the trust base by
  declaration (see `runner-spec.md`; a runner change is a
  trust-boundary change);
- the disposition machinery: DecisionRecord, the five modes, the CTA
  response grammar;
- the expression-language definition;
- the promotion bridge (AutomatonRelease / PromotionRecord).

Everything else — run-books, flows, conditions, configs, scenarios,
policies *above* this base — is content, and follows the normal
pipeline with no special procedure.

A draft with `touches_trust_boundary=true` modifies the trust base
and follows the **amendment procedure**:

1. **Self-amendment under current rules.** The draft is authorized
   under the *existing* machinery — the old rules govern the adoption
   of the new. No bootstrap paradox: amendment is constitutional, not
   circular.
2. **Declared governance impact.** The authorizing disposition states
   which guarantees are voided or changed (M2-style, cf. the mutation
   playbook's trust-boundary declaration).
3. **Verifier lineage.** The VerificationResult records which verifier
   version checked the draft. The circularity (new verifier checked
   by old verifier) is made visible, not hidden.
4. **No retroactive re-adjudication** (I-F8). Amended machinery
   governs subsequent matters only; in-flight matters complete under
   the machinery that opened them.

## 9. Invariants

- **I-F1 quarantine-by-construction.** No draft enters a build
  without a passing draft-level VerificationResult *and* a
  buildability disposition. Completeness, not truth — declared trust,
  like I-17.
- **I-F2 build purity.** BuildRun runs with no inference backend;
  determinism checked mechanically (derive twice, hashes match).
  Purity is a *measured* property: the RunnerReceipt attests the
  hermeticity conditions held (C-4) — declared trust, checkable via
  diversity, never sandbox-proven.
- **I-F9 failure determinism.** Derivation failure is deterministic
  information (same inputs → same failure). Retry only on attested
  environment faults (C-6).
- **I-F3 freshness.** Authorize binds the exact build hash and cites
  its VerificationResult; any change after authorization voids it.
- **I-F4 pending provenance.** A build whose drafts carry
  `reason_status=pending` may be built, but promotion requires an
  explicit overrule-mode disposition acknowledging the pending
  status. Authority is never laundered into evidence.
- **I-F5 lineage.** Every draft cites its turn; every build cites its
  drafts. Replay means audit-reconstruction, never re-execution.
- **I-F6 abstention acknowledgment.** No promotion on an abstained
  verification layer (F-FACT-7) without an explicit overrule-mode
  disposition naming the abstention. Generalizes I-F4's pattern:
  authority never launders a skipped check into a passed one.
- **I-F7 governance declaration.** A draft with
  `touches_trust_boundary=true` must declare the governed machinery
  it modifies and the verifier version that checked it; the
  authorizing disposition declares the governance impact (voided or
  changed guarantees).
- **I-F8 no retroactive re-adjudication.** Amended machinery governs
  subsequent matters only; in-flight matters complete under the
  machinery that opened them.

## 10. Pre-registered falsifiers (adjudicated 2026-09-20; stress-test F-FACT-6–F-FACT-9 added 2026-09-20)

- **F-FACT-1** "Factory output is inference-free." **FALSIFIED** as
  stated; decomposed. The build contributes no new inference but
  preserves the drafts' inferred content — "inference-free output"
  was never the requirement. Survivor: **authorship may be
  inferential; execution semantics must be mechanically provable
  deterministic** (AST allowlist + compile-once + validators at the
  promotion gate). Residual: build purity by construction + double-
  build check, not sandbox-proven.
- **F-FACT-2** "Authorizing a draft authorizes the release."
  **FALSIFIED**; produced the two-stage authorization (§5).
- **F-FACT-3** "Conversational authoring is reproducible."
  **FALSIFIED** as re-execution; **SURVIVES** narrowed as
  audit-reconstruction (content-addressed drafts + turn lineage +
  context pins), modulo the inherited context-GC gap (G6).
- **F-FACT-4** "AuthoringSession needs its own entity."
  **FALSIFIED**; collapsed into HarnessRun under a factory
  standing-policy domain (§3).
- **F-FACT-5** "The ambient can be trusted to write conditions."
  **FALSIFIED** doubly: outputs are verified, never trusted, and the
  ambient cannot write at all (`decide` excluded; publication is the
  Operator's act). Produced the verification triad (§6).
- **F-FACT-6** "Transcript replay suffices for flow verification."
  **FALSIFIED** — determinism/totality are universal over the
  transition set; no finite replay establishes them. The behavior
  layer now binds structural validators explicitly, separate from
  transcript replay (§6).
- **F-FACT-7** "The ambient may author a draft's own golden
  expectations." **FALSIFIED** as usable verification — self-grading
  voids the behavior layer. Expectations require independent lineage;
  self-authored expectations → behavior abstained → promotion needs
  explicit acknowledgment (I-F6).
- **F-FACT-8** "The factory authors harness governance specs with no
  special procedure." **FALSIFIED** — below the trust base,
  verification goes circular. Trust boundary + amendment procedure
  specified (§8); content above the boundary unaffected.
- **F-FACT-9** "The triad applies uniformly to all draft kinds."
  **FALSIFIED** — compiled/carried/mixed distinction (§7); carried
  artifacts take the collapsed pipeline (lineage + intent), honestly
  labeled as auditability, not verification.

## 11. Relation to existing machinery

- **Decision-making playbook** — the generalized pattern the factory
  instantiates: DoD conditionals, START/STOP/KEEP, the five
  disposition modes, the single DecisionRecord.
- **dsys-mutation-playbook** — contributes the reason classification
  (`reason` + `reason_status`, accepted | pending) and the
  `touches_trust_boundary` flag pattern, mirrored on Draft; the
  factory is where reasoned authorship happens *before* anything
  exists to mutate.
- **Dialog protocol** — contributes the turn structure, the typed
  request enum, write-gated authority, the CTA response grammar
  (dispositions enter as yes/no/counter, not freeform), and
  DR-DIALOG-001 context transport.
- **Promotion bridge** — AutomatonRelease / PromotionRecord are
  reused unchanged; the factory never mints releases, only
  candidates.

## 12. Open decisions (G6)

1. **Authoring closure bar** (§3b): I-13 analogue for drafts, or
   explicit persistence as project state.
2. **Context GC**: the factory inherits the dialog protocol's
   un-designed garbage collection; audit-reconstruction degrades if
   context blobs are reaped. Surface-not-reap is the standing bias.
3. **Ratification**: this spec is specified, not ratified.
