# D1–D7 Agent Compiler — Specification (Ratified 2026-09-26, DR-CMD-066)

## 0. Status

Ratified 2026-09-26 (Peter), DR-CMD-066. Step 3 of the ratified D1–D7
agent factory plan (DR-CMD-061).
**Specify only** — step 5 builds. It does not ratify the profile schema as a whole
(built-but-unratified), the C1–C5 couplings (still proposed), or the
step-2 substrate spec (still DRAFT).

Normative inputs: the profile schema and construction semantics in
`core/package/agent_behavior.py` (DR-CMD-062); the harness-native
substrate and runtime contract in `doc/d1-d7-agent-substrate-spec.md`
(DR-CMD-063); the ratified Q2 discriminator and the factory's own
flow-based pipeline (DR-CMD-064); pydantic-as-source for dsys-deployed
processes (DR-CMD-058); the bridge's B-1/B-2/B-3 template
(`doc/bridge-spec.md`).

Disambiguation: this "agent compiler" is not the `factory` of
`doc/factory-spec.md` — that factory authors *automaton* step-changes
(run-books, flows). This compiler builds *agents*: harness-plane
entities positioned in D1–D7.

## 1. Purpose

Define the deterministic, total, closed compiler: **profile → build
plan → agent**. The compiler takes a validated `AgentBehaviorProfile`
and produces a runnable harness-native agent occupying the profile's
position — the closed assembly of the substrate's seven components
(profile, backend binding, tool bindings, trigger wiring,
instrumentation, verifiers, actuation loop), invokable through a
Harness per AX1.

## 2. The compiler's own pipeline (specified as a flow)

Per DR-CMD-064 Decision 2, the factory's own build pipeline runs as
automaton flows. The compiler pipeline is specified here as the flow
`agent-compiler-flow`; step 5 authors it as pydantic sources per
DR-CMD-058 and bridges it to `AutomatonFlow` entities. Stating the
stages, named inputs/outputs, and guards now is what makes step 5
authoring mechanical.

States (all `task` kind unless noted), transitions guarded by
AST-allowlisted expressions over `payload.*`:

| State | In | Out | Guard to next |
|---|---|---|---|
| `ingesting` | `profile_bytes` | `profile`, `profile_hash` | parses as `AgentBehaviorProfile` |
| `validating` | `profile` | `violations[]` | `violations == []` — schema validators incl. derivations and C1–C5, C7 (C6 retired, DR-CMD-077); any violation → `failed` (loud, reason recorded) |
| `deriving` | `profile` | `derived_positions`, `position_vector` | derived == declared (D1/D3/D4/D5/D7); D2's recorded rule == profile's binary-enum `conflict_rule` (C6 retired, DR-CMD-077) |
| `planning` | `profile`, `derived_positions` | `build_plan` (§3) | plan complete: every profile facet mapped (§4 totality check) |
| `routing` | `build_plan` | `routing_table` (§5) | every write-scope channel resolves to a registered contracted tool (B-3 analog: unknown tool id → `failed`); every standing class and channel classified |
| `materializing` | `build_plan`, `routing_table` | `artifact_bytes`, hashes | canonical bytes; `plan_hash`, `artifact_hash` computed |
| `attesting` | `artifact_bytes` | `manifest` | manifest complete → `done` (`end`, outcome `completed`) |

End states: `done` (outcome `completed`); `failed` (outcome `aborted`)
on any refusal. A refusal is never downgraded to a warning: an invalid
profile, an unresolvable tool, or an unclassifiable action never
compiles.

Run-book structure (source; step-5 tools named, **new** — built in step
5): `rb-compiler-ingest` (`tool-parse-profile`), `rb-compiler-validate`
(`tool-run-validators`), `rb-compiler-derive` (`tool-derive-positions`),
`rb-compiler-plan` (`tool-emit-plan`), `rb-compiler-route`
(`tool-resolve-tools`, `tool-classify-actions`), `rb-compiler-materialize`
(`tool-canonicalize-artifact`), `rb-compiler-attest`
(`tool-mint-manifest`). Tool behavior is registered code (bridge §5:
naming is not defining); the flow declares structure only.

