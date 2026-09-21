# Production-driver matter: the process side that runs the updater flow

**Status: ADOPTED (narrowed, with conditions, DR-CMD-049)** —
disposed 2026-09-21. Framed under DR-CMD-048 (NBA O2),
evaluated the same turn (NBA O2 selection); the operator
selected "Adopt with conditions (narrowed)." Draft verdict
history: adopt-with-conditions (narrowed) — this evaluation.

**Spec:** `doc/production-drive-contract-spec.md` (ADOPTED,
DR-CMD-050, 2026-09-21) — the adopted contract specified: D1
the initiator is the operator; D2 invocation through the
CLI's flow-drive surface strapping a Harness (AX1/AX2); D3
the principal binding; D4 the K3 tripwire; D5 the manifest
read at initiation with the tool verifying per write
(governed/process split); D6 full profile only; D7 after
fail-closed (no retry, record, surface); I-26
authorized-initiation validator (R3); replay story (R1);
trust declared (R5); five checkable acceptances incl. the
ambient-initiation refusal (R2); the (b)-half boundary
settled (G6 Q3). Adopted-byte hash:
`ae55cda8fca174f69b868a2d0e55215b2b41e59300a6b940aded372b0a48c35a`.
Build not authorized — follows on the operator's separate
direction.

**Build:** 2026-09-21 — `core/package/updater.py` gains the
drive-contract block: `DriveInitiation` (the initiation record),
`DriveRefused` (refusal before start), `i26_authorized_initiation`
(the R3 predicate), and `production_drive()` (the gated entry point:
D6 profile gate, I-26 gate, D5 one-time manifest read, D7
fail-closed aftermath — record, surface, no retry, no
re-initiation). `core/package/drive_contract_golden_run.py` covers
the five acceptances plus the I-26 R3 discharge. Verified: the new
golden run (ok, 0 violations, 6 refusals), the updater golden run
(ok, 0 violations), the bridge golden run (ok), the main package
(0 violations), scenario simulation (PASS).

**Matter:** *production-driver* — follow-on matter of K1 Q3.
DR-CMD-046's F4 decomposition refused the (b)-half
(acquisition + lifetime) not-ready, with the return condition:
"returns as a follow-on matter once the production driver is
framed." This framing is that condition.

**Claim (S1):** dsys should define the production driver — the
process side of k1-repair-spec D7 that runs the updater flow
against the real accretion repo — such that its initiation,
authority, and handle-bearing are declared and authorized (no
ambient initiation; invocation through a Harness), because K1
and Q3(a) verified the governed side and the binding contract,
and without the driver the writer is undeployable: the flow has
no production process to run in, and the (b)-half (acquisition
+ lifetime) cannot be designed (F4).

**Scope (S2):** runtime. This matter is the process side of
k1-repair-spec D7: whatever runs the flow and bears the repo
handle in production. The governed side stands unchanged — the
flow table, the committing tool (with the D3 identity check),
and the I-18/19/20 + I-25 validators are not redesigned here,
and the fixture (`World.accretion_commits`) remains the
repository contract the golden run exercises. The (b)-half's
acquisition/lifetime *mechanics* are the follow-on matter, not
this one — but this frame must say enough about initiation and
handle-bearing that the follow-on has something to design
against (the boundary is a G6 question).

**Proposer (S3):** the operator, via `/pb-decide` NBA O2.
Lineage: K1's G6 Q3 ("the production repo-handle holder")
→ DR-CMD-039 → the K1 Q3 matter (framed DR-CMD-045,
evaluated, narrowed-adopted DR-CMD-046, (a)-half specified
DR-CMD-047 and built) → F4's staging constraint → this
framing.

**Prior art (S4):**
- k1-repair-spec D7 (the K3 boundary premise): the writer is
  a flow *tool* — the commit step is in the table; "the
  production process that runs the flow and holds the repo
  handle is K3-unbuilt; the fixture models it as a World
  fact. This spec designs the governed side; the process side
  composes with K3."
- DR-CMD-040 (K3 terminally INVALID): the process side is
  *not* ambient-driven — whatever holds the handle does not
  initiate execution. The hard constraint on this matter.
- DR-CMD-043 (AX1/AX2): invocation always through a Harness;
  the Automaton driver is a strapped Harness instance.
- DR-CMD-046 (F4): the (a)/(b) decomposition — (a) built,
  (b) refused not-ready pending this framing.
- The built (a)-half (`doc/k1-q3-binding-spec.md`, BUILT
  2026-09-21): the identity binding contract — installer
  mints the repo UUID, the committing tool verifies the
  handle against the manifest before every write, fail
  closed. The driver will be the bearer of the verified
  handle.
- The updater spec + K1 build: the flow the driver runs (9
  states, 16 transitions; `committing` with D3/D4a/D5a/D6).
