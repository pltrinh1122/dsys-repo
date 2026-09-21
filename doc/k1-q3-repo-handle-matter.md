# K1 Q3 matter: the production repository-handle holder

**Status: ADOPTED (narrowed, DR-CMD-046)** — disposed 2026-09-21.
The (a)-half (minting + provenance + identity-check contract) is
adopted with spec-stage conditions; the (b)-half (acquisition +
lifetime) was refused (not-ready) and returns as a follow-on once
the production driver is framed. Draft verdict history: framed
under DR-CMD-045, evaluated the same turn (adopt-with-conditions).

**Spec:** `doc/k1-q3-binding-spec.md` (DRAFT, 2026-09-21) — the
(a)-half specified: installer mints a repo UUID at install time
(`dsys.repo-id` in the repo's git config + `accretion_repo.
identity` in the manifest), the committing tool verifies the
handle's identity against the manifest before every write
(D5a extension, fail closed, abort-not-retry), I-25
identity-binding validator, replay story, five checkable
acceptances. **Adopted under DR-CMD-047 (2026-09-21); BUILT the
same day on the operator's "Yes, build it"** — the committing
tool's pre-write identity check (D3), I-25, golden-run cases
24–28; updater + bridge + main + scenario-sim golden runs all
PASS. See the spec's "Build evidence".


**Matter:** *k1-q3-repo-handle* — follow-on matter of K1
(DR-CMD-039), G6 Q3 of `doc/k1-repair-spec.md`. Framed 2026-09-21
under DR-CMD-045 (NBA O2).

**Claim (S1):** dsys should define the production
repository-handle holder for the updater's accretion writer such
that the committing tool's repository handle is a declared,
authorized binding — with a named minter, recorded provenance,
and a bounded lifetime — because K1 verified the committing logic
against a fixture, and without a bound handle the writer is
undeployable: the accretion repo is the system's memory of its own
updates, and an unbound handle is either unwritable (D5a fails open
in practice) or writable by the wrong principal (confused deputy).

**Scope (S2):** runtime. Q3 is the process side of k1-repair-spec
D7: the production process that runs the flow and holds the repo
handle. The governed side stands unchanged — the flow table, the
committing tool, and the I-18/19/20 validators are not redesigned
here, and the fixture (`World.accretion_commits`) remains the
repository contract the golden run exercises. Installer touch is
cited, not designed: the handle's provenance may need the
installation manifest to record the accretion repo's identity
(installer-spec's problem; no `install.sh` change in this matter).

**Proposer (S3):** the operator. Q3 is K1's own G6, carried through
DR-CMD-039 ("the production repository-handle holder"); Q1
(canonical serialization) was pinned by the K1 build, Q2 resolved
by D4a, Q3 alone remains open.

**Prior art (S4):** K1's fixture (`World.accretion_commits` — the
repository contract the golden run pins, not production Git
integration); D5a (git hard dependency, fail-closed); D6
(append-only); k1-repair-spec D7 (the K3 boundary premise —
governed side designed, process side open); DR-CMD-040 (K3
INVALID — the process side is *not* ambient-driven; whatever holds
the handle does not initiate execution); DR-CMD-043 (AX1/AX2 —
invocation always through a Harness; the Automaton driver is a
strapped Harness instance); the installer-spec (installation
manifest as provenance); the dialog protocol's principal binding
(dyad-or-human, agents excluded — a handle must not be issuable to
an agent principal).

**Motivation (S5, because-Z):** the first production drive of the
updater with K1's writer. The flow reaches `committing`. The tool
needs a repo handle. Where does it come from?
- "The tool opens the path in config" — a misconfigured or
  influenced path writes the system's update memory to the wrong
  repo, or to a non-repo. D5a says absent git fails closed — but
  fail-closed against *what* check? The check needs a definition
  of the right repo, which is exactly the missing binding.
- "The fixture" — K1 never leaves the lab; the verified writer is
  undeployable.
- "The ambient hands it one" — K3's F1, killed then invalidated
  (DR-CMD-040): ambient-initiated execution is out, and a handle
  is a capability — capabilities need a minter with authority,
  not a helpful ambient.
The Z: the K1 build proved the committing *logic*; the *binding*
is the undeployed remainder. Per the standing rule the artifacts
need operator disposition before deployment — and disposition
cannot be given to an unbound writer. (Anti-vibe bar: this is a
concrete first-production-drive scenario, not "production
integration would be nice.")

## G6 — the matter's open questions (for evaluation)

- **Who mints the handle?** Candidates: the installer at install
  time (recorded in the manifest); the driver per drive (from the
  manifest); the operator as a step-change. Each has a different
  authority story; the matter must pick one or decompose.
- **What binds the handle to *the installation's* accretion repo?**
  Identity, not just writability — the confused-deputy question.
  A handle to any writable git repo is not the answer.
- **Lifetime and revocation:** per-drive acquisition vs a
  long-held handle; what revokes a compromised handle, and what
  the flow does while it is revoked.
- **How do D5a and D6 transfer?** "Absent git → fail closed" and
  "append-only" were proved against the fixture. What does
  "absent git" mean when the handle is a binding rather than a
  path? What enforces append-only against the real handle?
- **Composition with K3's survivors:** AX1 constrains the process
  side — the handle holder operates under a Harness strap. The
  scenario-simulation pipeline (ambient-authored, operator-gated)
  hardens cases — do hardened scenario specs or their
  transcripts touch the same accretion repo? (I-22 separates
  simulation transcripts from production records — but the
  question is worth posing, not assuming.)
- **Installer boundary:** does the installer need to change (P4),
  or is manifest-recorded provenance sufficient? Cite, don't
  redesign.

## What this matter is not

- Not a redesign of the writer — K1's governed side stands
  (DR-CMD-039).
- Not a revival of K3's ambient-driven execution — DR-CMD-040 is
  terminal; the process side holds a handle, it does not initiate
  runs.
- Not the manifest format — the installer-spec's problem, cited
  here.

## Evaluation

### S5 motivation-fit (DR-CMD-042 lens)

- **Misplaced Z?** No. The Z makes a checkable world-claim — "no
  production repository handle exists anywhere in the design; K1's
  writer is undeployable without one" — true on cited evidence
  (DR-CMD-039; k1-repair-spec D7: "the fixture models it as a World
  fact"). The gap is real, not solution-first with a post-hoc Z.
  Not INVALID.
- **Fit failure?** No. The claim's Y (named minter, recorded
  provenance, bounded lifetime) directly serves the Z
  (deployability of the writer). The design does not defeat its
  own Z.
- **Verdict on S5:** holds.

### Falsifiers

- **F1 — "No holder needed."** *Falsifier:* the fixture's contract
  just gets a production implementation — the installer records
  the repo path in the manifest (minter + provenance), the driver
  opens it per drive (lifetime). No new entity, no new concept;
  Q3 dissolves into two small bindings on existing machinery.
  *Outcome:* **narrows, does not kill.** "Holder" as a new
  entity/process is refused (A2 — cf. the dialog protocol's
  GoalClassification rejection: no new entity). The survivor is
  the *binding*, not a holder: the matter's real content is the
  minting binding and the acquisition binding. S1's noun is
  over-claimed; its "such that" stands.
- **F2 — "D5a already covers it."** *Falsifier:* absent git →
  fail closed; the tool checks `git rev-parse`, done — the S5
  scenario's "fail-closed against what?" is answered.
  *Outcome:* **narrows.** D5a covers liveness ("is it a git
  repo"), not identity ("is it *this installation's* accretion
  repo"). The liveness half is ceded to D5a; the matter's core
  is the **identity binding** — D5a's check gains an identity
  conjunct (handle resolves to the manifest-recorded identity,
  else fail closed).
- **F3 — "Confused deputy is hypothetical."** *Falsifier:* no
  threat model, no attacker — the deputy framing is melodrama.
  *Outcome:* **killed, but sharpens.** The S5 failure mode is
  misconfiguration, not adversary; the identity binding is
  justified by fail-closed design, not threat modeling. The
  matter frames identity around misconfiguration.
- **F4 — "Premature: the acquisition half needs the production
  driver."** *Falsifier:* per-drive acquisition and lifetime need
  the production driver — K3-unbuilt, K3 invalid; AX1/AX2
  constrain it but do not design it. Designing a binding for a
  nonexistent binder is not-ready.
  *Outcome:* **survives as a staging constraint — decomposes the
  matter.** (a) Minting + provenance + the identity check as a
  contract: designable now, the installer already owns the
  manifest. (b) Acquisition + lifetime: **refused (not-ready)**,
  returns as a follow-on matter once the production driver is
  framed.

### Conditionals (on the narrowed matter)

- **A1** — this evaluation is the falsification; no refuted
  sub-claim survives (holder-as-entity removed, liveness ceded
  to D5a). Holds.
- **A2** — no new entity (F1). Holds.
- **A3** — plane discipline: no inference in execution; minter
  and acquirer are existing machinery. Holds.
- **A4** — spec before build: a KEEP gate; the spec stage must
  produce it. Noted, not failed.
- **A5** — the narrowed Y is checkable: the manifest carries the
  identity field; the tool verifies the handle against it;
  mismatch fails closed. Acceptances to be stated at spec stage.
- **R1** — replay preserved: if the identity (or the check
  result) enters the committed payload, K1's payload-canonicity
  replay identity must still hold. Spec-stage constraint, not a
  failure.
- **R2** — golden-run extension incl. refusal cases: spec-stage.
- **R3** — the identity binding will need an I-N validator
  (predicates, not procedures). Spec-stage.
- **R4** — zero inference in execution. Holds — nothing here
  infers.
- **R5** — trust declared: the installer as minter is trusted;
  manifest integrity is trusted. Held at framing; must be
  explicit in the spec.

### Draft verdict

**Adopt-with-conditions (narrowed):**

1. **Adopted now:** the production repository-handle *binding*
   (not a holder entity) — (a) minting + provenance via the
   installation manifest, and the identity check as a contract
   the committing tool enforces (extends D5a's fail-closed).
   The adopted-now Y: *named minter, recorded provenance,
   identity verified before write.*
2. **Refused (not-ready):** the acquisition/lifetime half (b) —
   returns as a follow-on matter once the production driver is
   framed (F4).
3. **Spec-stage conditions:** A4 (spec before build); R3 (I-N
   validator for the identity binding); R2 (golden-run cases
   incl. the wrong-identity refusal); R1 (replay-identity
   constraint if identity enters the payload); settle the
   manifest field's design home — specified here as a contract
   the installer implements, or designed in the installer-spec.


## Glossary

- **Repository handle (repo handle):** the production capability
  the committing tool uses to write to the accretion repo — the
  real counterpart of K1's `World.accretion_commits` fixture.
- **Minter:** the party that creates and issues the handle
  (installer, driver, or operator — the matter's first question).
- **Binding:** the declared association between the handle, the
  installation it serves, and the authority that issued it.
- **Governed side / process side:** k1-repair-spec D7's split —
  the governed side is the flow table and its tools (designed
  under K1); the process side is whatever runs the flow and
  holds the handle in production (this matter).
- **Fixture:** `World.accretion_commits` — the repository
  contract K1's golden run exercises; stands in for production
  Git integration, which does not exist yet.
- **Confused deputy:** the failure mode in which the writer,
  holding a valid-but-wrong handle, writes the system's update
  memory to a repo that is not the installation's accretion repo.
- **Accretion repo:** the git repo holding the installation's
  accretion records — the system's memory of its own updates
  (K1 D6: append-only).
