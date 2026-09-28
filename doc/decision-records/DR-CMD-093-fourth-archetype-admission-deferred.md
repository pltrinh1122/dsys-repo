# DR-CMD-093 — fourth archetype admission deferred (O3 ratified)

- **Status:** ratified (defer)
- **Date:** 2026-09-27 ~17:03 PDT
- **Matter:** "The derived may-act × office archetype — demonstrated
  non-vacuous — should be admitted to the archetype set now via the
  critical-risk disjunct." Separator: Peter (operator default,
  designated at START; proposer = ambient agent, so external
  separation holds — not rehearsal).

## Disposition

Peter rendered "ratify O3" (~17:03 PDT 2026-09-27) on the /pb-decide
matter framed ~17:01 PDT. O3 (defer, recommended) is **ratified**:
the derived may-act × office archetype is NOT admitted now; its
derived invariant set, refusal table, and gap analysis are preserved
in this record as the admission-ready candidate; the Triad is
sustained; no changes to `doc/d1-d7-archetypes.md`.

## Background

- DR-CMD-092 ratified the two-axis archetype model (acting-posture ×
  reading-posture), documenting the unnamed may-act × office cell and
  restating the DR-CMD-069 admission rule as the model's completion
  condition.
- This session established the **admission-vs-derivation distinction**
  (Peter conceded the conflation): derivation produces the candidate
  (from the axes, prior judgment, refusal analysis); admission earns
  it a place in the vocabulary via DR-CMD-069's two disjuncts —
  (a) ≥2 built profiles sharing the shape, or (b) a demonstrated
  critical authoring risk that field + coupling C7 do not cover.
- The candidate below was derived analytically from the axes —
  non-vacuous, with zero exemplar profiles built — exercising the
  derivation side of the distinction. This matter tested the admission
  side.

## The derivation, preserved on file

The may-act × office cell: an agent **permitted to act on the world
but forbidden from consulting it** — action on operator disposition
using only presented bytes. Provisional designation only; the cell
label remains undisposed.

Invariant set (checkable facet constraints):

