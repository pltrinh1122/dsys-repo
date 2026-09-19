# DR-5 Implementation Spec — Disclosure Verification View + CoS Drain Duty

Spec-only. Nothing here is implemented. Implements the ratified DR-5
(2026-09-18): the disclosures surface is required **as a verification
view**, not a disposal workbench; disposal runs through a CoS drain
duty. Decision procedure and narrowing rationale are recorded in
DR-5; this document specifies the machinery.

Two halves, deliberately asymmetric:

- **Part A — verification view.** Read-only, computed from
  `SystemState`, independent of any agent's presentation. This is the
  surface DR-5 requires. Its irreducible function is *audit*: the
  operator checks the CoS's queue against ground truth.
- **Part B — drain duty.** A standing CoS duty (trigger, sweep,
  closure bar) that performs disposal serially through existing
  triage machinery. No new disposition grammar.

Proposed implementation order: **A1 (seq fields) → A2 (view) →
B3 (closure bar + golden cases) → B1/B2/B4 (standing-policy
template)**. The standing policy text in B1 requires Peter's
`set_standing` disposition to become binding — the spec below is a
proposal, not a policy.

---

## A1 — Ordering without a clock: sequence fields

The drain duty needs "older than" without timestamps (the
architecture has no clock, per the CTA-hazard finding). Minimal
enabler: monotonic sequence numbers assigned at write time.

**Schema.**
- `Disclosure.seq: int = 0` — assigned when the disclosure is
  written.
- `HarnessRun.open_seq: int = 0` — the sequence value current when
  the run opened.

**Convention (load-bearing).** `seq` values are minted by the
*write path* (the runtime/store), never by the record author. A
writer-minted seq is gameable: forward-dating a disclosure exempts
it from the backlog rule below. `golden_run.py` assigns seqs in
write order; a real runtime uses a single monotonic counter.

**Falsifier.** If seq assignment cannot be trusted to the write
path in practice, the closure bar (B3) is gameable and must be
killed or re-thought. The bar is only as honest as the counter.

---

## A2 — The verification view

**Design.** A pure function over `SystemState`, not a stored
entity. Computed from ground-truth records — that is what makes it
independent of any agent's presentation, and that independence is
the entire point (DR-5: *nothing watches the watcher* otherwise).

**New module** `package/views.py`:

```python
def verification_view(s: SystemState) -> list[DisclosureViewRow]
```

`DisclosureViewRow`: `{id, kind, text, seq, triage_in_flight}`.
`triage_in_flight` is True when the disclosure is cited by a
`triage`-mode disposition with status PROPOSED — i.e., a CTA is
out but unanswered. Deterministic order: kind rank
(conflict < error < uncertainty), then `seq` ascending.

**Completeness** is by construction: the view enumerates every
`Disclosure` with status OPEN. There is no filter, no agent
discretion, no ranking beyond the deterministic order.

**What the view is not.** Not a workbench (no actions), not a
notification feed (FYI items were falsified as an entity — the
view shows obligations, not awareness items), not a substitute
for triage (each row still needs its own disposition).

