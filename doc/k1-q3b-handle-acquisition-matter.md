# The (b)-half: production repository-handle acquisition and lifetime

**Status: ADOPTED (narrowed, with conditions, DR-CMD-052)** —
disposed 2026-09-21. Framed 2026-09-21 (NBA O3, DR-CMD-051);
evaluated the same turn (NBA O1 selection; draft verdict:
adopt-with-conditions, narrowed); the operator selected
"Adopt with conditions (narrowed)." The K1 Q3 line is now
fully disposed: the (a)-half adopted/spec'd/built, the
production driver framed/adopted/spec'd/spec-adopted/built,
the (b)-half adopted narrowed here. **Spec drafted** 2026-09-21 (NBA O1)
and **ADOPTED whole, no conditions** the same turn
(DR-CMD-053). **Built** 2026-09-21 (NBA O1): `AcquisitionRecord`,
`AcquisitionRefused`, `i27_authorized_acquisition`, `acquire_handle`
in `core/package/updater.py`; `production_drive` re-checks a
provided record at initiation; `core/package/acquisition_golden_run.py`
(8 refusals, 0 violations); all existing golden runs still green.
Uncommitted.

**Draft verdict: adopt-with-conditions (narrowed)** — narrowed
harder than framed. S5 holds (the Z is a checkable world-claim,
true on cited evidence; not misplaced). Falsifiers: **F1**
("the installer's path config is enough") narrows — resolution
is reading `accretion.path` at initiation; the survivor is the
failure-mode contract (absent path → whose refusal; wrong
identity at the path → fail fast vs fail at write). **F2**
("rotation is YAGNI") kills the rotation/revocation half as
designed operations — no trigger in the adopted threat model
(F3 killed the adversary framing for the (a)-half), and it is
in tension with the binding spec's D5 ("minted once at
install, immutable thereafter"); the survivor is the lifetime
statement (identity lifetime = installation lifetime; new
identities come only from fresh installs, installer mints,
D1). **F3** ("implementation, not design") narrows sharply —
the surviving design core is the failure-mode contract + the
lifetime statement. **F4** ("a new K3 surface") killed — the
resolver reads operator-owned config; the tripwire holds,
reaffirmed as a constraint. **F5** ("G1 fails — not a matter")
narrowed, survives — the failure-mode contract and the
lifetime statement are decisions with alternatives that alter
the drive's guarantee. Conditionals holding on the narrowed
matter: A1 (rotation/revocation removed), A2 (contract, not a
thing), A3 (mechanical resolution), A5 (checkable), R4, R5
(trust in the install config + manifest); A4/R1/R2/R3 are
spec-stage gates. Spec-stage conditions: A4; settle fail-fast
(identity check at resolution — recommended: fail fast AND
keep D3 as the backstop, same I-25 predicate applied earlier)
vs fail-at-write; R3 (I-N validator for acquisition);
R2 (golden runs: absent-path refusal, wrong-identity-at-
resolution); R1 (resolution must not enter the payload);
R5 (trust declared). Evaluation only — no disposition, no
DecisionRecord.

**Lineage:** K1's G6 Q3 ("the production repo-handle holder")
→ DR-CMD-039 → the K1 Q3 matter (framed DR-CMD-045; the
(a)-half adopted DR-CMD-046, spec'd and adopted DR-CMD-047,
built and committed 2026-09-21) → DR-CMD-046 F4's staging
constraint ("acquisition needs the unframed production
driver") → the (b)-half refused not-ready, "returns as a
follow-on matter once the production driver is framed" →
the production driver framed (DR-CMD-048), adopted
(DR-CMD-049), spec'd and spec-adopted (DR-CMD-050), built
and committed (`8b61695`, 2026-09-21). The return condition
is satisfied; the (b)-half returns now.

**Matter:** *k1-q3b-handle-acquisition* — "dsys should define
how the production drive's bearer acquires the repository
handle at drive start (resolution mechanics) and how handles
rotate and revoke, such that the drive contract's bearer
comes to hold a D3-verifiable handle within the
drive-bounded lifetime, because the adopted drive contract
names the bearer and bounds the handle's lifetime to the
drive but does not say how the bearer comes to hold the
handle — and without acquisition the drive cannot run
against the real accretion repo."

## S1 — what acquires the handle

The process side of the drive contract's bearer: at drive
start, the manifest-recorded `accretion_repo.identity` must
be resolved to a concrete git repo on disk (the handle) and
presented to the bearer — the strapped Harness instance
walking the drive's FlowRun. The K1 Q3(a) build verified the
binding (the handle must match the manifest — I-25); the
drive-contract build verified the drive (initiation,
bearing, the fail-closed aftermath — I-26, D7). What is
missing is the acquisition: which repo, found how, by whom —
and what happens when the identity must change (rotation)
or die (revocation).

## S4 — sources

- DR-CMD-046 (F4): the (b)-half refused not-ready; "returns
  as a follow-on matter once the production driver is
  framed."
- The adopted drive-contract spec (DR-CMD-050): the settled
  boundary — "the contract names the bearer and bounds the
  handle's lifetime to the drive (step-function model — no
  long-lived bearer); acquisition mechanics + rotation are
  the (b)-half's."
