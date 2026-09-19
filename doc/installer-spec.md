# `dsys` installer — self-contained deployment design

Supersedes §6 of `agent-cli-packaging-spec.md` (the `install.sh` sketch).
Keeps that spec's §7 trust boundaries. Assumes the `dsys` command name
(ratified 2026-09-19; supersedes `dyad` and `dyad-agent`).

## 1. What "self-contained" means (falsifiable)

An installed tree is self-contained iff:

1. **It owns its runtime.** All Python dependencies live in a venv inside
   the tree, installed from a pinned lockfile. Nothing is added to the
   system Python, no `sudo`, no system packages.
2. **It is installable offline.** `install.sh --from <local dist>` performs
   zero network calls. Network is needed only to *acquire* the
   distribution, never to *deploy* it.
3. **It is verifiable.** A manifest records content hashes of every shipped
   artifact (CLI, architecture package, role bundles, scenarios).
   `dsys doctor` re-verifies the tree against the manifest.
4. **It is per-command hermetic where honesty allows.** `referee`,
   `scenario` (with stub backend), `state`, `roles`, `doctor` never touch
   the network. `execute` with a real LLM backend inherently does — the
   boundary is drawn per command (§4), not claimed per install.

What self-contained does *not* mean: relocatable (venvs embed absolute
paths — F-I3), fully offline at runtime for every command (F-I2), or a
container image (out of scope — §8).

## 2. Layout

Fixed home-relative root. Default `~/.dsys`, overridable with
`DSYS_HOME` (recorded in the manifest; a moved tree is detected, §7).

```
~/.dsys/
  bin/dsys                      # entry point (venv console script)
  venv/                         # hermetic Python env, pinned deps
  lib/
    dsys/                       # the CLI package
    core/                       # vendored architecture package/
                                # (schema, validators, views, golden_run)
    roles/                      # role bundles: <role>.md + <role>.json,
                                # versioned, content-hashed
  share/
    scenarios/                  # shipped scenario drivers
    fixtures/                   # golden-state fixture for self-test
  etc/
    config.yaml                 # backend, timeouts; flags > config > defaults
  var/
    state/                      # state snapshots (CLI-owned format)
    log/                        # run transcripts
    cache/                      # previous distributions (rollback)
    manifest.json               # installed versions + content hashes
```

`~/.local/bin/dsys` symlinks to `~/.dsys/bin/dsys` (created if
`~/.local/bin` exists or can be created; otherwise the installer prints a
PATH hint and exits 0 — a missing symlink is not a failed install).

## 3. Distribution

One artifact per release: `dsys-<version>.tar.gz` containing `bin/`,
`lib/`, `share/`, plus `INSTALLER_VERSION` and a `dist-manifest.json`
(hashes of everything in the tarball). The installer verifies the
tarball against `dist-manifest.json` before touching `~/.dsys`.

Sources, in order of preference:

1. `--from <path>` — local tarball. Fully offline.
2. `--from <url>` — fetched once with `curl`, hash-verified, then treated
   as (1). The only network the installer itself ever performs.
3. No source given — refuses with usage. The installer never guesses a
   URL; acquisition is the operator's explicit act.

## 4. Hermeticity boundary (per command)

| Command | Network | Notes |
|---|---|---|
| `referee` | never | pure function over state files |
| `scenario` | never with `--backend stub` | real backends are the scenario author's choice |
| `state`, `roles`, `doctor` | never | local tree only |
| `execute --backend stub` | never | installer self-test path |
| `execute` (real backend) | yes | inherent; backend auth is the backend's business |
| `session` | yes | sync service only; the one network surface besides backends |

`dsys doctor` reports the boundary explicitly: `hermetic: ok` covers the
tree; backend probes are advisory and labeled as such (F-I4).

## 5. Install procedure

`./install.sh [--from <path|url>] [--home <dir>] [--dev] [--uninstall] [--purge]`

