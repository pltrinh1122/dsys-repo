# dsys installer

`install.sh` deploys the `dsys` CLI tree from a source directory.
POSIX `sh` — no root/sudo, no interactive prompts, no network calls.

## What the base profile is

`--profile base` lays down the judging surface only: `bin/dsys`, the
CLI package (`lib/dsys/`), the vendored architecture core
(`lib/core/package/`), `etc/config.yaml`, and `var/`. No role bundles,
no scenarios, no execution surface.

`referee`, `doctor`, and `state` work identically to a full install.
`roles`, `scenario`, `execute`, and `session` refuse cleanly: stderr
names the missing profile, exit 1 (usage/config failure — not exit 4,
which is agent refusal). Base is not a degraded tier (F-I6): it is the
complete, verifiable minimum, defined by what `doctor`'s hermetic
checks verify.

## Source layout (this directory)

```
install.sh                     # the installer
README.md                      # this file
bin/dsys                       # entry wrapper (expects $DSYS_HOME/venv/bin/python)
lib/dsys/*.py                  # CLI modules (state, referee, doctor, roles, manifest)
etc/config.yaml                # default config; never clobbered on reinstall
roles/{cos,operator,auditor}/  # role bundles: role.yaml, prompt.md, bounds.md
                               # sealed in place (full profile only)
share/scenarios/               # scenario drivers (full profile only)
```

`lib/core/package/` is deliberately NOT in source: it is vendored at
install time from `~/workspace/dyad-architecture/package/`
(`__init__`, `__main__`, `schema`, `validators`, `views`,
`golden_run`), overridable with `--core DIR`.

## Install

```sh
./install.sh --home /tmp/dsys-e2e --profile base
./install.sh                                       # full profile -> ~/.dsys (or $DSYS_HOME)
./install.sh --from /path/to/dist --profile full --home /srv/dsys-test
```

Flags: `--profile base|full` (default `full`), `--from DIR`
(default: `install.sh`'s own directory), `--home DIR` (default:
`${DSYS_HOME:-$HOME/.dsys}`), `--core DIR` (default:
`~/workspace/dyad-architecture/package`), `--help`.

A `~/.local/bin/dsys` symlink is created only when installing to the
default home *and* `~/.local/bin` exists; otherwise a PATH hint is
printed and the install still succeeds.

Reinstalls are idempotent: the venv is rebuilt and the tree replaced,
`etc/config.yaml` is kept if present, and `var/state` / `var/log` are
never deleted. Reinstalling with `--profile base` over a full install
downgrades cleanly (removes `lib/roles` and `share/scenarios`).

## The venv decision (honesty note)

The venv is created with `--system-site-packages`, so `pydantic` is
**inherited from the host**, not vendored. Stated plainly:

- What it buys: zero network during install, zero dependency
  duplication — *deployment* is fully offline given a local source.
  (F-I1: *acquisition* of the source may need network; deployment
  never does.)
- What it costs: the install is not hermetic against the host Python.
  If the host removes or breaks pydantic, `dsys` fails loudly at
  import time — never silently.
- The way out: a future release may vendor wheels and install with
  `--require-hashes` into an isolated venv. The installer interface
  (`--from`, `--home`, `--profile`) will not change.

## Mutation rungs → installer behavior

Declared-mutation rule: mutation is allowed; *undisclosed* mutation is
the failure mode. `dsys doctor` attests the actual bytes.

- `configure` → `etc/config.yaml` is operator-owned. Copied only when
  absent; upgrades never clobber it. Excluded from pristine checks —
  editing config must never trip the doctor.
- `role` → `lib/roles/*` are sealed bundles: `roles.py seal` writes
  content hashes into `role.yaml` at install time (full profile only).
- `wrap` → wrapper scripts live outside the tree. Doctor stays green:
  it attests the tree, not its callers.
- `patch` → any edit under the tree trips doctor to MUTATED and names
  the diverged files. Attestation covers actual bytes, not intent.
- `fork` → out of scope for the installer. Fork identity is recorded
  in `var/manifest.json` when the tree derives from a fork.

## Deliberately not implemented

- `execute` with a real LLM backend (stub path only in self-test);
- session sync — the `session` command refuses on base, and the hosted
  sync service is a separate build;
- durability beyond the local tree (checkpoints, multi-writer
  convergence live in the session-sync design, not here);
- Docker image, system-wide install, secrets handling — all explicit
  non-goals of the installer spec.
