# Decision-Making Playbook

**Status: ratified machinery, implemented.** The decision machinery
(START/STOP/KEEP, G1–G6, disposition modes, dialectic) was ratified as
Architecture §8.2; the enhancements E1–E5, E7 were ratified under DR-4
(2026-09-18) and implemented in `core/package/{schema,validators,
golden_run}.py` (E6 was killed by its falsifier — §5). This document is
the consolidated canonical text, previously split between Architecture
§8.2/§8.3 and `playbook-enhancements-spec.md` (renamed 2026-09-21).
Architecture §8.2/§8.3 point here; they do not restate.

Conventions: `E` = base entity (the package's entity set before the
enhancements). New enums/fields are additive; all new fields Optional
with safe defaults so the existing golden chain passes unchanged (except
where noted).

---

## 1. Applicability — when this playbook applies, and when it does not

**Trigger.** A matter requires a decision that produces a disposition:
one of ratify | authorize | set_standing | overrule | triage, recorded
as a DecisionRecord. START opens candidacy when such a matter surfaces
with no draft.

**Non-trigger cases** (the playbook does not apply; entering START here
is refused back):
- **Execution sequencing.** Run-books drive execution; this playbook is a
  procedure the operator follows, not a node commanded — a run-book's
  step order never enters START (plane discipline).
- **Already-decided matters.** Cite the standing DecisionRecord. A
  re-decision with no falsification or supersession is refused at G3
  (non-redundant).
- **Rehearsal / simulation.** Simulation runs are quarantined (E1/I-11):
  a simulated outcome is never a disposition and never a premise.
- **Mutation matters.** Governed by the dsys-mutation-playbook (§8.4 of
  the Architecture), sharing the DecisionRecord entity discriminated by
  `playbook`.
- **Pure inference with no disposition.** Judgment without a disposition
  act (e.g. assessments, exploratory analysis) — no START, no record.
- **Mechanical closures.** Validator-enforced invariants (I-1..I-17)
  fire without the playbook's START.

---

## 2. Exercise — executed runs

**Executed run.** `core/package/golden_run.py::run()` — deterministic
machine run, executed 2026-09-21: **ok=True, 0 violations, 37 refusal
cases.**
- Admit path: case 1 — clean chain validates, including DecisionRecord
  records carrying the E-fields (`separator_id`, `state_ref`,
  `response`, `premises`).
- Kill paths: E1 cases 13–14 (quarantined-rehearsal premise,
  undecided-record premise); E4 cases 15–16 (dialectic without
  designated separator, self-separation unlabeled as rehearsal); E2
  cases 17–18 (stale authorization, authorize without state binding);
  E3 cases 19–20 (counter without counter text, counter-proposed
  disposition left approved); E7 cases 21–22 (absorption citing a
  missing directive, absorption on a non-overrule disposition); E5
  cases 23–24 (triage selecting the null option, authorize with no
  disposition = NO_ACTION). DR-1/2/3-era cases 2–12 exercise the base
  machinery.

**Derivation history (not an executed run).** Five disposition-mode
simulation runs (2026-09-18, all modes, no records written) surfaced the
E-observations. Simulations are never cited as executions (E1
quarantine).

**Ratification.** DR-4 (2026-09-18): implement E1–E5, E7 in spec order;
E6 killed by its falsifier.

---

## 3. The playbook

Parameters per decision: the *matter*, the *gate list*, the *exclusion
rules*, the *disposer* (terminal authority), and the *disposition mode* —
ratify | authorize | set_standing | overrule | triage — each with its own
definition of done. Plays are definition-of-done
conditionals — entry trigger + exit condition — condition-triggered and
re-entrant, never ordered steps (I-4).

Gates: **G1** well-formed (stated precisely enough to evaluate); **G2**
legitimate source (evidence from a source trusted for this domain); **G3**
non-redundant (not already decided, no duplicate of a standing decision);
**G4** actionable (adopting it changes a commitment, state, or behavior);
**G5** checkable (verifiable afterward whether the decision held → binding,
else provisional/advisory); **G6** uncertainty tagged (assumptions, unknowns,
provisional sources labeled; nothing material unlabeled).

