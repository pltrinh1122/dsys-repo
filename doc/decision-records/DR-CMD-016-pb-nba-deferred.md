# DR-CMD-016 — `/pb-nba` (next best action): deferred with a named revisit trigger (ratified)

- **Status:** ratified
- **Date:** 2026-09-20 ~19:10 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Need or not for a new slash command `/pb-nba` (next best action). Framed: *the operator's workflow has a gap — no instrument recommends the next best action — that a new `/pb-nba` would fill.*

## Options and gate trails (from `/pb-decide` START/STOP)

- **O1 — create `/pb-nba`** (agent surveys open matters and recommends the highest-priority next action): **killed**. G2 fail — no legitimate source evidences the gap; the need is hypothesized, never observed (the operator arrives with the agenda each session; the agent's in-chat proposals have covered the what's-next function). G3 fail — redundant with standing behavior (conversational next-step proposals) and in tension with the standing norm (follow the operator's named agenda; never pre-empt disposition). Falsifying observation: the function O1 would fill is already performed, gated by the operator's "Y".
- **O2 — decide nothing** (no new command; next-action stays conversational): survived G1–G4. Draft verdict was adopt.
- **O3 — defer** with revisit trigger: survived G1–G4 as fallback.

Dialectic (antithesis: ad-hoc proposals are inconsistent; a command would systematize): rebutted — "best" requires the operator's utility function, which only the operator holds; without it a command restates the visible queue or substitutes its own prioritization (pre-empting disposition). The ad-hoc-ness is the feature: low-ceremony, every proposal gated.

## Decision

**Ratified O3, as refined by the selector:** creation of `/pb-nba` is **deferred** — not closed. Revisit trigger (selector's words, canonicalized): *when `/pb-decide` is unable to recommend the next best action, Peter will provide clarity on the conditions for selecting.* (Selector said `/decide-pb` — the DR-CMD-001 alias; canonical `/pb-decide`.) On trigger, the matter re-enters START with the supplied selection conditions as input.

## Consequences (G4)

No new slash command; no new machinery in the command layer. The next-action function stays conversational (agent proposes, operator's "Y" gates). The matter is held open under the named trigger rather than closed.

## Checkability (G5)

Provisional (a deferral, not a binding close). Checkable: the trigger is observable — a future `/pb-decide` run on "next best action" that cannot produce a recommendation — and the selector's commitment to supply selection conditions then is explicit.

## Uncertainties (G6)

- "Unable to recommend" is itself a judgment call inside a future run (e.g., a G2 failure on "best" for lack of a legitimate prioritization source); the trigger fires on the agent's honest report, not on a mechanical signal.
- Assumes the conversational-proposal pattern keeps covering the need; if the workflow ever goes long-autonomous, the trigger may fire sooner.
- Numbering (disposition order): this ratification takes **DR-CMD-016** (first disposition since DR-CMD-015). Projected: any future ratification touching the `/pb-decide` contract remediation → DR-CMD-017; the `/eval-sc` family-membership candidacy → DR-CMD-018.
