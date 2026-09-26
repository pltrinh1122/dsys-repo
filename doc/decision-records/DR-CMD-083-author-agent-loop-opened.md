# DR-CMD-083 — agent-operated factory: the author-agent loop (matter opened)

- **Status:** opened (matter) — spec + build + verify commissioned; RATIFIED as built under DR-CMD-084
- **Date:** 2026-09-26 ~14:30 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** n/a (matter opening, not a disposition)

## Falsification result (premise)

Peter: "runners for the Triad already exists. falsify." — **FALSIFIED.** No
runner exists anywhere in the repo:

- Golden runs (`factory_golden_run.py`, `agent_behavior_golden_run.py`,
  bridge/updater/drive-contract/acquisition/PVB/scenario-sim/playbook
  suites) are verification harnesses, not operation engines.
- The updater driver drives automaton *flows*, not agents.
- `dsys execute --as <role>` exists only in `doc/cli-interface-spec.md`
  (spec, unimplemented).
- The Triad (staff/field/office, DR-CMD-069/071) is an *authoring
  constraint* (declare → gate → refuse-with-reasons), not an execution
  engine.

What the repo has: agents are verified (compile+verify green) but never
operated. The factory builds agents; nothing runs them.

## Peter's instruction (verbatim)

> "bootstrap an agent to author agents, invoke Factory to build the authored
> agents, and then run the agent's self-diagnostic playbook as verification
> of success."

## Architectural frame (load-bearing)

Zero inference inside execution is a ratified hard requirement (v1,
2026-09-17/18): all inference happens outside the machine, reaching it
only as discrete step-changes. Authoring a profile *is* inference
(drafting facets, prose, judgment). Therefore the author-agent is
**harness-side**: ambient inference governed by a ratified author-agent
profile — not an automaton-side executable. An automaton-side
author-agent would require inference inside execution (refused by the
invariant) or a generative template stage (explicitly declined,
DR-CMD-069: "no generative stage — profiles are still authored in
full").

The loop: operator commissions → author-agent (governed ambient) authors
a profile → stages it → the standing factory driver (deterministic
harness machinery) compiles + verifies → the built agent's
self-diagnostic playbook runs → all-green = success.

## Judgment calls

- **J0 — the harness-side frame.** Stands. Alternative (automaton-side
  author-agent) refused: violates zero-inference-in-execution and
  DR-CMD-069's no-generative-stage.
- **J1 — factory-invocation mechanism.** (i) Contracted factory tool
  (author-agent wields compile+verify; first D5-nonzero staff agent —
  extends what the machine guarantees) vs (ii) staged build-requests +
  standing factory driver (agents stay tool-free, D5 = 0.0; stigmergic,
  mirroring the D6 agent-source pattern). DR-CMD-064 (A: hybrid for built
  agents) and AX1 (invocation through a Harness) both point at (ii):
  compile+verify are deterministic harness machinery, not agent tools.
- **J2 — self-diagnostic playbook format.** Diagnostic cases authored AS
  PART of the profile artifact (`diagnostic_cases()` in the authored
  module); the driver runs them post-verify; all-green = the agent's own
  diagnostic passes. Distinct from the factory's generic golden runs
  (which test factory machinery); diagnostics test the *commissioned
  behavior* of the agent. Includes refusal cases against pure decision
  functions where the role warrants one.
- **J3 — bootstrap.** The ambient authors the FIRST author-agent profile
  ("wright"); the factory builds/verifies it; the operator commissions
  it; it then authors the rest. No paradox — mirrors how the Sextet was
  authored.
- **J4 — demo scope.** ONE new agent authored end-to-end through the
  loop: the **registrar** — stages registry-update proposals for verified
  built agents (the registry DR-CMD-078's authenticated-agent gating
  attests against). Genuinely new, small, and motivated. Honesty rule:
  the registrar's bytes must flow commission → author → stage → driver
  → diagnose; nothing hand-placed past the driver.

## What the machine guarantees (unchanged unless flagged)

- No new contracted tools; all staff agents stay D5 = 0.0.
- Proposer ≠ disposer: the author-agent stages profiles and build
  results; it never deploys. Deployment remains an operator disposition.
- The driver is deterministic harness machinery (same pipeline as
  `run_agent`, triggered by staged build-requests instead of a hardcoded
  list). Zero inference inside it.
- Deterministic replay: authored bytes are hash-pinned; the loop
  re-runs mechanically on pinned bytes.

## Verification (as instructed)

End-to-end loop green; the registrar's self-diagnostic passes (the
instructed success criterion); all existing suites stay green; two
consecutive runs byte-identical.

## As-built amendment (2026-09-26, build)

- **J4 registrar D6:** spec §8 draft said {OPERATOR, AGENT}; built as
  {OPERATOR, SELF}. Reason: J-H discipline (DR-CMD-080) — bind only
  what the role needs; no built agent currently stages verified-build
  notices, so AGENT would name nothing truthful. Verdict discovery is
  via SELF sweeps of the verdict staging area (coordinator precedent).
  The registry still serves DR-CMD-078's attestation need. Spec §8
  updated; historical text above preserved.
- **J1-ii confirmed in build:** the driver loads staged bytes via
  importlib from the harness root; authored modules use absolute
  imports. No contracted factory tool was added; all staff agents
  remain D5 = 0.0 — no guarantee changed.