**START — "open candidacy."** *When:* a matter surfaces with no draft.
Frame the matter as a falsifiable claim (vague matters refused back for
reframing); enumerate live options including explicit "decide nothing";
state gates before evaluating; run G1–G4 per option, routing failures to
STOP. *Done when:* every option carries a gate trail and each survivor has
a draft verdict — and nothing is admitted or decided.

**STOP — "kill or merge."** *When:* a gate fails, an exclusion fires, an
option is falsified, a standing decision is challenged or superseded.
Every kill names its reason: failed gate, exclusion rule, or
**killed-by-falsification** with the falsifying observation cited — a
rejection that can't name its reason is refused. Merge branch (G3): fold
into the canonical decision, record the alias. Falsification branch: demote
a standing decision exactly to the tier its surviving gates support.
**Supersession branch** (distinct from falsification): record "superseded
by Record N"; the original stands as valid history, not as error.
*Done when:* every non-adopted option is logged killed / merged / deferred
/ superseded with its reason cited; "decide nothing," if the outcome, is
recorded explicitly, never silent.

**KEEP — "promote and hold."** *When:* a draft verdict exists. Run G5
(binding vs provisional/advisory); enforce G6; write the DecisionRecord:
matter, options with gate trails, **selected option and selector named**
(selection among survivors is the disposition act), consequences (what the
decision changes, per G4), uncertainties, timestamp. Submit to the
disposer: ratify or reject recorded; unratified = draft = not a decision
(proposer ≠ disposer). *Done when:* the record is complete per above and
the disposition recorded. Standing rule: a ratified decision holds until
falsified or superseded; "falsify" re-triggers STOP.

Boundary: where framer and disposer are the same person, step 4 degrades
to explicitly recorded self-ratification; protection then comes from G5/G6,
not from separation of roles. Batch disposition (ratify a log with per-row
veto) is an operational mode, not a weaker gate.

**Disposition modes** (parameter on the disposition gate; a disposition
reaches only the hat that owns it):
- **ratify** — resolve a decision matter: select among surviving options.
  DoD: selected option and selector named on the DecisionRecord; one Y/N
  CTA per turn.
- **authorize** — permit a named action, esp. irreversible (leo N6). DoD:
  the action is named explicitly (`action_ref`); authorization precedes the
  action — post-hoc approval is not authorization; silence or bundled
  consent is not authorization; scope-bounded to what is named.
  Consumption-side: irreversible operations (`try_promote`, I-8) require a
  cited approved AUTHORIZE-mode disposition — a ratify-mode disposition is
  refused at the read site, not just the write site. Freshness (E2): the
  disposition binds the artifact's hash at disposition time
  (`state_ref`); a stale or unbound authorization refuses exactly like a
  missing one. Silence (E5): no authorization, no action.
- **set_standing** — establish persistent policy (e.g. interaction
  preferences). DoD: the rule stated durably with its domain
  (`standing_domain`); effective-from recorded; prior policy on the same
  domain superseded by reference (`supersedes_disposition_id`), never
  silently overwritten — one supersession chain per domain, exactly one
  root, no cycles; revocable — the record states how. Silence (E5):
  keeping the status quo is a decision and must be recorded as explicit
  sustain.
- **overrule** — defeat a standing veto/objection. DoD: names the veto
  (`veto_id`, must exist) and the authority cited (fleet_wins |
  local_wins); reason recorded; the overruled veto stays logged as
  overruled, never deleted. Effect-side: a veto with status overruled must
  cite its backing approved overrule disposition. Absorption (E7): the
  disposition may name the directive amendment absorbing the veto's
  reason (`absorbed_into_directive_id`) — the reason survives as a
  constraint; only the blocking is defeated. Silence (E5): sustain must
  be recorded.
- **triage** — dispose of an upward disclosure (conflict/error/uncertainty).
  DoD: every disclosure gets exactly one outcome — acknowledged |
  escalated (names the hat) | dismissed with reason; silence is not triage.
  Checkable via the Disclosure entity: every non-open disclosure cited by
  exactly one triage disposition, none cited by more than one. A
  triage-mode record may not select the enumerated "decide nothing"
  (E5) — that is the smuggling case, refused mechanically.

**Dialectic mode** (parameter, engaged when the matter is truth-apt rather
than mere choice among options):
- START requires every option to carry its strongest counter (Proposal-
  Framing); strawman options are refused at G1 — "well-formed" extends to
  "steelmanned," and antithesis must be genuine, non-strawman (DFD).