## 3. The build-plan schema (shared interface — defined ONCE here)

The build plan is the compiler's intermediate artifact and the
verifier's static input (`doc/d1-d7-verifier-spec.md` consumes it; it
does not redefine it). Pydantic v2, frozen models — the DR-CMD-058 pin.
Sketch (field names normative; step 5 finalizes types):

```python
class FactoryVersion(BaseModel):      # determinism scope (§6)
    model_config = ConfigDict(frozen=True)
    factory_release: str              # the factory's own release version
    schema_version: str               # agent_behavior module revision
    semantics_table_version: str      # construction-semantics table revision
    tool_registry_pin: str            # release tag + install-manifest hash
    probe_suite_version: str          # verifier's probe suite (static field here)

class BackendBindingPlan(BaseModel):  # D3 -> substrate component 2
    model_config = ConfigDict(frozen=True)
    temperature: float                # 0.0 iff deterministic_execution
    seed: int | None                  # set iff deterministic_execution
    model_pin: str                    # pinned model id; "unpinned" iff not deterministic
    wall_clock_dependent: bool        # False iff deterministic_execution

class ToolBindingsPlan(BaseModel):    # D5 -> substrate component 3
    model_config = ConfigDict(frozen=True)
    read_grants: list[str]            # from read_scope
    write_allowlist: list[str]        # contracted tool ids, registry-resolved

class TriggerWiringPlan(BaseModel):   # D6 -> substrate component 4 (per source)
    model_config = ConfigDict(frozen=True)
    source: str                       # operator | world | self
    listener: str                     # e.g. session-listener, webhook-allowlist, scheduler
    activation_gate: str              # from gating: may the trigger fire?
    authorization: str                # from authorization: stage-only | may-act ...

class InstrumentationPlan(BaseModel): # D4 -> substrate component 5
    model_config = ConfigDict(frozen=True)
    streams: list[str]                # subset of event | intent | verification
    inspectors: list[str]             # read grants on the log
    retention: str | None             # storage policy

class VerifierPlan(BaseModel):        # D7 -> substrate component 6 (per target)
    model_config = ConfigDict(frozen=True)
    target: str                       # intent | event | world | trigger
    placement: str                    # trust-boundary placement (§4 substrate spec)
    on_failure: str                   # fail_closed | fail_open | escalate

class RoutingEntry(BaseModel):        # Q2 -> actuation routing (§5)
    model_config = ConfigDict(frozen=True)
    action_class: str
    route: str                        # direct | workflow
    bound_tools: list[str]            # contracted tool ids this class binds

class StagingPlan(BaseModel):         # D1 actuation; Q3 RESOLVED (DR-CMD-065)
    model_config = ConfigDict(frozen=True)
    durability: str                   # accretion-backed, fixed; ephemeral defeated (see §7)

class ActuationPlan(BaseModel):       # D1 -> substrate component 7
    model_config = ConfigDict(frozen=True)
    loop: str                         # stage -> disposition -> execute
    per_event_disposition: bool
    standing_table: list[str]         # pre-authorized action-class rule entries
    feedback_loop: bool               # self_correction: bounded observe/compare/adjust
    planner: bool                     # self_planning: planner component
    routing: list[RoutingEntry]       # Q2 routing table
    staging: StagingPlan

class AgentBuildPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    agent: str
    profile_version: str
    profile_hash: str                 # sha256 of profile.canonical()
    factory_version: FactoryVersion
    derived_positions: dict[str, float | None]  # D1-D5, D7; D6 None
    backend_binding: BackendBindingPlan
    tool_bindings: ToolBindingsPlan
    trigger_wiring: list[TriggerWiringPlan]
    instrumentation: InstrumentationPlan
    verifiers: list[VerifierPlan]
    precedence_table: list[str]       # D2 principal_precedence
    tie_break: str                    # D2 conflict_rule: the binary enum
                                      # {principal_wins_ties, world_wins_ties}
    actuation: ActuationPlan
    plan_hash: str                    # sha256 of the canonical plan bytes
```

