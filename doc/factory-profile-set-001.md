# Factory Profile Set 001 — six agents through the D1–D7 factory

**Status:** built and verified 2026-09-26 (ambient run); the six-profile
set and the org-function labels **ratified by Peter 2026-09-26
(DR-CMD-068)**. D6 `agent` source added and coordinator-bound the same day
(DR-CMD-078, build uncommitted — **build RATIFIED as built, DR-CMD-082
(Item 10, 2026-09-26)**).
Profiles specified by Peter; constructed, compiled, and verified by the
step-5 machinery (`core/package/factory_profile_set_001.py`). `monitor`
(the afferent-relay mediation cell) was added later the same day,
completing the 2×2 mediation grid. `coordinator` (inter-agent mediation,
the F1 gap-filler) was added the same day (individually ratified,
DR-CMD-067).

**Labels (org-function theme, DR-CMD-068):** analyst (was diverge),
advisor (was converge), author (unchanged), executor (was execute),
monitor (was sentinel), coordinator (unchanged). Label-only rename
2026-09-26: no facet, vector, or verification-logic change. Artifact
hashes changed with the labels (expected) and were re-verified
deterministic post-rename.

**Pipeline per agent:** validate (schema C1–C5, C7 — C6 retired, DR-CMD-077 — + derived positions, zero
warnings asserted) → compile (`compile_profile`: profile → build plan →
agent artifact) → verify (`verify`: build → probe → check). All six
reached verdict **`verified`** / operable. No `refused`, no `failed` —
there are no findings to report beyond F1-CONFIRMED below; the judgment
calls are the only discretionary content, and each is documented, not
hidden.