1. **Preflight.** `python3 >= 3.10`; `curl` only if `--from` is a URL;
   writable home; ~200MB free. Warn (don't fail) if no agent backend is
   on PATH — `stub` keeps install green.
2. **Acquire + verify.** Resolve the dist, verify `dist-manifest.json`
   hashes. Any mismatch aborts before mutation.
3. **Venv.** `python3 -m venv ~/.dsys/venv`; `pip install` from the
   shipped lockfile with hash checking (`--require-hashes`). No network
   here when installing from a local dist (wheels vendored in the
   tarball) — this is what makes `--from <path>` truly offline.
4. **Lay down the tree.** `lib/`, `share/`, `etc/config.yaml` (only if
   absent — never clobber operator config on upgrade).
5. **Manifest.** Write `var/manifest.json`: installer version, dist
   version, install path, timestamp, and content hashes of CLI, core
   package, each role bundle, each scenario.
6. **Symlink.** `~/.local/bin/dsys` → `~/.dsys/bin/dsys`, idempotent.
7. **Self-test** (any failure aborts, naming the step):
   - `dsys --version` prints CLI + core + role hashes matching the manifest;
   - `dsys doctor` — hermetic checks green;
   - `dsys referee validate` on the shipped golden-state fixture — 0 violations;
   - `dsys execute --as auditor --backend stub --prompt "ping"` — exit 0.
8. **Cache.** Copy the dist tarball to `var/cache/` (bounded: keep last
   two) for offline rollback.

**Idempotent.** Re-running upgrades in place: venv rebuilt, tree
replaced, `etc/config.yaml` and `var/state` untouched, symlink
verified-not-duplicated.

**Uninstall.** `--uninstall` removes the tree and the symlink; `var/state`
is *kept* (it is operator data) unless `--purge` is also given. The
installer never deletes state silently (F-I5).

## 6. `var/manifest.json` (sketch)

```json
{
  "installer_version": "1.0.0",
  "dist_version": "0.3.0",
  "install_path": "/home/operator/.dsys",
  "installed_at": "2026-09-19T...",
  "artifacts": {
    "cli":      {"version": "0.3.0", "sha256": "..."},
    "core":     {"version": "0.3.0", "sha256": "..."},
    "roles/cos":      {"version": "1.2.0", "sha256": "..."},
    "roles/operator": {"version": "1.2.0", "sha256": "..."},
    "roles/auditor":  {"version": "1.2.0", "sha256": "..."}
  }
}
```

One version string covers CLI + core + role hashes in
`dsys --version` output (per the packaging spec); the manifest is the
machine-readable form. Fleet use: `dsys doctor` on any member machine
attests whether its tree matches a pinned release — identical
environments across the fleet, verified rather than assumed.

## 7. Moved-tree detection

The manifest records `install_path`. On startup, `dsys` compares it to
its actual location; on mismatch it refuses with a named error
("tree moved; reinstall — venvs are not relocatable") rather than
failing mysteriously on broken venv paths.

## 8. Non-goals (explicit)

- **No Docker image in v1.** The tree is the unit of deployment; it is
  image-bakeable as-is (copy `~/.dsys`, set PATH). No Dockerfile
  machinery until a real need appears.
- **No system-wide install.** No `/opt`, no root. A fleet that needs
  system-wide deployment bakes the tree into its image.
- **No secrets handling.** Unchanged from the packaging spec §7: backend
  auth is the backend's business; the installer never sees credentials.

## 9. Post-installation mutation & fork policy

Ratified 2026-09-19 (decision-making playbook): post-installation, the
user has **maximum flexibility to mutate even dsys's own files** —
via fork/clone of the dsys-repo (the software's own repo; distinct
from the accretion-repo). Immutability of the core was killed by
falsification: unenforceable on the user's own filesystem. The
available mechanism is not prevention but **detection + declaration**:

- **Declared-mutation rule.** Mutation is allowed; *undisclosed*
  mutation is the failure mode. `dsys doctor` distinguishes pristine
  from mutated and reports *what* diverged (rather than a bare hash
  FAIL); `var/manifest.json` records fork identity (repo/commit) when
  the tree derives from a fork. Attestation always covers the actual
  bytes.
- **Procedure.** Whether and how to mutate is decided through the
  **dsys-mutation-playbook** (spec:
  `dsys-mutation-playbook-spec.md`) — the second playbook, same
  pattern as the decision-making playbook: DoD conditionals,
  START/STOP/KEEP, gates G1–G4 + M1–M4 (ladder / trust-boundary
  declaration / upgrade fate / audience), shared DecisionRecord
  entity (`playbook="dsys-mutation-playbook"`), single disposition
  machinery. The rung ladder, least → most invasive: `configure` |
  `role` | `scenario` | `wrap` | `patch` | `fork`.
- **Trust boundary** (for dsys): `lib/core` validators, the referee,
  sync convergence, hash-chaining, manifest/doctor. Mutating these
  voids the architecture's guarantees *for your tree* — allowed, but
  declared (`voided_guarantees`, I-17).

G5: binding on the declared-mutation mechanics (doctor/manifest
behavior — checkable); the rung-selection criteria advisory
(judgment, not validators). G6: fork workflow undesigned
(`install --from` on a fork; manifest fork-identity fields);
upgrade-vs-mutated-tree behavior unspecified.

## 10. Base profile

Follows from the 2026-09-19 falsification ("a dsys instance contains at
minimum a CoS node" — falsified): no role, no backend, no scenario is a
universal minimum. The minimum is exactly what `doctor`'s hermetic
checks verify. One release tarball serves both profiles; the installer
selects with `--profile base|full` (default `full`).

### 10.1 Minimum tree

```
~/.dsys/
  bin/dsys
  venv/
  lib/dsys/                  # the CLI package
  lib/core/                  # architecture package:
                             # schema, validators, views, golden_run
  etc/config.yaml
  var/manifest.json          # profile: "base"
```

`var/state` and `var/log` are created on first use. No `lib/roles`, no
`share/scenarios`. The full profile adds exactly those two directories.

### 10.2 Command availability

| Command | base | full |
|---|---|---|
| `referee` | yes | yes |
| `doctor` | yes (hermetic subset) | yes |
| `state` | yes | yes |
| `roles`, `scenario`, `execute` | clean refusal | yes |
| `session` | clean refusal | yes (the sync surface; needs network) |

The refusal is mechanical, not a crash: stderr names the missing
profile ("`execute` is not installed in the base profile —
reinstall with `--profile full`"), exit 1 per the CLI exit-code
contract (usage/config/tool failure — not exit 4, which is agent
refusal). `referee` on a base tree is the identical pure function
as on a full tree; the profile removes surface, not correctness.

### 10.3 Self-test (base)

- `dsys --version` — hashes match the manifest;
- `dsys doctor` — hermetic checks green;
- `dsys state init --seed golden --out $TMP/g.json &&
  dsys referee validate --state $TMP/g.json` — 0 violations.

No fixture files ship: the golden state is *generated* by `state init`,
then judged by `referee` — which is itself the point (the tool that
judges is exercised, not a canned file).

### 10.4 Installer behavior

- `--profile base` lays down §10.1 only; `--profile full` adds
  `lib/roles` + `share/scenarios`.
- The manifest records `profile`; `doctor` verifies presence *and*
  absence per profile (a full tree missing roles = violation; a
  base tree missing roles = correct).
- Upgrade base → full: reinstall with `--profile full`. Idempotent;
  `etc/config.yaml` and `var/state` untouched.
- Moved-tree detection (§7) applies identically to both profiles.

## 11. Falsifiers (pre-registered)

- **F-I1.** "The install is fully offline." False as a blanket claim.
  Precise claim: *deployment* is offline given a local dist (`--from
  <path>` performs zero network calls); *acquisition* may need network.
  If any doc implies otherwise, kill the claim, not the design.
- **F-I2.** "Self-contained means no external calls at runtime." False
  per install, true per command (§4). `execute` with a real backend
  inherently reaches the network; everything else is hermetic.
- **F-I3.** "The venv is relocatable." False — venvs embed absolute
  paths. Moving `~/.dsys` breaks it; the installer detects the move (§7)
  and says so instead of failing obscurely.
- **F-I4.** "`doctor` green means the backend works." False — backend
  probes are advisory. Green means the hermetic parts are intact and
  hashes match; nothing more.
- **F-I5.** "Reinstall/upgrade is always safe." False if `var/state`
  holds unexported operator state. The installer never deletes or
  migrates `var/state` on upgrade, and uninstall keeps it without
  `--purge`.
- **F-I6.** "Base means degraded." False. Base is complete for
  its commands — `referee`/`doctor`/`state` lose nothing. What it lacks
  is surface (roles, scenarios, execution), and it says so with a clean
  refusal rather than a missing-file traceback.