**Coupling (anti-decoration).** A view nobody reads is D6's
disease. The view is load-bearing via B3: the closure bar reads
the view, not any agent's account of the queue. The operator
invokes it on demand for audit ("show me everything pending, from
ground truth").

**Falsifier.** If the closure bar is ever decoupled from the view
(e.g., rewritten to trust a CoS-maintained list), the view
becomes decorative — kill it then.

---

## B1 — Drain trigger (standing policy, proposed)

**Proposed policy text** (domain `cos-duties`; requires Peter's
`set_standing` disposition — not binding until then):

> When a disclosure is written while no governance run is open,
> the CoS opens a governance drain run. While a governance run is
> open, newly written disclosures join its sweep. Disclosure kinds
> drain in order conflict → error → uncertainty. G3-failed
> duplicates are dissolved without disposition and without
> operator time.

**Honesty note.** "Disclosure-written → open run" is not directly
validatable: without the run yet existing, no validator observes
the omission. It is enforced *indirectly* — by the closure bar
(B3), which bites at the one observable moment (run closure),
and by the verification view (A2), which lets the operator audit
whether drainage is happening. The trigger is policy; the bar is
mechanism. Additionally, the duty relies on CoS *liveness* (the
CoS opening runs at all), which is unmodeled — if the CoS never
runs, the duty never fires, and only the operator's audit via
the view would reveal it. Stated plainly so the gap is visible.

---

## B2 — Drain sweep (procedure)

Per open disclosure, in view order:

1. **G-gate** the disclosure as a triage matter (G1–G6). The CoS
   performs gating as diligence, as simulated in the CoS-initiation
   run.
2. **Dissolve** G3 failures (duplicates, non-disclosures): no
   disposition, run STOPs that item, operator never sees it.
   (Probe C of the CoS-initiation simulation.)
3. **Triage** each survivor via CoS-initiated triage disposition:
   one CTA per turn to the operator (existing grammar —
   singular `disclosure_ref`, DFD one-CTA-per-turn). The operator
   answers acknowledge / escalate / dismiss per item.

No new disposition grammar. The sweep is procedure + standing
policy, not schema.

**Kind-ordering caveat** (from the decision sim): conflict >
error > uncertainty is coarse — a docstring conflict outranks an
uncertainty about an irreversible action. Accepted as a
first-order heuristic; falsifier: if kind-order demonstrably
misorders in practice, add a severity signal or drop the
ordering claim. Do not smuggle severity into `kind`.

---

## B3 — Closure bar (new invariant I-13)

**Rule.** A governance run may not close while any *backlog*
disclosure remains undisposed. *Backlog* = status OPEN **and**
`seq < run.open_seq` — the queue as it stood when the run opened.
Disclosures written *during* the run (`seq >= open_seq`) are the
next cycle's problem.

This two-tier form is deliberate: a strict "no open disclosures
at close" bar would let a steady trickle of new disclosures pin
the governance run (and, via DR-1, the governance slot) open
forever. The backlog rule guarantees per-cycle progress — every
cycle drains a finite backlog — while new arrivals wait one
cycle. Livelock is replaced by visible pressure: if arrivals
outpace drainage across cycles, the view shows the growing
backlog, which is the correct failure signal (a capacity
problem, surfaced, not a correctness hole).

**Validator** (new `_drain_closure_bar`, registered in the
runner):
- For each `HarnessRun` with `authority_scope == GOVERNANCE`
  and `state == CLOSED`: for each disclosure with
  `status == OPEN` and `seq < run.open_seq` → I-13 violation:
  "governance run {run.id} closed with undisposed backlog
  disclosure {d.id}".
- Execution runs are unaffected: the duty is governance-scoped
  (the CoS's), by DR-5's narrowing.
- A disclosure cited by a PROPOSED-but-unanswered triage CTA is
  still OPEN, so the bar holds while a CTA pends. Operator
  silence pins the run — mitigated by ABANDONED closure and E5
  silence meanings, per the CTA-hazard finding. The pin is
  *visible* (view non-empty, slot held), which is the design
  working, not failing.

**Golden-run cases.**
- (24) Governance run `gr-x` (CLOSED, `open_seq=10`) with
  disclosure `dis-old` (OPEN, `seq=4`) → flagged: I-13
  "closed with undisposed backlog disclosure".
- Clean: same run with only `dis-new` (OPEN, `seq=12`) →
  passes (next cycle's problem).
- Clean: run CLOSED, verification view empty → passes.
- View assertion (not a refusal case): state with three OPEN
  disclosures (one per kind, mixed seqs, one cited by a
  PROPOSED triage disposition) → view returns all three,
  kind-ordered, correct `triage_in_flight` flags.

---

## B4 — Standing-policy record (template, not binding)

The B1 policy text, when Peter ratifies it via `set_standing`,
becomes a `Disposition` (mode SET_STANDING, domain `cos-duties`,
disposer = Peter). It then forms the single supersession chain
per domain per I-2; amendments supersede via
`supersedes_disposition_id`. Until that disposition exists, the
drain duty is proposal, not obligation — **human disposition is
terminal**, including over the CoS's own duties.

---

## Net delta

- Schema: `Disclosure.seq`, `HarnessRun.open_seq` (both `int`,
  default 0; runtime-minted per A1).
- New module `package/views.py`: `verification_view`.
- New validator `_drain_closure_bar` → invariant **I-13**.
- New refusal case: 1 (case 24; golden run 23 → 24).
- Standing-policy template for the drain duty (B1/B2/B4) —
  binding only on Peter's `set_standing` disposition.
- Doc updates: § on disclosures (DR-3) gains the view + duty;
  §8.2 playbook STOP DoD notes the closure bar for governance
  runs. (Doc edits deferred to implementation.)

## What this does not do (declared non-goals)

- No operator notification on disclosure write (attention is
  unmodeled; the FYI entity was falsified).
- No silence timeout / no clock (run-count and seq-order stand
  in; the CTA-hazard's timeout remains future work).
- No bulk disposal (singular `disclosure_ref` + one-CTA-per-turn
  + DR-1 stand — disposal stays serial).
- No severity field; kind-ordering stays coarse per its
  falsifier.
- The CoS-liveness gap (B1 honesty note) is declared, not
  closed.

---

## Falsification verdicts (2026-09-19, pre-implementation)

**A1 (seq fields) — SURVIVES, weakened.** The need stands (no
clock exists), but "runtime-minted, non-gameable" is
*unmechanized*: the architecture has no write-path entity, and no
validator can verify *who* minted a seq. The trust property is
asserted, not enforced. Downgrade: seq integrity is declared
trust in the write path, and B3's strength is conditional on it.
(Standing caveat, not a kill.)

**A2 (verification view) — SURVIVES, amended twice.**
(i) As specified, the closure bar reimplements the view's filter
inline — the `views.py` module is decorative. Amend: `_drain_closure_bar`
(and the orphan-queue validator below) must be implemented *in
terms of* `verification_view(s)`, or kill the module. The view's
justification is being the single definition of "the queue"
shared by validators and operator audit.
(ii) "Independent of any agent's presentation" is narrower than
it sounds: the view is independent of selective *showing* but
not of *authorship* — it audits written→disposed, never
detected→written. An unwritten disclosure is invisible to the
view by construction. DR-5's "nothing watches the watcher" is
half-served; the spec must say so.

**B1 (trigger) — SURVIVES as policy, with teeth added.** The
trigger as stated is not directly validatable (conceded in the
spec). Strengthening, validatable: the duty attaches to the
*scope*, not the run — B3 applies to every governance run, so
"open a drain run" simplifies to "never leave the queue
orphaned." New validator (I-13): verification view non-empty
AND no non-closed governance run exists → "open disclosures
with no governance run draining." Procedural rule: disclosure
write and drain-run opening are same-turn atomic (answers the
transient-gap objection). Abandonment does not exempt the bar;
the orphan rule catches the aftermath.

**B2 (sweep) — SURVIVES as procedure.** No mechanizable change
available; kind-order coarseness stands with its falsifier.

**B3 (closure bar) — SURVIVES, clarified.** Applies regardless
of `closure_reason` (abandoned closures included). Conditional
on A1's declared trust. Backlog form (`seq < open_seq`) stands —
the trickle-pinning objection to the strict form holds.

**B4 — SURVIVES.** Simplify the template text per the
scope-attachment (B1): the duty is "the governance scope drains
its backlog," not "the CoS opens a special run."

**KEY FINDING — the progress hole (not a kill of DR-5, a priced
cost).** Validators verify *closure-time* drainage; nothing
verifies *in-run* progress. An open-but-idle governance run
satisfies every check in this spec while draining nothing: the
bar never fires (no close attempted), the orphan rule is
satisfied (a run exists), the view shows the queue (nobody
reads it). The duty's core performance — *bring each item to
the operator* — is invisible to the machine. Closing the hole
mechanically means presentation-on-engagement ("when the
operator engages any run, open disclosures are surfaced"),
which is exactly the presentation half DR-5 narrowed away.
So: disposal is *routable* without a presentation surface, but
not *enforceably* so. DR-5 stands (verification view required),
but the decision sim's "graceful remediation" claim is
weakened — declare the cost: without presentation, drainage
relies on CoS diligence that no validator observes.

Estimated refusal cases revised: 23 → 25 (closure-bar + orphan-queue).
