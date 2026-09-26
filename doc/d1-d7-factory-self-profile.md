# D1–D7 Factory Self-Profile (Reflexivity)

**Status: RATIFIED (DR-CMD-076, 2026-09-26); implementation RATIFIED as
built (DR-CMD-082, Item 10, 2026-09-26).** This document is the factory
reflexivity deliverable required by DR-CMD-061 step 5: the agent factory
located in its own Seven Dimensions of Agent Behavior (D1–D7) reference
architecture (DR-CMD-060). The positions below were proposed for Peter's
step-7 run-through and ratified on 2026-09-26; nothing here is draft.

**What "the factory" is, for this document.** The factory is the step-5
machinery: the compiler (`core/package/factory_compiler.py`), the
conformance verifier (`core/package/factory_verifier.py`), and the
harness-native substrate components (`core/package/factory_substrate.py`),
run as AutomatonFlows (DR-CMD-064) through a Harness (AX1, DR-CMD-063).
"Operating" a built agent is out of scope for the factory (DR-CMD-061) and
therefore out of scope for this profile.

**Machine-valid profile.** The profile below was constructed and validated
against `core/package/agent_behavior.py` on 2026-09-26: all seven
dimensions validate, all couplings C1–C5/C7 hold (C6 retired, DR-CMD-077),
and `warnings()` returns
none. Position vector: D1 0.0, D2 principal_wins_ties, D3 0.0, D4 1.0,
D5 0.0, D6 structural (no scalar), D7 0.75.

```json
{
  "agent": "agent-factory",
  "d1_authority": {
    "per_event_disposition": true,
    "position": 0.0,
    "self_correction": false,
    "self_planning": false,
    "standing_dispositions": []
  },
  "d2_fidelity": {
    "conflict_rule": "principal_wins_ties",
    "principal_precedence": [
      "operator"
    ]
  },
  "d3_reproducibility": {
    "deterministic_execution": true,
    "position": 0.0,
    "replay_supported": true
  },
  "d4_observability": {
    "inspectors": [
      "operator",
      "auditor"
    ],
    "position": 1.0,
    "records_events": true,
    "records_intents": true,
    "records_verifications": true,
    "retention": "forever"
  },
  "d5_scope": {
    "position": 0.0,
    "read_scope": [
      "profile-source",
      "tool-registry"
    ],
    "write_scope": []
  },
  "d6_initiative": {
    "authorization": {
      "operator": "may-act on disposition"
    },
    "gating": {
      "operator": "authenticated-session"
    },
    "sources": [
      "operator"
    ]
  },
  "d7_verification": {
    "event_target": true,
    "intent_target": true,
    "on_failure": "fail_closed",
    "position": 0.75,
    "trigger_target": true,
    "world_target": false
  },
  "version": "1.0"
}
```

## Rationale per dimension

**D1 — Authority (0.0).** *Authority* is who commits to action: a
*per-event disposition* means each action waits for a fresh human decision;
a *standing disposition* is a pre-authorized action class. The factory
holds no standing dispositions: every compile and every verification run
is a per-event disposed event (DR-CMD-061 authorized step 5 as one run, not
as a standing permission). It does not correct or replan itself
(`self_correction`, `self_planning` false). Derived position 0.0: nothing
in its repertoire executes without a fresh disposition.

**D2 — Fidelity (principal_wins_ties).** *Fidelity* is whose claims
prevail when principal and world conflict (DR-CMD-077: D2's schema value
*is* the binary enum {principal_wins_ties, world_wins_ties}; the scalar
position retired with C6). For the factory, the "principal" side is the
ratified spec and the "world" side is the presented profile bytes. The
rule is `principal_wins_ties`: when profile bytes contradict the ratified
spec, the factory refuses rather than improvising — and refusal is
fidelity to the principal, not a third option. "Principal" over "intent"
because the question is jurisdictional (whose claims prevail), not
hermeneutic (what was meant); the -ties qualifier is load-bearing — the
enum governs the conflict limit case, not ordinary operation.

**D3 — Reproducibility (0.0).** *Deterministic execution* means the same
input always yields the same output; *replay* means an execution can be
re-run identically. The factory is deterministic by construction: the same
profile always compiles to the same artifact (golden-run case A4 asserts
byte-identical hashes across runs), and verification replays probe
sequences with hash equality (P-D3-replay). Derived position 0.0.

**D4 — Observability (1.0).** *Observability* is who can witness what
happened, measured as the fraction of instrumentation streams enabled:
events, intents, verifications. The factory records all three: flow
transition events, staged dispositions (intents), and verdict records
(verifications), inspectable by operator and auditor, retained forever.
Derived position 1.0.

