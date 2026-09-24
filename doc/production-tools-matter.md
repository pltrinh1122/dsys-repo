# Production-tools matter: the updater flow's executor tool registry

**Status: ADOPTED (narrowed, with conditions)** — DR-CMD-055,
2026-09-23 ~19:28 PDT. Disposition mode: authorize.
**Evaluated** 2026-09-21 ~21:00 PDT (falsification pipeline below;
`sc` evaluates — it does not decide, dispose, or write
DecisionRecords). **F2 resolved as (a):** executor-spec §8 gains
a scoped exception — "no network in the executor or tools,
except the release-check poll (updater-spec §5 P2), whose
result enters only as external trigger payload."

**Matter:** *production-tools* — the dist-shipped, release-pinned
executor tools the updater flow's run-books invoke. Follow-on of
DR-CMD-054 (the executor build): the executor is built and drives
flows, but the production tool registry does not exist.

**Claim (S1):** dsys should define the production tool registry —
the eight tools the updater's run-books bind
(`tool-fetch-feed`, `tool-compare-versions`, `tool-verify-checksum`,
`tool-read-policy`, `tool-invoke-installer`, `tool-run-doctor`,
`tool-record-promotion`, `tool-commit-accretion`) — as
dist-shipped `lib/dsys/tools/` modules satisfying the spec §8
tool contract (deterministic by declaration, idempotent by
requirement, hermetic, release-pinned), because the built
executor can drive the updater flow end-to-end but the flow's
first task honestly aborts on the missing tool: without
production tools the updater is undeployable, and the fixture
tools (`noop`, `fail_always`, `malformed`) are test doubles,
not the contract's fulfillment.

**Scope (S2):** runtime. This matter is the eight tools' real
implementations against the `run(ctx)` signature the executor's
registry loads (`TOOL_NAME: str` + `run(ctx)` per module, no
overlays, no search paths — `load_tools`). The run-books stand:
their step lists resolve today through the updater's entity
adapter (`make_runbook_resolver`); only the tool bodies are
missing. The governed side stands: K1's committing logic, the
D3 pre-write identity check, and the I-18/19/20 + I-25
validators are not redesigned here. The drive contract
(DR-CMD-050) stands: initiation, authority, and handle-bearing
are settled; this matter is what the driven steps *do*.

**Proposer (S3):** the operator, via `/pb-decide` NBA O2
(2026-09-21). Lineage: the executor spec's §8 tool contract →
DR-CMD-054 (adopted with C1–C6, built `408f8ed`) → the surface
suite's honest-missing-tool case (7b) → this framing.

**Prior art (S4):**
- The executor spec §8 (the tool contract): tools live in the
  dist (`lib/dsys/tools/`), mapped by tool name; signature
  `run(ctx: dict) -> {"ok": bool, "result": <json>, "ctx_delta":
  <json>}`; deterministic (declared; F-E2) and idempotent
  (required; crash recovery is at-least-once — F-E3); hermetic
  (no network in the executor or tools); dist-shipped and
  release-pinned (`runbook_id` + `release_version` recorded at
  init); "a custom tool is a fork matter
  (dsys-mutation-playbook), not an executor option."
- The built registry (`lib/dsys/executor.py::load_tools`):
  dist-shipped modules only; a module that fails to define
  `TOOL_NAME`/`run` is a packaging fault. Today it loads three
  fixtures: `noop`, `fail_always`, `malformed`.
- The eight production tools as World-functions
  (`core/package/updater.py` `_tool_fetch_feed`,
  `_tool_compare_versions`, `_tool_verify_checksum`,
  `_tool_read_policy`, `_tool_invoke_installer`,
  `_tool_run_doctor`, `_tool_record_promotion`,
  `_tool_commit_accretion`): the golden-run implementations
  against the `World` fixture — the behavioral contract the
  real tools must satisfy, not the tools themselves.
