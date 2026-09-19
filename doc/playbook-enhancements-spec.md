# Decision-Making Playbook — Enhancement Specs E1–E5, E7

Spec-only. Nothing here is implemented. Each spec is written to be
implementable directly: schema changes, validator changes, golden-run
cases. Derived from the five disposition-mode simulation runs
(2026-09-18). E6 was killed by its falsifier and is recorded at the end.

Conventions: `E` = base entity. New enums/fields are additive; all new
fields Optional with safe defaults so the existing golden chain still
passes unchanged (except where noted).

---

## E1 — Rehearsal quarantine + citation integrity

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

## E2 — Authorization freshness binding

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

## E3 — CTA response grammar

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

## E4 — Separator designation at START

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

## E5 — Mode-specific silence semantics

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

## E7 — Defeat-with-absorption as a named pattern

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

## E6 — KILLED by its falsifier

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

## Implementation order (proposed)

E1 → E4 (E4 rides E1's DecisionRecord) → E2 → E3 → E7 → E5.
E1 first: it is the premise-citation substrate the others reference.
Estimated new refusal cases: 2 (E1) + 2 (E2) + 2 (E3) + 3 (E4) + 1 (E5)
+ 2 (E7) = 12, taking the golden run from 11 to 23.
