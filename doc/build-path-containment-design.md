# Build-path containment design (spike)

- **Status:** design spike, commissioned 2026-09-27 (DR-CMD-110, O2 of the
  containment matter). Design only — no build, no code changes.
- **Disposition (DR-CMD-111, Peter 2026-09-27): O1a ADOPTED, O1b REFUSED.**
  The placement experiment (three arms, fresh subprocess each) falsified
  this doc's §4 relocation claim: a builder mutating imported factory
  module state in-process staged a must-refuse profile through all six
  steps with a well-formed transcript when vetting shared the builder's
  process (O1b's placement); the split placement (O1a) refused it with
  the byte-identical honest reason. The §5 recommendation is superseded
  on placement only; the threat model, trust-boundary analysis, and
  fail-closed requirements stand. Implemented in
  `core/package/rb_profile_build.py` (supervised child:
  `sys.executable -m core.package.rb_profile_build --build-child`;
  120s timeout; POSIX best-effort RLIMIT_AS/RLIMIT_CPU; child stderr to
  parent stderr, never into the transcript).
- **Boundary:** build-request → `drive_build`, RECEIVE through STAGE. The
  wright-invocation half (ambient-side authoring labor) is out of scope.
- **Standing rule (design term):** every profile build delegated to a
  builder subagent goes through `rb-profile-build` — the subagent authors
  and stages the build-request, then invokes `drive_build`. The design
  must keep that interface intact.

## 1. The gap, precisely

`drive_build` (in `core/package/rb_profile_build.py`) executes authored
module bytes **in-process** at RECEIVE — the single `exec()` call site in
the codebase (`rb_profile_build.py:179`). The exact sequence inside
`_tool_receive_build_request`:

1. Structural checks on the build-request mapping.
2. **Hash-pinning:** `sha256(authored_module_bytes)` must equal
   `content_hash`, else refuse fail-closed (golden-run case B-5 proves
   tampered bytes refuse *before* anything executes).
3. `compile()` the bytes, then `exec(code, namespace)` in a fresh
   namespace (`{"__name__": ...}` — no `sys.modules` pollution, but full
   builtins: the exec'd code can `import os`, `open()`, `socket`, etc.).
4. Extract `<profile_name>_profile` and the module's `ARCHETYPES`.

The builder function is then *called* in-process at VALIDATE
(`builder()`), and the resulting profile object flows through GATE,
COMPILE, VERIFY, STAGE in the same process.

Correction to the commission brief: the exec is at **RECEIVE**, not
"during VALIDATE→VERIFY". The brief's substance stands — commissioned
bytes run with the ambient's full process privileges — but the location
matters for the design: the exec precedes all validation, so nothing the
later steps check can contain what the exec already did.

### What already contains it (honest accounting)

- **Hash-pinning at RECEIVE:** only the commissioned bytes execute.
  Tamper or corruption refuses before exec. This is an *integrity* wall:
  it proves *which* bytes run.
- **Commission scoping:** builds run under an Operator commission; the
  authoring chain is trusted ambient/wright labor under standing
  disposition, not anonymous input.
- **Fresh namespace:** no `sys.modules` pollution (hygiene, not
  security — the code re-imports whatever it wants).
- **Fail-closed refusals:** exec/compile/builder failures refuse with
  reasons, never pass silently.
- **Deterministic replay:** same bytes → byte-equal transcript
  (canonical JSON; no timestamps, temp paths, or randomness in the
  transcript path).

### What it does not contain

Hash-pinning says nothing about *what the bytes do*. Commissioned bytes
— buggy or hostile — execute with the ambient's UID, environment,
filesystem, and network, **with no timeout and no resource limits**. A
`while True:` at module top level hangs RECEIVE forever; a memory bomb
OOMs the ambient; a hostile module exfiltrates or persists before any
step runs.

## 2. Threat model

**Adversary A1 — buggy authored code (non-adversarial, most likely).**
A builder function or module top-level with an infinite loop, runaway
allocation, or accidental filesystem/network side effect. Controls:
arbitrary Python at RECEIVE-exec and at the VALIDATE builder call.

**Adversary A2 — hostile bytes via a compromised commission chain.**
The hash matches because the bytes *are* what was commissioned — the
compromise is upstream (a subverted authoring subagent, a tampered
wright output that still got commissioned). Controls: same as A1, plus
intent. Note the limit: hash-pinning defeats the *network* attacker
(bytes swapped in transit refuse at B-5); A2 is strictly the
*commissioned-but-hostile* case.

**Not in model:** direct attack on the ambient outside the build path;
compromise of the Operator's commission itself (if the commission is
hostile, no build-path mechanism helps — that is governance, not
containment).

**Blast radius today:** the ambient process and everything it can
reach — workspace files, environment credentials, network. A hang stalls
the build indefinitely (no timeout); memory exhaustion can take down the
ambient rather than just the build.

## 3. Options

### O1 — Subprocess-isolated exec

Move the arbitrary-code surface into a supervised child process.

**O1a (narrow): isolate exec + builder call.** The child execs the
module and calls the builder, returning the constructed profile
serialized (`model_dump(mode="json")`) plus module metadata
(`ARCHETYPES`, builder name). The parent revalidates via
`model_validate` (already done at VALIDATE today), then runs GATE,
COMPILE, VERIFY, STAGE in-process on the revalidated data.

- Contains: module-level exec and the builder call — the two
  arbitrary-code sites.
- Costs: an IPC/serialization boundary mid-pipeline; the profile object
  graph still originates from hostile code (residual surface in
  downstream steps, though they operate on revalidated pydantic data).
- Does not fix: hangs/resource exhaustion *within the child* still need
  timeouts — which O1a needs anyway.

**O1b (whole-drive, recommended variant): run `drive_build` wholesale
in the child.** The parent's job becomes: hash-pin (pure `hashlib`,
safe) → spawn child with the build-request → enforce timeout →
receive the transcript dict → relay it. The child runs the identical
code and returns the identical canonical-JSON transcript.

