# Countersign mapping — dsys onto the Countersign core schema

- **Status:** authored under dyad-system d-work #156 (PR-C); a projection, not a model change
- **Date:** 2026-09-24
- **Code:** `core/package/countersign_map.py` (`to_countersign(state) -> dict`, `validate`, `check`),
  `core/package/countersign_map_golden_run.py`
- **Schema:** `core/package/countersign-core.json`, a pinned copy of dyad-system
  `crafts/countersign/templates/countersign-core.json` (commit `8302027`, branch
  `craft/156-countersign`)
  - version `0.1.0`
  - sha256 `647ef7d5c6e007a0584c39d78eecaa1f43b7b47cfc63223ad9f716c1fbc9ab1b`

  Both values are recorded in the module (`PINNED_SCHEMA_VERSION`, `PINNED_SCHEMA_SHA256`). The
  golden run fails when the copy's sha256 or version differs.
- **Run:** `cd core && python -B -m package.countersign_map_golden_run` (exit 0 = ok)

## Purpose
The Countersign core is one logical schema of eight entities, defined in the dyad-system craft
`crafts/countersign/` (`rules/schema.md`). Both dyad-system and dsys project their own stores onto
it; neither migrates storage (F7). This document is dsys's column of the mapping contract (F1–F7).

The mapping keeps dsys's pydantic model unchanged:
- no field is renamed;
- no enum changes;
- no golden run moves.

Everything the core needs but dsys does not store is **derived by a stated rule** (F3). The
mapping's output passes the same `validate()` and `check()` as the craft's projector; the module
mirrors both, using the stdlib only.

## Mapping table