- STOP's killed-by-falsification must name the **external separator** (IFF2):
  the falsifying observation must come from outside the proposer's frame.
  Self-falsification is labeled *rehearsal*, not falsification.
  Separator designation (E4, I-12): entering dialectic mode requires naming
  the separator (operator default, or a named external auditor/hat). No
  designated separator → the run is rehearsal by construction, and its
  record is quarantined under I-11.
- Synthesis conditional: when thesis and antithesis both survive gating, a
  synthesis option is framed and re-enters START before any disposition
  (re-entrant plays, I-4).
- DecisionRecord gains the dialectic trail: thesis / antithesis / synthesis /
  separator, alongside options, gate trails, and consequences.
- Disposition honors at most one Y/N CTA per turn (DFD); batch mode runs
  as sequential single-CTA turns, not one bundled vote.

---
## 4. Enhancement mechanisms E1–E5, E7 (DR-4, implemented)

Each spec was written to be implementable directly: schema changes,
validator changes, golden-run cases — and each is implemented in
`core/package/{schema,validators,golden_run}.py` (committed; golden run
PASS, §2). "Falsifier status" records the standing survival condition
per enhancement.

---

### E1 — Rehearsal quarantine + citation integrity

**Observation.** Four of five simulation runs caught the same fabrication:
an option citing a simulated, draft, or otherwise unratified record as if
decided (triage's dismissed-option citing the unratified DR-4 synthesis;
authorize's refuse-option; set_standing's restated counter; overrule's
near-miss citing the simulated posture policy). Every catch was
posture-dependent. None was mechanical.

**Design.** Two mechanisms:
1. *Rehearsal quarantine.* Records produced in rehearsal are flagged and
   cannot be cited as premises by non-rehearsal records.
2. *Citation integrity.* An option's supporting premises are explicit
   record-ID citations; every cited premise must resolve to a real,
   ratified-or-approved, non-quarantined record.

**Schema.**
- New entity `DecisionRecord(E)` — the package models dispositions but
  not decision records; §8.3 describes the fields. Add it now:
  - `matter: str`
  - `options: list[str]` (option texts; gate trails ride alongside as
    `gate_trails: list[str]`, parallel)
  - `selected: Optional[str]`
  - `selector_id: str`
  - `verdict: str` (adopted | killed | merged | deferred | superseded)
  - `consequences: str = ""`, `uncertainties: str = ""`
  - `premises: list[str] = []` — record IDs cited as supporting premises
    (DecisionRecord or Disposition IDs)
  - `dialectic: bool = False`, `separator_id: Optional[str] = None`,
    `thesis/antithesis/synthesis: Optional[str] = None` (see E4)
  - `rehearsal: bool = False`
  - `disposition_id: Optional[str] = None`
- `SystemState.decision_records: dict[str, DecisionRecord]`.

**Validators** (new `_citation_integrity`, registered in the runner):
- For every non-rehearsal DecisionRecord `r`, for every `pid` in
  `r.premises`: `pid` must resolve in `decision_records` or
  `dispositions`; if it resolves to a DecisionRecord with
  `rehearsal=True` → violation "premise cites quarantined rehearsal
  record"; if it resolves to a record whose verdict/status is not in
  (adopted/approved/acted) → violation "premise cites undecided record".
- FK entries: `("decision_records", "disposition_id", "dispositions",
  False)`. Premise IDs are checked by the dedicated validator, not the
  generic FK pass (they span two collections).

**Golden-run cases.**
- (a) `rec2` (non-rehearsal) with `premises=["rec-sim"]` where `rec-sim`
  has `rehearsal=True` → flagged: "premise cites quarantined rehearsal
  record".
- (b) `rec3` with `premises=["rec-draft"]` where `rec-draft.verdict`
  is unset/draft → flagged: "premise cites undecided record".
- (c) clean chain: `rec1` cites `disp1` (approved) → passes.

**Falsifier status.** Survives iff premises are writable as ID lists.
They are: `premises: list[str]` is a first-class field, not prose
mining. The spec does not attempt to extract citations from free text.

---

### E2 — Authorization freshness binding

**Observation.** The authorize simulation's G6 produced a freshness
condition ("valid only while the artifact is unchanged") as prose. Prose
doesn't refuse.