- The K1 Q3(a) binding spec (DR-CMD-047): D1 (the installer
  mints, writes `dsys.repo-id` to the repo's git config and
  `accretion_repo.identity` to the manifest), D2 (identity
  is a UUID, not a path — path is liveness), D3 (the
  per-write check), D4 ("Rotation is not defined" —
  explicitly the (b)-half's).
- The installer-spec: `accretion.path` in `etc/config.yaml`
  or the `--accretion-path` flag (the path side — liveness,
  per D2).
- The drive contract's D5: the manifest is read once at
  initiation (process side).
- The K3 tripwire (DR-CMD-040; drive-contract D4):
  acquisition mechanics must not become an
  ambient-programmable initiation path.

## S5 — motivation-fit

The Z is a checkable world-claim: "no acquisition design
exists anywhere in the design" — true on cited evidence
(DR-CMD-046 refused it not-ready; the drive-contract
spec's G6 residuals name acquisition mechanics + rotation
as the (b)-half's; the binding spec's D4 says "Rotation is
not defined"). Not misplaced, not fit-failing. Not INVALID.

## G6 — load-bearing questions

- **Q1 (resolution):** how does the drive resolve the
  manifest identity to a concrete repo? Via
  `accretion.path` (the installer's config/flag)? What if
  the path is absent, or points at a repo whose
  `dsys.repo-id` does not match? (Composes with D3's
  fail-closed.)
- **Q2 (who resolves):** the CLI surface at initiation, the
  Harness strap, or the drive's first step? Bears on the
  governed/process split — D5's one-time manifest read is
  process-side; is resolution part of that read or a
  separate act?
- **Q3 (rotation):** what triggers rotation — compromise,
  reinstall, the installer's doing? Who mints the new
  identity (the installer again, per D1's rationale)? Does
  rotation rewrite the manifest — and is the manifest
  mutable post-install?
- **Q4 (revocation):** what happens to the old handle? Is
  there a revocation record, or does rotation simply orphan
  the old UUID?
- **Q5 (absence):** the repo is absent at drive start — fail
  closed presumably, but whose duty is the refusal:
  acquisition's, or the drive's D7?
- **Q6 (the K3 edge):** could acquisition mechanics — a
  resolver the ambient can influence — become an
  ambient-programmable initiation path? The tripwire
  applies to acquisition too.

## What it's not

- Not the binding (built, DR-CMD-047). Not the drive
  contract (built, DR-CMD-050).
- Not a handle-manager entity — A2's no-new-entity
  discipline from the (a)-half carries: the survivor
  should be a contract (resolution + rotation as declared
  mechanics), not a thing.
- Not a scheduler, not a daemon — the step-function model
  stands (no long-lived bearer).

## Glossary

- **Acquisition:** the drive-start mechanics by which the
  bearer comes to hold the repository handle (resolution
  of the manifest identity to a concrete repo).
- **Resolution:** mapping `accretion_repo.identity` to a
  concrete git repo on disk.
- **Rotation:** replacing the repo identity with a newly
  minted one (both sides, per D1's write-both-places).
- **Revocation:** retiring an identity so it can no longer
  verify.
- **Bearer:** the strapped Harness instance walking the
  drive's FlowRun (the drive contract's glossary) — the
  party acquisition serves.
