# D1–D7 Conformance Verifier — Specification (Ratified 2026-09-26, DR-CMD-066)

## 0. Status

Ratified 2026-09-26 (Peter), DR-CMD-066. Step 4 of the ratified D1–D7
agent factory plan (DR-CMD-061).
**Specify only** — step 5 builds. It consumes exactly what the compiler produces — the agent
artifact defined in `doc/d1-d7-compiler-spec.md` §3 — and does not
redefine it. Terms defined in the compiler spec's Glossary (§12) are
used here with the same meaning and are not restated, except where
this spec adds verifier-specific meaning.

Normative inputs: the compiler spec (build-plan schema, Q2 routing,
determinism scope); the profile schema and derivation functions in
`core/package/agent_behavior.py` (DR-CMD-062); the harness-native
substrate and runtime contract (`doc/d1-d7-agent-substrate-spec.md`,
DR-CMD-063); the ratified Q2 discriminator (DR-CMD-064); the probe
precedents — scenario simulation's sandbox + transcript separation
(DR-CMD-041) and the bridge's recompile-hash-equality discipline
(`doc/bridge-spec.md` §4).

## 1. Purpose

Define the conformance verifier: **build → probe → check**. Given a
built agent (the compiler's agent artifact) and its profile, the
verifier proves the agent occupies its profiled position: derived
positions hold, couplings C1–C5, C7 hold in the built wiring, gates and
authorizations behave per D6, and the Q2 routing routes per the plan.
A failed check **refuses the agent** — the verdict is `refused`, a
terminal state, never a silent degradation and never a partial pass.

What the verifier is not: it does not re-derive the profile (the
compiler validated it); it does not operate agents (DR-CMD-061
non-goal); it does not judge whether the profile's *position* is wise
(Peter disposes positions) — only whether the built agent *matches*
it.

## 2. The verifier's own pipeline (specified as a flow)

Per DR-CMD-064 Decision 2, the verifier runs as an automaton flow,
specified here as `agent-verifier-flow`; step 5 authors it as pydantic
sources per DR-CMD-058 and bridges it. Probe runs are **verification
exercises**, labeled as such in every transcript — never presented as
production execution.

| State | In | Out | Guard to next |
|---|---|---|---|
| `ingesting` | `artifact_bytes`, `profile_bytes` | `artifact`, `profile` | manifest parses; `profile_hash` matches `plan.profile_hash` — mismatch → `failed` (the verifier was handed the wrong pair, loudly) |
| `static_checking` | `artifact`, `profile` | `static_violations[]` | §3 — violations here are conformance failures, not verifier errors |
| `probing` | `artifact` | `probe_results[]` | §4 — every probe in the suite executed against the sandbox |
| `checking` | `static_violations`, `probe_results` | `verdict` | §5 — aggregate |
| `attesting` | `verdict`, evidence | `verdict_record` | record complete → terminal |

Terminal states: `verified` (outcome `completed`) — all checks pass;
`refused` (outcome `completed`, verdict refused) — a conformance
failure, with reasons cited; `failed` (outcome `aborted`) — reserved
for verifier-internal malfunction (fixture crash, sandbox error), never
for a non-conformant agent. `refused` is a verdict, not an error.

Run-book structure (source; step-5 tools named, **new** — built in step
5): `rb-verifier-ingest` (`tool-load-artifact`), `rb-verifier-static`
(`tool-recompute-positions`, `tool-recheck-couplings`,
`tool-check-wiring`), `rb-verifier-probe` (one step per probe P-*
below, each invoking `tool-run-probe` with the probe's fixture id),
`rb-verifier-check` (`tool-aggregate-verdict`),
`rb-verifier-attest` (`tool-mint-verdict-record`).

## 3. Static checks (no redefinition)

The verifier recomputes; it does not re-specify. All derivation
functions are called from `agent_behavior.py` — the single source of
truth. The build-plan schema is read per the compiler spec §3.

- **S1 — position recomputation:** recompute D1/D3/D4/D5/D7 from the
  profile facets; assert equality with `plan.derived_positions`; assert
  D2's recorded rule equals the profile's `conflict_rule` and is a member
  of the binary enum (DR-CMD-077; C6 retired with the scalar). A mismatch
  means the artifact was not built from this profile → `refused`.
- **S2 — coupling recheck:** re-run C1–C5, C7 against the profile (the
  schema validators already passed at compile time; this guards
  against artifact/profile skew between build and verify).
- **S3 — wiring completeness:** every D6 source has a `trigger_wiring`
  entry with non-empty gate and authorization (C4, on the built
  wiring — not just the profile); every D5 write channel resolves in
  the pinned registry (`factory_version.tool_registry_pin`); every
  enabled D7 target has a `verifiers` entry with a placement and an
  `on_failure` policy.
- **S4 — routing well-formedness:** `actuation.routing` is total over
  the standing table and write channels; every `direct` entry binds
  exactly one effect tool; every `workflow` entry names ≥2 tools or an
  inter-step guard condition.
- **S5 — advisory surfacing:** `profile.warnings()` are recorded in the
  verdict as advisories — never failures, never suppressed.

## 4. Probe harness and probe procedures

**Harness.** Probes execute the built agent inside a
manifest-provisioned sandbox (DR-CMD-041 precedent): fixtures declare
the trigger scripts, canned tool results, and disposition policies;
contracted tools are replaced by **recording stubs** that assert the
called tool is in the plan's `write_allowlist`, record arguments, and
return fixture-canned results — **no real tool ever executes during
probing**. Dispositions are **simulated** per scripted policies
(`approve-all`, `refuse-all`, `standing-only`,
`escalate-all`) declared in the fixture; the real operator is never
involved. Probe transcripts are verification evidence, quarantined
from production logs (transcript separation, DR-CMD-041 I-22). Fixtures
are seeded; the probe suite is versioned
(`factory_version.probe_suite_version`): same artifact + same suite →
same verdict.

**Q3 (resolved, DR-CMD-065):** probes run under the plan's pinned
`staging.durability` value (`accretion-backed`); the pinned value is a
condition of the run.

Probes (each: setup → inject → observe → assert → record):

- **P-D6-trigger:** inject one trigger per enabled source (operator
  session fixture, world webhook fixture with/without valid signature,
  self scheduler fixture). Assert: the activation gate admits/drops
  per the plan; admitted triggers route per the authorization rule —
  `stage-only` authorizations stage without acting; `may-act`
  authorizations may act within the standing table. Assert a dropped
  trigger produces no staged action and no tool call.
- **P-D5-scope:** attempt tool calls inside and outside
  `write_allowlist` (the stub harness makes the attempt observable).
  Assert: in-scope calls proceed; out-of-scope calls are unreachable
  (no binding exists — assert the stub was never consulted because no
  route exists, not merely that it refused).
- **P-D1-disposition:** stage a per-event action under each simulated
  disposition policy. Assert: `approve-all` → executes after the
  simulated disposition; `refuse-all` → never executes;
  `standing-only` → standing-class actions execute, others stage;
  `escalate-all` → staged for principal. Assert self-correction loops
  terminate (bounded iterations) and consult a verifier each cycle
  (C2, probed dynamically).
- **P-D3-replay:** if `replay_supported`, replay the probe transcript
  through the re-execution driver; assert hash equality of the derived
  state sequence (bridge §4 discipline). If
  `deterministic_execution`, inject the same trigger twice; assert
  identical actuation. (For D3 > 0 agents, probes assert properties
  over the run, never single-transcript identity.)
- **P-D7-boundary:** for each enabled target, inject a verification
  failure at that trust boundary. Assert the plan's `on_failure`
  policy: `fail_closed` → halt and stage; `fail_open` → log and
  continue (with the continuation recorded); `escalate` → staged for
  principal disposition. Assert the failure and the response are both
  in the verification stream (D4).
- **P-D2-fidelity:** present scripted principal/world conflicts,
  including ties. Assert tie-breaking matches `tie_break` (DR-CMD-077:
  `principal_wins_ties` → zero world-wins resolutions across the scripted
  ties; `world_wins_ties` → zero principal-wins).
- **P-D4-trace:** after the other probes, assert: every enabled stream
  (`instrumentation.streams`) has records; each record carries
  attribution; inspectors in the plan can read the log; the retention
  policy is recorded.
- **P-Q2-routing:** propose a single-effect action with bound
  arguments → assert the `direct` route (one stub call, no flow
  drafted). Propose a multi-step action → assert a flow source is
  **drafted and staged, never executed** — and that this holds even
  when the action class carries a standing disposition (compiler spec
  §5: unseen flow structure is never pre-authorized). Propose a novel
  (unnamed-class) action → assert runtime classification by the same
  predicate.
- **P-C-couplings (dynamic spot-checks):** C1 — a per-event action
  leaves event records; C3 — with `event_target` enabled, tampering
  with the trace fixture is detected by the event verifier.

## 5. Verdicts

`verdict ∈ {verified, refused}` with per-dimension results and cited
reasons. `verified` requires: zero static violations **and** every
probe passing **and** every advisory recorded. `refused` names each
failed check and the evidence (probe transcript ids, static check
ids). There is no partial pass, no "verified with warnings" that
downgrades a failure: advisories (S5) are informational; failures
refuse. A refused agent may be rebuilt (new compile, new artifact) and
re-verified; refusal is per artifact, identified by `artifact_hash`.

## 6. Acceptance criteria (step-6 golden suite)

- **B1 (clean path):** a conformant built agent (e.g. compiled from
  the dsys profile) → `verified`, zero violations, all probes pass.
- **B2 (tamper refusal):** artifacts mutated post-compile — widened
  `write_allowlist`, dropped gate, removed verifier entry, altered
  routing entry — each → `refused` with the specific check cited.
  (Mutation is detected via `plan_hash`/`artifact_hash` mismatch at
  `ingesting`, or via S1–S4 when hashes are re-minted consistently —
  both paths refused.)
- **B3 (probe failures):** each probe P-* has a failing-fixture case
  (e.g. gate admits an unsigned world trigger; stub called for an
  unlisted tool) → `refused`.
- **B4 (probe determinism):** same artifact + same probe suite version
  → identical verdict and identical per-probe results across runs.
- **B5 (no silent degradation):** no verdict state other than
  `verified`/`refused`/`failed` exists; a `refused` agent's artifact
  is never marked operable by any verifier output.
- **B6 (advisories):** a profile with `warnings()` non-empty →
  `verified` (if all checks pass) with advisories present in the
  verdict record — and a case asserting an advisory is never promoted
  to a failure.
- **B7 (Q3):** probes run under the pinned `staging.durability`
  (`accretion-backed`, DR-CMD-065); the verdict records the value the
  probes ran under.

## 7. Reuse vs. new

**Reuse:** the agent artifact + build-plan schema (compiler spec §3 —
referenced, not redefined); derivation functions and validators
(`agent_behavior.py`); contracted-tool contracts and the closed
registry (production-tools-spec); the sandbox + transcript-separation
precedent (DR-CMD-041 scenario simulation); recompile/replay hash
equality (bridge §4); pydantic-as-source + bridge for the verifier's
own flow (DR-CMD-058, DR-CMD-064); disposition modes DR-2 (simulated
at probe time).

**New** (specified here, built step 5): the verifier flow
(`agent-verifier-flow`); the probe harness (fixtures, recording stubs,
simulated disposition policies); the per-dimension probe procedures
(§4); the verdict record schema; the verifier's run-book tools
(`tool-load-artifact` … `tool-mint-verdict-record`).

## 8. Non-goals

- The verifier does not operate agents and does not authorize
  operation: `verified` is a conformance claim about the artifact,
  not a deployment authorization (DR-CMD-061 non-goal; DR-CMD-064
  Decision 2 governs step-5 implementation only).
- The verifier does not choose or repair positions: a mismatch is
  `refused`, never "fixed."
- The verifier does not build systems or re-derive profiles.
- Probe fixtures are not production traffic: nothing probed is
  presented as production execution, and probe evidence never enters
  production logs.

## 9. Open questions

- **Q3 — staging durability** (resolved): pinned to accretion-backed
  (DR-CMD-065). Ephemeral defeated.
- **Probe-suite authority:** who versions and disposes probe-suite
  changes (operator-disposed step-change, presumably — the suite is
  trusted verifier code; to be settled at step 5).
- **Q1 — backend handle** (carried from the compiler spec): the
  verifier asserts the binding's *parameters* (temperature/seed/pin
  per D3) against the plan; the concrete facility binding is step 5's.

## 10. Glossary

- **Agent artifact:** per the compiler spec §3: `{plan:
  AgentBuildPlan, manifest}` — the verifier's input. Referenced here,
  defined there.
- **Conformance:** the built agent matches its profile: positions,
  couplings, gates, authorizations, and routing hold as built.
- **`failed` (verifier):** terminal state for verifier-internal
  malfunction only — never the verdict on an agent.
- **Probe:** one scripted verification exercise (P-*): fixtures in,
  assertions on the agent's observable behavior, recorded evidence
  out. Labeled as verification, never as production execution.
- **Probe harness:** the sandbox executing probes: manifest-provisioned
  fixtures, recording tool stubs, simulated dispositions; no real
  tools, no real operator.
- **Recording stub:** the probe-harness stand-in for a contracted
  tool: asserts allowlist membership, records the call, returns
  fixture-canned results.
- **Refused:** the conformance verdict on a non-matching agent:
  terminal, reason-cited, per artifact hash. Never silent, never
  partial.
- **Simulated disposition:** a scripted approve/refuse/escalate policy
  standing in for the operator at probe time. The operator is never
  probed.
- **Static check:** verification without executing the agent (S-*):
  recomputation against the plan and profile.
- **Verified:** the conformance verdict: zero static violations, all
  probes passing, advisories recorded. A claim about the artifact, not
  a deployment authorization.
- **Verdict record:** the attested output: verdict, per-dimension
  results, cited evidence, advisory list, factory and probe-suite
  versions.