**D5 — Scope (0.0).** *Scope* is what the agent may affect, via its bound
*write scope* of contracted tool channels. The factory binds zero
production tools: it never calls the eight contracted tools. Its durable
writes (staged proposals, verdict records, flow drafts) go through
accretion-backed staging as pipeline-internal operations (DR-CMD-065), not
through tool bindings. Read scope covers the profile source and the tool
registry it resolves against. Derived position 0.0. See the open question
below — this is the least comfortable reflexive fit.

**D6 — Initiative (structural, no scalar).** *Initiative* is what may
activate the agent: the *activation gate* (may the trigger fire?) is
distinct from the *authorization rule* (may the agent act on it?). The
factory has exactly one source: the operator, behind an
authenticated-session gate, authorized to may-act on disposition. The
factory never self-activates (AX1: invocation always through a Harness;
the factory initiates no drives). Schema note (DR-CMD-078/080, mechanical
consequence of the already-ratified D6 `agent`-source build): the D6 source
enum now carries four members {operator, world, self, agent}; the factory's
own D6 binding remains {operator} — DR-CMD-075 (no self source) is unchanged.

**D7 — Verification (0.75).** *Verification* is how rigorously claims are
checked at trust boundaries: intent (is this the principal's?), event (is
the trace intact?), world (is the claim corroborated?), trigger (did the
gate admit this?). The factory verifies intent (dispositions carry
authority), event (hash-chained logs and staging), and trigger (activation
gates on its own invocation) — but not world: it validates profile bytes
against the schema (an intent/spec check), it does not corroborate them
against independent ground truth. `on_failure` is `fail_closed`: a
verification failure halts rather than continuing.

## Reflexive check

On 2026-09-26 the factory was run against this very profile:
`compile_profile` produced an artifact and `verify` returned
**verified / operable** (artifact `489007a6e372198e`). The factory therefore
attests, by its own conformance criteria, that the agent described here
could be built and operated. This is evidence about the profile's
conformance, not a ratification of its positions — ratification is Peter's
step-7 disposition.

## Open questions for step-7 review — all decided (Item 7 closed, DR-CMD-076)

1. **D5 reflexive fit — DECIDED (DR-CMD-076): keep 0.0.** D5 is read over
   contracted tool channels; the factory binds none. Its accretion writes
   are pipeline-internal operations on its own substrate (DR-CMD-065), not
   tool-mediated effect scope. The factory-specific-channel alternative
   (`staging-write`, D5 > 0.0) was declined.
2. **D2 principal/intent reading — DECIDED (DR-CMD-076), AMENDED
   (DR-CMD-077).** The conflict is jurisdictional: principal's claims
   (ratified spec) vs world's claims (presented profile bytes); on conflict,
   refuse (`principal_wins_ties`). The deployment-environment reading was
   declined — the factory never reads the environment, so the conflict
   rule would go vacuous. DR-CMD-077 retired the scalar position and C6:
   D2 is the binary enum outright.
3. **D6 self-source — DECIDED (DR-CMD-075): no self source.** The factory's
   AutomatonFlow transitions are continuation, not activation: every
   mid-flow transition fires on `run_completed`/`run_aborted` control-plane
   signals downstream of the single `external` entry trigger, which is
   injected by the operator's disposition. D6 stays {operator}.
4. **D7 world_target — DECIDED (DR-CMD-075): no corroboration for now.**
   `world_target` stays false; D7 stays 0.75. Deferred as G6 with revisit
   trigger: revisit if a built agent's failure traces to a false registry
   claim that attestation would have caught.

## Glossary

- **AgentBehaviorProfile**: the pydantic schema locating one agent across
  D1–D7 (`core/package/agent_behavior.py`).
- **Activation gate**: the per-source rule deciding whether a trigger may
  fire; distinct from authorization (D6).
- **Artifact**: the compiler's output — a build plan plus a manifest
  binding it to the source profile by hashes.
- **Authorization rule**: the per-source rule deciding whether the agent
  may act on an admitted trigger, or must stage the action for disposition.
- **AutomatonFlow**: the deterministic FSM execution substrate; the
  factory's own pipelines run as AutomatonFlows (DR-CMD-064).
- **D1–D7**: the Seven Dimensions of Agent Behavior reference architecture
  (DR-CMD-060): Authority, Fidelity, Reproducibility, Observability, Scope,
  Initiative, Verification.
- **Disposition**: the Operator's decision on a proposed action or matter
  (ratify, authorize, set-standing, overrule, triage).
- **Per-event disposition**: each action waits for a fresh human decision;
  the opposite of a standing (pre-authorized) disposition.
- **Reflexivity**: the factory's DR-CMD-061 requirement to profile itself
  in D1–D7 terms.
- **Verdict**: the verifier's output for one artifact: `verified`
  (operable), `refused` (not operable), or `failed` (verifier malfunction
  only).
