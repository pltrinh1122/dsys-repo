# Dialectic Mode — Enhancement Specs D1–D6

Spec-only. Nothing here is implemented. Derived from the chained
playbook-execution simulation (2026-09-18), which surfaced two link
types — *dependence* (premises, I-11) and *succession* (supersession
chains) — plus the findings that chains propagate stalls rather than
corruption, that rehearsal quarantine matters most in chains
(anti-laundering), and that the chain vocabulary is mode-specific.

Conventions: additive Optional fields with safe defaults. `Premise`
and `KillRecord` are nested pydantic models (not identity-keyed
entities).

Proposed implementation order: **D3 → D4 → D5 → D2 → D1 → D6.**
D2 reshapes `premises`, so D1 (which reads premises) is specified
against the typed shape and implemented after D2. D5 needs D4's parent
link. D6 is advisory and lands last.

---

## D3 — Deadlock quarantine

**Observation.** The chain break demonstration showed counters stalling
downstream via I-11. Dialectic has its own stall shape: thesis and
antithesis both survive gating, no synthesis emerges — a deadlock.
Nothing currently stops a downstream node from citing a deadlocked
record as a decided premise.

**Design.** `deadlocked` joins the verdict vocabulary. Citation
integrity treats it as uncitable — the chain can't build on a
deadlock; it must resolve it or route around it. No new validator:
this composes with the existing circuit breaker.

**Schema.**
- `DecisionRecord.verdict`: vocabulary documented as
  `adopted | killed | merged | deferred | superseded | deadlocked | draft`.
  (Plain `str` field; no enum migration.)

**Validators** (extend `_citation_integrity`):
- Add `"deadlocked"` to `_UNDECIDED_VERDICTS` (rename mentally to
  "uncitable verdicts"; keep the identifier to minimize churn, with a
  comment). A premise citing a deadlocked record → "premise cites
  deadlocked record".

**Golden-run cases.**
- (25) `rec9` (adopted, non-rehearsal) with premise citing `rec8x`
  (`verdict="deadlocked"`, dialectic, thesis + antithesis present, no
  synthesis) → flagged: "premise cites deadlocked record".

**Falsifier status.** Standing. If real runs never deadlock (synthesis
conditional always fires in-node), demote to documentation.

---

## D4 — Cross-node dialectic parentage

**Observation.** "Synthesis re-enters START" currently dies at the node
boundary. The dialectic trail is per-record, but chains continue
dialectics across mode boundaries (Chain 1's triage→ratify joint did
exactly this: the escalation's conflict became the ratify node's
dialectic matter). The continuation is implied, never linked.

**Design.** An explicit parent link for continued dialectics.

**Schema.**
- `DecisionRecord.dialectic_parent_id: Optional[str] = None` — the
  record whose dialectic this node's matter continues.

**Validators** (new `_dialectic_parent`, registered in the runner):
- `dialectic_parent_id` set but unresolvable in `decision_records` →
  violation "dialectic parent {id} missing".
- Resolves to a record with `dialectic=False` → violation "dialectic
  parent must be a dialectic record".
- (Checked in the dedicated validator, not the generic FK pass: the
  target condition is not mere existence.)

**Golden-run cases.**
- (26) `rec10` with `dialectic_parent_id="rec1"` where `rec1`
  has `dialectic=False` → flagged: "dialectic parent must be a
  dialectic record".
- Clean shape: `rec11` with `dialectic_parent_id="rec7x"` where
  `rec7x` has `dialectic=True` → passes.

**Falsifier status.** Standing unless dialectic parents are always the
immediately preceding node — then the link duplicates premises and
dies.

---

## D5 — Separator independence across links

**Observation.** E4's self-separation rule is per-node. Chains let it
leak: node 2 names as separator the *proposer of node 1*, whose
synthesis node 2 continues. Same capture, one link wider.

**Design.** Extend E4 across the D4 link. Coupled to E4's fate: if the
operator is always the separator everywhere, this never fires.

**Schema.** None — uses D4's `dialectic_parent_id` and the existing
`separator_id` / `proposer_id` / `rehearsal` fields.

**Validators** (extend `_dialectic_separator`):
- R has `dialectic_parent_id` resolving to P, R is dialectic,
  R.`separator_id` == P.`proposer_id`, and R.`rehearsal` is False →
  I-12 violation "separator across chain link must be independent".

**Golden-run cases.**
- (27) `rec12` (dialectic, proposer `a-leo`, separator `a-leo`,
  `dialectic_parent_id="rec7x"` where `rec7x.proposer_id="a-leo"`,
  `rehearsal=False`) → flagged: "separator across chain link must be
  independent".
- Same shape with `rehearsal=True` → passes (quarantine handles
  citability).

