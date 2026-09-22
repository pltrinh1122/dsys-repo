# Production-tools matter: the updater flow's executor tool registry

**Status: FRAMED** — 2026-09-21 ~19:15 PDT, under `/pb-decide` NBA
(O2: "frame the production-tools matter"). Not evaluated, not
disposed. Next step is the operator's: evaluate (falsification
pipeline) or dispose.

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
- **The 7b case:** the surface-suite case proving the
  honest missing-tool path — timer-triggered updater
  flow, `tool-fetch-feed` unimplemented, child aborts
  after `retry:3`, flow routes `run_aborted` to failed.
