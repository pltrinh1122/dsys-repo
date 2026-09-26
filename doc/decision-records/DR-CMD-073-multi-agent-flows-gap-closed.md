# DR-CMD-073 — multi-agent flows coverage gap closed

- **Status:** implemented; evidence presented for acceptance
- **Date:** 2026-09-26 ~11:00 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** authorize (Peter: "close the gap"); acceptance of the
  evidence below closes factory step-7 run-through item 6
- **Matter:** *the DR-CMD-072 standing gap* — coordinator arbitrating live
  staged proposals from other actors mid-flight was unexercised by any
  suite.

## Disposition

Peter disposed "close the gap" on the coverage hole named in DR-CMD-072's
consequences: coordinator *routing* was covered per-actor (C-coordinator-*),
but no suite exercised the coordinator arbitrating live staged proposals
from other actors. The M-* battery in `core/package/factory_golden_run.py`
now does.

## Flow design (what the battery exercises)

`CoordinatorSweepDriver` — deterministic reference machinery in the golden
run, NOT a shipped factory component (the factory builds agents; it does
not operate them, DR-CMD-061):

1. **Fixtures:** analyst stages a finding, monitor stages a corroborating
   reading, advisor stages a draft verdict — each through the real
   `StagingArea` into one shared accretion-backed writer, and each from a
   verified build (analyst, monitor, advisor, coordinator all
   compile→verify→`verified` in M1).
2. **Sweep** (self source): the driver reads the staging file, ingests
   pending proposals from other actors. Disposed proposals are excluded;
   the coordinator's own prior arbitrations are history (referenced via
   `supersedes`), not re-arbitrated as inputs.
3. **Route/sequence** (operator source): the authored
   `COMMISSIONED_ROUTING` table (AP-A3 commission afferent, fixture) ranks
   finding → corroboration → draft-verdict → operator.
4. **Arbitrate:** group by `claim_id`; conflicting verdicts produce a
   proposed resolution staged WITH the caveat disclosed (J-F: escalate
   stages with eyes open, never suppresses, never disposes).
5. **Stage:** the arbitration is staged as a coordinator proposal,
   disposition `pending`.

**Driver-vs-flow judgment (documented in code):** a deterministic driver,
not an AutomatonFlow. DR-CMD-064's discriminator routes *governed
workflows* (intermediate observation, inter-step guards, unit replay)
through flows; this pipeline is a total function over the sweep — no
branching on observations, no guards, no replay — so a driver suffices.
If arbitration ever needs to branch on untrusted proposal content, it
graduates to an AutomatonFlow.

**Determinism claim:** arbitration inputs are ordered by (routing rank,
content hash); payloads carry no sequence numbers, so the content hash is
arrival-order-independent. M2 stages the same three fixtures in all 6
arrival orders across fresh roots and asserts byte-identical arbitration
payloads. M1 repeats the full pass on a fresh root and asserts
byte-identity.

## The F1 gap, mechanical (M6)

D6 has no `agent` source. The battery asserts the coordinator's profile
sources are exactly `{operator, self}` AND that the arbitration it produced
cites its afferent path as `["self:staging-sweep",
"operator:commissioned-routing"]` — the inter-agent afferent (other actors'
staged proposals) riding self+operator, mechanically confirmed in-flow.

## Coverage (M-*)

- **M1** (14 checks): verified builds → fixtures → sweep → arbitrate →
  stage. Inputs ingested, commissioned order applied, routing table
  applied, no conflicts, arbitration `pending`, inputs still pending, zero
  disposition records, zero tool effects, chain intact, coordinator write
  allowlist empty, repeat-run byte-identical.
- **M2** (1 check): 6 arrival orders → identical arbitration.
- **M3** (4 checks): late analyst finding mid-flow → deterministic
  re-sequence; new arbitration declares `supersedes` on the old one's
  content hash; the old record is byte-unchanged in the file (accretion:
  superseded by staging, never rewritten); nothing disposed.
- **M4** (4 checks): analyst "supported" vs advisor "rejected" on claim-x
  (monitor corroborates) → one conflict entry, all three proposals party
  to it, verdicts split 2–1, proposed resolution staged with the caveat
  ("coordinator proposes, operator disposes"), conflict never disposed.
- **M5** (1 check): the disposition-shaped temptation — a `may-act`
  routing rule — refuses at `[staff/S4]` at the authoring gate, before
  compile. It cannot be authored.
- **M6** (2 checks): F1 mechanical (above).

## Verification evidence (observed 2026-09-26, three consecutive runs)

- `factory_golden_run`: **ok=true, 138 passed** (was 112; +26 M-*),
  **0 violations, 5 expected refusals** (unchanged: A2a–A2d, C-analyst-c6)
- `factory_profile_set_001`: 6 verified, 0 warnings (exit 0)
- `factory_archetypes` self-test: ok
- Regression suites all green: agent_behavior, bridge, updater,
  drive_contract, acquisition, pvb_workflow (ok=true); scenario_sim,
  playbook golden run (exit 0)
- Tree uncommitted; no git operations performed

One check was corrected during the build (not an implementation change):
M4-parties initially asserted 2 parties; the driver correctly reports all
three proposals on the conflicted claim as parties with the verdicts split
2–1 in the `verdicts` map — the check was fixed to the implementation's
documented semantics.

## Consequences

- The DR-CMD-072 standing gap is closed: coordinator arbitration of live
  staged proposals is now exercised — fixtures, sweep, arbitration,
  late-arrival re-sequencing, conflict with disclosed caveat,
  disposition-temptation refusal, and the F1 afferent path, all green and
  deterministic.
- Factory step-7 run-through item 6 (step-6 coverage) is now complete on
  the evidence above, **pending Peter's acceptance**. Remaining open
  run-through items: the two build-time judgment calls (item 5), the
  factory self-profile (item 7), the defect deferrals (item 9), and the
  final ratify-or-amend (item 10).
- Next free identifier: **DR-CMD-074** (DR-CMD-059 still earmarked for the
  PVB Definition of Done).

## Glossary

- **M-* battery:** the multi-agent flow cases in `factory_golden_run.py`
  (DR-CMD-073): coordinator arbitration coverage.
- **CoordinatorSweepDriver:** the golden run's deterministic reference
  drive for coordinator arbitration — sweep → route/sequence → arbitrate →
  stage. Reference machinery, not a shipped factory component.
- **Commissioned routing rules:** the operator-source (AP-A3) routing
  table fixture the driver sequences by; authored, not inferred.
- **Content hash:** sha256 over a payload's canonical JSON; payloads carry
  no sequence numbers, so identical content hashes identically regardless
  of staging order — the basis of the M2 order-independence claim.
- **Superseded by staging:** a re-arbitration declares `supersedes` on the
  prior arbitration's content hash and stages anew; the prior record is
  never rewritten or disposed (accretion).
