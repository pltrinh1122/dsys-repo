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
    toolchain/                  # derivation toolchain material, pinned:
                                # <toolchain>-<version>/ with content hashes
                                # recorded in var/manifest.json (§11:
                                # the runner verifies pins against these)
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

One release = one tag on `github.com/pltrinh1122/dsys-repo`
(`v<dist_version>`) published as a GitHub Release with two attached
assets: `dsys-<tag>.tar.gz` (a `git archive` of the tag — the tag *is*
the content manifest, so no separate per-file list is needed) and
`dsys-<tag>.tar.gz.sha256` (the tarball's checksum, the release's own
attestation). The installer verifies the tarball against the checksum
asset before touching the install home; a mismatch aborts before any
mutation (F-I13: downloading from github.com is not verification).

Sources, in order of preference:

1. `--release <tag>` — acquire from GitHub Releases: resolve the tag's
   assets via the API, download tarball + checksum, verify
   sha256(tarball) against the published checksum (or against a pinned
   `--release-sha256`, which must agree with the published one —
   out-of-band pin wins for fleet use), unpack, then install offline
   from the unpacked tree. Network is used for acquisition only;
   everything after unpack follows the offline path (F-I1, F-I12).
2. `--from <path>` — local source tree. Fully offline.
3. No source given — `--from` defaults to the script's own directory;
   `--release` requires an explicit tag. The installer never guesses a
   URL; acquisition is the operator's explicit act, and the release
   location is fixed convention, not configuration.

The manifest records acquisition provenance under `source`:
`{"mode": "release", "tag", "tarball_sha256"}` or `{"mode": "local",
"path"}`. Provenance, not verification — verification happened at
acquire time.

## 4. Hermeticity boundary (per command)

| Command | Network | Notes |
|---|---|---|
| `referee` | never | pure function over state files |
| `scenario` | never with `--backend stub` | real backends are the scenario author's choice |
| `state`, `roles`, `doctor` | never | local tree only |
| `execute --backend stub` | never | installer self-test path |
| `derive` | never | the runner's CLI surface (§11): derivation is offline given the input closure |
| `execute` (real backend) | yes | inherent; backend auth is the backend's business |
| `session` | yes | sync service only; the one network surface besides backends |

`dsys doctor` reports the boundary explicitly: `hermetic: ok` covers the
tree; backend probes are advisory and labeled as such (F-I4).

## 5. Install procedure

`./install.sh [--from <path|url>] [--home <dir>] [--dev] [--uninstall] [--purge]`

`--dev` installs from the working tree (the `--dev` loop, §12);
`--from` installs from a release artifact. The two modes differ in
provenance, not in checking machinery.

