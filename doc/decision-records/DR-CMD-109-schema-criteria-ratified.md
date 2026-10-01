# DR-CMD-109 — DR-CMD-099's five schema-artifact criteria RATIFIED as written

- **Status:** adopted (ratify)
- **Date:** 2026-09-27 ~20:51 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (selection among /pb-decide variants)
- **Matter:** ratify-or-amend the five commissioned mechanical vetting
  criteria for schema artifacts (DR-CMD-099, dependent act (b)).

## The criteria (ratified text)

Adopted in DR-CMD-099; the *content* was Peter's ratify-or-amend. A
presented schema artifact is registered iff all of:

1. The artifact **validates against its schema** (mechanical parse +
   schema check — no discretion).
2. Its **version bumps per rule** (monotonic increment over the
   registered tip for that artifact line; no skips, no repeats).
3. The **supersedes-chain is intact** vs the registry tip (the new
   version's supersession claim resolves to the currently registered
   head — no forks, no dangling claims).
4. **Required metadata is present**, including a Decision Record
   reference authorizing the change (no anonymous schema changes).
5. **No duplicate content-hash** already registered (the registry is
   content-addressed; re-registration of identical bytes is refused).

**Ambiguous → defer:** any artifact failing a criterion, or presenting a
case the criteria do not cover, is staged for operator disposition —
never registered, never silently dropped. Proposer ≠ disposer holds for
the ambiguous middle.

## Dialectic trail

- **O1 — ratify as written.** The five are mechanical and
  discretion-free; the ambiguous→defer rule covers what they don't; the
  set stood unchallenged since DR-CMD-099; and ratification is what
  makes O3 operable — `tool-register-artifact` landed (DR-CMD-103) and
  `recorder` is registered and operable (DR-CMD-107). Draft: adopt.
- **O2 — amend first.** The honest amendment candidates were (a)
  pinning the meta-schema behind criterion 1's "schema check" for
  schema artifacts, and (b) aligning criterion 5's "refused" with
  `tool-register-artifact`'s idempotent "returns existing receipt" —
  both behavior-neutral polish. Draft: decline as amendments; record as
  implementation notes instead.
- **O3 — leave unratified.** No reason — the content is stable, the
  machinery is ready, and staying unratified keeps O3 inoperable.
  Draft: refuse.

Peter rendered **"O1"** (~20:51 PDT 2026-09-27). **Selected: O1.**

## Decisions

### 1. The five criteria — RATIFIED as written

The content is no longer ratifiable-or-amendable-in-waiting; it is the
commissioned vetting content `recorder` runs against presented schema
artifacts. DR-CMD-099's O3 is now fully operable: commissioned profile
(`recorder`, clerk, registered), contracted tool channel
(`tool-register-artifact`), commissioned criteria (this record). The
dog-food loop for the Architecture's own schemas is closed.

### 2. Implementation notes (recorded under this ratification, not amendments)

- **(a) Criterion 1 for schema artifacts** means validation against the
  commissioned meta-schema. The meta-schema is not yet pinned; the
  ambiguous→defer rule covers the gap meanwhile — a schema artifact
  whose "schema check" cannot be performed mechanically is deferred, not
  passed.
- **(b) Criterion 5 "refused" vs the tool's idempotency.** The tool
  returns the existing receipt without advancing the registry on a
  duplicate content-hash; the criterion refuses re-registration. These
  agree operationally: in neither case is a new registration created.
  The wording difference is not a behavior difference.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Per Peter's "O1 then O2" selection (DR-CMD-108), build-path
  containment is now the active matter.
- Next free identifier: DR-CMD-110 (DR-CMD-059 still reserved for PVB
  DoD).

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the
selection only): this record. Commit and push return as follow-on
dispositions.
