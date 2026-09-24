# Open-source agentic systems vs. the dsys Architecture — holistic evaluation

**Status:** Working evaluation summary (not a DecisionRecord; no disposition taken).
**Date:** 2026-09-23.
**Question:** Can an available open-source agentic system implement the dsys Architecture, in whole or in part, rather than us building it from scratch?
**Method:** Web research (grounded in the production-tools spec, updater spec, agent-CLI packaging spec, and dialog protocol spec; licenses verified against primary sources) followed by a falsification dialectic on the harness-plane claims.

## 0. Final conclusion — LangGraph vs. the dsys Architecture (Harness + Automaton)

**Shared outcome, opposite theories.** Both want agents to reliably deliver on an Operator disposition. They disagree on *how* reliability is achieved — and the disagreement reduces to one architectural decision: whether deliberation and execution share a plane.

- **LangGraph: single-plane, model-driven.** Deliberation and execution interleaved in one loop; the model evaluates the loop condition (`while <model wants to continue>`); the operator is backstop (interrupt as veto). Theory: reliability through capable adaptivity + human veto. A complete agent-orchestration toolkit; for governed human workflows, an incomplete governance platform — oversight (visibility, veto, snapshots) without governance (no authorization model, no attribution record, no deterministic proof).
- **dsys Architecture: two-plane, disposition-driven.** The Harness (deliberation — inference as bounded participant, never governor) and the Automaton (execution — zero inference, declared steps, deterministic replay). Theory: reliability through declared scope + dispositional control + determinism. Design intent: not to constrain creativity for problem solving, but to constrain the solution space to eliminate unnecessary wandering.

**Design-intent asymmetry.** LangGraph was designed for *agent applications* — assistants, copilots, research agents — where the model drives and the operator backstops. Governance was never its design problem; its "incompleteness" for governed workflows is domain-relative, not a design failure. The dsys Architecture was designed *specifically* for governed human workflows — business workflows where authorization, attribution, and proof-grade auditability are requirements, not nice-to-haves. The comparison is therefore not "our design beats theirs at their game" but "different design problems": each is complete for its own problem and misapplied to the other's. The nested-adoption framing is the one place the two problems overlap — governed deliberation inside a governed system.

**Five precise points of non-interchangeability:** (1) who evaluates the loop condition — model vs structure; (2) who authors disposition — model per-action vs operator per-action or in-advance (the (model,·) cell is structurally empty in dsys; delegation is not model disposition); (3) disposition as point (single implied authority at invocation) vs structure (per-turn keys, ingress validators including the R5 prompt-as-data wall, transcript discipline); (4) transcript vs message log — validated record production vs transport; (5) contracted registry vs registered tools — the contract (idempotency, no-network, subprocess scope, declared arg mappings), not the registration, is the bound.

**The constructive result.** The only adoption framing that survives contact with the architecture is nested: a LangGraph-style model-driven inner loop *configured by the Harness* — Harness-chosen contracted tools, a per-invocation scope envelope, a typed-request exit gate, harness-plane only (R4) — with Harness-level per-turn configuration as the operator control (not LangGraph's interrupt hook, which intervenes in the model's context rather than the control plane). This gives adaptivity where it belongs (deliberation) and keeps constraint where it belongs (execution): the architecture already contains both theories of reliability, assigned to planes.

**Boundary condition.** The two-plane model earns its complexity where the cost of an *unaccountable* action exceeds the cost of *formalization*. Where formalization costs more than any plausible harm, the single-plane loop is the right tool. The extra machinery's function is converting silent failures into loud, attributable ones — mechanism failures scale with machinery (conceded cost), but governed failures are more numerous, unnamed, in the single-plane design.

## 1. Headline finding

No open-source system implements the Architecture. The serious adopt candidates are **durable-execution engines**, not LLM agent frameworks — and even there, adoption covers only the executor's plumbing (journaling, crash recovery, timers), never the governance. Roughly 70–80% of the Architecture's distinctive content (dispositions, DecisionRecords, strapped driver, referee, pinned registry, hash-chained accretion, disclosure, guard language) has no open-source counterpart and must be built regardless.

One correction to the initial research verdict, forced by the dialectic: the "LLM frameworks are a category error" finding holds for the **automaton plane** (R4 forbids inference in execution), but was over-broad — for the **harness plane** the adoption question is well-posed, because the Harness legitimately uses inference for control. The answer there is still thin (see §4), but the question was fair.

## 2. Ranked candidates