- The run-book bindings (`updater.py::compile_flow`): six
  run-books (`rb-release-check` ×2 steps, `rb-release-verify`,
  `rb-policy-gate`, `rb-release-drive`,
  `rb-release-verify-installed` ×2 steps, `rb-accretion-commit`)
  with step policies (`retry:3` on the check, `abort`
  elsewhere).
- The 7b evidence (`tests/test-automaton-surface.sh`): a
  timer-triggered updater flow reaches its first task;
  `tool-fetch-feed` is not implemented; the child records
  three `step_started`/`step_failed` attempts under `retry:3`,
  then aborts; the flow routes `run_aborted` to the failed
  end state. Honest failure, not a completed production run.
- K1 + Q3(a) (`doc/k1-q3-binding-spec.md`, BUILT): the
  committing tool's pre-write identity check (D3, fail
  closed, abort-not-retry) — the sharpest tool in the
  registry, already designed on the governed side.
- The installer falsification finding (2026-09-20):
  reinstall idempotency holds operationally — relevant to
  `tool-invoke-installer`'s idempotency claim.
- DR-CMD-040 (K3 terminally INVALID): nothing in this
  matter may smuggle ambient initiation back in — tools
  don't initiate, they execute.

**Motivation (S5, because-Z):** the first real drive, blocked
on the last mile. The checkable world-claim: *the updater
flow's production tools exist nowhere* — not in the dist,
not in the registry, not in any spec. The executor build
closed every other gap on the drive path (stepping, guards,
policies, child runs, trigger payloads from child ctx,
disclosures, replay); the 7b case proves the path is honest
but dead-ends at the first step. The Z is not vibe: the
updater exists to keep installations current (`~/dsys-inst`
is a live installation), the drive contract authorizes
production drives, and a drive that aborts at `checking`
every time is not a drive. Each candidate tool definition
must survive §8's hermeticity (no network in tools) and
F-E3's at-least-once idempotency.

**G6 — open questions:**
1. **Feed ingress (load-bearing):** spec §8 says no network
   in the executor or tools — but the first step is
   `tool-fetch-feed`. Does the tool read an injected payload
   (the wrapper fetches the feed and injects it via
   `--trigger external --payload`, recorded as bytes —
   hermeticity preserved), or does §8 bend for this one
   tool? The name says fetch; the contract says hermetic.
   One of them has to give, and the answer reshapes the
   run-book's first step.
2. **The closed list:** are these eight tools the whole
   registry, or do the run-book step lists change once real
   tools exist (e.g. does `tool-fetch-feed` survive Q1)?
3. **World-function porting:** which `_tool_*`
   implementations port directly (`compare-versions` is
   pure; `read-policy` reads a config file) vs need real
   system integration (`invoke-installer` shells to
   `install.sh`; `run-doctor` invokes the doctor machinery;
   `commit-accretion` does real git against the D3-verified
   handle)?
4. **Idempotency (F-E3):** crash recovery is at-least-once;
   every tool must be idempotent. `tool-invoke-installer`
   (installer idempotency is established) and
   `tool-commit-accretion` (append-only D6 + D3 pre-write
   check) are the sharp cases — state the argument per
   tool, don't assert it.
5. **Determinism (F-E2, declared):** which tools' determinism
   is non-obvious? `tool-read-policy` reads a config file
   that can change between advances — replay never
   reinvokes, so replay is safe, but two live advances can
   see different configs. Is that within "deterministic by
   declaration," or does the tool need to pin what it read
   into `ctx_delta`?
6. **Release pinning:** `runbook_id` + `release_version` are
   recorded at init — how does the installer carry
   `lib/dsys/tools/`, and what binds a tool module's bytes
   to the release the run-book was pinned to?
7. **Custom tools:** spec §8 already answers this (a custom
   tool is a fork matter, not an executor option) — confirm
   it stands, or say why not.

**What this matter is not:**
- Not the run-books: their step lists resolve via the
  adapter today (though G6 Q1/Q2 may change what the steps
  mean).