1. **Preflight.** `python3 >= 3.10`; `curl` only if `--from` is a URL;
   writable home; ~200MB free. Warn (don't fail) if no agent backend is
   on PATH — `stub` keeps install green.
2. **Acquire + verify.** `--release <tag>`: resolve the tag's assets
   via the GitHub Releases API, download tarball + checksum asset,
   verify sha256(tarball) against the published checksum (or the pinned
   `--release-sha256`, which must agree). `--from <path>`: use the local
   tree directly. Any mismatch aborts before mutation.
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
   - `dsys derive --manifest <carried-identity-fixture>` — exit 0,
     output hash == input hash (runner smoke test: derivation is
     reachable and the toolchain pin verifies).
8. **Cache.** Copy the dist tarball to `var/cache/` (bounded: keep last
   two) for offline rollback.

**Idempotent.** Re-running upgrades in place converges the tree (§10.5):
venv rebuilt, tree replaced per the profile's owned set, `etc/config.yaml`
and `var/state` untouched, symlink verified-not-duplicated. Convergence is
operational, not byte-identical; profile switching is the same converge
operation with the other `--profile`.

**Uninstall.** `--uninstall` removes the tree and the symlink; `var/state`
is *kept* (it is operator data) unless `--purge` is also given. The
installer never deletes state silently (F-I5).

## 6. `var/manifest.json` (sketch)

```json
{
  "installer_version": "1.0.0",
  "dist_version": "0.3.0",
  "source": {"mode": "release", "tag": "v0.1.0",
             "tarball_sha256": "…"}  // or {"mode": "local", "path": "…"},
                                     // or {"mode": "dev", ...} (see §12),
  "install_path": "/home/operator/.dsys",
  "installed_at": "2026-09-19T...",
  "artifacts": {
    "cli":      {"version": "0.3.0", "sha256": "..."},
    "core":     {"version": "0.3.0", "sha256": "..."},
    "roles/cos":      {"version": "1.2.0", "sha256": "..."},
    "roles/operator": {"version": "1.2.0", "sha256": "..."},
    "roles/auditor":  {"version": "1.2.0", "sha256": "..."},
    "toolchain/exprc": {"version": "2.1.0", "sha256": "..."},
    "toolchain/sealer": {"version": "1.4.0", "sha256": "..."}
  }
}
```

The `toolchain/*` entries are the runner's pin registry (§11): a
DerivationManifest pins `toolchain/exprc@2.1.0`, and the runner
verifies the pin against exactly these hashes before deriving
(R-2). `dsys doctor` verifies toolchain material presence + hashes
like any other artifact.

One version string covers CLI + core + role hashes in
`dsys --version` output (per the packaging spec); the manifest is the
machine-readable form. Fleet use: `dsys doctor` on any member machine
attests whether its tree matches a pinned release — identical
environments across the fleet, verified rather than assumed.

The manifest also carries the dist's **component registry** verbatim
under the `components` key: the architecture's component set
(`components.json` at the dist root), each entry declaring its kind
(`shipped` | `specified-only`), the profiles it ships in, and its
defining artifacts. The installer *carries* this registry — it authors
nothing about components and maintains nothing (F-I11). `dsys doctor`
owns the status: its `components` check evaluates every entry against
the live tree and reports per-component **instantiated |
specified-only | absent | mutated** (F-I10). A partial architecture
can therefore never report all-green: specified-only components
(factory, transcription, automaton-executor, session-sync, dialog) are
visible as specified-only, not silently absent.

Release installs record `"source": {"mode": "release", "tag",
"tarball_sha256"}` (`tarball_sha256` is the verified hash — provenance,
not a second verification). `--from` installs record `"source":
{"mode": "local", "path"}`. `--dev` installs record working-tree
provenance instead (§12): `"source": {"mode": "dev", "repo": "...",
"commit": "...", "dirty": false, "diff_hash": "..."}`.

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
`share/scenarios`, no `lib/toolchain`. The full profile adds exactly
those three directories.

### 10.2 Command availability

| Command | base | full |
|---|---|---|
| `referee` | yes | yes |
| `doctor` | yes (hermetic subset) | yes |
| `state` | yes | yes |
| `roles`, `scenario`, `execute` | clean refusal | yes |
| `derive` | clean refusal | yes (the runner's CLI surface, §11) |
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
  `lib/roles` + `lib/toolchain` + `share/scenarios`.
- The manifest records `profile`; `doctor` verifies presence *and*
  absence per profile (a full tree missing roles = violation; a
  base tree missing roles = correct).
- Switching profiles is `install` with the other `--profile` (§10.5):
  base→full adds `lib/roles` + `lib/toolchain` + `share/scenarios`;
  full→base removes them — pristine files deleted, mutated/unknown
  files quarantined to `var/quarantine/<ts>/` with a record, never
  silently destroyed. `etc/config.yaml` and `var/state` untouched in
  both directions.
- Moved-tree detection (§7) applies identically to both profiles.

## 10.5 Idempotency & profile switching

**Equality.** "Idempotent" means operational convergence, not
byte-identity (the byte-identity claim was falsified 2026-09-19:
`installed_at` is rewritten every run, `__pycache__` regenerates).
Two install states are equivalent iff: `dsys doctor` exits 0 with
`pristine`; the normalized manifest (profile + file hashes;
`installed_at`/`install_path` excluded) is identical; the
install-owned file sets (`bin/`, `lib/`, `share/`) are identical as
path→sha256; the command matrix (§10.2) holds; and operator material
(`etc/config.yaml`, `var/`) is preserved byte-identical.

**OWNED(p).** The dist-provided file set per profile:
- base: `bin/dsys`, `lib/dsys/*.py`, `lib/core/package/*.py`;
- full: base + `lib/roles/**` (sealed bundles) + `lib/toolchain/**`
  (pinned toolchain material, §11) + `share/scenarios/*.py`.

**Converge.** `install(p)` (`lib/dsys/install_tree.py::converge`) runs
from any state — absent, base, full, mutated:
1. Triage every on-disk file under `bin/`, `lib/`, `share/` not in
   OWNED(p):
   - pristine per the previous manifest (hash matches) → delete
     (reproducible from the dist);
   - mutated (hash differs) or unknown (never in the manifest) →
     quarantine to `var/quarantine/<utc-ts>/`, relative paths
     preserved, with a `record.json` (`quarantined_at`,
     `from_profile`, `to_profile`, per-file `path`/`sha256`/`reason`).
     Never silently destroyed (declared-mutation rule).
2. Lay down OWNED(p) wholesale from the dist (converges stale files too).
3. `etc/config.yaml` created only if absent, never clobbered;
   `var/` untouched except quarantine writes.
4. Venv rebuilt; manifest rewritten; self-test as §10.3.

Files *in* OWNED(p) that were mutated are overwritten, not quarantined:
"tree replaced" is the specified reinstall semantic, reinstall is
doctor's own prescribed remedy for a mutated tree, and the mutation
playbook's patch rung carries an explicit upgrade-fate gate for
exactly this.

**Cross-install.** `install(p)` is total — it never refuses a
well-formed invocation — so profile switching needs no separate
operation: switching *is* `install` with the other profile.
base→full→base converges to base; full→base→full converges to full.
One exception, and it is opt-in: with accretion commit authority set
to `operator` (§13) and dirty accreted state the operator declines to
commit, the installer refuses before mutating the tree rather than
clobber or silently skip. Standing mode (the default) never refuses.

**Acceptance** (`tests/test-install-idempotency.sh`, isolated `--home`s):
T0a `base,base→base`; T0b `full,full→full`; T1 `base,full,base→base`;
T2 `full,base,full→full`; T3 a mutated role bundle survives a
full→base switch byte-identical inside the quarantine with
`reason=mutated`; T4 an unknown file survives a same-profile reinstall
with `reason=unknown`. T1/T2 plant `var/state` + config markers and
assert byte-identity across the sequence.

G6: `etc/` files beyond `config.yaml` are currently out of the sweep
(operator territory); stray top-level files are outside the
installer's domain.

## 11. Runner bridge (2026-09-20)

The runner (`runner-spec.md`) never provisions — falsified
2026-09-20: no installing or configuring hosts, containers, or
toolchains; provisioning is a deployment/installation concern under
its own authority. The installer is that concern, and this section
is the bridge: what the installer owes the runner, and where the
boundary lies.

**What the installer provides.** The installed tree is the runner's
*provisioned material*: runner software (the `derive` command) plus
toolchain material (`lib/toolchain/`, content-hashed, §2) — laid
down by `install.sh`, verified by `doctor`. The runner verifies
DerivationManifest pins against the manifest's `toolchain/*` hashes
(R-2); "unknown toolchain" means "not in `var/manifest.json`."
Moved-tree detection (§7) applies: a moved tree is refused at
startup, so pins are never verified against a stale manifest.

**What the installer does not provide.** The sealed *environment*
the derivation executes in is provisioned per-deployment — the
operator's act, under the operator's authority — and appears in the
receipt only as the environment fingerprint the runner attests
(R-1, mechanism-agnostic). `install.sh` lays down software and
material; it does not build the seal. (F-I7.)

**Attestation chain.** Four links, each verifying the previous:
`dist-manifest.json` (release) → `var/manifest.json` (installed
tree, `doctor`-verified) → DerivationManifest pins (runner-verified
against the manifest) → RunnerReceipt (seal attested, output
hashed). Pin verification and seal attestation are different links;
neither subsumes the other.

**Idempotency, same shape.** Reinstall converges over (dist,
profile) — operational convergence, verified. Derivation is
idempotent over manifest hash (R-5 cache). Different mechanisms,
same shape: equality by hash, no silent drift.

**Offline, same pattern.** Deployment is offline given a local dist
(F-I1); derivation is offline given the input closure (`derive`
touches no network, §4). Install-time and build-time hermeticity
are the one pattern at two phases.

**Caches, distinguished.** `var/cache/` holds previous
distributions for rollback (installer). The runner's
DerivationCache is derivation memoization, content-addressed by
manifest hash (runner). Different caches, different purposes; the
DerivationCache lives under `var/` as runner accretion material,
never confused with the dist cache.

**Profiles.** `derive` and `lib/toolchain` are full-profile: the
runner produces release bytes — acting, even though deterministic —
and the base profile's purpose is judging with minimal surface. A
base tree refuses `derive` cleanly (§10.2). Receipt *verification*
(checking attestation + hash equality) is pure judging and could
ride `referee` later; not committed here.

**No Docker, consistent.** §8's "no Docker image in v1" stands, and
is consistent with the runner's mechanism-agnostic seal: had the
installer baked a container story, it would have mandated the
runner's mechanism. It doesn't.

## 12. `--dev` loop (2026-09-20)

The development loop for dsys itself — software, specs, or both:
mutate → install → exercise → verify → iterate. An extension by
*specification*, not a system: a specified `--dev` mode, iteration
DoD conditionals, manifest provenance fields. No new entities
(F-DEV-1), no forked checking machinery (F-DEV-2), not a run-book
(F-DEV-3), no per-iteration dispositions (F-DEV-4).

### 12.1 `--dev` mode

`install.sh --dev` installs from the working tree (dsys-repo
checkout), not a dist tarball. `--from` takes a release artifact;
`--dev` takes source.

- **Provenance replaces release-verification.** No
  `dist-manifest.json` exists in dev mode. The manifest records
  `source: {mode: "dev", repo, commit, dirty, diff_hash}` instead of
  `dist_version`. A dirty tree is recorded, not refused — recording
  is disclosure, and undisclosed is the only failure mode. Dist
  *packaging* from a dirty tree is refused (releases are
  clean-tree-only; packaging itself undesigned).
- **Fast converge.** Skip venv rebuild when the lockfile hash is
  unchanged — converge, don't rebuild.
- **Offline by construction.** The working tree is local; `--dev`
  performs zero network calls.
- **Disclosed mutation by construction.** A --dev install *is* a
  mutated tree. Doctor's hash-verification machinery is
  mode-agnostic (F-DEV-2) — tree-vs-manifest hashes are checked
  identically — but the baseline differs: dev mode baselines against
  the recorded *source*, so expected divergences are not violations
  while beyond-provenance divergence is.

### 12.2 Iteration DoD (conditionals, not a sequence)

An iteration is complete when:

- **D1 — provenance recorded.** Install completed; manifest carries
  `source{repo, commit, dirty, diff_hash}`.
- **D2 — expected divergences only.** Doctor: tree matches provenance.
  Beyond-provenance divergence is STOP — undisclosed mutation.
- **D3 — affected checks pass.** Golden run / referee / scenarios
  covering the touched machinery: 0 violations. *Which* checks cover
  the change is judgment (stated in the iteration plan); the *results*
  are mechanical.
- **D4 — reason stated.** The iteration serves a mutation matter with
  a recorded reason (I-17) — once per matter, not per iteration.

For pure-spec development the install step is vacuous: specs are
content, and "exercise" is re-running validators and golden runs.
The loop is uniform across software and spec.

### 12.3 Disposition economy

One disposition per matter (mutation playbook: rung, reason,
trust-boundary declaration); iterations are *checked*, not decided.
Fresh dispositions occur only at matter boundaries — patch→fork
escalation, trust-boundary discovery mid-iteration (amendment
procedure), matter mis-scoping — each because *new authority is
exercised* (F-DEV-4). Disposition without new authority is theater.

### 12.4 Relation to machinery

- The loop is dyad-executed and DoD-gated — not a run-book (F-DEV-3):
  run-books are zero-inference automaton-plane; the loop's core acts
  are judgmental and it produces the plane's inputs rather than
  executing within it.
- Mechanical segments (install, golden run, referee, derive fixture)
  may be automated as a **scenario**: declarative exercise spec,
  driver-interpreted, human at the judgment joints.
- Iteration history is git's business (log, bisect). The architecture
  records matters and outcomes — DecisionRecord, RunnerReceipts,
  referee results — not keystrokes (F-DEV-1).

## 13. Accretion repo (2026-09-20)

The `accretion-repo` term was ratified 2026-09-19 (a git repository as
the durable store of a dsys installation's accreted state) but left as
an unexercised deployment pattern (G6). This section exercises it:
the installer sets up a **local** accretion repo at install time, so
accreted state has history and no future install can silently
override it. Local only — no remote, no push, no sync (session sync
is a separate, unimplemented build).

**Accreted set.** `etc/` + `var/` minus any `cache` directory — the
ratified narrowing (2026-09-19: "var/ minus cache"), generalized to
nested cache dirs (`var/cache`, `var/runner/cache`, …): cache material
is ephemeral and regenerable by definition. The exclusion is a
pathspec (`:(exclude,glob)**/cache{,/**}`), quoted literally — shell
glob expansion of an exclusion pathspec would silently invert it.
`var/manifest.json` rides along (it is install-authored, but it lives
under `var/` and its history is worth having).

**Repo shape.** The repo's git dir lives at `<accretion-path>/.git`
with `core.worktree` set to the install home — a separate git dir,
never a `.git` inside the install tree (F-A3). The installer passes
`--git-dir`/`--work-tree` explicitly on every invocation and
pathspec-scopes every command to the accreted set
(`etc var :(exclude,glob)**/cache :(exclude,glob)**/cache/**`), so the
rest of the tree is never staged, never committed, never shown dirty.
The `--` separator lives in exactly one place (the wrapper): a
doubled `--` becomes a pathspec for a literal file named `--` and
fails the add — silently, if the caller swallows stderr.

**Path.** Default `<accretion-root>/{instance}`, accretion root
`/var/daccretion`, instance = install-home basename —
e.g. `/var/daccretion/dsys-inst`. Overridable as configuration
(`accretion.path` in `etc/config.yaml`) or flag (`--accretion-path`);
precedence flags > config > default, per the config contract.
Each instance gets its own path; two homes never share a repo.

**Resume vs overwrite.** Default is **resume**: if a repo already
exists at the accretion path, the install continues its history.
`--overwrite` sets up a **fresh** accretion repo: the existing repo
dir is moved aside to `<path>.bak-<utc-ts>/` (never deleted — history
is not silently destroyed) and a new repo is initialized; the
current accreted state becomes its first snapshot.

**Snapshot commits.** On resume the installer brackets the tree
mutation: a pre-install snapshot commit before converge, a
post-install snapshot commit after the manifest is written. Commit
messages name the boundary (`dsys accretion: pre-install snapshot
(installer 1.0.0, profile full)`). Repo-local `user.name` /
`user.email` are set at init (`dsys-accretion` /
`dsys-accretion@localhost`) so the installer never depends on the
operator's global git identity. A commit is skipped when there is
nothing to commit.

**Commit authority** (ratified 2026-09-20). Default is **standing
authorization**: the operator's standing disposition covers
accretion journaling, and the installer commits without asking. The
preference flag `--accretion-require-authorization` (or
`accretion.commit_authority: operator` in config) flips to
**operator authorization**: with dirty accreted state the installer
prompts (`Commit accretion snapshot before installing? [y/N]`);
a "no" — or a non-terminal stdin — refuses the install before any
tree mutation, naming the dirty paths. Standing mode never refuses;
operator mode refuses rather than clobber or silently skip.

**Never fails the install.** If git is absent from PATH, or the
accretion path is not writable, the installer warns and continues
with accretion disabled; the manifest records
`accretion: {"enabled": false, "reason": ...}`. Accretion is a
durability backstop, not a prerequisite.

**Fail-closed carve-out (K2 repair, DR-CMD-038).** The
`--accretion-required` flag suspends the rule above for
updater-driven installs: accretion is required, so any of the
disable conditions (git absent, path not a directory, path not
writable, `--no-accretion`) fails the install with a nonzero exit
naming the reason, before any accreted-state mutation — no manifest
is written, so no lying manifest. The gate fires at the start of
the converge step; the venv recreation that precedes it touches no
accreted state. Interactive installs keep the default: warn and
continue. The updater's drive always passes `--accretion-required`
together with an explicit `--accretion-path` (the previous
installation's effective path), and never passes `--overwrite`.

**Manifest & doctor.** `var/manifest.json` gains
`accretion: {"enabled", "path", "commit_authority"}` (the installer
carries provenance; it does not verify the repo). `dsys doctor`'s
manifest check displays `accretion=<path>` or `accretion=off`.

**Iteration DoD** (conditionals, not a sequence):
- A1: after install, `<path>/.git` is a valid repo,
  `core.worktree` == install home, and every tracked path is under
  `etc/` or `var/` and none under a `cache/` directory.
- A2: fresh install → exactly one commit; resume reinstall →
  pre/post snapshot commits bracket the mutation; accreted files are
  byte-identical across the reinstall unless the operator changed
  them — in which case the change is committed, never lost.
- A3: `--overwrite` with an existing repo → the old repo exists at
  `<path>.bak-<ts>/`, the new repo has a fresh history, the install
  completes, and the backup path is reported on stdout.
- A4: `--accretion-require-authorization` with dirty accretion and
  stdin not a terminal → nonzero exit before any tree mutation,
  stderr names the dirty paths.
- A5: no git on PATH, or accretion path not writable → install
  completes, warning on stderr, manifest records
  `accretion.enabled=false`.
- A6: `dsys doctor` stays green (12/12) and `pristine` on a home
  with accretion enabled — the repo is outside the manifest's
  coverage by construction.

## 14. Falsifiers (pre-registered)

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
- **F-I7.** "Reinstall is byte-identical." False — `installed_at` is
  rewritten every run and `__pycache__` regenerates. The precise claim
  is operational convergence (§10.5).
- **F-I8.** "Per-profile idempotency implies switch idempotency."
  False — the inference is a non sequitur (falsified 2026-09-20);
  switching is a distinct operation and needed its own specified
  semantics — now §10.5.
- **F-I9.** "Installing the runner installs its containment." False
  (2026-09-20 falsification). `install.sh` lays down runner *software*
  and toolchain *material*; the sealed *environment* the runner
  derives in is provisioned per-deployment under the operator's
  authority and appears in the receipt only as an attested
  environment fingerprint. The installer never builds the seal.
- **F-DEV-1.** "The --dev loop needs a new entity (DevIteration)."
  False. Manifest provenance + the matter's DecisionRecord +
  RunnerReceipts + referee results + git log reconstruct any
  iteration. The architecture records matters and outcomes, not
  keystrokes; iteration history is git's business.
- **F-DEV-2.** "A --dev tree should verify against dist-manifest."
  False — no dist exists in dev mode. Declaration replaces
  release-verification; doctor's hash machinery is mode-agnostic and
  only the baseline differs (recorded source, not release).
- **F-DEV-3.** "The dev loop can be a run-book." False. Its core acts
  are judgmental and it produces the automaton plane's inputs;
  run-books are zero-inference and execute within the plane.
  Mechanical segments may be scenarios; the loop is dyad-executed,
  DoD-gated.
- **F-DEV-4.** "Iterations need per-iteration dispositions." False.
  The matter is decided once; iterations are checked. Fresh
  dispositions occur only at matter boundaries (escalation,
  trust-boundary discovery, mis-scoping) — where new authority is
  exercised.
- **F-I10.** "`dsys doctor` provides a mechanical status of
  instantiation." False as stated (2026-09-20 falsification). Doctor
  verifies installation integrity (tree hashes, layout, config) plus
  core validity (golden chain) — it cannot name which playbooks or
  factory machinery are real vs spec-only, cannot see sibling
  instances, cannot detect staleness vs origin, and cannot distinguish
  idle from exercising. Narrow survivor: doctor *can* report
  per-component status once the architecture's component set exists as
  machine-readable dist metadata — which is the component registry
  (§6). Instantiation is a relation between the component set and the
  installed tree; doctor sees the tree side, the registry supplies the
  other. Honest limit: the decision-making playbook is a procedure
  embodied by the operator — no file presence proves it is being
  followed. Some instantiation is behavioral, not mechanical.
- **F-I11.** "The installer should maintain a registry of installed
  components and provide status." False (2026-09-20 falsification):
  two jobs assigned to the wrong tool. (a) Staleness: install-time
  facts decay; status is a runtime predicate — a registry the
  installer "maintains" is frozen (lies) or updated by something else
  (not the installer's). (b) Wrong level: the installer is
  per-instance; the component set, including spec-only components, is
  per-architecture — the installer cannot register what it never laid
  down. (c) Redundancy: file→component mapping is dist metadata, not
  installer knowledge. (d) Mutation desync: declared-mutation means
  the tree drifts; only the checker observes the drift. Survivor: the
  installer *carries* the dist's registry verbatim into the manifest;
  **doctor** maintains and provides status. Installer records
  provenance; doctor reports current truth.
- **F-I12.** "`--release` makes the installer an online tool."
  FALSIFIED as a blanket claim. Network is confined to the acquisition
  step ([0/7]): resolve the tag's assets, download tarball + checksum,
  verify, unpack. Everything after unpack — preflight, venv, tree
  layout, manifest, self-test — runs the identical offline path as
  `--from <path>`. The surviving precise claim: the installer performs
  network I/O in at most one step, and that step is named, optional,
  and explicit (`--release`).
- **F-I13.** "Downloading a release tarball from github.com verifies
  it." FALSIFIED. TLS authenticates the server, not the artifact; the
  auto-generated GitHub source tarball has no published hash to check
  against. The installer verifies sha256(tarball) against the release's
  attached checksum asset (or a pinned `--release-sha256`, which must
  agree with the published checksum) and aborts before any mutation on
  mismatch. Trust basis, stated: the checksum is the release's own
  attestation, not an independent one; for fleet use, pin the hash
  out-of-band.
- **F-A1.** "The accretion repo makes the installer depend on git."
  False. Git is opportunistic: absent from PATH, or accretion path not
  writable, the installer warns and continues with accretion disabled
  (A5). The install never fails for want of a journal.
- **F-A2.** "Auto-commit violates operator authority." False as a
  blanket claim. Standing authorization is the operator's own
  disposition (ratified 2026-09-20) covering accretion journaling;
  the preference flag `--accretion-require-authorization` restores
  per-commit operator authorization. And a local journal commit is
  not publication — publication remains the operator's act; the
  repo has no remote and the installer never pushes.
- **F-A3.** "The accretion repo pollutes doctor's pristine check."
  False. The git dir lives outside the install tree, every git
  command is pathspec-scoped to the accreted set, and the manifest's
  file coverage never includes the repo (A6).
