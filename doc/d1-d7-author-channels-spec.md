# Author-agent channels — spec (DR-CMD-085)

**Status:** RATIFIED — DR-CMD-087 (2026-09-26 ~14:48 PDT; J-CH1 and J-CH2 ratified as recommended)
**Matter:** Half 1b of the containment matter. The channels are the
containment boundary's I/O: the only paths in and out of the
author-agent loop. (Half 1a — the host container, `venv` vs docker vs
`venv`+subprocess-discipline — is a pending /pb-decide sibling. This
spec designs the boundary's I/O so the container decision changes the
host, not the channels.)

## 1. Falsified premises (do not reintroduce)

- **No relay topology.** The CLI invokes harness machinery; it does not
  relay chat to a separate endpoint. J0 stands: the author-agent is
  ambient inference governed by a profile. There is no separate
  conversational endpoint to relay *to* (falsified 2026-09-26).
- **No execution containment exists yet.** What is real is *authority*
  containment — stage-only, D5 0.0, G1–G6 — and these channels are its
  I/O surface. Direct calls into `author_agent.py` from outside the
  boundary remain possible in Python; the discipline is that all
  crossings go through this module, so the pending container finds the
  boundary's I/O already complete.

## 2. Vocabulary (ADOPTED — DR-CMD-087)

The afferent/efferent pair vocabulary (proposed since DR-CMD-069,
undisposed) is used **provisionally**. Mechanics are name-independent:
channel kinds are enums; display names live in exactly one table
(`CHANNEL_NAMES`). Adopting, amending, or renaming the vocabulary
changes that table only — never the mechanics.

The **afferent–efferent triad** (provisional name): the three parties
principal, agent, world. The D4 trace/log is the witness, not a party.

- Principal → agent afferents: **AP-A1** disposition, **AP-A2** standing
  disposition, **AP-A3** commission, **AP-A4** authorization.
- Agent → principal efferents: **AP-E1** staged proposal, **AP-E2**
  report, **AP-E3** disclosure, **AP-E4** clarification request.
- World → agent afferents: **AW-A1** trigger event, **AW-A2** read
  data, **AW-A3** world claim, **AW-A4** tool result.
- Agent → world efferents: **AW-E1** tool invocation, **AW-E2** flow
  initiation, **AW-E3** effect attestation (proposed new: D7 has no
  egress target, so outbound claims are unverified at the boundary
  today).

## 3. Principal-afferent: commissions IN (J-CH1)

**Decision:** the **staged commission queue is canonical**; the CLI is
a thin ingress adapter over the *same* admission. Refused alternative:
CLI-direct invocation bypassing staging — two ingress paths with
different auditability would break "channels as the containment
boundary."

- **Admission** (`admit_commission`): every commission crosses one
  gate, enforced against the agent's D6 mechanically —
  principal_id must map to a bound source (operator → OPERATOR; the
  wright binds OPERATOR only), brief / acceptance criteria /
  disposition ref non-empty, kind ∈ {AP-A3 one-shot, AP-A2 standing},
  commission_id unique. **Every admission and every refused admission
  is logged** (`kind: "channel-admission"`) — refused ingress is
  audit-visible. Refuse-with-reasons, never silent.
- **Queue read side** (`pending_commissions`): commissions with no
  authoring session — the queue the governed ambient works from.
- The wright's standing commission (Peter's instruction, DR-CMD-084)
  rides **AP-A2**; task commissions ride **AP-A3**. AP-A1/AP-A4 are
  vocabulary-complete but unbound for the wright (no case has needed
  them).

## 4. Principal-efferent: reports OUT

- **AP-E1 staged proposal:** the authored profile bytes
  (`stage_authored_profile` — existing, unchanged).
- **AP-E2 report:** `read_results(commission_id)` gathers the staged
  verdicts + diagnostics into the return payload for the invoker (what
  the CLI prints). Refusals: no verdict staged → reasons listing what
  *is* present; verdict malformed (verified without diagnostics) →
  reasons. A refused verdict is a *complete* result (the loop
  concluded); only missing/malformed records refuse.
- **AP-E3 disclosure:** the channel-admission and channel-refusal
  records themselves — durable visibility of every boundary crossing.
- **AP-E4 clarification request:** unbound (no case has needed it;
  ambiguity today is resolved ambient-to-operator, outside the
  channel — future matter if a commission format ever requires it).

## 5. World channels: specified, unbound

The vocabulary is specified (§2); **nothing is bound for the wright**
(D7 0.75 harness-internal-reader, D5 0.0 — J-H discipline: don't bind
what the role doesn't need). The gates are profile-driven and every
refused attempt is logged (`kind: "channel-refusal"`) — boundary
probes are audit-visible:

- `world_ingress`: refuses for the wright citing D7 (no world_target;
  fail_closed). A profile *with* world_target would pass the gate —
  and then refuse as "unimplemented: future field-agent matter"
  (honest: vocabulary specified, handling not built).
- `world_egress`: refuses for the wright citing D5 (no contracted
  tools; write_scope empty). A profile with contracted tools would
  likewise hit "unimplemented: future field-agent matter."
- **Future matter:** field-agent world channels (AW-A1..A4 /
  AW-E1..E3 handling). This spec is the vocabulary anchor for it.

## 6. CLI: invocation, not conversation

`python -m core.package.author_channels <commission|drive|report|pending>
…` — subcommands invoke harness functions and print records.
**Anti-relay clause:** the CLI never converses and cannot reach the
authoring inference (ambient-side, J0). It stages commissions, runs
the driver, and prints staged results — invocation, not conversation.
Exit codes: 0 ok, 2 usage, 4 governance refusal (consistent with the
CLI spec's 4 = refusal).

## 7. Name-independence (supports J-CH2)

`PrincipalAfferent`, `PrincipalEfferent`, `WorldAfferent`,
`WorldEfferent` are enums; `CHANNEL_NAMES` is the single display
table, marked PROVISIONAL. Golden-run case H9 pins this: every enum
member has exactly one table entry, and behavior never branches on a
display string.

## Glossary

- **channel**: a typed, gated path across the containment boundary;
  the only legitimate I/O of the author-agent loop.
- **afferent**: a channel carrying input *into* the agent
  (principal→agent, world→agent).
- **efferent**: a channel carrying output *out of* the agent
  (agent→principal, agent→world).
- **afferent–efferent triad** *(provisional)*: the three parties
  principal, agent, world across which the pairs are defined.
- **admission**: the gate a commission crosses; validates against the
  agent's D6 and logs the decision either way.
- **containment boundary**: the I/O surface these channels define;
  the pending host container will host it, not redesign it.
- **witness**: the D4 trace/log — records crossings, is party to none.
- **AP-** *(provisional)*: agent↔principal channel codes.
- **AW-** *(provisional)*: agent↔world channel codes.