**The agent artifact** (the compiler's final output; the verifier's
input): `{plan: AgentBuildPlan, manifest: AgentArtifactManifest}` where
the manifest carries `{profile_hash, plan_hash, artifact_hash,
factory_version}`. The harness interprets the plan at invocation time;
the artifact contains no generated code and no behavior definitions —
structure only (bridge F2: naming is not defining).

Canonical bytes: sorted-keys compact JSON (the `canonical()` discipline
in `agent_behavior.py`, extended to the plan: sets sorted, e.g. D6
sources).

## 4. Facet-by-facet compilation (totality)

Each row is a compile rule the `planning` stage implements, following
the construction semantics in `agent_behavior.py`. The table is the
totality argument: every field of `AgentBehaviorProfile` appears in
exactly one rule; the `planning` guard asserts no facet is unmapped.

| Facet | Plan section | Compile rule |
|---|---|---|
| D1 `per_event_disposition` | `actuation.loop`, `actuation.per_event_disposition` | true → stage→await-disposition→execute with no bypass path emitted |
| D1 `standing_dispositions` | `actuation.standing_table` | each named class → rule entry {class, bound tools, arg templates, route} |
| D1 `self_correction` | `actuation.feedback_loop` | true → bounded observe/compare/adjust loop wired to the D7 verifiers |
| D1 `self_planning` | `actuation.planner` | true → planner component; its plans are staged per the D1 position |
| D2 `principal_precedence` | `precedence_table` | conflict precedence table, in listed order |
| D2 `conflict_rule` | `tie_break` | the binary enum {principal_wins_ties, world_wins_ties}: whose claims prevail on principal/world ties |
| D3 `deterministic_execution` | `backend_binding` | true → temperature 0.0, seed set, model pinned, `wall_clock_dependent=False` |
| D3 `replay_supported` | `instrumentation` (+ plan note) | true → event log + re-execution driver wiring recorded |
| D4 `records_events/intents/verifications` | `instrumentation.streams` | one stream per true facet |
| D4 `inspectors` | `instrumentation.inspectors` | read grants on the log |
| D4 `retention` | `instrumentation.retention` | storage policy verbatim |
| D5 `read_scope` | `tool_bindings.read_grants` | data-source grants verbatim |
| D5 `write_scope` | `tool_bindings.write_allowlist` | each channel → contracted tool id; **unknown id → compile refusal** (B-3 analog) |
| D6 `sources` | `trigger_wiring[]` | one wiring entry per source |
| D6 `gating[source]` | `trigger_wiring[].activation_gate` | verbatim (C4: present for every source) |
| D6 `authorization[source]` | `trigger_wiring[].authorization` | verbatim (C4: present for every source) |
| D7 `intent/event/world/trigger_target` | `verifiers[]` | one verifier component per true target, placed per substrate spec §4 |
| D7 `on_failure` | `verifiers[].on_failure` | fail_closed → halt+stage; fail_open → log+continue; escalate → stage for principal (C7 already enforced) |

## 5. Q2 routing (discriminator — edge wording finalized)

Ratified discriminator (DR-CMD-064): a *tool action* is exactly one
contracted-tool call with all arguments bound at disposition time; a
*governed workflow* is anything requiring intermediate observation,
guards between steps, or unit replay → automaton flow.

Finalized edge wording (G6 carried from the /pb-decide — this is the
disposition of that carried uncertainty):

- **"Bound at disposition time"** means bound from the union of: (a) the
  disposition record (per-event actions), (b) the standing-disposition
  rule and the activating trigger event (standing actions) — with **no
  dependence on the result of any prior tool call** and **no guard
  evaluated between calls**.
