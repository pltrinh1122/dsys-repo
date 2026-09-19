# dsys-mutation-playbook — spec

Status: specified 2026-09-19, ratified policy; package implementation +
golden-run verification in this revision. Applicability amended 2026-09-19
(§9): the ladder describes the target system; the decision machinery is
operable today.

The second playbook, following the pattern of the decision-making
playbook (§8.2): a **set of definition-of-done conditionals** (never a
sequence), with its own gates, writing the shared DecisionRecord entity
(discriminated by `playbook`), disposed through the single disposition
machinery. Playbooks proliferate; disposition doesn't.

Matter: **whether and how to mutate/extend the installed dsys** —
post-installation, the user has maximum flexibility to mutate even
dsys's own files, via fork/clone of the dsys-repo (the software's own
repo — distinct from the accretion-repo, which holds the machine's
accreted state). Ratified 2026-09-19: mutation is allowed; *undisclosed*
mutation is the failure mode.

## 1. The ladder (the option space)

Every mutation matter enumerates these rungs, least → most invasive,
plus the explicit null option. The ladder is advisory order, not a
sequence — a matter may enter at any rung (re-entrant plays, I-4); gate
M1 evaluates whether lower rungs suffice, never assumed.

| rung | what changes | trust-boundary | upgrade fate |
|---|---|---|---|
| `configure` | `etc/config.yaml` | no | survives |
| `role` | new role bundle | no (framing only) | survives (roles dir) |
| `scenario` | new scenario | no (writes no records) | survives |
| `wrap` | scripts around `dsys` | no | survives (outside tree) |
| `patch` | edit `~/.dsys` in place | maybe | fights upgrade (`lib/` rebuilt) |
| `fork` | fork/clone the dsys-repo; own dist | maybe | upgrades come from your repo |
| (null) | do nothing | — | — |

The trust boundary for dsys, concretely: `lib/core` validators, the
referee, sync convergence, hash-chaining, manifest/doctor. Mutating
these voids the architecture's guarantees *for your tree* — allowed,
but you are then running a different machine, and you say so.

## 2. START — "open candidacy"

*When:* a mutation matter surfaces with no draft.

- Frame the matter as a falsifiable claim: "changing X will achieve Y
  without breaking Z."
- Enumerate the live rungs including the explicit null option.
- State the gates before evaluating. Inherited: **G1** well-formed,
  **G2** legitimate source, **G3** non-redundant, **G4** actionable.
  Mutation-specific:
  - **M1 ladder** — no lower rung suffices (criterion A1). A rung is
    killed when a lower one does the job.
  - **M2 trust-boundary declaration** — if the change touches the trust
    boundary, the voided guarantees are declared on the record
    (criterion A3 + the declared-mutation rule).
  - **M3 upgrade fate** — the mutation's fate on the next upgrade is
    stated (criterion A4): survives / rebuilt / comes-from-my-repo.
  - **M4 audience** — consumers named; if beyond the operator, fork
    identity declared so others know what they're trusting
    (criterion A5).
- Run G1–G4 + M1–M4 per rung, routing failures to STOP.

*Done when:* every rung carries a gate trail and each survivor has a
draft verdict (recommended rung) — and nothing is mutated.

## 3. STOP — "kill or merge"

*When:* a gate fails, a rung is falsified, a standing mutation decision
is challenged or superseded.

- Every kill names its reason: failed gate or killed-by-falsification
  with the falsifying observation cited — a rejection that can't name
  its reason is refused.
- Escalation rule: `patch` is killed for a trust-boundary change with
  an audience beyond the operator (M2+M4) — the rung must be `fork`
  (declared, versioned, attestable), never an undeclared in-place edit.
- Merge branch (G3): fold into an existing extension, record the alias.
- Supersession branch: a superseded mutation decision stands as valid
  history ("superseded by Record N"), not as error.

*Done when:* every non-selected rung is logged killed / merged /
deferred / superseded with its reason cited; the null option, if the
outcome, recorded explicitly, never silent.

## 4. KEEP — "promote and hold"

*When:* a draft verdict (recommended rung) exists.

- Run **G5**: binding vs provisional/advisory. Binding: the
  declared-mutation rule (doctor distinguishes pristine/mutated and
  reports what diverged; the manifest records fork identity) — mechanically
  checkable. Advisory: the criteria themselves — judgment, not validators.
- Enforce **G6**: uncertainties tagged (e.g. fork workflow details,
  upgrade-vs-mutated-tree behavior — both currently unspecified).
- Write the DecisionRecord: `playbook="dsys-mutation-playbook"`,
  matter, rungs with gate trails, **selected rung and selector named**,
  `touches_trust_boundary`, `voided_guarantees` (required when the
  boundary is touched — I-17), M3/M4 answers, consequences,
  uncertainties, timestamp.
- Submit to the disposer through the single disposition machinery:
  - **ratify** — adopt the recommended rung (proceed).
  - **overrule** — the operator overrides the recommended rung
    (e.g. playbook says `role`, operator insists `fork`); reason recorded.
  - **triage** — the mutation proposal is unclear or contested; exactly
    one outcome per the triage DoD.
  - authorize / set_standing available, rarely used here.
- Unratified = draft = not a decision (proposer ≠ disposer).

*Done when:* the record is complete per above and the disposition
recorded. A ratified mutation decision holds until falsified or
superseded; "falsify" re-triggers STOP.

## 5. Mechanical closures

- **I-17 (mutation-record closure):** a DecisionRecord with
  `playbook="dsys-mutation-playbook"` must name a valid rung
  (configure | role | scenario | wrap | patch | fork); if
  `touches_trust_boundary`, `voided_guarantees` must be non-empty.
  The validator checks *completeness of the declaration*, not its
  truth — author-declared, declared trust (cf. DR-5/A1); gameability
  tagged G6.