- The installer-spec: the installation manifest, the install
  tree, base|full profiles.
- The dialog protocol's principal binding (dyad-or-human,
  agents excluded — cited in the K1 Q3 matter's S4).

**Motivation (S5, because-Z):** the first real drive. The
checkable world-claim: no production driver exists anywhere
in the design — the updater flow can run against the fixture
(`World.accretion_commits`) or not at all; the process side
is a World fact. The Z is not vibe: the updater exists to
keep installations current (`~/dsys-inst` is a live
installation), K1+Q3(a) verified everything the governed
side can verify, and F4 showed the binding's second half
cannot even be designed until the binder exists. The
concrete scene the frame must answer: the operator invokes
a drive — *what* runs, under *whose* authority, holding
*which* handle, and what starts it? Each candidate answer
must survive K3's corpse (no ambient initiation) and AX1
(invocation through a Harness).

**G6 — open questions:**
1. **Initiation (load-bearing):** what starts the driver?
   The operator's direct invocation? A scheduler
   step-change? Something else? K3 forbids ambient
   initiation; AX1 requires Harness invocation — the frame
   must name the initiator without violating either.
2. **Authority:** under which principal does the driver run?
   (The dialog principal binding admits dyad-or-human and
   excludes agents.)
3. **Handle-bearing vs acquisition:** does the driver hold
   the handle across drives (long-lived bearer) or acquire
   per drive? Where exactly this matter ends and the
   (b)-half's acquisition/lifetime design begins.
4. **The manifest:** the installer mints the identity (D1);
   does the driver read the manifest per drive, once at
   startup, or never (leaving it to the tool)?
5. **Profiles:** which of base|full runs the driver?
6. **After fail-closed:** the D3 check aborts the drive on
   identity mismatch — what is the driver's duty after the
   abort? (Loud failure is specified for the tool; the
   driver's side is open.)

**What this matter is not:**
- Not ambient-initiated execution — K3 is terminal; the
  frame must not smuggle it back in.
- Not the (b)-half: handle acquisition/lifetime mechanics
  are the follow-on matter, unblocked by this framing.
- Not a redesign of the governed side (flow table, tools,
  validators stand).
- Not the installer-spec's minting implementation (the D5
  contract stands).

## Glossary

- **Production driver:** the process side of k1-repair-spec
  D7 — whatever runs the updater flow against the real
  accretion repo in production (this matter).
- **Process side / governed side:** D7's split — the
  governed side is the flow table and its tools (designed
  under K1); the process side is whatever runs the flow
  and bears the handle.
- **Initiation:** whatever starts the driver on a given
  drive — the matter's load-bearing question.
- **Handle-bearer:** the driver in its capacity as the
  holder of the D3-verified production handle.
- **The (b)-half:** the refused-not-ready acquisition +
  lifetime design (DR-CMD-046, F4) — returns as a
  follow-on matter once this frame exists.

## Evaluation

Falsification pipeline, run 2026-09-21 (`/pb-decide` NBA O2
selection). `sc` evaluates; it does not decide, dispose, or
write DecisionRecords.

### S5 motivation-fit