- Contains: everything arbitrary — exec, builder, and any residual
  object-graph surface. The blast radius shrinks from "the ambient
  process" to "one throwaway child."
- Fail-closed across the new boundary: child crash / timeout / OOM /
  malformed transcript → the parent stages a refusal with an explicit
  reason (`build subprocess timed out after Ns`, `exited 137`), never a
  pass, never silent.
- Costs (honest): a supervision layer — IPC protocol (request bytes in,
  transcript JSON out), timeout selection and tuning, resource limits
  (`RLIMIT_AS`/CPU via `preexec_fn` on POSIX — best-effort,
  platform-noted), traceback capture. Refusal *reasons* must survive
  the boundary verbatim (B-2/B-3 compare against the direct-compile
  oracle); tracebacks go to the parent's stderr for debugging and
  **never** into the transcript, protecting byte-equality.
- Does not fix: hostile-but-commissioned bytes that produce a
  *well-formed* profile — that is the vetting chain's job
  (GATE/COMPILE/VERIFY still run, now in the child), not containment's.
  Nor a compromised commission chain upstream.

**Determinism under O1:** the transcript is already canonical JSON with
no timestamps or temp paths (VERIFY's staging path deliberately never
enters the transcript), so the child produces byte-equal transcripts in
principle. The golden run's replay checks (B-1, B-4) re-verify this at
build time — the design requires them green, not assumed green.

**Interface under O1:** `drive_build(build_request) -> transcript`
keeps its signature and return contract; supervision lives *inside*
`drive_build` so there is no insecure alternate path and the standing
rule (builders stage requests, call `drive_build`) survives unchanged.

### O2 — Restricted exec environment (capability-dropping, in-process)

