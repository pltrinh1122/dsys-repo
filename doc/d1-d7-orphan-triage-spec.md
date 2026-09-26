# Orphan-Triage Policy — Structural Specification

- **Status:** implemented (structural scope), DR-CMD-081 ratified 2026-09-26;
  implementation **RATIFIED as built, DR-CMD-082 (Item 10)**
- **Scope:** structural policy only — duty, closure, surfacing. Shape-specific
  routing rules (which orphan kinds go where, aging thresholds, escalation
  ladders) are a deferred G6 (tripwire: first production orphan past 30 days
  untriaged, or the first production run's retrospective, whichever first).

## 1. The conservation law

DR-CMD-074 Item 5b: an admitted trigger that matches no standing
disposition is **staged, not silently dropped**. Every trigger is therefore
conserved — none vanishes. Conservation without a drain is accumulation, so
5b's promise ("nothing vanishes; every trigger is accounted for") requires
a triage policy, or staging becomes slow-motion dropping without the
honesty. This document specifies the drain.

## 2. Design: DR-5 pattern instantiated

The policy instantiates the dsys core's DR-5 orphan pattern — orphan queue
\+ drain duty \+ closure bar (I-13) — for the factory substrate. Nothing is
reinvented; the pattern is bound to factory parts:

- **Orphan queue:** derived, not stored. An *orphan* is a staged proposal
  whose disposition record says `"staged"` (parked: admitted, unmatched)
  with no superseding triage record. `OrphanQueue.scan()` re-derives
  membership from the append-only staging file on every call — oldest
  first, deterministic, session-independent.
- **Drain duty:** the coordinator. Its sweep (SELF cadence backstop, J-G)
  plus staging-event wake (DR-CMD-078 `agent` source) already covers the
  substrate the orphans stage into; the duty attaches where the eyes
  already are.
- **Closure bar:** holds by construction. The file is append-only, so the
  *only* exit from the queue is a triage record, and `OrphanQueue.triage()`
  is the only writer of triage records. There is no removal API. Triage
  requires a disposition in `{routed, refused, archived}` and a non-empty
  reason — refuse-with-reasons (`OrphanTriageError`), never silent. An
  untriaged orphan therefore cannot stop being reported: no code path can
  make it leave the queue except a valid triage.
- **Surfacing:** orphan count + oldest age (`oldest_seq`) as standing
  coordinator disclosure, carried in the arbitration record's `"orphans"`
  section. Orphans stay excluded from arbitration *inputs* (the sweep skips
  disposed proposals): surfaced, never re-arbitrated, never re-driven.

## 3. Triage dispositions (structural)

- `routed` — assigned to a profile for handling; the caller supplies the
  target (`route_to=`); the structure records it, never chooses it.
- `refused` — declined with reasons.
- `archived` — parked permanently with reasons.

Each appends a superseding disposition record (`triage: true`) carrying the
decision, the reason, and any caller-supplied routing. The *choice* among
them for a given orphan kind is the deferred shape-specific G6.

## 4. What this deliberately does not decide

- Which orphan kinds route to which profiles.
- Aging thresholds (when an orphan becomes stale; when staleness escalates).
- Escalation ladders beyond the coordinator's standing disclosure.

These need real orphan shapes; zero production orphans exist. The G6
tripwire above reopens them on evidence, not imagination.

## 5. Glossary

- **Orphan:** a staged proposal whose disposition record says `"staged"`
  with no superseding triage record — an admitted trigger that matched no
  standing disposition, parked per DR-CMD-074 Item 5b.
- **Orphan queue:** the derived set of untriaged orphans, oldest first;
  membership is recomputed from the append-only staging file, never stored.
- **Drain duty:** the obligation to work the queue down; attaches to the
  coordinator, whose sweep and staging-event wake cover the substrate.
- **Closure bar:** the invariant that nothing leaves the orphan queue
  except via a triaged disposition with reasons; enforced structurally
  (append-only file + single writer + mandatory reasons), echoing I-13.
- **Triage:** recording a `routed` / `refused` / `archived` disposition
  with a non-empty reason on an untriaged orphan — the queue's only exit.
- **Standing disclosure:** the coordinator's arbitration record section
  reporting `untriaged_count` and `oldest_seq`; the queue's permanent
  visibility.
- **Shape-specific rules:** the deferred G6 — which orphan kinds go where,
  aging thresholds, escalation ladders. Presumed by nothing in this
  document.
