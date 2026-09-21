# K1 Q3(a) spec: the repository-handle identity binding

**Status: ADOPTED (DR-CMD-047)** — disposed 2026-09-21.
Not built: the build follows on the operator's separate direction.

**Matter:** *k1-q3-repo-handle*, (a)-half only: minting +
provenance + the identity check as a contract. The (b)-half
(acquisition + lifetime) was refused (not-ready) and returns as a
follow-on once the production driver is framed — it is not
designed here.

**Claim restated (S1 narrowed):** dsys should bind the updater's
accretion writer to the installation's accretion repo such that
minting happens at install time with the identity recorded in the
installation manifest, and the committing tool verifies the
handle's identity against the manifest before every write, failing
closed on mismatch — because K1 proved the committing logic and
the binding is the undeployed remainder; an unverified handle
writes the system's update memory to the wrong repo on
misconfiguration.

**Scope:** runtime. The installer implements the manifest field
per the contract specified here — design home settled: the
contract lives here, the implementation lives in the
installer-spec (cited, not redesigned). No new CLI surface, no
network touch, no inference in execution. The flow table, the
committing tool's write path, and I-18/19/20 are unchanged; this
spec adds a pre-write check and its validator.

**Prior art:** DR-CMD-046 (narrowed adoption; the evaluation's
F1–F4); k1-repair-spec D5a (git hard dependency, fail-closed),
D4a (abort, not retry), D6 (append-only); the installer-spec
(installation manifest); K1's `World.accretion_commits` fixture
(the repository contract the golden run exercises).

## Decisions

- **D1 — the installer mints.** At install time, the installer
  generates a repo UUID (UUIDv4), writes it to the accretion
  repo's git config as `dsys.repo-id`, and records the same
  value in the installation manifest as
  `accretion_repo.identity`. The installer is the adopted Y's
  named minter. Rationale: minting must happen exactly once, at
  the moment the repo comes into existence under the
  installation's authority — the installer is the only party
  present at that moment.
- **D2 — identity is a UUID, not a path.** The manifest records
  the UUID; the path is liveness (D5a), not identity. *Alternative
  considered and rejected:* path-only check — a path can be
  rebound (symlink, remount, a re-created repo at the same path
  after deletion); it answers "is it a git repo at this path,"
  not "is it *this installation's* repo," failing F2's identity
  requirement. A UUID stored in the repo's own config cannot be
  rebound without rewriting the repo.
- **D3 — the check extends D5a.** Before every write, the
  committing tool verifies, in order: (1) the handle resolves to
  a git repo (existing D5a — absent git → fail closed); (2)
  `git config dsys.repo-id` in that repo equals the manifest's
  `accretion_repo.identity`. Mismatch — including a missing key
  on either side — fails closed: abort, not retry (D4a), no
  commit, `run_aborted → failed`. The check runs before payload
  construction, so the committed payload is byte-identical to
  K1's (R1).
- **D4 — trust declared (R5).** The installer as minter is
  trusted; manifest integrity is trusted — a compromised
  manifest compromises identity, declared not solved here. The
  UUID is identity, not a secret: stored in plaintext in both
  places. Rotation is not defined.
- **D5 — manifest field design home settled.** The contract —
  field `accretion_repo.identity`, UUIDv4 format, semantics
  (minted once at install, immutable thereafter) — is specified
  here; the installer-spec implements the manifest write. No
  `install.sh` change is designed in this spec.

## Validators (R3)

- **I-25 — identity-binding:** the committing tool writes only
  to a handle whose repo identity (`dsys.repo-id`) equals the
  manifest-recorded `accretion_repo.identity`. A predicate over
  (manifest, handle), not a procedure. Violations: identity
  missing on either side; mismatch; handle not a git repo (the
  D5a conjunct).

## Replay story (R1)

The identity check precedes payload construction and leaves the
payload untouched: K1's payload-canonicity replay identity holds
unchanged, and existing transcripts validate unmodified. The
identity itself never enters the committed payload.

## Trust declarations (R5)

- The installer as minter is **trusted**; manifest integrity is
  **trusted** (compromise declared, not solved).
- The UUID is **identity, not a secret** — no confidentiality is
  assumed or provided.

## Acceptances (checkable sequences)

1. Matching identity → the K1 committing path proceeds
   unchanged (existing K1 golden-run cases).
2. Wrong identity (`dsys.repo-id` ≠ manifest) → fail closed:
   abort, no commit, `run_aborted → failed`.
3. Missing `dsys.repo-id` in the repo config → fail closed, as
   in (2).
4. Not-a-repo handle → fail closed (existing D5a case,
   unchanged).
5. Full chain: updater + bridge + main golden runs PASS, 0
   violations.

## G6 — residuals

- The (b)-half (acquisition + lifetime): refused not-ready;
  returns as a follow-on once the production driver is framed.
- UUID rotation: not defined — identity, not secret.
  Re-install mints anew (installer concern, cited).
- Multi-installation hosts: each installation mints its own
  identity; no cross-installation binding is designed here.

## Glossary

- **Identity binding:** the verified association between the
  committing tool's handle and the installation's accretion
  repo, via the repo UUID.
- **Repo UUID (`dsys.repo-id`):** a UUIDv4 minted once at
  install time, stored in the accretion repo's git config and
  in the installation manifest as `accretion_repo.identity`;
  the repo's identity.
- **Minter:** the installer — the party that generates the UUID
  and records it in both places.
- **Fail closed (D5a extension):** on absent-git or identity
  mismatch, the drive aborts (not retries) with no commit.
- **Accretion repo:** the git repo holding the installation's
  accretion records — the system's memory of its own updates
  (K1 D6: append-only).