1. **DBOS Transact** (Python, MIT) — strongest adopt fit, for the run-book durability layer only. Workflows as annotated Python functions; completed steps journaled to Postgres and never re-executed (matches our idempotency contract); deterministic workflow bodies; durable timers (maps the updater's poll). Costs: Postgres dependency (fights the base-profile offline install) and the journal living outside the accretion repo (two-store problem).
2. **Temporal** (MIT) — semantically the purest match to the replay theory (append-only event history *is* the execution; replay-verification tooling), but a multi-service server cluster: disproportionate for a single-operator CLI. Revisit only at fleet scale.
3. **LangGraph** (MIT) — harness/dialog plane at most, never the automaton. Low value: the Harness is already specified and its de facto backend (the orchestrator's subagents) already is "a loop that calls the model."

Disqualified: Restate (BSL 1.1, not OSI open source), Windmill (AGPL-3.0), Cadence (dominated by Temporal; stale Python SDK), Hatchet (no deterministic replay story), Prefect (retries re-execute; replay is re-execution, not re-derivation), and all inference-loop-centric frameworks (CrewAI, AutoGen/Microsoft Agent Framework, OpenAI Agents SDK, Semantic Kernel, Google ADK, Strands, Smolagents, Haystack, LlamaIndex, MetaGPT, OpenHands) — none has deterministic replay, a determinism contract, or append-only journaling.

## 3. Build-vs-adopt per subsystem

| Subsystem | Verdict |
|---|---|
| Automaton executor + run-book stepping + crash recovery | Adopt (DBOS) or build — a *migration* question; the executor already exists (DR-CMD-054) |
| Replay derivation + validators (R1, I-14/15/16, I-18/19/20, I-31) | Build — no engine derives our state sequence or checks its hash |
| The eight production tools | Build — dsys-specific system interfaces; built under DR-CMD-057 |
| Accretion (hash-chained commits, canonical payload, watermark, D3 identity) | Build — novel; git-backed |
| Disposition / DecisionRecord machinery, pb playbooks | Build — governed process, zero candidates |
| Strapped driver, referee mode, trust boundaries, role bundles | Build — our authority architecture |
| Pinned registry + I-31, release pinning | Build |
| Disclosure surface (DR-5) | Build (trivial) |
| Guard expression language (AST-allowlisted) | Build (thin layer atop any engine) |
| Harness / dialog inference plane | Build (or LangGraph-hosted turn loop — see §4; low value) |
| CLI, installer, doctor, base\|full profiles, offline install | Build — partially done |

## 4. Harness-plane dialectic — the nuanced differences

The following survived a falsification pass (claims decomposed to F-items; killed/narrowed/holding recorded). They are the durable content of the evaluation.

### 4.1 Bounded inference (enumerated actions)

Claim: *bounded inference meets the spirit of the Harness.* **Narrowed.** Bounded-to-enumerated outputs is *necessary* — and the Harness already embodies it in the closed request enum {propose, classify, triage, assess, challenge} + goal. But it is not *sufficient*: the Harness's spirit further requires the R5 prompt-as-data wall, issuance validators, strap gates, authority precedence, and the three-key disposition pipeline. LangGraph conditional edges are bounded inference too and carry none of these properties. The selection mechanism (pick from an enum) is genuinely shared; the authority structure around the pick is not: framework = the pick executes (approval optional); Harness = the pick is a request entering a keyed pipeline.

### 4.2 The six blocking mechanisms (LangGraph as Harness)

1. **Prompts are the instruction channel.** The framework's control mechanism *is* instruction-following (ReAct-style system prompts). Our R5 requires prompt_text to be data, never instruction. Strip instruction-following and what remains is a graph runner.
2. **Tool calls execute on model authority.** `ToolNode` runs the model's `tool_calls`; human-in-the-loop is `interrupt()` (pause/approve/resume). Our write path is a three-key pipeline where the model never proposes writes at all — only result-only classifications.
3. **Conditional edges route on raw model output.** No issuance-validator gate (R1–R5, closed enum, principal binding) between model output and its effect.
4. **Checkpointing is state snapshots, not transcripts.** Mutable state dict for resume/time-travel; nothing like citable transcripts by request_id, 3-valued thread state, or a monotonic disclosure sequence.
5. **Single-approver interrupts.** One human per thread approving a paused action; no counterpart to authority precedence (fleet_wins/local_wins + local vetoes) or the authorization-only freeform channel.
6. **No closed request type system.** Message types, not request types; the enum + validators are the Harness's core and have no analogue.

**The wrapper argument.** Nothing physically prevents wrapping — the problem is what survives it: suppress mechanisms 1–3 (the framework's actual value), bypass 4, reimplement 5 plus the enum, validators, strap gates, and disposition pipeline from scratch. The wrapper ends up thicker than the wrapped, and fights the framework the whole way, because every framework default points toward model authority while the wrapper points away. The deeper issue is **loop ownership**: the framework's loop is model-driven, ours is disposition-driven; both can't own it. The "wrapper" resolves to either the real architecture with a vestigial framework inside, or the framework with our properties bolted on and unenforced.

### 4.3 LangGraph as transcription engine

Claim: *LangGraph is equivalent to our transcription engine in front of the Harness.* **Killed.**
- **F1 (artifact):** LangGraph produces a *message log* (freeform content + tool calls); our transcription is *validated record production* (R1–R5 at issuance, closed enum, request_ids, result-only). Transport is not transcription; if the Harness must validate and re-shape the log, LangGraph didn't transcribe.
- **F2 (ordering):** R1–R5 are *issuance* validators — they run before the model is invoked. A framework "in front" invokes the model before the Harness sees the exchange: backwards. Fixing the order means the Harness interposes on every model call, i.e. owns the loop; LangGraph becomes a subroutine.
- **F3 (record shape):** message log is model-shaped, transcript is request-shaped; conversion is custom and lossy in the wrong direction (stripping exactly what the framework produced).
- **F4 (gap):** our transcription engine is already specified (file transport with atomic rename + orphan-surfacing, validator wall, transcript minting) and thinner than the framework. No gap to fill.

### 4.4 Multimodal inputs — genuine requirement, wrong supplier

The observation that dialog inputs exceed text (images, audio, video) identifies a **real gap**: our transport spec is text-leaning and has no blob story. But it doesn't help LangGraph's case:
- The framework's multimodal support is content-block plumbing to the provider SDK; the model does the work. Our transport can carry the same payload as content-hash-addressed blob references. Trivially replicable.
- Multimodal **strengthens the case against** the framework: images are a known instruction-injection vector, so the R5 wall matters *more* on the multimodal path — which the framework passes straight into the instructing message.
- The hard part — transcript discipline for blobs (canonical form, content-hash URI addressing, citability, retention) — is unsolved by the framework and must be designed by us regardless.

**Recorded gap:** the dialog protocol needs a blob-attachment convention (canonical bytes, content-hash URIs, mime discipline). Our architecture work, not framework work.

### 4.5 Implied authority disposition — point vs. structure

In LangGraph's native flow, the Operator prompt is intent *plus implied authority disposition for the whole run*: one act authorizes every tool the model may choose, every step it may take, and every resumption after a crash (the checkpointer resumes under the original implied authority — disposition is never re-established because it never lapsed). Authority is **ambient** after invocation.

Our disposition is a **structure**, not a point: re-established at prompt ingress (issuance validators + R5 wall), at tool execution (write-disposition key), and at record minting (transcript discipline). The diagram makes visible exactly one place where LangGraph checks authority — the start — and it's checked by the act of starting.

### 4.6 Our loop vs. the while-loop

The ReAct while-loop and our loops are shaped similarly (iterate until done) but the authority is inverted. The whole difference is **who evaluates the loop condition**: the while-loop runs `while <model wants to continue>` — the controlled thing is also the governor. Ours run `for step in <declared steps>` (automaton) and `while <keys incomplete>` (harness) — the governor is the structure; the model, where present, is an input, never the governor. LangGraph's contribution over the hand-rolled loop was everything *around* the loop condition (durability, observability, composition) without ever changing *who evaluates it*. Our architecture changes the governor and keeps the plumbing deliberately thin.

### 4.7 What we give up — the autonomy/accountability trade

Not supporting `while <model wants to continue>` forfeits, in every case a form of *autonomy* (the model's freedom to decide next):
1. **Model-judged completion** — "keep going until you think it's done."
2. **Runtime invention of steps** — the run growing a step the author didn't declare.
3. **Autonomous error recovery** — the model reading a tool error and trying another way (the while-loop's genuine superpower).
4. **Opportunistic pursuit** — following serendipitous findings; no undeclared pursuits.
5. **Zero-formalization tasking** — "just go do the thing"; everything here must be declared or formalized first.
6. **Vague-goal execution** — executing directly on vague intent; our Harness converts vague to formal first, and the conversion is the work.

The mirror: the while-loop gives up knowing what it will do before it does it, reproducing what it did, and attributing each effect to an authorization. **Boundary condition:** our model is worth it where the cost of an *unaccountable* action exceeds the cost of *formalization* (release promotion, installer execution, dispositional records). Where formalization costs more than any plausible harm (drafting an email, casual exploration), the while-loop is the right tool. The architecture doesn't claim the while-loop is never useful; it claims there's a class of execution where model-governed continuation is disqualified, and that class is what dsys is for.

### 4.8 CoS-level plan adjustment — governed, not autonomous, adaptivity

Claim: *we support plan adjustment at the CoS level, which controls routing.* **Holds, with two qualifiers.**
- Plan adjustment exists (step-changes: new versions, injected events, config updates; STOP/START/KEEP dispositions; the mutation playbook) and lives at the CoS level — the automaton never adjusts itself; all adjustment arrives from outside through the CoS-run disposition machinery (DR-1).
- **Level qualifier on "routing":** CoS controls *run/matter-level* routing (which run-book or playbook is STARTed, STOPped, KEPT). It does not control *step-level* routing within a run (fixed by spec; deterministic transitions, I-15).
- This recovers **governed adaptivity**, not autonomous adaptivity: coarse-grained (whole runs), slow (disposition cycle, not next-turn), non-autonomous (CoS proposes, Operator disposes). It softens the "runtime invention of steps" gap *across* runs while it stands *within* a run. Per-turn self-healing remains disqualified — which is the point, not an oversight.

### 4.9 Disposition: author × timing grid — delegation is not disposition

Claim: *LangGraph defaults to model-inference disposition with operator interrupt; we default to Operator disposition and can also support model-inference disposition.* **F3 killed**; the symmetry is false. The actual space:

| author \ timing | per-action | in advance |
|---|---|---|
| model | LangGraph default (emission = execution) | — (structurally empty for us) |
| operator | our default (three-key pipeline) | standing dispositions, `auto` policy, interaction preferences |

LangGraph: model disposes per-action, operator vetoes per-action. Ours: operator disposes per-action, operator disposes in advance. Model-authorship of disposition is not a supported cell — it contradicts the three-verb anchor (disposition is the human's structural verb), §14 write-gated authority (the ambient never publishes), and the DecisionRecord requirement of explicit Operator disposition. What we *do* support is **advance Operator disposition via policy**: under an `auto` policy or standing disposition the model proceeds with no per-action operator involvement — but the author remains the Operator acting in advance, the bounds are the Operator's, the model cannot widen them, and the validator wall still stands between model output and effect, with every effect attributed to the prior Operator act. Delegation differs from model disposition in the *author*, not just the timing.

## 5. Open items

- **DBOS spike (optional):** port one run-book (`rb-release-check` + two tools) onto DBOS Transact to measure the Postgres/base-profile friction before any migration disposition. This is the only adoption with a positive expected return, and it's a migration question, not greenfield.
- **Blob-attachment convention** for the dialog protocol (§4.4): canonical bytes, content-hash URI addressing, mime discipline, retention. Required before multimodal inputs are first-class.
- No disposition has been taken on any adoption; this summary records the evaluation only.

## Glossary

- **Automaton:** the deterministic execution plane. Zero inference inside; run-books are strictly sequential step sequences over a closed tool registry; deterministic replay (R1) is mandatory.
- **Harness:** the inference plane. Guided turns of human prompts + LLM responses aimed at definition-of-done conditions; inference is a bounded participant, never the governor; the Operator's disposition attaches to the inferencing.
- **CoS (chief-of-staff):** the role running the decision-making playbook (triage, dialectic, dispositions). At most one non-closed CoS run per (principal, authority-scope) (DR-1). Plan adjustment lives here, not in the automaton.
- **Run-book:** a finite-state-machine-style declared step sequence the automaton executes.
- **Disposition:** the authorizing act that makes an effect attributable. The human's structural verb (three-verb anchor: dsys issues/ingests/advances; the human authorizes/disposes; the ambient infers/stages/writes what was disposed).
- **DecisionRecord:** the recorded outcome of a disposition; requires explicit Operator disposition.
- **R1:** deterministic replay — re-derivation from the log, never re-invocation.
- **R4:** zero inference inside automaton execution.
- **R5:** the prompt-as-data wall — prompt_text is data, never instruction; no freeform instruction field in requests.
- **Strap/unstrap gates:** harness run-lifecycle gates controlling when inference may proceed.
- **Three-key pipeline:** a harness turn completes on three keys — issuance + process authorization + write disposition.
- **Write-gated authority:** the ambient never publishes; publication is the Operator's act through the ambient's hands.
- **Standing disposition:** an Operator disposition made in advance as policy for future cases (vs. per-action).
- **Accretion:** the append-only, hash-chained record of runs (accretion repo), with watermark-based commits.
- **I-31:** the pinned-registry predicate binding a run's recorded release version to the installed distribution's tool registry.
- **Implied authority disposition:** the LangGraph-native pattern where the Operator's prompt authorizes the entire downstream run ambiently.
- **Model-inference disposition:** a mode where the model's inference output is itself the authorizing act (LangGraph's default; structurally unsupported in dsys).
- **Transcription engine:** the machinery turning a dialog exchange into a validated, citable transcript (validator wall + transcript minting) — distinct from *transport* (moving messages), which is all a framework provides.
- **Bounded inference:** constraining model outputs to an enumerated set (necessary in the Harness, already embodied by the closed request enum; not sufficient for its authority properties).