- D1 > 0.0 (may-act; distinguishes from staff's 0.0)
- D4 = 1.0 (operator-authorized actions only — staff's authorization
  discipline applied to acting)
- D5 > 0.0 with declared, bounded `write_scope`
- D7 = 0.75, `world_target=false` (office reading; distinguishes from
  field's 1.0)
- D2 declared, `commission_wins_ties` — action parameters bound by
  commission/disposition; presented bytes fill within bounds only
- D6 ⊆ {operator} (activation only; no stigmergic activation without
  external corroboration)

Non-vacuousness (no exemplar profile built):

- **(a) Satisfiable** — by composition of already-satisfied
  constraints: staff proves D4 1.0 + D7 0.75 is satisfiable; the
  executor proves D1>0 + D4 1.0 is satisfiable. The risk in the
  combination — acting without external corroboration — is the
  archetype's raison d'être, not a contradiction.
- **(b) Discriminating** — four hypothetical profiles, none built:

  |       | D1  | D4  | D7   | Verdict    | Reason                          |
  |-------|-----|-----|------|------------|---------------------------------|
  | P1    | 0.5 | 1.0 | 0.75 | **pass**   | would-be member                 |
  | P2    | 0.5 | 0.5 | 0.75 | **refused**| may-act without full operator authorization |
  | P3    | 0.5 | 1.0 | 1.0  | **refused**| reading-posture violation — field's cell |
  | P4    | 0.0 | 1.0 | 0.75 | **refused**| not may-act — staff+office territory |

- **(c) Non-redundant — the coverage gap.** No existing archetype
  checks the may-act×office coupling. Staff refuses P1/P2 at the door
  for D1 ≠ 0.0 — never examining their authorization discipline, so it
  cannot distinguish P1 (safe) from P2 (dangerous). Office checks
  reading posture only — P2 passes office clean. Field refuses all for
  D7 ≠ 1.0. A D1>0/D7 0.75 profile whose action parameters come from
  uncorroborated presented bytes is refused *nowhere for the right
  reason*.

## The real-world referent attempt, and its falsification

The disposition required a believable real-world shape behind the
invariants. Proposed referent: a **payroll disbursement executor** —
presented with a signed payroll file each cycle, moves the money;
may-act (D1>0, D5>0), office reading (validates signatures/schema of
the presented file; duty to the presented instrument).

Falsified in three cuts (material to the disposition):

1. The money-movement domain **legally requires what the archetype
   forbids**: OFAC/sanctions screening, fraud detection,
   destination-account validation, balance checks — every one a
   `world_target` consultation against external ground truth. A
   strict-office executor (`world_target=false`, ever) is not merely
   infeasible but non-compliant (banks must refuse even validly-signed
   instructions to mule accounts).
2. The example's safety came from **PKI, not from the invariants**:
   "accept only signed instructions" defeats the uncorroborated-email
   attack regardless of archetype — authentication infrastructure did
   the work the archetype was supposed to demonstrate.
3. The feasible residue — validate signature/schema, transfer per
   file — is a **deterministic pipeline** (automaton/run-book
   territory): no inference, no discretion, no agency. And the
   corroboration the example needed (hours, tax tables, account
   validity) was smuggled upstream into whoever built the file —
   the end-to-end system was never office.

**Recorded:** the payroll referent is falsified and unavailable as
the shape's referent. File-based disbursement execution exists, but
every real instance either consults external ground truth (→ field,
not office) or is a script (→ not an agent). Not even one feasible
referent exists yet, let alone two built profiles.

## Dialectic trail

- **Thesis:** the archetype is derived and proven non-vacuous; the
  coverage gap is real; the critical-risk disjunct exists precisely so
  admission needn't wait for exemplars — admit now.
- **Antithesis (steelmanned):** "demonstrated critical risk" with zero
  instances, zero near-misses, zero profiles refused for the wrong
  reason is *argument*, not demonstration; admitting on analysis alone
  sets the precedent that the risk disjunct is satisfiable by whoever
  argues best — gutting the ≥2-profiles discipline and the completion
  condition ratified in DR-CMD-092.
- **Synthesis:** keep the derivation on file as admission-ready; do
  not admit now; the trigger stays exactly as ratified. The falsified
  referent is one more count for deferral.

## Options with gate trails

- **O1 — admit now** (adopt via the critical-risk disjunct). G1 pass
  (falsifiable matter); G2 pass (implementation
  `core/package/factory_archetypes.py` as read 2026-09-27 can carry a
  fourth entry; set tuples; docs); **G3 CONDITIONAL** — no standing
  decision forbids admission; DR-CMD-069/092's risk disjunct provides
  the path, but whether analytic gap-analysis qualifies as a
  "demonstrated critical risk" is the separator's judgment, not
  ambient's (deliberately left unresolved); G4 pass (provisional
  designation only; invariants, docs, gate code specified). Draft
  verdict: adopt-if-qualified. **Not adopted.**
- **O2 — do not admit** (sustain the Triad; derivation stands as
  analysis only). G1–G6 pass. Draft verdict: sustain.
- **O3 — defer, with the derived set on file as the admission-ready
  candidate** (recommended, ADOPTED). G1–G6 pass. Draft verdict: defer.

## Consequences

- The derived invariant set, refusal table (P1–P4), coverage-gap
  analysis, and the falsified payroll referent are preserved in this
  record as the admission-ready candidate.
- The Triad is sustained; NO fourth archetype is added; no doc changes
  to `doc/d1-d7-archetypes.md` (deferral = the derivation lives in
  this record only).
- Trigger restated verbatim: a fourth archetype is admitted iff ≥2
  built profiles share the may-act shape, or a demonstrated critical
  risk (incident, near-miss, or a profile refused for the wrong
  reason) that field + coupling C7 do not cover.
- The payroll-referent falsification is recorded as one more count for
  deferral: not even one feasible referent yet, let alone two
  profiles.

## Uncertainties (G6)

- Cell label for the may-act × office cell still undisposed — needed
  only if the trigger fires.
- Whether analytic gap-analysis could ever clear the word
  "demonstrated" deliberately left undecided (O1's G3 conditional
  unresolved by design).

## Premises

DR-CMD-069 (archetype adoption + admission rule), DR-CMD-092
(two-axis model + completion condition),
`core/package/factory_archetypes.py` (invariant code as read
2026-09-27).

Next free identifier: DR-CMD-094 (DR-CMD-059 still reserved for PVB DoD).

---

## Addendum 2026-09-27 ~17:15 PDT — three vetted referent shapes; D2 correction

Recorded before DR-CMD-094's admission disposition. The deferral
consequence above ("not even one feasible referent yet") is superseded
by the findings below; the deferral *disposition* itself stands as
decided until DR-CMD-094.

**(a) Digest-poster (low-stakes) survives all cuts.** A team digest
poster — handed the team's presented standup notes each morning, posts
a formatted digest to Slack, never verifies notes against external
ground truth — was pressure-tested with the same three cuts that
falsified payroll: (1) the domain *rewards* office reading
(fact-checking standup notes would be bizarre and unwanted — the office
constraint is natural, not merely satisfiable); (2) the failure mode
(hallucinated digest items) has no external guard — no signature or
schema verifies "this item came from the notes," so the D2 invariant
does real, otherwise-unguarded work; (3) the value is *judgment*
(selecting highlights, summarizing, rewording), not fidelity — a
cron+template cannot supply it, so the residue is an agent, not a
script. Inclusion is NOT ruled out: one feasible referent shape exists.

**(b) Inbox-organizer vetted as clean occupant.** Presented inbox per
the email_ingest precedent (verified staff+office this morning);
mailbox action (move/delete/highlight) is D1>0/D5>0 on standing
disposition; classification judgment at runtime is genuine discretion.
Delete = trash-not-destroy — a bounded write_scope, exactly the D5
invariant the new cell names. Spam/phishing from bytes alone (no
reputation feeds) is weaker than feed-augmented but feasible — the
morning e2e classified five emails from bytes. It is the may-act
sibling of an already-verified profile: the smallest possible step from
existing green ground. Strongest referent yet.

**(c) News-crawler: fails as a single agent, survives restructured.**
A single agent crawling the open web reads *raw world claims* — field
reading by H1's definition ("harness-internal staged material, not raw
world claims"), not office; if it posts, it lands in the executor's
existing cell (field may-act). Restructured the architecture-native way
— a field fetcher (staff+field, like monitor) stages articles into a
corpus, and a **news-synthesizer-poster** (may-act × office) reads only
the staged corpus and posts the synthesis — the second half occupies
the new cell cleanly. The split is the harness's staging idiom, not
gerrymandering. Boundary conditions for the build: commissioned source
list; synthesis-of-coverage scope, not truth-seeking.

**(d) D2 correction.** This record's derivation said the cell's D2
invariant is "commission_wins_ties." DR-CMD-077 made D2 the binary
enum {principal_wins_ties, world_wins_ties} — there is no
commission_wins_ties value. The implemented invariant (DR-CMD-094,
CL6) is **principal_wins_ties**: the principal's commission binds
action parameters; presented bytes never win ties; world_wins_ties is
incoherent with office reading (no world_target).

Net: three vetted referent shapes (digest-poster, inbox-organizer,
news-synthesizer-poster). The trigger's first disjunct now has a
concrete build pair: inbox-organizer + news-synthesizer-poster.
