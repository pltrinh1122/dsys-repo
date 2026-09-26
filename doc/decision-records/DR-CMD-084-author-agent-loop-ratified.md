# DR-CMD-084 — author-agent loop ratified

- **Status:** ratified
- **Date:** 2026-09-26 ~14:35 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** agent-operated factory — bootstrap an agent to author agents, invoke the Factory to build the authored agents, run each built agent's self-diagnostic playbook as verification of success (opened DR-CMD-083)

## Disposition

Peter rendered "ratify" (~14:35 PDT) on the author-agent loop as presented.
The loop is **RATIFIED as built** — J0 through J4 as built, with the
as-built deviation recorded below.

## Ratified judgments

- **J0 — harness-side frame: stands.** Authoring is inference;
  zero-inference-in-execution (ratified hard requirement, v1) forbids an
  automaton-side author-agent; DR-CMD-069's no-generative-stage stands.
  The author-agent is ambient inference governed by a ratified profile.
- **J1 — factory invocation: (ii) staged build-requests + standing
  factory driver.** Alternative (i), a contracted factory tool wielded
  by the wright, **refused**: it would make the wright the first
  D5-nonzero staff agent and crack open the closed tool registry.
  Compile+verify are deterministic harness machinery (same pipeline as
  `run_agent`, triggered by staged build-requests), stigmergic like the
  D6 agent-source pattern (DR-CMD-078/080). DR-CMD-064 (A: hybrid for
  built agents) and AX1 (invocation through a Harness) both point at
  (ii).
- **J2 — self-diagnostic playbook:** `diagnostic_cases()` authored as
  part of the profile artifact; the driver runs it post-verify;
  all-green = the agent's own diagnostic passes. Tests commissioned
  behavior, not factory machinery (distinct from the factory's generic
  golden runs); includes refusal cases against pure decision functions
  where the role warrants one.
- **J3 — bootstrap:** the ambient authored the FIRST author-agent
  profile ("wright"); the factory built/verified it; Peter's
  instruction is the wright's standing commission. No paradox —
  mirrors how the Sextet was authored.
- **J4 — demo:** the **registrar** authored end-to-end through the loop
  (commission → governed session → staged bytes → driver → diagnose),
  hash-pinned in the authoring manifest — nothing hand-placed past
  staging.

## As-built deviation (ratified with the build)

- **Registrar D6:** spec §8 draft said {OPERATOR, AGENT}; built as
  {OPERATOR, SELF}. J-H discipline (DR-CMD-080) — bind only what the
  role needs; no built agent currently stages verified-build notices,
  so AGENT would name nothing truthful. Verdict discovery is via SELF
  sweeps of the verdict staging area (coordinator precedent). Spec §8
  updated; historical draft text preserved in DR-CMD-083.

## Ratified artifacts

- **The wright** — `core/package/authored/wright.py`, registered in
  `core/package/factory_profile_set_002.py`: staff+office, D5 0.0,
  OPERATOR-only, stage-only authorizations, D7 0.75 (fail_closed).
  3 diagnostics.
- **The registrar** — `core/package/authored/registrar.py`, registered
  in set-002: staff+office, D6 {OPERATOR, SELF}, stage-only
  authorizations, D7 0.75 (fail_closed); pure
  `registry_update_decision()`; 6 diagnostics including refusal cases.
- **`core/package/author_agent.py`** — the harness: commissions,
  governance checklist (G1–G6), hash-pinned staging, build-requests,
  standing factory driver, diagnostics runner. Zero inference inside.
- **`core/package/author_agent_golden_run.py`** — loop replay +
  refusal battery.
- **`doc/d1-d7-author-agent-spec.md`** — status RATIFIED (this record).
- Live evidence: `core/package/authored/authoring-log.jsonl` — 1
  commission, 2 sessions, 2 staged, 2 build-requests, 2 verdicts, both
  `verified`.

## Verification (final)

- **Registrar self-diagnostic: 6/6 green** — the instructed success
  criterion, met. Wright 3/3 green.
- Author-loop golden run: **6/6** (L1–L6: two replays, tamper refusal,
  archetype-gate refusal at S2, diagnostics-failure, byte-identity
  across replays).
- Factory golden run held at **183 passed / 0 violations / 4 expected
  refusals** — new files only; the DR-CMD-082-ratified factory tree
  untouched. Agent-behavior golden run 0 violations; archetype
  self-test green; set-002 both verified; bridge, updater, drive
  contract, acquisition, PVB workflow, scenario sim, playbook all
  green. Two consecutive runs byte-identical.

## Guarantees held

- **No new contracted tools.** All staff agents stay D5 = 0.0. No
  guarantee changed (J1-ii confirmed in build: driver loads staged
  bytes via importlib from the harness root; authored modules use
  absolute imports).
- **Proposer ≠ disposer throughout.** The author-agent stages profiles
  and build results; it never deploys. Deployment remains an operator
  disposition.

## Build order (recorded)

Wright profile authored → factory verified → driver built → operation.
This order is consistent with the falsification recorded in DR-CMD-083:
no runner needed to be built first. The profile is declarative and
factory-verifiable without any runner; the driver (operating loop)
was built against the verified profile, stigmergically, after it.

## Chain

DR-CMD-083 (matter opened) → DR-CMD-084 (ratified as built).
DR-CMD-059 remains reserved for the PVB Definition of Done. Next free
identifier: DR-CMD-085.
