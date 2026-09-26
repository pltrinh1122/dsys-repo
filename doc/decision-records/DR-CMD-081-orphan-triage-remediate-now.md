# DR-CMD-081 — Orphan-triage policy: remediate now (scoped), shape-specific rules deferred as G6

- **Date:** 2026-09-26
- **Matter:** orphan-triage policy timing — open G6 from DR-CMD-074 Item 5b
- **Disposition:** REMEDIATE NOW, scoped to structure (Peter, 2026-09-26)
- **Status:** ratified; implementation in this record's wake

## Background

DR-CMD-074 Item 5b decided unmatched triggers are **staged, not silently
dropped**: under a standing-only authorization rule, a trigger matching no
standing disposition produces a staged disposition record (decision
`"staged"`) instead of vanishing. The standing consequence, recorded then:
the staging area accumulates unmatched triggers — **orphans** — with no
defined exit. The policy's timing was left explicitly open, "not as
deferred," awaiting Peter's disposition. This record is that disposition.

## The /pb-decide

Framed 2026-09-26 as remediate-now vs. defer-explicitly, elicited through
four examples:

1. **5b's missing second half.** Stage-don't-drop is a conservation law —
   every trigger conserved. Conservation without a drain is accumulation.
   An orphan staged with no triage policy is a trigger *kept* but never
   *looked at*: slow-motion dropping, minus the honesty. The triage policy
   is what makes 5b's promise true rather than theatrical.
2. **The precedent already exists.** dsys core solved this exact shape:
   DR-5's disclosure surface carries an orphan queue + drain duty + I-13
   closure bar (implemented 2026-09-19). The factory instantiates the
   pattern; it does not invent one.
3. **The coordinator just grew eyes.** DR-CMD-078 gave the coordinator
   event-driven waking on staging events. Orphans stage into that same
   substrate, so the duty holder already has the sensory apparatus — the
   policy only tells it what to do when it sees one.
4. **The imagination risk is bounded.** Zero production orphans exist, so
   the *shape-specific* dispositions (which orphan kinds route where,
   aging thresholds) cannot be designed well against imagination. But the
   *structural* part — duty + closure + surfacing — presumes no orphan
   shapes at all.

## Selection (Peter, 2026-09-26)

**Remediate now, scoped to structure:**

- **Duty holder:** the coordinator — its sweep (SELF cadence backstop,
  J-G) plus staging-event wake (DR-CMD-078) already covers the substrate.
- **Closure invariant (closure bar):** nothing leaves the orphan queue
  except via a triaged disposition **with reasons** — routed to a profile,
  refused, or archived. An untriaged orphan cannot silently exit.
- **Surfacing:** orphan count + oldest age as standing coordinator
  disclosure (in the arbitration record).

**Deferred as G6 — shape-specific routing rules:** which orphan kinds go
where, aging thresholds, escalation ladders. Nothing about orphan shapes
is presumed by the structural policy.

**G6 tripwire:** revisit at the **first production orphan past 30 days
untriaged**, or the **first production run's retrospective**, whichever
comes first.

## Alternatives not taken

- **Defer entirely as G6:** cheapest now, honest with a crisp tripwire —
  but 5b's conservation law would run drainless until the tripwire fired,
  and the first orphans would arrive into a policyless system.
- **Full remediate now** (structure + shape-specific rules): completest on
  paper, but the rules would be designed against zero data and would be
  wrong.

## Implementation (structural, DR-5 pattern instantiated)

- `OrphanQueue` (substrate component, `core/package/factory_substrate.py`):
  queue membership is *derived* from the append-only staging file — an
  orphan is a staged proposal whose disposition record says `"staged"`
  with no superseding triage record. Because the file is append-only, the
  only exit from the queue is a triage record, and `triage()` is the only
  writer of triage records, enforcing non-empty reasons and a disposition
  in `{routed, refused, archived}`. The closure bar holds by construction.
- Coordinator arbitration body gains an `"orphans"` section
  (`untriaged_count`, `oldest_seq`): the standing disclosure. Orphans stay
  excluded from arbitration *inputs* (never re-arbitrated) while reported
  in disclosure (surfaced, not re-driven).
- Golden-run battery O-*: orphan birth through the real 5b path,
  disclosure surfacing, all three triage dispositions with reasons,
  closure-bar cases (empty reason / unknown id / double triage refused;
  untriaged orphan persists across subsequent activity and stays out of
  arbitration inputs), determinism.

## Identifier discipline

- This record: **DR-CMD-081**.
- DR-CMD-059 remains reserved for the Product Vision Board Definition of
  Done. Next free identifier: **DR-CMD-082**.
- Amends nothing ratified; closes the DR-CMD-074 Item 5b timing G6.