- **The discriminator counts effects**, i.e. invocations of
  contracted tools bound in `write_scope`. Read-only tool uses during
  inference (under `read_scope` grants) are not effects and are not
  routed — they are part of harness-plane inference.
- **Compile-time classification** (`routing` stage): each named
  standing-disposition class and each write-scope channel is classified.
  A class binding to exactly one effect tool with bindable arguments →
  `direct`. A class binding to multiple effect tools, or requiring
  inter-step guards → `workflow`.
- **Runtime classification** (emitted as the routing predicate, applied
  by the built agent per proposed action): a proposed action whose
  effect sequence is a single call satisfying the binding condition →
  `direct`; any longer sequence, any result-dependence, any inter-step
  guard → `workflow`.
- **Workflow path at runtime:** the built agent drafts the
  `AutomatonSource` (pydantic, DR-CMD-058) for the staged action and
  stages it for **per-event operator disposition** — always, even when
  the action class carries a standing disposition. Rationale: the flow
  source is new behavior-structure the operator has not seen; a
  standing disposition pre-authorizes the action *class*, never an
  unseen flow. Proposer≠disposer holds (bridge §5); on disposition the
  source compiles via the bridge and drives.

## 6. Determinism, totality, closedness

- **Deterministic:** `compile(profile.canonical(), factory_version)` is
  a pure function. Same profile canonical bytes + same factory version
  → byte-identical artifact bytes. Recompilation hash equality is the
  checkable property (bridge §4's discipline, applied to agents).
- **Factory version covers** (all of it, exactly): `factory_release`,
  `schema_version` (the `agent_behavior` module revision),
  `semantics_table_version` (the construction-semantics table revision),
  `tool_registry_pin` (release tag + install-manifest hash),
  `probe_suite_version`. Any change in any of these is a new factory
  version and may change artifact bytes — that is expected, not a
  determinism violation.
- **Total:** every *valid* profile compiles. Validity is exactly the
  schema's validators (derivations, C1–C5, C7 — C6 retired, DR-CMD-077). The `planning` guard's
  facet-coverage assertion is the mechanical totality check: an
  unmapped facet refuses loudly rather than dropping silently.
- **Closed:** the closed input set is `{profile canonical bytes,
  factory_version}`. The tool registry is pinned *inside*
  `factory_version` — it is never fetched. No network, no inference, no
  wall-clock reads, no ambient state at compile time. The compiler is
  deterministic even when its products are stochastic (DR-CMD-061:
  two-plane logic — D3 governs the built agent, never the compiler).

## 7. Q3 RESOLVED (staging durability — accretion-backed, DR-CMD-065)

Q3 is resolved 2026-09-26 (Peter): `staging.durability` is
**accretion-backed**, fixed — no longer a parameter. Every staged
proposal (actions + verification evidence) is committed to the
accretion repo: pending proposals survive restarts and stay auditable,
including ones never disposed. The ephemeral alternative is defeated
(lighter, but a crash loses the pending queue silently and undisposed
proposals leave no trace). The verifier's probes run under the pinned
value (§4 of the verifier spec).

## 8. Acceptance criteria (step-6 golden suite)

The step-6 suite exercises at least:

- **A1 (determinism):** compile the dsys profile → artifact; recompile
  identical inputs → byte-identical artifact bytes (hash equality).
- **A2 (totality):** every valid profile in the golden corpus
  (corners, interiors, dsys-adjacent per DR-CMD-061 step 6) compiles;
  the planning guard's facet-coverage assertion holds on each.
- **A3 (refusals):** one invalid profile per coupling C1–C5, C7 → refusal
  at `validating`, reason recorded; nothing compiles past it.
- **A4 (B-3 analog):** `write_scope` naming an unregistered tool id →
  refusal at `routing`.
- **A5 (routing):** single-effect standing class → `direct` entry;
  multi-effect class → `workflow` entry; routing table total over
  classes and channels.
- **A6 (closedness):** compile with network, inference, and clock
  unavailable → succeeds; artifact identical to the connected run.
- **A7 (version sensitivity):** same profile, bumped registry pin →
  `factory_version` differs and `artifact_hash` differs; same profile,
  same version → identical.
- **A8 (Q3):** the suite runs each profile with `staging.durability`
  pinned to `accretion-backed` (DR-CMD-065); the pinned value is
  recorded verbatim in the plan.

## 9. Reuse vs. new

**Reuse:** the profile schema + derivation functions + validators
(`agent_behavior.py` — the compiler calls them, never reimplements);
the construction-semantics table; contracted tools + the closed
registry (production-tools-spec); the bridge's B-1/B-2/B-3 pattern;
pydantic-as-source (DR-CMD-058); automaton flows as the pipeline form
(DR-CMD-064); disposition modes DR-2 (for the runtime flow-source
path, §5).

**New** (specified here, built step 5): the compiler flow
(`agent-compiler-flow`); the build-plan schema (§3); the Q2 routing
predicate (§5); the compiler's run-book tools (`tool-parse-profile`
… `tool-mint-manifest`); the staging area + disposition interface the
plan describes (substrate components, built step 5).