**Design.** Authorize dispositions bind the named action *and* the state
the authorization was evaluated against. Consumption sites verify both;
stale authorization refuses exactly like missing authorization.

**Schema.**
- `ArtifactPackage.content_hash: str = ""` — canonical hash of the
  artifact's canonical JSON, computed at artifact close (sha256). This
  answers the falsifier inside the spec: the hash source is named.
- `Disposition.state_ref: Optional[str] = None` — the artifact hash the
  authorization was evaluated against (authorize mode only).

**Validators.**
- I-2: authorize-mode disposition with approved/acted status and empty
  `state_ref` → violation "authorize without state binding".
- `try_promote`: after the existing mode/status checks, require
  `d.state_ref` non-empty and `d.state_ref == artifact.content_hash`,
  else refuse "authorization is stale: artifact changed since
  disposition (N6)".
- I-8: promotion whose disposition's `state_ref` mismatches the
  artifact's current `content_hash` → violation.

**Golden-run cases.**
- (a) `disp1.state_ref` set to `art1`'s hash at build → existing promote
  path passes (update `build_state`: `art1` gains a fixed
  `content_hash`, `disp1.state_ref` matches it).
- (b) `try_promote` with a disposition whose `state_ref` is a stale
  hash → refused: "authorization is stale".
- (c) approved authorize disposition with empty `state_ref` →
  I-2 violation.

**Falsifier status.** Survives: hash source named (`content_hash` at
artifact close). If a future artifact type has no canonical bytes, that
type cannot be authorize-bound — the validator then requires
`content_hash` non-empty for any artifact cited by a promotion.

---

### E3 — CTA response grammar

**Observation.** The triage simulation's operator answered the single
Y/N CTA with a counter-proposal ("No. Escalate. Name the hat."). The
agent improvised the re-entry correctly, but the move is uncodified:
"at most one CTA per turn" has no response-side companion.

**Design.** Disposition responses are ternary; a counter-proposal keeps
the disposition PROPOSED, records the counter text, and spawns a linked
synthesis re-entry.

**Schema.**
- `DispositionResponse(str, Enum)`: `YES | NO | COUNTER`.
- `Disposition.response: Optional[DispositionResponse] = None`
  (None = legacy / not yet answered).
- `Disposition.counter_text: Optional[str] = None`
- `Disposition.reentry_ref: Optional[str] = None` — the re-entered
  matter/run ID spawned by a counter.

**Validators** (extend `_disposition_modes`):
- `response == COUNTER` requires non-empty `counter_text`, else
  violation "counter response without counter text".
- `response == COUNTER` with `status` in (APPROVED, ACTED) → violation
  "counter-proposed disposition cannot be approved".
- `response == YES` with `status` == PROPOSED → violation "affirmed
  disposition left proposed" (the CTA was answered; the status must
  follow).

**Golden-run cases.**
- (a) disposition with `response=COUNTER`, empty `counter_text` →
  violation.
- (b) disposition with `response=COUNTER`, `status=APPROVED` →
  violation.