- Not the executor, the drive contract, or initiation
  (DR-CMD-054, DR-CMD-050 — built).
- Not ambient-initiated anything — K3 is terminal; tools
  execute, they never initiate.
- Not a plugin architecture: the registry is dist-shipped
  modules, no overlays, no search paths (spec §8).
- Not the (b)-half: handle acquisition/lifetime
  (DR-CMD-053, built).

## Glossary

- **Production tool:** one of the eight real tool
  implementations the updater's run-books invoke —
  `lib/dsys/tools/` modules satisfying the §8 contract.
  Not the World-functions in `updater.py` (the behavioral
  contract), not the fixtures (`noop`, `fail_always`,
  `malformed` — test doubles).
- **Tool registry:** what `load_tools` builds from
  `lib/dsys/tools/*.py`: name → `run(ctx)`. Dist-shipped,
  release-pinned; unknown names fail loudly at advance
  time (the 7b honest-abort path).
- **Hermetic (tools):** no network in the executor or
  tools (spec §8, extends per-command hermeticity).
  Network-derived facts enter only as recorded external
  input (trigger payloads), never by a tool reaching out.
- **Dist-shipped:** carried by the installation
  distribution (`install.sh`), not overlaid or
  search-pathed at runtime.
- **Release-pinned:** the tool modules a run ran against
  are identified by the `runbook_id` + `release_version`
  recorded at `init`; a different release's tools are a
  different binding.
- **Release pinning:** the tool modules a run ran against
  are identified by the `runbook_id` + `release_version`
  recorded at `init`; a different release's tools are a
  different binding.
- **The 7b case:** the surface-suite case proving the
  honest missing-tool path — timer-triggered updater
  flow, `tool-fetch-feed` unimplemented, child aborts
  after `retry:3`, flow routes `run_aborted` to failed.

## Evaluation

Falsification pipeline, run 2026-09-21 ~21:00 PDT (`/pb-decide`
NBA O1 selection). `sc` evaluates; it does not decide, dispose,
or write DecisionRecords.

### S5 motivation-fit

The checkable world-claim — *the updater flow's production
tools exist nowhere* — holds on cited evidence:
`lib/dsys/tools/` loads exactly three fixtures (`noop`,
`fail_always`, `malformed`); the eight production names
resolve nowhere in the registry; the 7b case proves the
honest abort at the first step. The Z (the first real drive;
the updater exists to keep installations current;
`~/dsys-inst` is a live installation) is well-placed — not
INVALID, not misplaced, not vibe. One probe — "is the Z
really the drive, or just completing the executor line?" —
fails to refute: the executor line is complete and the drive
still aborts; the tools are the last mile, not a victory lap.

### Falsifiers