## 10. Non-goals

- The compiler does not operate agents (DR-CMD-061 non-goal stands).
- The compiler does not choose positions: it builds the profile it is
  given; Peter disposes positions. An invalid profile is refused, never
  "repaired."
- The compiler does not build systems: its product participates in
  dsys; dsys itself is not compiler-built.
- The compiler emits no behavior: tool implementations, the inference
  facility, and the scheduler are registered/existing code the plan
  references, never defines.

## 11. Open questions

- **Q1 — backend handle** (carried): which concrete inference facility
  the `backend_binding` binds to; deferred to step 5. The interface
  (§3) is what step 3 compiles against.
- **Q3 — staging durability** (resolved): pinned to accretion-backed
  (DR-CMD-065; §7). Ephemeral defeated.
- **Reflexivity** (DR-CMD-061): the factory itself must be profiled in
  D1–D7 and published. The factory runs as operator-disposed flows
  (DR-CMD-064); its profile is published with the step-5 build, not in
  this spec.

## 12. Glossary

- **Agent artifact:** the compiler's final output: `{plan:
  AgentBuildPlan, manifest}` with canonical bytes and hashes. What the
  verifier consumes and the harness interprets. Contains structure
  only — no generated code, no behavior definitions.
- **AgentBuildPlan:** the shared interface (§3): the pydantic record of
  every build decision the compiler made from a profile. Defined once,
  here; the verifier references it.
- **Closed (compiler):** the input set is exactly {profile canonical
  bytes, factory_version} — no network, inference, clock, or ambient
  state at compile time.
- **Deterministic (compiler):** same inputs → byte-identical artifact;
  "same" is scoped by `FactoryVersion` (§6).
- **Disposition record:** the operator's recorded disposition of a
  staged action (DR-2 modes); one source of bound arguments (§5).
- **Effect:** an invocation of a contracted tool bound in `write_scope`.
  The Q2 discriminator counts effects, not reads.
- **Factory version:** the five-part determinism scope (§6):
  factory_release, schema_version, semantics_table_version,
  tool_registry_pin, probe_suite_version.
- **Governed workflow:** (Q2) any action requiring intermediate
  observation, guards between steps, or unit replay → routed to an
  automaton flow.
- **Harness-native agent:** per the substrate spec: profiled,
  harness-plane, invoked through a Harness per AX1.
- **Routing table:** the Q2 output: per action class, `direct` vs
  `workflow` with bound tools (`actuation.routing`).
- **Standing-disposition rule:** a pre-authorized action-class entry
  (D1); with the activating trigger event, the second source of bound
  arguments (§5).
- **Tool action:** (Q2) exactly one contracted-tool call with all
  arguments bound at disposition time → direct call.
- **Total (compiler):** every valid profile (validity = the schema's
  validators) compiles; the planning guard asserts facet coverage
  mechanically.