- (c) disposition with `response=YES`, `status=APPROVED`,
  `counter_text` set and linked `reentry_ref` → passes (the triage
  run's shape, had it been recorded).

**Falsifier status.** Standing. If counter-proposals prove rare in real
runs, this stays a small enum, not a burden — the cost of carrying it
is three Optional fields.

---

### E4 — Separator designation at START

**Observation.** The operator served as separator in both dialectic runs
by default, never by declaration. An undeclared separator is how
rehearsal masquerades as dialectic.

**Design.** Entering dialectic mode requires naming the separator. No
designated separator → the run is rehearsal by construction, and its
record is quarantined under E1.

**Schema** (rides on the new `DecisionRecord` from E1):
- `DecisionRecord.dialectic: bool = False`
- `DecisionRecord.separator_id: Optional[str] = None`
- `DecisionRecord.proposer_id: str` (needed for the self-separation
  check; the existing playbook rule "self-falsification is labeled
  rehearsal" becomes mechanical).

**Validators** (new `_dialectic_separator`):
- `dialectic=True` with empty `separator_id` → violation "dialectic
  without designated separator".
- `dialectic=True` with `separator_id == proposer_id` and
  `rehearsal=False` → violation "self-separation must be labeled
  rehearsal".
- `dialectic=True` with `separator_id == proposer_id` and
  `rehearsal=True` → passes (rehearsal quarantine handles citability).

**Golden-run cases.**
- (a) dialectic record, no `separator_id` → violation.
- (b) dialectic record, separator == proposer, `rehearsal=False` →
  violation.
- (c) dialectic record, separator == proposer, `rehearsal=True` →
  passes (quarantined).
- (d) dialectic record, external separator, `rehearsal=False` →
  passes.

**Falsifier status.** Standing unless the operator is always the
separator in practice — measurable after real runs; if so, fold into a
default and demote the rule.

---

### E5 — Mode-specific silence semantics

**Observation.** Silence meant opposite things across runs — triage:
failure; authorize: safe default; set_standing/overrule: status-quo
smuggling caught by G3. The meaning was derived per-run, never declared
per-mode.

**Design.** The silence meaning is data on the mode, not prose in the
run. A declared table; consumption sites consult it; one new
mechanical check kills the smuggling case.

**Schema.**
- `SilenceMeaning(str, Enum)`: `NO_DECISION` (ratify — unratified means
  draft), `NO_ACTION` (authorize — no authorization, no action),
  `OUTCOME_REFUSED` (triage — silence is not triage),
  `SUSTAIN_MUST_BE_RECORDED` (set_standing, overrule — keeping the
  status quo is a decision and must be recorded as explicit sustain).
- `MODE_SILENCE: dict[DispositionMode, SilenceMeaning]` in schema.py;
  `resolve_silence(mode)` helper consulted by `try_` operations.

**Validators** (extend `_disposition_modes`):
- Triage-mode DecisionRecord whose selected option is the explicit
  "decide nothing" → I-2 violation "triage: silence is not an outcome".
  (The smuggling case, mechanically closed. Detection: selected option
  text matches the enumerated "decide nothing" option — options are
  `list[str]`, so this is exact-string comparison against the option
  the START phase enumerated, not prose mining.)

**Golden-run cases.**
- (a) assert the table: `MODE_SILENCE` maps all five modes, values as
  above.
- (b) triage-mode record selecting "decide nothing" → violation.
- (c) authorize path with no disposition → `try_promote` refuses
  (already the behavior; now documented as `NO_ACTION`).

**Falsifier status.** Standing. If a sixth mode needs a fourth silence
meaning, the table grows — it was designed as data precisely so it
can.

---

### E7 — Defeat-with-absorption as a named pattern

**Observation.** The overrule synthesis didn't just defeat the veto —
it absorbed the veto's reason into the amended directive. That move is
the natural shape of overrule done right, not a one-off.

**Design.** Name the pattern: an overrule disposition may carry the
directive amendment that absorbs the defeated reason. The reason
survives as a constraint; only the blocking is defeated.

**Schema.**
- `Disposition.absorbed_into_directive_id: Optional[str] = None`
  (overrule mode only) — the directive whose amendment carries the
  veto's reason.
- FK: `("dispositions", "absorbed_into_directive_id", "directives",
  False)`.

**Validators** (extend `_disposition_modes`):
- `absorbed_into_directive_id` set on a non-overrule disposition →
  violation "absorption is an overrule pattern".
- Overrule with `absorbed_into_directive_id` set: the cited directive
  must exist (FK/RI) and the disposition must be approved/acted, else
  "absorption cites an undecided amendment". (Whether the amendment
  text faithfully carries the veto's reason is a truth obligation for
  the dyad — same boundary as E1's premise honesty.)

**Golden-run cases.**
- (a) overrule disposition with `absorbed_into_directive_id`
  citing a missing directive → RI violation.
- (b) ratify-mode disposition with `absorbed_into_directive_id` set →
  violation.
- (c) clean absorption: overruled veto + backing approved overrule
  disposition citing an existing amended directive → passes (the
  overrule run's shape, had it been recorded).

**Falsifier status.** Standing unless three real overrules pass without
needing absorption — then it demotes to an example.

---

## 5. E6 — KILLED by its falsifier

**Proposal was:** standing-policy migration — memory-text policy →
root disposition with back-reference.

**Falsifier held:** migration risks rewriting history — the disposition
can claim the text said something it didn't. No verbatim-quoting
discipline was proposed that the machine could check, and a human
auditing every migration reintroduces the narrative reference the
proposal tried to eliminate. Keep the narrative reference (set_standing
run's solution): the record names the memory-text policy it supersedes;
the validator checks the chain; the dyad checks the reference. The
boundary is honest and stays.

---

## 6. Decision records

**DR-1 — CoS-run coexistence invariant (ratified 2026-09-18).**
Matter (falsifiable): "The enforced Harness run invariant is honestly
stated and mechanically checkable." Options: (a) keep the separate-counting
exception; (b) distinct principal for the CoS run; (c) refine to per
(principal, authority-scope); (d) defer as provisional; (e, synthesis) adopt
(c) with authority-scope defined as execution | governance, scopes disjoint
by construction. Gate trails: (a) G1–G4 pass, antithesis unrebutted (silent
carve-out, name≠check); (b) G1–G4 pass, conditional on principal being
per-agent (G6: principal's definition uncertain); (c) G1 conditional on
defining authority-scope; (d) demoted to fallback (PASS would certify
unapproved semantics). Dialectic trail: thesis (a); antithesis — the
exception is architecture-derived, never approved, a different invariant
wearing the old name; synthesis (e) — the invariant protects against
*competing uncommitted state*, and governance does not compete with
execution. Separator: Peter (agent run labeled rehearsal). Selected option:
(e). Selector: Peter. Consequences: AuthorityScope enum added;
`is_chief_of_staff` removed (single-home); I-9 reworded with no exception;
golden run gains a 6th refusal case (second execution run refused).
Uncertainties: principal's exact definition (operator vs agent) still open —
(b) revives iff principal proves per-agent. Standing: ratified; holds until
falsified or superseded.

**DR-2 — disposition modes as playbook parameter (ratified 2026-09-18).**
Matter (falsifiable): "The decision-making playbook contains all modes of
Operator disposition." Falsification (4 angles): authorization-of-action ≠
ratification-of-record (leo N6 irreversible actions); standing dispositions
(interaction preferences) are persistent, not episodic; hat routing
(Founding form gate, Steward intake, Bond ratifier) — a disposition reaches
only the hat that owns it; overrule defeats a veto rather than selecting an
option. Commit conceded as ratify-mode. Claim falsified; synthesis:
disposition *mode* becomes a playbook parameter — ratify | authorize |
set_standing | overrule | triage — each with its own DoD conditionals.
Selected option: extend (not narrow). Selector: Peter. Consequences:
DispositionMode enum + mode-gated fields on Disposition; I-2 extended with
mode-DoD validator; golden run gains 7th refusal case (nameless
authorization refused). Standing: ratified; holds until falsified or
superseded.

**DR-3 — mechanical closures for disposition modes (ratified 2026-09-18).**
Matter: "each disposition mode maps to checkable exit DoD." Stress test:
ratify ✓ (DR-1 exercised it); authorize leaked at consumption
(`try_promote` accepted any disposition for irreversible publish);
set_standing had no standing-record linkage or supersession reference;
overrule's effect chain dangled (unbacked overruled veto possible); triage
was unmappable (no Disclosure entity). Synthesis: checks belong at read
sites, not just write sites. Selected: implement all four closures.
Selector: Peter. Consequences: Disclosure entity + exactly-one-triage
validator; `try_promote`/I-8 require approved AUTHORIZE-mode disposition
(disp1 is now the exemplar); `supersedes_disposition_id` + one-chain-per-
domain validator; overruled vetoes must cite backing overrule disposition;
golden run grows to 11 refusal cases. Standing: ratified; holds until
falsified or superseded.

**DR-4 — simulation-derived playbook enhancements (ratified 2026-09-18).**
Matter: "which simulation observations become mechanisms." Five
disposition-mode simulation runs (all modes, no records written)
surfaced seven candidate enhancements; Peter's verdicts: E1 rehearsal
quarantine + citation integrity Y, E2 authorization freshness binding Y,
E3 CTA response grammar Y, E4 separator designation Y, E5 mode silence
semantics Y, E6 standing-policy migration N (killed by its falsifier —
migration risks rewriting history; the narrative reference stands), E7
defeat-with-absorption Y. Selected: implement E1–E5, E7 in spec order.
Selector: Peter. Consequences: DecisionRecord entity added (the package
had dispositions but no decision records); I-11, I-12; authorize binds
artifact hash; CTA responses yes/no/counter; MODE_SILENCE table;
defeat-with-absorption pattern; golden run grows to 23 refusal cases,
PASS. Standing: ratified; holds until falsified or superseded.

---

## 7. Implementation order (executed)

E1 → E4 (E4 rides E1's DecisionRecord) → E2 → E3 → E7 → E5. E1 first:
it is the premise-citation substrate the others reference. Estimated new
refusal cases at spec time: 2 (E1) + 2 (E2) + 2 (E3) + 3 (E4) + 1 (E5)
+ 2 (E7) = 12, taking the golden run from 11 to 23. Later additions
(flow I-14/I-15/I-16, DR-5 disclosure surface, mutation I-17) grew it to
37 refusal cases, PASS, 0 violations (executed 2026-09-21, §2).

---

## Glossary

- **admission** — the START gate: a matter enters candidacy only when
  framed as a falsifiable claim with live options enumerated.
- **authorize** — a disposition mode: permit a named action (esp.
  irreversible); binds the artifact's hash (`state_ref`); silence is
  NO_ACTION.
- **CTA** — call to action: the disposer's Y/N prompt; at most one per
  turn; responses are YES | NO | COUNTER (E3).
- **DecisionRecord** — the record written on disposition (E1): matter,
  options with gate trails, selected option and selector, consequences,
  uncertainties, premises, verdict; shared with the dsys-mutation-
  playbook discriminated by `playbook`.
- **dialectic** — the truth-apt mode: thesis/antithesis/synthesis with a
  designated external separator; self-falsification is rehearsal.
- **disposition** — the disposer's terminal act on a matter: ratify |
  authorize | set_standing | overrule | triage, each with its own DoD.
- **disposer** — the terminal authority; disposition requires the
  disposer's act (proposer ≠ disposer).
- **DoD conditional** — a play: entry trigger + exit condition,
  condition-triggered and re-entrant, never an ordered step.
- **falsify** — the operator's opt-in challenge posture: a claim or
  mental model attacked with its own inferred conclusion; survivors are
  specified, the killed are recorded.
- **gate (G1–G6)** — the six matter gates: well-formed, legitimate
  source, non-redundant, actionable, checkable, uncertainty-tagged.
- **hat** — the authority a disposition reaches; a disposition reaches
  only the hat that owns it.
- **KEEP** — the play that promotes a draft verdict: G5/G6, write the
  DecisionRecord, submit to the disposer.
- **overrule** — a disposition mode: defeat a standing veto, absorbing
  its reason into a directive amendment (E7); sustain must be recorded.
- **playbook** — a set of definition-of-done conditionals governing a
  decision domain; never a sequence.
- **premises** — the record-ID citations supporting a decision; every
  cited premise must resolve to a real, decided, non-quarantined record
  (E1).
- **proposer** — the party framing the matter and its options; never the
  disposer of the same matter.
- **ratify** — a disposition mode: select among surviving options;
  unratified = draft = not a decision.
- **rehearsal** — any unratified, simulated, or self-separated run; its
  records are quarantined and cannot be cited as premises (E1).
- **run-book** — a strictly sequential procedure driving execution; the
  playbook never sequences run-books (plane discipline).
- **separator** — the external party whose falsifying observation kills
  an option; designated at START in dialectic mode (E4).
- **set_standing** — a disposition mode: establish persistent policy,
  superseding prior policy by reference; sustain must be recorded.
- **silence meaning** — the per-mode declared meaning of silence:
  NO_DECISION | NO_ACTION | OUTCOME_REFUSED | SUSTAIN_MUST_BE_RECORDED
  (E5).
- **START** — the play that opens candidacy: frame the matter, enumerate
  options, state gates, run G1–G4; nothing admitted or decided.
- **standing decision** — a ratified decision; holds until falsified or
  superseded.
- **STOP** — the play that kills or merges: every kill names its reason;
  "decide nothing" is recorded explicitly, never silent.
- **triage** — a disposition mode: dispose of an upward disclosure
  (acknowledged | escalated | dismissed); silence is not triage.
- **veto** — a standing objection defeatable only by overrule with cited
  authority.