**Falsifier status.** Coupled to E4's measurement — evaluate together
after real runs.

---

## D2 — Typed premises: the cited antithesis

**Observation.** Premises are undifferentiated IDs. In a dialectic
chain it matters *which role* the cited record played — supporting
thesis, surviving antithesis, or separator's verdict. Without roles, a
record can claim "antithesis defeated" while citing only its friends.

**Design.** Premise entries carry a role. A dialectic record claiming a
synthesis must cite the antithesis it defeated with role `opposes` —
mechanizing the DFD's "genuine antithesis" requirement across the
chain.

**Schema.**
- `PremiseRole(str, Enum)`: `SUPPORTS | OPPOSES | SEPARATES`.
- `Premise(BaseModel)`: `record_id: str`,
  `role: PremiseRole = PremiseRole.SUPPORTS`.
- `DecisionRecord.premises: list[Premise]` (was `list[str]`).
  The `SUPPORTS` default keeps the migration honest: every existing
  premise was, in fact, cited in support.

**Migration.** `_citation_integrity` iterates `p.record_id`.
Golden-run premise lists migrate to typed form, e.g.
`premises=[Premise(record_id="disp1")]`. The three E1 cases keep their
assertions unchanged (their violations are about target state, not
role).

**Validators** (extend `_citation_integrity` or a new
`_dialectic_premises`; prefer the latter, registered in the runner):
- R has `dialectic=True`, `verdict="adopted"`, `synthesis` set, and no
  premise with `role == OPPOSES` resolving to a *decision record* →
  I-12 violation "synthesis without cited antithesis".
- (Antitheses live in records, not dispositions: the role check
  requires the target in `decision_records`.)

**Golden-run cases.**
- Migrate E1 cases 13/14 to typed premises (assertions unchanged).
- (28) `rec13` (dialectic, adopted, synthesis set,
  premises=[Premise("disp1")] only) → flagged: "synthesis without
  cited antithesis".
- Clean: `rec14` with an additional
  `Premise("rec7x", OPPOSES)` → passes.

**Falsifier status.** Structural answer built in: roles default for
ordinary records, but the validator *requires* an `opposes` premise on
adopted dialectic syntheses. If that requirement is later relaxed,
D2 rots per its falsifier and should be killed.

---

## D1 — Kill persistence across chain links

**Observation.** The chaining simulation's break demo covered stalls,
not resurrection: node 3 re-proposing an option node 2 killed *by
falsification* — quietly, without defeating the recorded kill. Every
other chain mechanism assumes kills stay dead; nothing enforces it.

**Design.** Kills are first-class sub-records. Resurrecting a killed
option requires defeating the recorded falsification: name the kill,
supply a new separator. Specified against D2's typed premises (hence
implemented after D2).

**Schema.**
- `KillRecord(BaseModel)`: `kill_id: str`
  (convention: `{record_id}:kill:{n}`, minted by the record author),
  `option_text: str`, `separator_id: str = ""`, `observation: str = ""`.
- `DecisionRecord.kills: list[KillRecord] = Field(default_factory=list)`
- `DecisionRecord.defeats_kill_refs: list[str] = Field(default_factory=list)`