- **Declared-mutation rule (installer surface):** `dsys doctor`
  distinguishes pristine from mutated and reports what diverged;
  `var/manifest.json` records fork identity (repo/commit) when the
  tree derives from a fork. Attestation always covers the actual bytes.
- Exactly-one-record per mutation matter; the record is citable
  (E1) like any DecisionRecord.

## 6. Worked example

Matter: "Add a `lineage` view command to `dsys referee` showing
provenance chains."

- START: rungs enumerated. `configure` killed (M-fail: no config
  surface for new commands — fails G4). `role` killed (framing can't
  add a command). `scenario` killed (scenarios don't ship commands).
  `wrap` survives (a wrapper script could shell out) — M1: suffices?
  The view needs validator internals; wrapper would reimplement —
  killed by falsification (duplicates the referee's trust boundary
  without its checks). `patch` survives M1–M4 for the operator alone;
  `fork` survives.
- STOP: `patch` vs `fork` — audience is the operator only today, but
  the change touches the referee (trust boundary, M2): voided
  guarantees declared ("referee output no longer comparable across
  trees"). Draft verdict: `fork` (longevity + boundary proximity
  outweigh patch's speed — criterion B).
- KEEP: G5 — binding on the declared-mutation mechanics, advisory on
  the rung judgment. DecisionRecord written
  (`playbook="dsys-mutation-playbook"`, rung=`fork`,
  touches_trust_boundary=true,
  voided_guarantees=["referee outputs not comparable across trees",
  "fleet attestation must name the fork"]). Disposition: operator
  ratifies. Only then is the fork cut.

## 7. Relation to the decision-making playbook

| | decision-making (§8.2) | dsys-mutation (this spec) |
|---|---|---|
| shape | DoD conditionals, START/STOP/KEEP | same |
| gates | G1–G6 | G1–G4 + M1–M4 |
| record | DecisionRecord | DecisionRecord, `playbook` discriminated |
| disposition | ratify/authorize/set_standing/overrule/triage | same five modes, same DoDs |
| closures | I-2, I-11, I-12, … | + I-17 |

The mutation playbook does not duplicate disposition, records, or
closures — it specializes the matter and the gates.

## 8. Pre-registered falsifiers

- **F-M1:** the playbook cannot *prevent* mutation — only declare it.
  Any reading that promises prevention fails against root on the
  user's own filesystem (the O2 kill, carried forward).
- **F-M2:** `patch` is never the selected rung for a trust-boundary
  change with an audience beyond the operator (escalation rule, §3).
- **F-M3:** the ladder is advisory order, not a sequence (I-4); M1 is
  evaluated per matter, never assumed from position.
- **F-M4:** `voided_guarantees` is author-declared; I-17 checks the
  declaration's completeness, not its truth. A false declaration is a
  G6-tagged trust failure, not a validator failure.
- **F-M5:** if the six rungs prove insufficient (a future component
  that fits none), the ladder extends — the rung set is not closed.
  (The architecture "has very few dsys components at the moment";
  more will come.)
- **F-M6:** "the playbook is fully operable today." False — only the
  decision/record machinery is (§9). Executing rungs requires the
  installed system.

## 9. Applicability (amended 2026-09-19)

Falsification ("the current architecture supports extensibility as
referenced" — falsified 2026-09-19): the ladder in §1 describes the
*target* dsys system's extension surface, not the current package's.
As implemented:

- **Operable today:** the `scenario` rung (scenarios run on the exit
  contract; new scenario scripts are genuine extensions) — and the
  *decision* machinery itself. A mutation matter can be framed, gated,
  and recorded (I-17) before its rung exists. Recording the decision
  is separable from executing the rung: decide now, mutate later.
- **Developer mode (deliberately not a rung):** editing the
  machine-native package source directly (entities, validators, views,
  golden-run cases) — how the architecture itself is extended today.
  It is not on the ladder because the ladder decides post-installation
  mutation by a user of an installed dsys, a different matter from
  pre-installation development. Conflating them would muddy both.
- **Specified, not implemented:** `configure`, `role`, `wrap`,
  `patch`, `fork` (as a workflow), and the declared-mutation installer
  surface (doctor divergence reports, manifest fork identity). The
  playbook becomes fully operable once dsys exists as an installed
  thing.

## 10. Reason classification (2026-09-19)

Every mutation matter states its reason. The reason is classified —
the classification marks *evidentiary status*, not permission, except
the third rule, which is refusal-shaped:

- **accepted** — the reason is evidenced by observations in artifacts
  (records the system holds: transcripts, state, disclosures,
  evidence) and afferent (incoming observations arriving into the
  system). Evidence is what matters, regardless of who first stated
  the reason.
- **pending** — the reason comes from human disposition (the
  operator's judgment; terminal authority) but is not evidenced.
  Allowed — the operator's authority suffices — but marked: it rests
  on authority alone, awaiting corroboration.
- **refused** — mutation without reason is not allowed. At START, a
  matter with no stated reason is refused back for reframing
  (composes with "vague matters refused").

The separation is authority vs evidence: the human can always
authorize (pending) but cannot self-certify evidence (accepted
requires observations). Whether a status is *true* is author-declared
(declared trust, cf. F-M4); what is checkable is presence and shape —
implemented as I-17: `DecisionRecord.reason` (required on adoption;
`reason_status` must be `accepted`|`pending`).

G6 tagged: the reading of "afferent" (incoming observations —
disclosures, evidence records, anything arriving from outside);
what resolves `pending` (later evidence, expiry, explicit sustain —
unspecified); whether the classifier generalizes beyond mutation
matters (e.g. Condition versioning, when built).
