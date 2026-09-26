# DR-CMD-067 — coordinator profile ratified

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~08:44 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *the 'coordinator' agent profile* — inter-agent mediation:
  routing staged findings to downstream consumers, arbitrating
  conflicting staged proposals from multiple agents, sequencing
  multi-agent pipeline work. Identified as the ensemble gap in the
  five-profile orthogonality/coherence evaluation (five mediators, no
  coordinator); the F1 gap-filler.

## Decision

**ADOPTED — the coordinator profile is ratified as built.** Facet
choices and derived position vector (DR-CMD-062; positions derived,
never hand-set):

| D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|----|----|----|----|----|----|----|
| 0.0 | 0.2 | 0.5 | 1.0 | 0.0 | structural | 0.75 |

- **D1 0.0** — per-event disposition, no standing dispositions.
  Arbitration outputs are *proposed* resolutions (draft-verdict kind)
  staged for operator disposition; the coordinator never disposes a
  conflict itself.
- **D2 0.2, intent_wins_ties** — routing and arbitration follow the
  principal's commission and pipeline wiring (the converge precedent).
- **D3 0.5** — arbitration involves judgment (the converge precedent).
- **D4 1.0** — full event/intent/verification streams.
- **D5 0.0** — empty write_scope: routing decisions and arbitration
  drafts are staged proposals (the J-A precedent).
- **D6** — operator (commissioned routing rules) + self (staging-area
  sweeps), both stage-only with explicit gates and authorizations.
- **D7 0.75, escalate** — intent, event, trigger boundaries verified
  (no world target: harness-internal reads, the converge precedent);
  failures escalate with the caveat disclosed (J-F).

## Verification evidence

Run through the step-5 machinery
(`core/package/factory_profile_set_001.py::run`):

- Verdict: **`verified`**, operable. 21/21 static checks passed; 10/10
  probes green (P-D6-trigger, P-D5-scope, P-D1-disposition, P-D7-boundary,
  P-D4-trace, P-D3-replay, P-D2-fidelity, P-Q2-routing, P-C1, P-C3);
  **zero warnings**, zero advisories.
- Deterministic: byte-identical artifact hash across repeat runs
  (sha256 prefix `6f9acf8b20225331`).

## F1 status

The inter-agent-afferent gap is **acknowledged and mechanically
confirmed** (F1-CONFIRMED): D6's source enum is exactly
{operator, world, self} — there is no "agent" source. The
coordinator's true afferent (other agents' staged proposals, read via
the accretion-backed staging area) is therefore carried on SELF +
OPERATOR, both stage-only. This mislabeling is documented as a finding,
not a defect.

**The D6 "agent" source is NOT added by this record.** Extending the
source enum is a schema change requiring separate ratification; it is
deferred, explicitly not ratified here.

## Consequences (per G4)

- The coordinator joins the verified profile set
  (`core/package/factory_profile_set_001.py`, `PROFILE_SET_001`);
  `doc/factory-profile-set-001.md` records its vector, rationale,
  verdict, and findings.
- The profile-set document's "unratified as a set" status is unchanged:
  this ratification covers the coordinator profile only, not the set
  as a whole, and not the factory implementation or step-6 sufficiency
  (reserved for step 7).

## Uncertainties (G6)

- Whether to add a D6 "agent" source (or a D7 provenance target) is
  deferred to a future matter; the coordinator's self/operator
  mislabeling stands as the mechanical evidence motivating it.
- Inter-agent arbitration policy (how conflicting proposals are
  weighted) is commission-defined at run time; no standing arbitration
  rule is ratified here.

## Identifier discipline

- DR-CMD-067 consumed by this record. DR-CMD-059 remains earmarked for
  the PVB Definition of Done — **not consumed**.
- Next disposition identifier: **DR-CMD-068**.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the matter
only): this record; `core/package/factory_profile_set_001.py`
(coordinator builder + J-F + F1-CONFIRMED); `doc/factory-profile-set-001.md`
(coordinator row/section/findings). Commit and push return as follow-on
dispositions.