Exec the module with a scrubbed namespace: a custom `__import__`
allowlisting only what authored modules legitimately need
(`core.package.*`, `hashlib`, `json`, … — the allowlist needs a survey
of the authored corpus), `open` removed or wrapped, dangerous builtins
dropped. Applied at RECEIVE-exec and at the VALIDATE builder call.

- Contains: casual exfiltration/persistence via direct imports; keeps
  everything in-process, so debuggability and determinism are untouched
  and complexity is low.
- **Must be stated plainly:** Python builtins-scrubbing is a
  speed-bump, not a wall — sandbox escapes via restricted `exec` are
  extensively documented. O2 raises the bar for *accidental* damage
  (A1) but must never be presented as containing a hostile author (A2).
- Does not fix: resource exhaustion or hangs (no timeout in-process
  without signal/thread machinery — itself new complexity); determined
  hostile code; allowlist maintenance burden as the authored corpus
  grows.

### O3 — Accept the gap as bounded (declined baseline)

The characterization, for the record: RECEIVE's hash-pinning plus
commission scoping *is* the containment — only Operator-commissioned
bytes from trusted authoring labor ever execute; builds are infrequent
and observed. The residual (buggy/harmful commissioned bytes) is
accepted explicitly, with a revisit tripwire (e.g., the first
build-request from non-ambient authorship, or any exec-time anomaly).
Peter declined this on 2026-09-27 in favor of commissioning this spike;
it remains the honest baseline the other options are measured against.

## 4. Where the trust boundary should sit

RECEIVE's hash-pinning is the **integrity** wall — it proves *which*
bytes run — and it is load-bearing and stays. But it is not a
containment wall: it says nothing about what the bytes *do*. Today the
integrity wall and the blast radius share a process, which means the
integrity guarantee is doing double duty it was never designed for.

The wall that needs moving is the **exec location**, not the hash
check. The recommended boundary:

- **Parent (ambient process):** integrity + supervision. Hash-pin,
  spawn, timeout, resource-limit, relay transcript, translate child
  failure into staged refusal. The parent never execs authored bytes.
- **Child (throwaway process):** execution. Runs the identical
  six-step code; returns the identical transcript. Its compromise costs
  one child process.
- **Vetting chain (GATE/COMPILE/VERIFY):** unchanged in *what* it
  checks; relocated into the child under O1b. It answers "is this
  profile sound?" — a different question from "what did the bytes do
  while running?", which is the only question containment answers.

Hash-pinning stays load-bearing for integrity; subprocess isolation
becomes the containment wall. Each wall does one job — defense in
depth, not a thicker single wall.

## 5. Recommendation

**Adopt O1b: whole-`drive_build` in a supervised child process, with
supervision inside `drive_build` so the interface and the standing rule
survive unchanged.** It is the only option that actually moves the
blast radius rather than narrowing the code's vocabulary (O2) or
relabeling the gap (O3). The costs are real — IPC boundary, timeout
tuning, verbatim reason relay, POSIX resource-limit portability — but
they are bounded, one-time, and proportionate: builds are infrequent,
so per-build spawn overhead is irrelevant, and the transcript's
canonical-JSON design already did the hard determinism work. What it
does not fix is stated in §3 and stays out of scope: well-formed
hostile profiles are the vetting chain's problem, and a compromised
commission is governance's problem.

## 6. Migration

- **`drive_build` signature unchanged.** The only in-repo caller besides
  builders is `rb_profile_build_golden_run.py`; the factory golden run
  (192) never touches `drive_build` — it is unaffected by construction.
- **rb-profile-build 7/7:** B-5 (tamper) refuses at parent-side RECEIVE
  before any spawn — unchanged. B-1..B-4, B-6, B-7 exercise
  staged/refused outcomes with exact reason strings; all survive if
  the child relays `BuildRefused` reasons verbatim and the parent adds
  no transcript fields. The byte-equal replay checks (B-1, B-4) must be
  re-run green at build time — required, not assumed.
