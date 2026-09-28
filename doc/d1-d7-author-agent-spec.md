# The author-agent loop — spec (DR-CMD-083)

**Status:** RATIFIED (DR-CMD-084, 2026-09-26)
**Matter:** agent-operated factory — bootstrap an agent to author agents,
invoke the Factory to build them, run each built agent's self-diagnostic
playbook as verification of success.

## 1. Problem

The D1–D7 factory (ratified DR-CMD-082) verifies agents but operates none:
falsified 2026-09-26 — no runner exists; golden runs are harnesses; the
updater drives flows not agents; `execute --as` is spec-only; the Tetrad is
an authoring constraint, not an execution engine. Every profile to date
was authored by the ambient directly. The loop closes that gap for
*authoring*: a governed author-agent authors profiles, the Factory builds
them, their self-diagnostics verify them.

## 2. Frame (J0 — stands)

The author-agent is **harness-side**: ambient inference governed by a
ratified author-agent profile. It is not automaton-side and not an
executable: authoring requires inference, and zero inference inside
execution is a ratified hard requirement. The alternative (automaton-side
author-agent) is refused by that invariant and by DR-CMD-069's declined
generative stage. What is mechanical — commissioning records, staging,
build-requests, compile+verify, diagnostics — is deterministic harness
code with zero inference. What is inferential — drafting the profile —
happens in the ambient, *governed* by the profile (the profile is the
contract the ambient operates under, citable in review).

## 3. The loop

1. **Commission.** The operator stages a commission record: `{id, role
   brief, acceptance criteria, disposition_ref}`. Nothing is authored
   without one (proposer≠disposer: the ambient proposes, the operator
   commissioned).
2. **Author.** The ambient, governed by the wright profile (§5), drafts
   the profile module: builder function, declared archetypes,
   `diagnostic_cases()`, rationale (judgment calls) as staged prose.
   Governance checklist (§6) is recorded as satisfied-or-refused.
3. **Stage.** The authored bytes are written to the harness's
   `authored/` area with a hash-pinned authoring manifest
   (commission → bytes hash → rationale). The bytes are *proposed*, not
   trusted.
4. **Drive.** The standing factory driver — deterministic harness
   machinery, the same validate→compile→verify pipeline as `run_agent`,
   triggered by staged build-requests instead of a hardcoded list —
   loads the staged bytes, runs archetype gate → personalization
   binding → compile → verify, and stages the verdict. (J1: this, not a
   contracted factory tool. Agents stay D5 = 0.0; compile+verify are
   harness machinery per DR-CMD-064 A and AX1; the pattern is
   stigmergic — build-requests ride the staging medium, mirroring the
   D6 agent source.)
5. **Diagnose.** The driver runs the profile's own `diagnostic_cases()`
   post-verify. All-green = the agent's self-diagnostic passes — the
   instructed success criterion. (J2.)
6. **Dispose.** Deployment of the built agent remains an operator
   disposition. The author-agent never deploys (stage-only).

Deterministic replay: authored bytes are hash-pinned in the manifest;
the loop re-runs mechanically on pinned bytes (commission → stage →
drive → diagnose) with no inference.

## 4. Factory-invocation (J1 — chosen: staged build-requests + driver)

- (i) Contracted factory tool — refused for this matter: it would make
  the wright the first D5-nonzero staff agent and add compile/verify to
  the closed tool registry, extending what the machine guarantees for
  no mechanical need.
- (ii) Staged build-requests + standing factory driver — chosen. The
  driver is harness code (a generalized `run_agent`); it introduces no
  new agent capabilities and no new tools. One-shot mode
  (`run_factory_driver_once`) serves verification; standing operation
  is an operator-run loop, out of scope for this matter.

## 5. The wright profile (J3 — bootstrap)

`wright` — agent-profile author. Staff + office (author precedent):
D1 0.0 per-event, D2 principal_wins_ties (artifacts track the
commission), D3 0.5 (authoring is inferential; replay_supported),
D4 1.0, D5 0.0 (empty write_scope — build-requests are staged, J-A),
D6 {OPERATOR} authenticated-session, stage-only; D7 0.75,
fail_closed (a failed verification halts the loop — no artifact
leaves on a failed check, author precedent). Bootstrap: the ambient
authors the wright first (this spec's §5 is its contract); the factory
builds/verifies it; Peter's instruction is its standing commission.

## 6. Authoring governance checklist

Recorded per authoring session; a missed item refuses the session:

- G1 commission exists and is operator-attributed.
- G2 declared archetypes conform (mechanical gate).
- G3 profile validates with zero warnings (mechanical).
- G4 rationale staged (judgment calls as prose, not hidden).
- G5 stage-only: no deployment, no commit, no push by the author-agent.
- G6 diagnostics authored alongside (J2) — a profile without its own
  diagnostic cases is incomplete.

## 7. Self-diagnostic playbook (J2)

`diagnostic_cases()` in the authored module returns a list of
`(case_id, predicate)` pairs; each predicate takes a context
`{profile, artifact, verdict}` and returns `(passed, detail)`.
Kinds: facet checks (the commissioned shape holds), artifact checks
(the build carries what the commission required), refusal checks
(against pure decision functions where the role warrants one — e.g.
the registrar refuses registry updates for unverified agents).
The driver runs them post-verify; any failure fails the loop. These
test the *agent's commissioned behavior*, not factory machinery
(that is the golden runs' job).

## 8. Demo scope (J4)

One agent end-to-end: the **registrar** — stages registry-update
proposals when a built agent verifies (the registry DR-CMD-078's
authenticated-agent gating attests against: "author is a verified
built agent"). Staff + office, D6 {OPERATOR, SELF} (commissioned
registry policy + scheduler-cadence sweeps of the verdict staging
area), stage-only, D7 0.75 fail_closed (registry integrity: never
stage an update for an unverified agent — refusal with reasons
instead). **As-built deviation:** the draft said {OPERATOR, AGENT};
built as {OPERATOR, SELF} per J-H discipline — no built agent
currently stages verified-build notices, so AGENT would name nothing
truthful; SELF sweeps discover verdicts. Honesty rule: the
registrar's bytes flow commission → author → stage → driver →
diagnose; the authoring manifest pins every step.

## 9. Guarantees

Changed by this matter: none — no new tools, no D5 change, no new
agent capabilities. The driver and diagnostics runner are harness
machinery (same trust class as the golden runs). Proposer≠disposer
holds throughout: the author-agent proposes (profiles, build
results); the factory verifies (mechanically); the operator disposes
(commissions, deployments).

## Glossary

- **author-agent**: harness-side ambient inference governed by a
  ratified authoring profile; authors agent profiles. Not an
  executable.
- **wright**: the author-agent's profile name — agent-profile author
  (staff + office).
- **registrar**: the demo agent — stages registry-update proposals
  for verified built agents (staff + office).
- **commission**: an operator-attributed record authorizing one
  authoring task (role brief, acceptance criteria, disposition ref).
- **factory driver**: deterministic harness machinery running
  validate→compile→verify on staged build-requests.
- **build-request**: a staged record asking the driver to build one
  authored profile.
- **self-diagnostic playbook**: `diagnostic_cases()` authored with
  the profile; run post-verify; all-green is the success criterion.
- **authoring manifest**: hash-pinned record of
  commission → bytes → rationale → verdict → diagnostics.
- **stigmergic**: coordination through a shared medium (staging),
  never direct triggering — the D6 agent-source pattern.