| dsys entity | Countersign entity | rule |
|---|---|---|
| `Human` | Party, `kind: human` | P1 |
| `Agent` | Party, `kind: agent` | P1 |
| (any `AutomatonRun` or `FlowRun`) | Party `party-executor`, `kind: executor` | P1 |
| `DecisionRecord` | Act (explicit) and Proposal `proposal-dr-<id>` | A1, R1 |
| `HarnessRun` | Act (explicit, or implicit under standing authority) | A2 |
| `AutomatonRun`, `FlowRun` | Act (automatic, processor = executor) | A3 |
| `Proposal` (+ `RatificationRecord` verdict as state) | Act (synthesized) and Proposal `proposal-pr-<id>` | A4, R1 |
| `Disposition` (CTA put up, not triage) | Proposal `proposal-disp-<id>`, unless a DecisionRecord carries it | R1 |
| `Disposition` (decided or answered) | Countersignature | C1, C2 |
| `Disposition` with `mode: set_standing`, answered yes | Mandate | M1 |
| `AutomatonRelease`, joined with `PromotionRecord.disposition_id` | Release | L1 |
| `AutomatonEvent` | Event (of its run's act) | E1 |
| `FlowTransitionEvent` | Event (of its flow run's act) | E1 |
| `Disclosure` | Escalation, opening the triage act | X1 |
| validators / `try_*` gates | Check (`timing: after` / `before`) | F6 |

Ids take the form `<entity>-<kind>-<dsys id>`: lower-cased, with every run outside `[a-z0-9.-]`
replaced by `-`. Every instance's `profile` carries `dsys_collection` and the original `dsys_id`.
Arrays are sorted by id (numeric runs compared as numbers). There is no clock, so the output is
byte-identical for the same state.

## Derivation rules (F3)
Neither `mode` nor `processor` is a stored dsys field. Both come from the entity **type** and its
links.

### Parties
- **P1:**
  - every Human becomes a `human` party;
  - every Agent becomes an `agent` party;
  - one `executor` party exists iff any AutomatonRun or FlowRun exists.

### Acts
- **A1:** a DecisionRecord is an explicit act; its processor is its `proposer_id`.
- **A2:** a HarnessRun is an explicit act; its processor is its dyad's agent. It is **implicit**
  instead iff a Directive targeting the run cites an in-force `set_standing` disposition (one
  answered yes). The run then proceeds under standing authority rather than a live per-act
  countersignature.
  - This is a stated inference: dsys records no other link from a run to a standing policy.
- **A3:** an AutomatonRun or a FlowRun is automatic; its processor is the executor.
- **A4:** a dsys Proposal gets a synthesized explicit act, `act-proposal-<id>`.
  - Its state is its RatificationRecord verdict, or `draft` when it has none.
  - Its processor is its dyad's agent.
- **A5 / A6 (the act of a disposition), first match wins:**
  1. a DecisionRecord whose `disposition_id` names it;
  2. a Directive citing it (the act is the target HarnessRun);
  3. for an overrule, its veto, then the veto's directive, then that directive's target run;
  4. a PromotionRecord citing it (the act is the HarnessRun that produced the artifact);
  5. otherwise, a synthesized explicit act `act-disp-<id>`, processed by the proposer, with
     `profile.synthesized: true`.

### Proposals
- **R1:**
  - A DecisionRecord gives `proposal-dr-<id>` (the options put up).
  - A non-triage Disposition not carried by a DecisionRecord gives `proposal-disp-<id>` (the CTA
    put up):
    - `body_ref` is `action_ref`;
    - `artifact_hash` is `state_ref`.
  - A dsys Proposal gives `proposal-pr-<id>`.
  - The author is always the proposing agent.

### Countersignatures
- **C1:** every Disposition that is **decided** (status `approved`, `rejected` or `acted`) or
  **answered** (it has a `response`) maps to a countersignature. The answered case is included
  because a counter keeps status `proposed` (E3).
  - `answer`:
    - from the CTA response: `yes` → `yes`, `no` → `no`, `counter` → `amend`;
    - with no response, from the status: `approved` or `acted` → `yes`, `rejected` → `no`
      (`profile.answer_source: status`).
  - `signer` is the disposer.
  - `text` is the disposition text, verbatim; `counter_text` is kept in the profile.
  - `bound_hash` is `state_ref`.
  - `at` is `""` (dsys has no clock).
  - `subject`: for a triage, the escalation of its `disclosure_ref`; otherwise the R1 proposal.

### Basis: the DispositionMode rename (F4)
- **C2:** dsys's `DispositionMode` uses the word **mode** for what Countersign calls a
  countersignature's **basis** (its kind). Countersign's *mode* (explicit, implicit, automatic)
  is a property of an **act**.

  The rename happens **at this boundary only**. `schema.py` is unchanged, and the glossary marks
  `DispositionMode` as a disposition *kind*.

  | `DispositionMode` | `basis` |
  |---|---|
  | `set_standing` | `mandate` |
  | `authorize`, when a PromotionRecord cites the disposition | `release` |
  | `authorize` (otherwise), `ratify`, `overrule`, `triage` | `per-act` |

  The original value is kept in the countersignature's `profile.disposition_mode`. A mapping that
  wrote a `DispositionMode` value into `basis` fails the schema's enum. The golden run's refusal
  R3 exercises this.

### Mandates, releases, events, escalations
- **M1:** a `set_standing` disposition answered yes is a Mandate.
  - `scope.event_class` is `standing_domain`.
  - `scope.rights` is `[standing_domain]`.
  - `plan_template` and `budget` are null; dsys stores neither.
  - The profile names its `supersedes` and `superseded_by` dispositions.
- **L1:** an AutomatonRelease is a Release.
  - Its countersignature is the one of the disposition cited by the PromotionRecord with the
    same `release_version`.
  - `definition_ref` is `dsys:artifacts/<ids>`.
  - `hash` is the artifacts' `content_hash`.
  - The profile lists the run-books and flows pinned to the version.
- **E1:** an Event keeps its `seq`.
  - `at` is `seq:<n>`, because dsys has no clock (`[DR-5/A1]`).
  - The payload is the event's kind and payload, or, for a FlowTransitionEvent, the transition
    fields.
- **X1:** a Disclosure is an Escalation.
  - It comes `from` `ext:dsys-disclosure-<id>`, because dsys records no originating act.
  - It opens the act of the triage disposition that cites it, or nothing while it is untriaged.

## Checks the mapping must pass
These mirror the craft's `project_countersign.check`:
1. The document matches the pinned schema, using the stdlib subset of JSON Schema. An unknown
   keyword is an error, not silently ignored.
2. Every id is unique, and every reference resolves.
3. An act's processor has the kind its mode requires: an agent for explicit and implicit, the
   executor for automatic.
4. A proposal's author is an agent, and a countersignature's signer is a human.
5. An escalation opens an explicit act, or none.

The golden run checks the golden state clean and deterministic. It then checks the derivations:
- implicit mode through a standing directive;
- a triage escalation;
- counter → amend.

It has five refusal cases:
- a tampered schema copy;
- an agent as signer;
- an agent processing an automatic act;
- a `DispositionMode` used as `basis`;
- an escalation opening an automatic act.

Golden-state counts:

| entity | count |
|---|---|
| parties | 3 |
| acts | 7 |
| proposals | 3 |
| countersignatures | 1 |
| mandates | 0 |
| releases | 1 |
| events | 2 |
| escalations | 0 |

## The dsys profile (F5): not mapped
dsys's extension entities have no core counterpart. They stay dsys's profile, outside the core:
- Principal, Hat, R (and the retired Bond), Dyad, Fleet;
- CoS Directive (read only as a link, A2 and A6), GateCheck, Application, LocalVeto,
  AuthorityPolicy;
- Claim, Falsifier, FalsificationRecord, Evidence, KnowledgeUnit, MaterializationVerdict;
- the IFF CovenantGates;
- Intent, Session, DyadTransaction, Ledger and LedgerEntry, Subagent, Briefing;
- Playbook and CommonsPlaybook;
- Condition, Thread, InteractionPreference, StrapGate, ArtifactPackage (read only for hashes);
- RunBook, Step, Tool, AutomatonFlow, FlowState, FlowTransition (named in a release's profile, not
  mapped).

A consumer that needs them reads dsys, not the Countersign document.

## Known limits
- **Derived, not stored.** `mode` and `processor` are derived (F3). A2's implicit rule rests on the
  Directive → `set_standing` link, the only one dsys records. Recording mode as a stored field is
  out of scope for #156.
- **No clock.** `at` is empty on countersignatures and `seq:<n>` on events.
- **Pinned schema not installed.** `install_tree.py` converges only `core/package/*.py`, so the
  pinned `countersign-core.json` is not copied into an installed tree. There, the mapping itself
  runs, but the golden run reports `pinned schema missing`. The component registry lists only the
  two `.py` artifacts for this reason.