**Non-negotiable held:** proposer ≠ disposer — no agent disposes.
`advisor` "deciding" = drafting proposed verdicts staged for operator
disposition; `executor` actuates only disposed or standing-disposition
actions; `monitor` watches and alerts but never acts; `coordinator`
arbitrates conflicts as *proposed* resolutions staged for operator
disposition — it never disposes a conflict itself. D5 write_scope is
contracted tools only (the compiler's closed registry, J1). D6: every
enabled source carries an explicit gate and an explicit authorization.
D4 fully on for all six.

## Position vectors (derived from facets, DR-CMD-062; D2 categorical, DR-CMD-077)

| agent       | D1   | D2                  | D3  | D4  | D5   | D6   | D7   | verdict    |
|-------------|------|---------------------|-----|-----|------|------|------|------------|
| analyst     | 0.0  | world_wins_ties     | 0.5 | 1.0 | 0.0  | —    | 1.0  | verified   |
| advisor    | 0.0  | principal_wins_ties | 0.5 | 1.0 | 0.0  | —    | 0.75 | verified   |
| author      | 0.0  | principal_wins_ties | 0.5 | 1.0 | 0.0  | —    | 0.75 | verified   |
| executor     | 0.25 | principal_wins_ties | 0.0 | 1.0 | 0.4  | —    | 1.0  | verified   |
| monitor    | 0.0  | world_wins_ties     | 0.0 | 1.0 | 0.0  | —    | 1.0  | verified   |
| coordinator | 0.0  | principal_wins_ties | 0.5 | 1.0 | 0.0  | —    | 0.75 | verified   |

D2 is the binary enum {principal_wins_ties, world_wins_ties} (DR-CMD-077) —
no scalar. D6 is structural (no scalar) for all; the coordinator binds the
`agent` source (DR-CMD-078). Artifact hashes (sha256,
prefix, post-DR-CMD-078 2026-09-26):
analyst `2bce53a24badd872`, advisor `607d4fee015ae507`,
author `2a9b55174b0f8c16`, executor `342657626cb32f2f`,
monitor `4e7751b4bdfa066e`, coordinator `41ccd6690bfdd1ec`
(byte-identical across repeat runs; the D6 agent-source schema change —
SCHEMA_VERSION 1.1 → 1.2 — altered every profile's bytes, so pre-DR-CMD-078
hashes are superseded).
Static checks: 19–30 per agent, all passed. Probes: 10 per agent
(P-D6-trigger, P-D5-scope, P-D1-disposition, P-D7-boundary, P-D4-trace,
P-D3-replay, P-D2-fidelity, P-Q2-routing, P-C1, P-C3), all passed.
Advisories: none on any agent.

## analyst — cognitive-assist: ideate, research, observe

- **D1 0.0** — per-event disposition, no standing dispositions: every
  research output is a staged proposal; nothing is pre-authorized.
- **D2 world_wins_ties** — honest research: when the principal's
  hypothesis conflicts with evidence, evidence wins the tie.
- **D3 0.5** — stochastic inference (temperature), replayable runs.
- **D4 1.0** — full event/intent/verification streams; inspectors
  operator + auditor; retention forever.
- **D5 0.0** — broad reads (web-search, arxiv, docs-library, code-repos,
  event-log, accretion-repo); **empty write_scope**: research notes are
  staged proposals, not tool effects (see J-A).
- **D6** — operator (authenticated-session / stage-only) + world
  (allowlist + signature / stage-only; no self-commit).
- **D7 1.0, escalate** — all four trust boundaries verified; failed
  verification escalates the finding rather than dropping or blocking
  the research.

Compiler: ok. Verifier: `verified`, operable, 22 static / 10 probes green.

## advisor — cognitive-assist: decide, design, synthesize

- **D1 0.0** — per-event disposition, no standing dispositions:
  "decisions" are draft verdicts staged for the operator; the agent
  never disposes.
- **D2 principal_wins_ties** — draft verdicts track the principal's
  intent at ties; world input informs but does not override it.
- **D3 0.5** — stochastic synthesis, replayable runs.
- **D4 1.0** — full instrumentation, as analyst.
- **D5 0.0** — reads staged proposals (staging-area, accretion-repo,
  event-log, disposition-records); **empty write_scope**: draft verdicts
  are staged proposals (see J-A).
- **D6** — operator (authenticated-session / stage-only) + self
  (scheduler-cadence; ambient-staging-only / stage-only; no self-commit):
  scheduled rollups may synthesize, never self-dispose (see J-D).
- **D7 0.75, escalate** — intent, event, and trigger boundaries verified
  (no world target: advisor reads harness-internal staged proposals,
  not raw world claims); failures escalate.

Compiler: ok. Verifier: `verified`, operable, 21 static / 10 probes green.

## author — mechanical-assist: spec, code, generate

- **D1 0.0** — per-event disposition, no standing dispositions: artifacts
  are generated into staged proposals for review; the author never
  commits (proposer ≠ disposer).
- **D2 principal_wins_ties** — the artifact implements the principal's
  intent at ties.
- **D3 0.5** — stochastic generation, replayable runs.
- **D4 1.0** — full instrumentation, as analyst.
- **D5 0.0** — reads staging-area, accretion-repo, disposition-records,
  spec-library; **empty write_scope**: specs/code are staged proposals
  (see J-A).
- **D6** — operator only (authenticated-session / stage-only): generation
  happens on request, never on a schedule.
- **D7 0.75, fail_closed** — intent, event, trigger boundaries verified;
  a failed intent check halts: no artifact leaves on failed verification.

Compiler: ok. Verifier: `verified`, operable, 19 static / 10 probes green.

## executor — mechanical-assist: run, remedy, report, audit

- **D1 0.25** — per-event disposition **plus** standing dispositions
  `tool-run-doctor` and `tool-verify-checksum` (registered tool ids, so
  J2 resolves them direct): routine checks are pre-authorized;
  installer/promotion effects are per-event (disposed) only.
- **D2 principal_wins_ties** — executes disposed intent, full stop.
- **D3 0.0** — deterministic execution, replay supported: the acting
  agent is the reproducible one.
- **D4 1.0** — full instrumentation, as analyst.
- **D5 0.4** — four contracted-tool write channels (tool-invoke-installer,
  tool-run-doctor, tool-record-promotion, tool-commit-accretion); reads
  disposition-records, event-log, accretion-repo, policy-config.
- **D6** — operator (authenticated-session / may-act on disposition) +
  world (allowlist + signature / may-act within standing dispositions,
  otherwise stage-only) + self (scheduler-cadence / may-act within
  standing dispositions, otherwise stage-only): the dsys three-source
  shape, fitted to an acting agent.
- **D7 1.0, fail_closed** — all four boundaries verified; failed
  verification halts actuation: the strong-D7 acting agent.

Compiler: ok. Verifier: `verified`, operable, 30 static / 10 probes green.
P-Q2-routing confirms: single bound tool calls go direct; multi-step
sequences draft a governed flow, staged and never executed — including
for standing-disposition classes (unseen flow structure is never
pre-authorized).

## monitor — mediation-assist: watch, alert (afferent-relay)

- **D1 0.0** — per-event disposition, no standing dispositions: every
  alert is a staged proposal for operator disposition; the monitor
  never acts and never disposes.
- **D2 world_wins_ties** — split by aspect (see J-E): D2 adjudicates
  ties between principal and world on the *reading* — whether the watched
  target changed — and there the world wins. An honest watch reports
  evidence, not wishes. *What* to watch is not a D2 tie: it is the
  commission afferent, authenticated by D7 intent_target.
- **D3 0.0** — deterministic execution, replay supported: watch
  evaluation is a pure function of prior reading + new reading. The
  reproducible watcher.
- **D4 1.0** — full instrumentation, as analyst.
- **D5 0.0** — reads watch-targets, event-log, accretion-repo,
  disposition-records; **empty write_scope**: alerts are staged
  proposals (see J-A).
- **D6** — operator (authenticated-session / stage-only) + world
  (allowlist + signature / stage-only; no self-commit): the commission
  defines the watch; the world supplies the change signal; both are
  stage-only, so a watch can never self-actuate.
- **D7 1.0, fail_closed** — all four boundaries verified; an
  uncorroborated change is never staged as an alert (no false alarms
  into the disposition queue). The verification failure is staged as a
  watch-health disclosure — a different kind from a change alert — and
  watching continues.

Compiler: ok. Verifier: `verified`, operable, 22 static / 10 probes green.
Determinism confirmed: byte-identical artifact hash across repeat runs.

## coordinator — mediation-assist: inter-agent mediation (F1 gap-filler)

Ratified by Peter 2026-09-26 (DR-CMD-067). Routes staged findings to
downstream consumers, arbitrates conflicting staged proposals from
multiple agents, sequences multi-agent pipeline work.

- **D1 0.0** — per-event disposition, no standing dispositions:
  arbitration outputs are *proposed* resolutions (draft-verdict kind)
  staged for operator disposition; the coordinator never disposes a
  conflict itself (proposer ≠ disposer).
- **D2 principal_wins_ties** — routing and arbitration follow the
  principal's commission and pipeline wiring (the advisor precedent).
- **D3 0.5** — stochastic judgment, replayable runs (the advisor
  precedent): arbitration involves judgment.
- **D4 1.0** — full instrumentation, as analyst.
- **D5 0.0** — reads staging-area, accretion-repo, disposition-records,
  pipeline-config, event-log; **empty write_scope**: routing decisions
  and arbitration drafts are staged proposals (see J-A).
- **D6** — operator (authenticated-session / stage-only: commissioned
  routing rules) + self (scheduler-cadence; staging-area sweeps /
  stage-only; no self-commit): the coordinator's true afferent is other
  agents' staged proposals, which D6 cannot name — see F1-CONFIRMED.
- **D7 0.75, escalate** — intent, event, and trigger boundaries verified
  (no world target: the coordinator reads harness-internal staged
  proposals, the advisor precedent). Failures escalate (see J-F): the
  draft is staged with the verification caveat disclosed, so the
  operator disposes with eyes open.

Compiler: ok. Verifier: `verified`, operable, 21 static / 10 probes green.
Determinism confirmed: byte-identical artifact hash across repeat runs.

## Judgment calls (mine, documented in the module)

- **J-A — empty write_scope for analyst/advisor/author.** The closed
  contracted-tool registry (compiler J1, pinned in FactoryVersion)
  contains no artifact-writing tool; invented channel names are refused
  at routing, and the `contracted-tools-only` alias would grant
  installer/promotion tools these agents must never touch. Their work
  product — notes, draft verdicts, specs/code — *is* their staged
  proposals: generation is realized by the accretion-backed staging area
  (DR-CMD-065), not by tool effects. All three verify with D5 = 0.0.
- **J-B — D2.** analyst is world-wins-ties; advisor/author/executor are
  principal-wins-ties. (DR-CMD-077: the former scalar gradations retired;
  the advisor/author thin separation is moot — both are principal-wins-ties.)
- **J-C — executor's standing dispositions name tool ids**, so they route
  direct; heavier effects stay per-event.
- **J-D — advisor's self source is stage-only**, so scheduled rollups
  can synthesize without ever self-disposing.
- **J-E — monitor's D2.** `world_wins_ties` (the analyst precedent)
  governs the *reading*: when the principal's
  belief conflicts with the evidence of change, evidence wins. *What* to
  watch is the commission afferent, not a D2 tie — authenticated by D7
  intent_target. D7 on_failure is `fail_closed` rather than `escalate`:
  the monitor's value proposition is filtering, so an uncorroborated
  change must not reach the disposition queue as an alert; it is
  suppressed, and the verification failure is staged separately as a
  watch-health disclosure while watching continues.

- **J-F — coordinator's D7 on_failure is `escalate`** (the advisor
  precedent) rather than `fail_closed`: the coordinator's entire output
  is a proposed resolution staged for operator disposition anyway, so
  the draft is staged *with* the verification caveat disclosed — the
  operator disposes with eyes open rather than receiving a silent
  suppression.

## Findings

- **F1-CONFIRMED — the inter-agent-afferent gap is mechanically real.**
  D6's source enum was exactly {operator, world, self}; there was no
  "agent" source. The coordinator's true afferent — other agents'
  staged proposals — was therefore carried on SELF (staging-area sweeps)
  + OPERATOR (commissioned routing rules), both stage-only. This
  mislabeling was documented as a finding, not a defect: adding a D6
  "agent" source was a schema change requiring separate ratification
  and was NOT made here (see DR-CMD-067).
  **AMENDMENT 2026-09-26 (DR-CMD-078):** Peter ratified OPEN NOW — the
  coordinator must operate autonomously upon state changes. The enum now
  carries `agent` (activation by another built agent's staging state
  change, observed through the staging medium — stigmergic trigger,
  through staging never around it); the coordinator binds it with
  authenticated-agent gating (chain verifies + author is a verified built
  agent) and stage-only authorization, keeping the SELF cadence as
  reconciliation backstop. F1 is implemented; see
  `doc/d1-d7-d6-agent-source-spec.md`.

No refused or failed verdicts; no warnings; no advisories. F1-CONFIRMED
was the only finding (now implemented per DR-CMD-078); the judgment calls
above are the complete record of discretion exercised.