**Validators** (new `_kill_persistence`, registered in the runner):
- For every record R with `selected` set: for every typed premise P
  resolving to a decision record T: for every kill K in T.`kills`:
  if `R.selected == K.option_text` (exact-string, E5's discipline)
  and `K.kill_id not in R.defeats_kill_refs` → I-11 violation
  "selects option killed in {P.record_id} by {K.separator_id} without
  defeating the kill".
- Rehearsal records are still checked (strictest reading): quarantine
  governs citability, not internal honesty.

**Golden-run cases.**
- (29) `rec15x` with `kills=[KillRecord(kill_id="rec15x:kill:1",
  option_text="dyad-principal", separator_id="h-op",
  observation="upward-disclosure incoherence")]`, verdict adopted;
  `rec16` (adopted, selected="dyad-principal",
  premises=[Premise("rec15x")], `defeats_kill_refs=[]`) → flagged:
  "without defeating the kill".
- Same shape with `defeats_kill_refs=["rec15x:kill:1"]` → passes.

**Falsifier status.** Standing iff exact-string matching holds up.
Reworded resurrections slipping through = theater = kill D1 unless
options get canonical IDs.

---

## D6 — Separator pedigree on citations

**Observation.** I-11 checks *that* a premise is decided, not *how* —
a synthesis separated by the operator and one separated by an external
auditor cite identically. Whether that distinction should ever gate
chain behavior is currently unknown.

**Design.** Advisory metadata only, per the proposal. A policy hook,
not a validator: load-bearing joints *may* one day require external
separation. The binary quarantine (E1/E4) keeps doing the real trust
work.

**Schema.**
- `DecisionRecord.external_separator: bool = False` — True when the
  separator is a named external auditor/hat rather than the operator.

**Validators.** None. (Deliberate: the proposal's falsifier is "no
chain behavior ever conditions on separator kind" — a validator now
would be decorative enforcement of decorative metadata.)

**Golden-run cases.** None with refusal semantics. Field-presence
assert: a record with `external_separator=True` validates clean.

**Falsifier status.** Kill D6 the first time anyone asks what it's
*for* and the answer is still "maybe someday."

---

## Net schema delta (D1–D6)

`DecisionRecord` gains: `kills`, `defeats_kill_refs`,
`dialectic_parent_id`, `external_separator`; `premises` retyped to
`list[Premise]`. New nested models: `Premise`, `PremiseRole`,
`KillRecord`. New validators: `_dialectic_parent` (D4),
`_dialectic_premises` (D2), `_kill_persistence` (D1); extensions to
`_citation_integrity` (D3), `_dialectic_separator` (D5). D6 adds no
validator by design.

Estimated new refusal cases: 1 (D3) + 1 (D4) + 1 (D5) + 1 (D2) + 1 (D1)
= 5, taking the golden run from 23 to 28. D6 contributes none.

---

## Falsification verdicts (2026-09-18, pre-implementation)

**D1 — SURVIVES, threat model narrowed.** The stated falsifier
("reworded resurrections slip through") assumes an *adversarial*
agent evading its own architecture — and its proposed remedy
(canonical option IDs) doesn't fix cross-record rewording either, so
the falsifier is malformed. The honest failure mode is *inadvertent*
resurrection: node 3 re-selecting node 2's killed option having
forgotten the kill, while citing node 2. Against forgetfulness,
exact-string matching on cited records catches the common case —
explicit reopening uses the same words, because defeating a kill
requires naming its kill ID. Survives with the threat model written
into the spec: guards citation-scoped forgetfulness, not evasion.
Resurrection without citation is out of scope by construction —
uncited ideas aren't owned.

**D2 — FALSIFIED as specified; requirement survives, mechanism
shrinks.** The premise-role retyping (supports/opposes/separates
across every premise, migration of E1's cases, `_citation_integrity`
churn) is over-machinery for the actual requirement, which is one
sentence: *a claimed synthesis must cite the antithesis it defeated.*
That is a targeted `antithesis_record_id: Optional[str]` field plus
one validator — a fifth of the churn, none of the migration. (The
`separates` role has no real consumer: separator verdicts are usually
operator speech, not records.) Redirect: implement the field, not the
retyping.

**D3 — FALSIFIED.** Two independent kills. (1) The playbook's
synthesis conditional already *mandates* re-entry when thesis and
antithesis both survive — a recorded deadlocked-but-adopted record
represents a run that violated the playbook, so the hole is at the
write site, not the citation site. (2) Quarantine is too blunt for
what deadlock *is*: "this question is settled as unresolvable" is a
legitimate, citable finding ("don't reopen the principal question"),
whereas "deferred with reason=deadlock" already covers the
not-yet-resolvable case in existing vocabulary. D3 would block the
former to prevent the latter. Redirect (unapproved, noted only): a
write-site "synthesis-required" check instead of read-site quarantine.

**D4 — FALSIFIED as specified.** Too narrow for its motivating case
and redundant otherwise. The motivating joint (Chain 1's
triage→ratify) has a *non-dialectic* parent — D4's validator
("parent must be a dialectic record") doesn't even cover the case
that motivated it. For genuinely dialectic continuations, the
adjacent case is already carried by premises; the empirical falsifier
(non-adjacent continuation) is untestable at spec time, which means
we'd be building on a guess. The honest remainder is a
*matter*-continuation link, not a dialectic-specific one — a bigger
claim (matter identity across nodes is undefined) for another day.

**D5 — FALSIFIED (dependent).** Falls with D4: without an explicit
continuation link, the machine cannot distinguish dialectic
continuation (where separator independence matters) from ordinary
support citation (where the operator routinely proposes and separates
— flagging that would misfire constantly). Revivable on a future
matter-continuation link; do not implement on premises alone.

**D6 — FALSIFIED by its own falsifier, at spec time.** The falsifier
reads: kill it the first time anyone asks what it's for and the
answer is still "maybe someday." Asked now, before implementation:
the answer is "maybe someday." No current consumer; E1/E4's binary
quarantine does the trust work. Killed. Re-propose if a consumer
appears.

Net survivors: **D1** (narrowed threat model) and the **D2 redirect**
(`antithesis_record_id`). D3–D6 dead.
