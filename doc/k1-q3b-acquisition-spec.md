# The (b)-half: production repository-handle acquisition contract spec

**Status: ADOPTED (DR-CMD-053)** — disposed 2026-09-21.
The operator selected "Adopt the spec" (disposition,
ratify). Build follows on the operator's separate
direction; the build is not authorized by this record.

**Parent:** `doc/k1-q3b-handle-acquisition-matter.md` —
ADOPTED (narrowed, with conditions, DR-CMD-052) 2026-09-21.
The adopted-now Y: *the bearer resolves the handle via
accretion.path at initiation; absent path refuses; the
identity lives as long as the installation.*

**Scope:** the acquisition *contract* — how the drive
contract's bearer comes to hold the handle (resolution
mechanics, the failure-mode contract, the lifetime
statement), settling the drive contract's D5 ("the drive
resolves the manifest-recorded accretion-repo identity from
the installation manifest once, at initiation — process
side") by specifying *how*. Not the binding (built,
DR-CMD-047). Not the drive contract itself (built,
DR-CMD-050). Not rotation/revocation as designed operations
(refused, DR-CMD-052). Not a handle-manager entity (refused,
A2).

## The contract

- **D1 — resolution: the CLI surface reads the install
  config's `accretion.path` at initiation.** Before the
  drive starts, the CLI surface (process side — the same
  side that performs D5's one-time manifest read) resolves
  the accretion path via the config contract's precedence
  (installer-spec: flag `--accretion-path` > config
  `accretion.path` in `etc/config.yaml` > default
  `<accretion-root>/{instance}`), opens `<path>/.git` as
  the handle, and presents it to the bearer. Resolution is
  part of initiation, performed before the Harness is
  strapped and the FlowRun starts; the drive (governed
  side) never resolves — it receives the verified handle.
  This preserves the governed/process split.
- **D2 — fail fast at resolution; D3 stays the backstop.**
  The spec-stage condition (DR-CMD-052) is settled: the
  I-25 predicate — the same predicate the committing
  tool applies per write — is applied at resolution. The
  CLI surface verifies the handle's `dsys.repo-id` against
  the manifest's `accretion_repo.identity` before the
  drive starts; a mismatch refuses the drive (fail fast).
  The D3 per-write check (K1 Q3(a) spec D3, built) remains
  the enforcement point inside the drive — defense in
  depth, no new machinery (the same predicate, applied
  earlier).
- **D3 — the failure-mode contract.** (a) The path is
  absent — no path resolvable under the config contract,
  or `<path>/.git` is not a valid repo → the drive
  refuses before starting (initiation's duty, composing
  with the drive contract's I-26/D6 gates). (b) The
  manifest records no `accretion_repo.identity`
  (accretion disabled — installer-spec's "never fails the
  install" leaves this possible) → the drive refuses
  before starting. For the updater's drive specifically,
  this case cannot arise (the K2 repair: the updater
  always passes `--accretion-required` with an explicit
  `--accretion-path`), but the contract states the
  refusal as the general rule. (c) The repo's
  `dsys.repo-id` does not match the manifest identity →
  fail fast at resolution (D2); D3's per-write check
  aborts the drive if one ever starts with a mismatched
  handle (the built backstop). After any refusal: no
  retry, record, surface (the drive contract's D7).
- **D4 — the lifetime statement.** The identity's
  lifetime is the installation's lifetime. A new
  identity comes only from a fresh install (the
  installer mints, D1); reinstall resumes and preserves
  the repo and its identity (the K2 install-home
  concept). There is no in-place rotation operation and
  no revocation record — the old identity dies with the
  old installation. Rotation is reinstall; revocation is
  not a designed operation.
- **D5 — the K3 edge.** The resolver reads
  operator-owned install config (`etc/config.yaml`,
  the `--accretion-path` flag passed by the invoker).
  The updater's drive passes an explicit
  `--accretion-path` — the previous installation's
  effective path, deterministic from the install home
  (the K2 repair), not an ambient choice at drive time.
  No ambient-programmable acquisition path exists; the
  tripwire holds (DR-CMD-040; the drive contract's D4):
  any acquisition path the ambient can program or
  trigger is K3 revived and terminally invalid.

## I-27 — authorized acquisition (R3)

`i27_authorized_acquisition` is a predicate over the
drive's acquisition record (predicates, not procedures):

- the path was resolved under the config contract's
  precedence (flag > config > default), and
- `<path>/.git` is a valid git repo, and
- the manifest recorded an `accretion_repo.identity`
  (accretion not disabled), and
- the repo's `dsys.repo-id` matched the manifest
  identity (the I-25 predicate, applied at resolution), and
- resolution happened at initiation (process side),
  before drive start, and
- the resolution record did not enter the committed
  payload (R1).

Violation → the drive is refused: it does not start. A
drive found post-hoc to violate I-27 is invalid. (At
spec stage the predicate is defined; enforcement at
initiation belongs to the CLI surface — still
unimplemented, §3.7 — and the golden run checks the
predicate, R2.)

## Replay (R1)

The drive's acquisition record — the resolved path, the
resolved identity, the I-27 verdict — is recorded in
the drive transcript envelope. Replay is transcript
re-validation (the drive contract's AX2 consequence):
re-validation of the transcript reproduces the verdict.
The resolved path must not enter guard evaluation or
the committed payload (the executor spec's clock
boundary, applied to the path as to the wall clock).
So: acquisition is recorded, and the replay-identity
is unchanged — re-validation reproduces the verdict.

## Trust declared (R5)

- **The install config's integrity** (`accretion.path`):
  trusted — the config is operator-owned (the config
  contract); the resolver reads what the operator
  wrote.
- **The installation manifest's integrity**: trusted —
  the manifest-recorded identity is the binding's root
  (declared in K1 Q3(a) R5, reaffirmed in the drive
  contract's R5 and here).
- **The repo's git config** (`dsys.repo-id`): trusted
  as the binding's second side (K1 Q3(a) R5).
- **The operator as the config author**: the same trust
  class as the dialog protocol's write disposition (the
  operator's instruction is authority).

## Acceptances (R2)

- A-R2-1: the accretion path is absent → the drive
  refuses before starting (fail fast, initiation's
  duty).
- A-R2-2: the path resolves but the repo's
  `dsys.repo-id` does not match the manifest identity →
  refuse at resolution (fail fast); and D3's per-write
  check remains the backstop for a drive started with a
  mismatched handle.
- A-R2-3: the manifest records no
  `accretion_repo.identity` (accretion disabled) → the
  drive refuses before starting.
- A-R2-4: resolution success → the drive starts; replay
  by transcript re-validation reproduces the verdict,
  and the resolved path does not enter the payload.

## G6 residuals

- The CLI flow-drive surface remains specified but
  unimplemented (cli-interface-spec §3.7) — enforcement
  of I-27 at initiation belongs to it.
- The identity's lifetime across `--overwrite`
  reinstalls (the moved-aside backup) is the
  installer's domain — out of scope here.
- The golden-run harness for acquisition cases (R2)
  follows the drive-contract golden run's pattern
  (`drive_contract_golden_run.py`) at build.

## Glossary

- **Acquisition:** the drive-start mechanics by which the
  bearer comes to hold the repository handle (resolution
  of the manifest identity to a concrete repo, plus the
  failure-mode contract).
- **Resolution:** mapping `accretion_repo.identity` to a
  concrete git repo on disk — read `accretion.path`
  (config contract precedence), open `<path>/.git`,
  verify `dsys.repo-id` against the manifest identity.
- **Handle:** the resolved git repo the bearer commits
  against — the K1 Q3(a) binding's handle.
- **Bearer:** the strapped Harness instance walking the
  drive's FlowRun (the drive contract's glossary) — the
  party acquisition serves.
- **Fail fast:** refusing the drive at initiation, before
  it starts, rather than letting a doomed drive run to
  the committing tool's per-write check.
- **The backstop:** the D3 per-write identity check
  (K1 Q3(a) spec D3, built) — the enforcement point
  inside the drive; acquisition's fail-fast check is
  the same predicate applied earlier.
- **Initiation's duty:** the CLI surface's
  responsibility — refusals for absent path, disabled
  accretion, or identity mismatch belong to initiation,
  not to the drive.
- **Config contract:** flag `--accretion-path` >
  `accretion.path` in `etc/config.yaml` > default
  `<accretion-root>/{instance}` (installer-spec).
- **The K3 tripwire:** any initiation path the ambient
  can program or trigger is K3 revived and terminally
  invalid (DR-CMD-040) — reaffirmed for acquisition.