- **F1 — "The World-functions ARE the tools; this is a
  porting task, not a design matter."** *Falsifier:* the
  eight `_tool_*` functions in `core/package/updater.py`
  already define behavior — signatures, ctx keys, abort
  conditions. Does the matter reduce to mechanical
  porting? *Outcome:* **narrows, sharply.** The behavioral
  contracts port, but four things don't survive mechanical
  porting: (a) the `(ctx, w)` signature must become
  `run(ctx)` — the World (network, git, installer, policy
  source, the `surfaced` list) has to be replaced by real
  system interfaces, per tool; (b) `fetch-feed`'s "sole
  network touch" contradicts executor-spec §8's hermeticity
  — the port is impossible as stated (see F2); (c) abort
  reasons: the executor's C1 already normalizes every
  exception into the failure record *with the message
  preserved* (`tool raised {type}: {e}` —
  `lib/dsys/executor.py::invoke_tool`), so D3's
  wrong-identity reason and the checksum-mismatch reason
  survive structurally — what the spec stage must settle
  is the failure-record *schema* on the disclosure path
  (the drive contract's D7 record/surface duty); (d)
  subprocess scope: `tool-invoke-installer` (install.sh)
  and `tool-commit-accretion` (git) naturally shell out,
  against §8's "Tools run in-process" — the honest reading
  is that §8 governs *invocation* (importlib-loaded,
  `run(ctx)` called in-process, not tools-as-executables),
  not what a tool may spawn; the spec stage should state
  that explicitly rather than leave it ambiguous.
  The matter is therefore not "write eight tools" — it is
  "settle the four non-portable decisions, then the rest
  is build work."
- **F2 — "§8's hermeticity is wrong; fetch-feed needs the
  network."** *Falsifier:* the updater's own governed
  contract predates §8 and assumes network —
  `_tool_fetch_feed`: "The sole network touch: one GET of
  the pinned feed"; updater-spec §5 (Hermeticity story,
  P2): "The sole network touch is the `release-check`
  poll — a GET of the pinned feed URL. Confined to that
  run-book; the result enters the machine only as an
  external trigger payload (data, content-hashed into the
  event log — the dialog R5 boundary: no instruction
  field, never resolved by the untrusted side)."
  Executor-spec §8: "no network in the executor or tools."
  *Outcome:* **not narrowed — a genuine spec conflict
  between two adopted specs, which the disposition must
  resolve.** Three options: (a) §8 gains a scoped
  exception — "no network in the executor or tools,
  except the release-check poll (updater-spec §5 P2),
  whose result enters only as external trigger payload";
  (b) updater-spec §5 is amended — the GET moves to the
  wrapper (outside the architecture), the tool reads the
  injected payload; (c) a stated mapping both live with.
  Trust shape, for the disposition: under (b)/(c) the
  network touch moves into the *ungoverned* wrapper, and
  the governed trust anchor becomes the pinned checksum
  gate (`tool-verify-checksum`) — the wrapper fetches
  (untrusted transport), the tool verifies. Under (a) the
  network touch stays inside the governed run-book and
  §8's blanket claim — which extends the ratified
  per-command hermeticity story — takes one explicit
  carve-out. Note the updater spec already answers two
  sub-questions: the poll result is external-input-as-
  payload (§3 R1 — replay re-validates, never re-fetches),
  and `checking`'s `retry:3` is *for* transient network
  (§5: "retry:3 then abort (transient network)"). The
  feed-authenticity pin is operator-owned config
  (`updater.feed_url`, §4 R5) — the answer to "where does
  the pin live."
- **F3 — "The fixture tools suffice; production tools are
  a deployment detail."** *Falsifier:* `noop` /
  `fail_always` / `malformed` already exercise every
  executor path (the surface suite proves it).
  *Outcome:* **killed.** The fixtures exercise the
  executor's *handling* of tools; they implement none of
  the updater's *behavior*. The 7b case is the evidence:
  with fixtures only, every production drive aborts at
  the first step. A drive that always aborts is not a
  drive.
- **F4 — "This is K3 revived."** *Falsifier:* building
  tools that invoke the installer reintroduces
  ambient-driven execution through the back door.
  *Outcome:* **killed.** Tools execute; they never
  initiate (DR-CMD-040). The executor invokes tools only
  inside an operator-initiated, I-26-authorized drive;
  the installer invocation is the *payload* of an
  authorized drive, not an initiation path. The drive
  contract's D4 tripwire covers initiation; nothing here
  creates one.
- **F5 — "Eight tools is eight matters; decompose."**
  *Falsifier:* each tool has its own system interfaces
  and its own idempotency argument; one matter can't
  spec all eight well. *Outcome:* **narrows.** The
  matter's real design content is the *registry
  contract* (F1's four decisions + F2's conflict
  resolution). Once those are disposed, the eight tool
  bodies are build work against their settled
  World-function contracts — not eight separate
  dispositions. `tool-commit-accretion` deserves first
  scrutiny at spec stage (D3 identity check + real git +
  append-only D6 under F-E3 at-least-once: the
  idempotency argument is watermark re-check — a
  re-invocation after a crash diffs the flow log against
  the watermark and finds nothing new to commit).