The checkable world-claim — *no production driver exists
anywhere in the design* — holds on cited evidence: D7 ("the
production process that runs the flow and holds the repo
handle is K3-unbuilt; the fixture models it as a World
fact"); the CLI's `automaton init`/`advance` and the
automaton-executor spec are both specified-not-implemented
(the executor additionally undisposed — "awaiting Peter's
approval," 2026-09-20). The Z is not vibe: the updater
exists to keep installations current (`~/dsys-inst` is a
live installation), K1+Q3(a) verified everything the
governed side can verify, and F4 showed the (b)-half cannot
be designed until the binder exists. Motivation is
well-placed — not INVALID, not misplaced.

### Falsifiers

- **F1 — "The operator's shell invocation is enough; no
  driver needs defining."** *Falsifier:* the CLI specifies
  `dsys automaton init` / `advance` — the operator can drive
  flows from the shell. Does the production driver reduce to
  "the operator runs CLI commands"? *Outcome:* **narrows.**
  Driver-as-new-entity is refused under A2 (no new entity —
  cf. the K1 Q3 F1 precedent, where holder-as-entity was
  refused and the binding survived). What survives is not a
  thing but a **contract**: initiation + authority +
  handle-bearing for production updater drives. "The
  operator runs a command" doesn't say which command, under
  whose authority, bearing which handle, or what starts it
  when the operator isn't watching — the CLI surface is a
  candidate vehicle, not a replacement for the definition.
- **F2 — "AX2 (and the executor spec) already cover it."**
  *Falsifier:* AX2 defines the Automaton driver as a
  strapped Harness instance — "the deterministic walker
  that advances automaton flows (in production and in
  testing)." The automaton-executor spec (2026-09-20)
  defines the stepping runtime ("the 'advances' in 'dsys
  issues, ingests, advances'"). Is the production driver
  already designed? *Outcome:* **narrows, sharply.** The
  stepping machinery exists (AX2 ratified; the executor
  specified). What neither covers is **initiation** — the
  executor explicitly disowns it: "Not a scheduler. It
  never decides *when* to act"; "the loop, if any, belongs
  to the wrapper (cron/script, outside the architecture)."
  And neither names the updater's production instantiation:
  whose authority, which handle. The matter is **not about
  stepping** — it's about initiation + authority +
  handle-bearing. (Noted in passing: the executor spec is
  itself undisposed — a neighboring open thread, not this
  matter's to dispose.)
- **F3 — "Initiation is someone else's problem."**
  *Falsifier:* some existing machinery must own *when* a
  production drive starts. *Outcome:* **killed.** No such
  machinery exists: the executor disowns scheduling, no
  scheduler exists in the design, the CLI doesn't schedule.
  Initiation is homeless — which is precisely why the
  matter must cover it. Sharpens: the executor's "wrapper
  (cron/script, outside the architecture)" is an explicit
  non-contract — dsys declares nothing about it. This
  matter is where that contract (or its explicit absence)
  gets defined.
- **F4 — "This is K3 revived."** *Falsifier:* K3 =
  ambient-initiated execution, terminally INVALID
  (DR-CMD-040). Does defining a production driver
  reintroduce ambient initiation through the back door?
  *Outcome:* **killed, but sharpens into the tripwire.**
  The matter as framed holds the line (DR-CMD-040 is an S4
  hard constraint; G6 Q1 demands the initiator survive K3).
  The tripwire, stated explicitly for the spec stage: **any
  initiation path the ambient can program or trigger is K3
  revived and terminally invalid** — including a
  wrapper/cron the ambient writes. This becomes a spec-stage
  negative acceptance.
- **F5 — "Subtract the (b)-half and nothing remains."**
  *Falsifier:* the (b)-half takes acquisition + lifetime;
  initiation + authority + bearing might be a paragraph,
  not a matter. *Outcome:* **narrows, survives.** What
  remains is real and homeless: the initiation contract
  (named initiator, principal, through-a-Harness per AX1),
  the bearer's duties (G6 Q4 the manifest read; G6 Q6 the
  duty after fail-closed), and the K3 tripwire. It is the
  authorization story for every production drive, and
  nothing else defines it.

### The narrowed survivor

Not a driver entity (F1, A2). Not stepping machinery (F2 —
AX2's walker, the executor's step function). The survivor is
the **production-drive contract**: *a named initiator, an
authorized principal (dyad-or-human, agents excluded),
invocation through a Harness (AX1), bearing the D3-verified
handle* — plus the K3 tripwire (no ambient-programmable
initiation) and the bearer's duties (manifest, fail-closed
aftermath).

### Conditionals (on the narrowed matter)

- **A1** — this evaluation is the falsification; no refuted
  sub-claim survives (driver-as-entity removed per F1;
  stepping ceded to AX2/the executor per F2). Holds on the
  narrowed matter.
- **A2** — no new entity: the survivor is a contract, not
  a thing. Holds (this was F1's narrowing).
- **A3** — plane discipline: no inference in execution;
  initiation must not be ambient (F4's tripwire). Holds as
  a constraint.
- **A4** — spec before build: a spec-stage gate. Noted,
  not failed.
- **A5** — the narrowed Y is checkable ("every production
  drive has a named initiator…"): acceptances to be stated
  at spec stage. Noted.
- **R1** — replay: initiation must not break deterministic
  replay; the drive's record is the transcript.
  Spec-stage.
- **R2** — golden-run coverage, including the K3-tripwire
  refusal (ambient-programmed initiation refused).
  Spec-stage.
- **R3** — an I-N validator will be needed (e.g.,
  "every drive's initiator is authorized," as a predicate).
  Spec-stage.
- **R4** — zero inference in execution. Holds.
- **R5** — trust declared (the initiator? the wrapper?).
  Spec-stage.

### Draft verdict

**Adopt-with-conditions (narrowed):** the production-drive
*contract* (initiation + authority + handle-bearing + the K3
tripwire) — not a driver entity, not stepping machinery.

Spec-stage conditions: A4 (spec before build); the
initiation contract with a named initiator and the
principal binding; R3 (I-N validator for authorized
initiation); R2 (golden-run cases incl. the
ambient-initiation refusal); R1 (replay story — initiation
must not break transcript replay); R5 (trust declared);
settle the (b)-half boundary (G6 Q3) — where this contract
ends and acquisition/lifetime design begins.