- **Staged-but-unregistered flow:** unchanged. STAGE still produces the
  staged bundle + transcript for Operator disposition; the run-book
  still never publishes, registers, or disposes.
- **New contract surface (to be commissioned at build):** the IPC
  failure taxonomy and its refusal strings (timeout, crash, OOM-kill,
  malformed transcript), the timeout value, and the resource limits.
  These become part of the run-book's contract and need the same
  disposition discipline as the rest.

## 7. Open questions

1. Timeout value for the child: wall-clock bound per build? Per stage?
   (Builds are infrequent; generous-but-finite is the right shape —
   exact number is a build-time disposition.)
2. Resource limits: `RLIMIT_AS`/`RLIMIT_CPU` via `preexec_fn` are
   POSIX-only. Is Linux-first acceptable, or is a portable fallback
   required?
3. Child interpreter: `sys.executable` (same venv — required for
   `core.package` imports). Pinned and asserted at spawn, or assumed?
4. Should the parent cheaply re-verify the child's transcript
   (recompute `content_hash` over the relayed bundle) as defense in
   depth on the IPC boundary?
5. Traceback policy: refusal *reasons* verbatim into the transcript;
   full tracebacks to parent stderr only. Confirm no diagnostic
   content is owed to the staged bundle.
6. O1a vs O1b is the one structural fork: O1b is recommended for the
   cleaner boundary (§4), but O1a keeps GATE/COMPILE/VERIFY in the
   parent if Peter prefers the vetting chain to stay ambient-side at
   the cost of the residual object-graph surface. This is a genuine
   disposition point.

## 8. Glossary

- **Ambient:** the harness-side agent (Muse) that authors, stages, and
  drives builds; the process whose privileges authored code currently
  inherits.
- **Authored module:** the Python source bytes a builder subagent
  authors (e.g. `core/package/authored/recorder.py`); exposes
  `<profile_name>_profile()` and `ARCHETYPES`.
- **Blast radius:** the set of state an adversary can damage — today,
  the ambient process and everything it can reach.
- **Build-request:** the run-book's input contract —
  `{commission_ref, profile_name, authored_module_bytes, content_hash,
  declared_archetypes}`.
- **BuildRefused:** the run-book's refusal exception; carries the step
  id and the exact reason, staged verbatim into the transcript.
- **Byte-equal transcript:** two runs on the same bytes produce
  identical `transcript_bytes()` (canonical JSON); the replay-identity
  the golden run enforces.
- **Commission chain:** Peter → commission → authoring labor
  (wright/ambient) → staged build-request. Hash-pinning verifies the
  bytes match the commission; it does not vet the commission.
- **Deterministic replay:** the property that the same build-request
  bytes always yield the same transcript.
- **drive_build:** the run-book driver —
  `drive_build(build_request) -> transcript`; pure function of the
  build-request, zero inference.
- **Fail-closed:** any failure refuses with reasons and halts; nothing
  passes silently or by default.
- **Hash-pinning:** `sha256(authored_module_bytes) == content_hash` at
  RECEIVE; the integrity wall.
- **IPC:** inter-process communication — here, build-request bytes to
  the child, transcript JSON back.
- **RECEIVE:** run-book step 1 — accepts the build-request, hash-pins,
  execs the module, extracts the builder. The exec site.
- **Standing rule:** profile builds go through `rb-profile-build` —
  builders stage requests and call `drive_build`, never hand-drive
  validate/gate/compile/verify.
- **Trust boundary:** the line across which trust assumptions change —
  here, proposed between parent (integrity + supervision) and child
  (execution).
- **Wright:** the staff+office author profile that drafts profile
  modules and stages build-requests; its invocation half is out of
  scope for this design.
- **Zero inference:** no LLM calls anywhere in the build path; the
  authored bytes arrive as an injected discrete step-change.