### The narrowed survivor

Not "eight tools to write" (F1, F5). Not a hermeticity
repeal (F2 — a scoped resolution, not a repeal). The
survivor is the **production tool registry contract**:
the F2 conflict resolution, the World→system interface
mapping per tool (F1a — incl. `w.surfaced` → the
disclosure outbox `var/disclosures/`, and the
installed-version source), the failure-record schema on
the disclosure path (F1c), the subprocess scope stated
against §8 (F1d), and per-tool idempotency arguments
(commit-accretion first). The eight bodies follow as
build work.

### Conditionals (on the narrowed matter)

- **A1** — this evaluation is the falsification; no
  refuted sub-claim survives (F3/F4 killed; F1/F2/F5
  narrowed). The F2 conflict is not a refutation of the
  matter — it is a conflict between adopted specs for
  the disposition to resolve. Holds on the narrowed
  matter.
- **A2** — no new entity: the registry exists, tools are
  modules, the `Tool` entity's `name` is already in the
  ontology (executor-spec §8). Holds.
- **A3** — plane discipline: zero inference in execution;
  whichever F2 option is picked, the feed bytes stay data
  — never resolved, never executed (dialog R5 boundary,
  updater-spec §5; AST-allowlisted guards enforce it
  structurally). Holds as a constraint on the
  disposition.
- **A4** — spec before build: a spec-stage gate. Noted,
  not failed.
- **A5** — the narrowed Y is checkable: the 7b case
  becomes the acceptance (a drive with production tools
  gets past `checking`); per-tool golden-run acceptances
  against the World-function contracts. Spec-stage.
- **R1** — replay: tools are never reinvoked in replay
  (executor-spec §9, structural); the poll result is
  recorded data, so replay re-validates without
  re-fetching (updater-spec §3). Holds.
- **R2** — golden-run coverage, spec-stage: per-tool
  acceptances incl. the checksum-tamper refusal
  (`sha256:tampered` → verify aborts), the D3
  wrong-identity refusal (governed side already covered
  by K1 cases 24–28 — the tool must preserve them), and
  the network-disabled → `retry:3` → abort path.
- **R3** — a validator will be needed: candidate I-31 —
  "every step's tool resolves to the pinned release's
  registry" (release-pinning enforcement). Spec-stage.
- **R4** — zero inference in execution. Holds
  structurally.
- **R5** — trust declared, spec-stage: the feed-URL pin
  (operator config) and transport trust; the wrapper's
  role under F2 option (b)/(c) if chosen;
  deterministically-lying tools (F-E1, already declared).
- **G6 Q7** (custom tools): settled — spec §8 already
  answers it (a custom tool is a fork matter, not an
  executor option). No change.

### Draft verdict

**Adopt with conditions (narrowed)** — the production-tool
*registry contract* (F1's four decisions + F2's conflict
resolution), not eight tool builds. Disposition mode:
**authorize** (the spec stage).

Spec-stage conditions: A4 (spec before build); the F2
resolution — the operator picks (a)/(b)/(c) (ambient
recommendation: (a), the scoped §8 exception — the updater
spec's §5 story is complete and adopted, and an explicit
carve-out beats moving the network touch into the
ungoverned wrapper); the World→system interface mapping
per tool; the failure-record schema on the disclosure path;
the subprocess scope stated against §8; per-tool
idempotency arguments (commit-accretion first); R2
golden-run acceptances (tamper, wrong-identity,
network-disabled→retry→abort); R1 replay story for the poll
result as recorded data; R3 (I-31 candidate); R5 trust
declared. G6 Q7 stands as settled.

**Disposed** as DR-CMD-055, 2026-09-23 ~19:28 PDT — O1:
authorize, F2 as (a). The spec stage is authorized; spec
adoption returns as a follow-on disposition (no reframing
needed — the conditions above are its terms of reference).
