# Production-tools spec: the updater flow's executor tool registry

**Status: ADOPTED** — spec stage authorized by DR-CMD-055 (2026-09-23, mode: authorize); spec adopted by DR-CMD-056 (2026-09-23, mode: authorize). **Built** 2026-09-23 under DR-CMD-057 (O1: all eight tools at once); mechanical verification: `lib/dsys/tools/_production_tools_golden_run.py` — RESULT: PASS, 73 cases, 0 violations. As-built deltas are recorded in §11, not bridged silently.

This spec is the registry contract for the eight production tools the updater flow's run-books invoke. It settles DR-CMD-055's spec-stage conditions: the F2 resolution applied, the World→system interface mapping per tool, the failure-record schema on the disclosure path, the subprocess scope against §8, per-tool idempotency arguments, the R2/R1/R3/R5 stories, and the A5 acceptance. Prior art it does not redesign: the executor (§8 tool contract, C1/C2), the run-books and their step policies, the drive contract (D7, I-26), K1's committing design (DR-CMD-039), and the Q3(a) identity binding (DR-CMD-047).

## 1. What this spec is

The eight tools are dist-shipped `lib/dsys/tools/` modules. Each defines `TOOL_NAME: str` and `run(ctx: dict) -> {"ok": bool, "result": <json>, "ctx_delta": <json>}`, loaded by the executor's `load_tools` (no overlays, no search paths). This spec defines, per tool: what system interface replaces the golden-run `World` fixture, what enters and leaves `ctx`, what aborts, and why re-invocation under at-least-once crash recovery is safe. The eight `_tool_*` World-functions in `core/package/updater.py` are the behavioral contract — this spec is the production mapping, not a second behavior.

## 2. The tool contract (executor-spec §8, as amended by DR-CMD-055)

- **Deterministic** (declared; F-E2) and **idempotent** (required; crash recovery is at-least-once — F-E3). `ctx` and deltas stay small and JSON-shaped (the `FlowTransitionEvent.payload` discipline, extended).
- **Hermetic, as amended:** no network in the executor or tools, *except the release-check poll* (updater-spec §5 P2) — the F2(a) resolution. The poll is the sole network touch in the registry: one HTTPS GET of the pinned feed URL, confined to `tool-fetch-feed`. Its result enters the machine only as external trigger payload — data, content-hashed into the event log, never resolved or executed by the untrusted side (the dialog R5 boundary; guards are AST-allowlisted expressions over recorded fields).
- **Subprocess scope (F1d):** "tools run in-process" governs *invocation* — modules are importlib-loaded and `run(ctx)` is called in the executor's process; tools are not separate executables. A tool may spawn subprocesses (`install.sh`, `git`); it may not touch the network except the §2 carve-out above.
- **Installation location:** tools locate the installation via the `DSYS_HOME` environment variable (C4-established: runs live at `<DSYS_HOME>/var/runs/<run_id>.json`; `lib/dsys/paths.py` resolves the home with `DSYS_HOME` winning). Tools never take the home from `ctx` — environment facts stay out of the recorded log.
- **Dist-shipped and release-pinned** (`runbook_id` + `release_version` recorded at init). A custom tool is a fork matter (dsys-mutation-playbook), not an executor option (G6 Q7 — stands).

## 3. The registry: closed list and release pinning

| TOOL_NAME | Run-book | Step |
|---|---|---|
| `tool-fetch-feed` | `rb-release-check` | 1 |
| `tool-compare-versions` | `rb-release-check` | 2 |
| `tool-verify-checksum` | `rb-release-verify` | 1 |
| `tool-read-policy` | `rb-policy-gate` | 1 |
| `tool-invoke-installer` | `rb-release-drive` | 1 |
| `tool-run-doctor` | `rb-release-verify-installed` | 1 |
| `tool-record-promotion` | `rb-release-verify-installed` | 2 |
| `tool-commit-accretion` | `rb-accretion-commit` | 1 |

Six run-books, eight tool steps, eight tools. **The list is closed** (G6 Q2): each run-book step binds exactly one tool name, and the step lists are fixed. A new capability is a new run-book step, which is a spec amendment — never a registry addition at runtime.

**Release pinning** (G6 Q6): the installer carries `lib/dsys/tools/` as part of the dist tree — the tools are installed files like any other component, covered by the install manifest. The binding is two-sided: the manifest records `source` (`{mode: "release", tag, tarball_sha256}` for `--release` installs; `{mode: "local", path}` for `--from` installs) and `dist_version` at install time; the run records `runbook_id` + `release_version` at init (§8). A run's tools are the pinned release's tools — I-31 (§7) predicates exactly this.

## 4. Per-tool contracts

Each tool's `run(ctx)` returns `{"ok", "result", "ctx_delta"}`. Any contract deviation — exception, non-dict return, missing keys — is normalized by the executor's C1 into a tool failure; the run-book's declared step policy then applies (`retry:3` on the `rb-release-check` steps for transient network; `abort` elsewhere). "Abort" below means the tool raises (or returns `ok: false`) with the stated reason; the reason string is preserved verbatim through C1 into the failure record (§5).

### 4.1 `tool-fetch-feed` (rb-release-check, step 1)

- **System interface:** reads `updater.feed_url` (the pinned feed URL, operator-owned config) via `config.load(home)`; performs the §2 carve-out GET (one HTTPS request, timeout-bounded).
- **Mapping:** `w.network_enabled` → the GET's outcome (no flag in production; a failed GET raises, and `retry:3` covers transience — updater-spec §5). `w.feed_version` → parsed from the feed document. `w.feed_sha256` → sha256 of the received response bytes. `w.feed_checksum_ok` → the feed's declared checksum for the candidate release, recorded as `feed_checksum` (a mismatch between declared and computed is the tamper signal the next tool checks).
- **ctx_delta:** `{feed_sha256, remote_version, feed_checksum}`. The raw feed bytes are *not* stored — the small-ctx discipline holds; the hash binds the bytes for replay (§6).
- **Abort:** GET failure (unreachable host, non-2xx, timeout, unparseable feed) → raise; the step policy retries 3 times, then the run aborts.
- **Idempotency:** a pure read-and-record. Re-invocation under at-least-once re-fetches and overwrites the delta with fresh values; no side effects exist to duplicate.
- **Determinism note:** two live advances may observe different feed bytes. That is external input as data (updater-spec §3 R1): each advance records what it saw; replay re-validates against the record and never re-fetches.

### 4.2 `tool-compare-versions` (rb-release-check, step 2)

- **System interface:** reads the installed release version from the installation manifest, `<home>/var/manifest.json` → `dist_version`. (Maps `w.installed_version`.)
- **ctx_delta:** `{installed_version}`. Guards compare `payload.remote_version != payload.installed_version`; comparison only, no inference.
- **Idempotency / determinism:** a pure read of a value stable within an installation. Trivially idempotent.

### 4.3 `tool-verify-checksum` (rb-release-verify, step 1)

- **Pure function of ctx:** if `ctx["feed_checksum"] != ctx["feed_sha256"]`, raise `ToolAborted("checksum mismatch: no candidacy")`. (Maps the World's comparison; in production both sides arrive via the fetch tool's delta.)
- **What it verifies:** the feed's *self-declared* checksum against the hash of the bytes actually received — feed integrity in transit. A tampered feed aborts here: no candidacy, `run_aborted` → failed. The *candidate release artifact's* integrity is the installer's discipline, not this tool's: `install.sh` verifies the release artifact during the drive, and a verification failure surfaces as a nonzero exit in §4.5.
- **Idempotency:** pure comparison. No side effects.

### 4.4 `tool-read-policy` (rb-policy-gate, step 1)

- **System interface:** reads `updater.policy` (`auto | notify | off`, default `notify`) and `updater.auto_max_bump` (`patch | minor | major`, default `patch`) from operator config via `config.load(home)`. (Maps `w.updater_policy`, `w.auto_max_bump`.)
- **Behavior** (the World function, exactly): `auto` with the bump within `auto_max_bump` → `{decision: "drive"}`; `auto` over the bump → `{decision: "defer", reason}` and the candidate is surfaced; `notify` → `{decision: "defer", reason: "policy=notify: surfaced, not driven"}` and the candidate is surfaced; `off` → `{decision: "defer", reason: "policy=off: recorded only"}`; anything else → raise `ToolAborted(f"unknown updater policy: {policy!r}")` — a typo'd policy (`autoo`) aborts loudly rather than degrading silently to `off`.
- **ctx_delta:** `{policy, auto_max_bump, decision, reason}` — the tool pins what it read. This is the G6 Q5 answer: the determinism declaration covers the (config, versions) → decision function, and the inputs are pinned in the log. Two live advances may see different configs; each records what it saw; replay never reinvokes.
- **Surfacing** (maps `w.surfaced`): deferrals that surface (auto-over-bump, notify) mint a disclosure of the fixed kind `updater-deferred` (`{version, reason}`) into `<home>/var/disclosures/`, under the DR-5 seq discipline (write-path-minted, monotonic, no clock). This extends the executor's disclosure family (§7's fixed `automaton-exception` template) by one fixed template — declared here, not smuggled.
- **Idempotency:** the tool checks `ctx` for an existing `surfaced_seq` for the candidate version and skips re-minting. Re-invocation under at-least-once therefore surfaces at most once.

### 4.5 `tool-invoke-installer` (rb-release-drive, step 1)

- **System interface:** spawns `install.sh` as a subprocess (the §2 subprocess scope): `argv = ["install.sh", "--release", version, "--accretion-path", acc_path, "--accretion-required"]` — the composed perform step (K2 repair): the explicit accretion path always, never `--overwrite` (D5), always fail-closed (D2).
- **Accretion path** (maps `_accretion_path(w)`): the running installation's manifest `accretion.path` when recorded; else the default rule `"/var/daccretion/" + basename(home)`. During an upgrade drive the "previous install" is the running one — no new inputs are needed.
- **Mapping:** `w.installer_argvs` / `w.installer_invocations` → the spawned argv (observable in the process table, not recorded by the tool). `w.accretion_writable` / `w.installer_exit_code` → the subprocess's real outcome: an unwritable accretion path fails closed inside the installer (`--accretion-required`) and surfaces as a nonzero exit.
- **Abort:** nonzero exit → raise `ToolAborted(f"installer exited {code} for {version}")`. A failed install converges nothing — the version does not advance.
- **ctx_delta:** `{exit_code: 0}`. The tool does **not** record `installed_version`: convergence is the installer's, and the manifest is the installer's to write. (The World's `w.installed_version = version` is the fixture modeling the installer, not a tool write — a porting subtlety, stated so it is not misread.)
- **Idempotency:** the installer is idempotent — the 2026-09-20 finding (reinstall after operator mutations → exit 0; config, state, and log preserved and honored). A crash *during* the install followed by at-least-once re-invocation re-runs `install.sh` for the same version, which converges to the same state.

### 4.6 `tool-run-doctor` (rb-release-verify-installed, step 1)

- **System interface:** runs the dist's doctor checks in-process (`lib.dsys.doctor` against `<home>`) — no subprocess is needed; the §2 in-process invocation covers it. (Maps `w.doctor_ok`.)
- **ctx_delta:** `{doctor_ok}`.
- **Idempotency:** reads only.

### 4.7 `tool-record-promotion` (rb-release-verify-installed, step 2)

- **Behavior** (the World function, exactly): if `ctx["doctor_ok"]`, record the promotion; else record nothing.
- **System interface** (maps `w.promotions`): the promotion bridge (AutomatonRelease/PromotionRecord — the step-change). The record is written to `<home>/var/promotions/<version>.json` with deterministic content (`{version, feed_sha256}`, sorted-keys compact JSON — the K1 canonical discipline, extended). This is the first of the updater-spec §4's two recordings; the second is the accretion commit (§4.8).
- **ctx_delta:** `{promotion_recorded: true | false}`.
- **Idempotency:** re-invocation overwrites byte-identical content — the record for a version is a pure function of (version, feed_sha256). No duplicate promotion can exist.

### 4.8 `tool-commit-accretion` (rb-accretion-commit, step 1)

K1's design (DR-CMD-039), ported to the executor. The sharpest tool in the registry — specified first, as DR-CMD-055 requires.

- **ctx in:** `{flow_run_id, event_range: {first_seq, last_seq}, drive_identity, commit_authority}` — seeded by the flow's transition into the committing state. `drive_identity` is the drive-resolved manifest identity (the drive contract's governed/process split: the process side resolves it once at initiation; the tool's D3 check is a pure comparison, no file I/O for the check). `commit_authority` is `standing | operator` from the initiation record.
- **The write:** the tool reads the parent run's event log from `<DSYS_HOME>/var/runs/<flow_run_id>.json`, locates the watermark (the tip commit's covered event range), diffs the `{first_seq..last_seq}` range against it, and builds the canonical payload (`accretion-commit/v1`, sorted-keys compact JSON, sha256 content-hash — K1 Q1, pinned by the golden run) over the uncovered events. It commits via `git` (subprocess, §2 scope) using the handle acquired per the acquisition contract (DR-CMD-053).
- **D3 pre-write identity check** (K1 Q3(a), DR-CMD-047): before every write, the handle's repo identity (`dsys.repo-id`) must equal the drive-resolved identity; mismatch — or a missing key on either side — fails closed: abort, not retry (D4a), no commit, `run_aborted` → failed.
- **Authority:** `standing` commits without asking; `operator` on an autonomous drive refuses (aborts) — the drive cannot prompt (K1 D3). (Maps `w.accretion_commit_authority`.)
- **Git hard dependency** (D5a): git unavailable → abort. (Maps `w.git_available`.)
- **Idempotency — the watermark re-check:** the re-check precedes the write. Re-invocation after a crash reads the repo tip: if the tip already covers the event range (the commit landed before the crash), the diff is empty → no commit, `{"ok": true, "result": {"committed": false, "reason": "already-covered"}, "ctx_delta": {}}`. Otherwise the tool re-builds the byte-identical canonical payload (deterministic from the same events) and commits. Append-only (D6) holds because a duplicate commit never occurs — the watermark check, not the payload hash, is the guard.
- **Abort, not retry:** the run-book policy is `abort` (D4a) — a failed commit is never blindly retried inside the drive; the next drive's cumulative commit is the retry.

## 5. Failure records and the disclosure path (F1c, D7)

The failure-record schema is fixed by the built executor, not by this spec. Every attempt is `step_started` → outcome (I-28 adjacency); a failed attempt appends:

```
step_failed: {step_seq, tool, error, malformed}
```

`error` is the C1-normalized reason — for a raised tool, `tool raised {type}: {message}` (`lib/dsys/executor.py::invoke_tool`); for the 7b missing-tool path, `unknown tool '<name>' at advance time`. The tool's own message reaches the operator verbatim: D3's wrong-identity refusal, the checksum mismatch, the unknown-policy abort, and the installer exit code are all legible in the transcript without any disclosure machinery having to interpret them. `malformed` distinguishes contract deviations (the `malformed` fixture's case) from honest tool failures.

D7 (drive contract) — *after fail-closed: no retry, record, surface* — is satisfied in two halves: the transcript **records** (the `step_failed` chain with reasons, plus the `run_aborted` → failed routing), and the flow driver **surfaces** by minting the fixed-template `automaton-exception` disclosure into `<home>/var/disclosures/` when the drive reaches the failed end state. The spec-stage work F1c called for is this statement: the schema is the executor's, the reasons are the tools', and the disclosure is the driver's.

## 6. Replay (R1)

`automaton replay --run <id>` re-folds the event log from seq 0 and re-checks, never reinvoking tools (executor-spec §9). The poll result is recorded data — `feed_sha256`, `remote_version`, `feed_checksum` enter through `step_completed`'s `ctx_delta` — so replay re-evaluates the guards against the recorded values and re-derives the state path; the checkable assertion is hash equality of the derived state sequence between the live run and the replay (updater-spec §3). A trailing `step_started` with no outcome event is valid (crash recovery pending, C2) — the next `advance` re-invokes the tool, and §4's idempotency arguments are what make that safe.

## 7. I-31 — the pinned-release registry (R3)

`i31_pinned_registry`: a predicate over the run record — for every `step_started` event, the tool module's bytes are those shipped in the dist identified by the run's recorded `release_version`. The binding both sides cite: the install manifest's `source` (`{mode: "release", tag, tarball_sha256}` or `{mode: "local", path}`) and `dist_version`, recorded at install; the run's `runbook_id` + `release_version`, recorded at init (§8). The predicate holds iff the run's `release_version` identifies the dist whose `lib/dsys/tools/` the registry loaded. Violation → the run is invalid (referee's exit 5, the same class as replay violations). At spec stage the predicate is defined; enforcement belongs to `init`/`advance`, and the golden run checks the predicate (R2).

## 8. Trust declaration (R5)

- `updater.feed_url`: the pinned feed URL — operator-owned config, the feed-authenticity pin. Transport trust is TLS to that URL; the checksum gate (§4.3) is the governed integrity check, not the transport.
- `updater.policy` / `updater.auto_max_bump`: operator-owned config; the automaton cannot alter its own policy (updater-spec §4 — policy changes are operator step-changes).
- The installer: dist-shipped trusted code; its idempotency is the §4.5 argument's load-bearing premise (the 2026-09-20 finding).
- `git`: a hard dependency (D5a) — its absence fails closed, never degrades.
- Deterministically-lying tools (F-E1): declared trust, same class as `Disclosure.seq` minting — replay checks the record, it cannot detect a tool that lied deterministically.
- Disclosure seq: write-path-minted, monotonic, no clock (DR-5).

## 9. Acceptance (A5, R2)

**A5 — the 7b successor:** a timer-triggered updater flow with the production registry installed and a scripted feed advances past `checking` — the honest-abort path is replaced by a completed (or policy-deferred) drive. The 7b case remains in the surface suite as the missing-tool regression.

**R2 — golden-run cases** (per tool, against the §4 contracts):
1. Feed tamper: declared checksum ≠ received-bytes hash → `tool-verify-checksum` aborts, no candidacy, `run_aborted` → failed.
2. Wrong identity: handle `dsys.repo-id` ≠ drive-resolved identity (and each one-sided absence) → `tool-commit-accretion` aborts closed, reason preserved verbatim (the K1 cases 24–28, preserved through the port).
3. Network failure: GET fails → `retry:3` → abort (the transient-network path, updater-spec §5).
4. Unknown policy (`autoo`) → `tool-read-policy` aborts loudly; no silent degradation to `off`.
5. Installer nonzero exit → `tool-invoke-installer` aborts; the version does not converge.
6. `doctor_ok: false` → `tool-record-promotion` records nothing (`promotion_recorded: false`).
7. Crash after commit: re-invoked `tool-commit-accretion` finds the watermark covering the range → no duplicate commit (`committed: false`).
8. Operator authority on an autonomous drive → `tool-commit-accretion` refuses.
9. I-31: a run whose recorded `release_version` does not identify the loaded tools' dist → invalid.

## 10. Glossary

- **Production tool:** one of the eight `lib/dsys/tools/` modules specified here — the real implementations the updater's run-books invoke. Not the `_tool_*` World-functions in `core/package/updater.py` (the behavioral contract), not the fixtures (`noop`, `fail_always`, `malformed` — test doubles).
- **Tool registry:** what `load_tools` builds from `lib/dsys/tools/*.py`: name → `run(ctx)`. Dist-shipped, release-pinned; unknown names fail loudly at advance time.
- **Hermetic (tools, as amended):** no network in the executor or tools, except the release-check poll (updater-spec §5 P2) — DR-CMD-055 F2(a). Network-derived facts otherwise enter only as recorded external input.
- **World-function:** a `_tool_*` function in `core/package/updater.py` — the golden-run implementation against the scripted `World` fixture. The behavior to satisfy, not the tool.
- **World:** the golden-run fixture (`core/package/updater.py::World`) — "everything outside the machine the golden run scripts." Each §4 mapping replaces one of its attributes with a real system interface.
- **ctx / ctx_delta:** the run's folded JSON state / the JSON object a tool's `run(ctx)` returns to extend it. Small by discipline (executor-spec §8).
- **DSYS_HOME:** the environment variable identifying the installation home (C4-established). Tools locate config, manifest, and outboxes through it — never through `ctx`.
- **Drive-resolved identity:** the accretion repo identity resolved once at initiation (process side, from the install manifest's `accretion_repo.identity`); the committing tool's D3 check is a pure comparison against it.
- **Watermark:** the tip commit's covered event range — what the accretion repo already contains. The commit tool diffs the flow log against it; an empty diff means nothing to commit.
- **Canonical payload:** `accretion-commit/v1` — sorted-keys compact JSON with a sha256 content-hash (K1 Q1). Deterministic bytes from deterministic events.
- **Disclosure outbox:** `<home>/var/disclosures/` — seq-minted JSON records (DR-5). The operator's read-only surfacing surface.
- **Release-pinned:** the tool modules a run ran against are identified by the `runbook_id` + `release_version` recorded at init; I-31 predicates the binding.

## 11. As-built (build DR-CMD-057, 2026-09-23)

Deltas between the adopted spec and the built tools, recorded rather than bridged. The R2 golden run (`lib/dsys/tools/_production_tools_golden_run.py`) pins each one.

1. **Feed document format** (was unpinned): a JSON object `{"version": "<release>", "feed_sha256": "sha256:<hex>"}`. `<hex>` is the publisher's sha256 over the canonical JSON (sorted keys, compact separators) of the document with the `feed_sha256` member removed; the tool recomputes it identically. The recorded `feed_sha256` is that recomputed content hash — the spec's "sha256 of the received response bytes" read as the received *document's* content hash: raw-byte hashing is unimplementable for a self-describing checksum (the declaration is part of the bytes). The verify comparison's shape (`feed_checksum != feed_sha256` → tamper → abort) is unchanged.
2. **Timeouts** (were unpinned): the feed GET is bounded at 30s; the `install.sh` spawn at 600s; git spawns at 120s.
3. **No default feed URL:** `updater.feed_url` has no default — a missing pin aborts (`no pinned feed URL configured`) rather than inventing a trust decision.
4. **Config reading:** tools parse the `updater:` block of `etc/config.yaml` directly (yamlutil subset), not via `config.load` — `config.load` warns-and-ignores unknown keys, and the tool must pin exactly what it read into `ctx_delta`.
5. **`tool-record-promotion`:** the version string is restricted to `[A-Za-z0-9._-]+` — a feed-supplied version must not become a path. Version precedence: `ctx` `remote_version`, else the manifest's `dist_version` (the installer's converged version). `feed_sha256` must come from `ctx`: it is recorded poll data, never re-derived (R1).
6. **`tool-run-doctor`:** runs the non-strict posture (the CLI default); `doctor_ok` is true iff no check reports `fail` — warns are advisory.
7. **`tool-commit-accretion`:**
   - The accretion path is resolved like the installer's (manifest `accretion.path` when enabled and recorded, else the `/var/daccretion/<basename>` default rule); no path travels in `ctx`.
   - Event-log channel precedence: the K1 `_commit_input` (popped, never emitted) first; else the flow run's recorded log at `<home>/var/runs/<flow_run_id>.json`. The `event_range` bounds the diff on both channels.
   - The watermark walk: the fixture assumed the tip commit is the last accretion commit; installer snapshots share the repo, so the tool walks the log back to the most recent commit matching the K1 message pattern and reads the watermark from its embedded payload (message/payload disagreement fails closed).
   - Initial watermark is -1, not 0: the built executor numbers flow events from 0 while the fixture's flow seqs started at 1.
   - The payload is committed at `accretion/<payload_hash>.json`; git author identity is passed via `-c` flags (envelope, never replay identity — K1 D5).
   - On the file channel, `source_state` is the first in-range event's `from_state_id`.
   - Absent `commit_authority` defaults to `standing` (the fixture World's default).
8. **I-31** is implemented as `i31_pinned_registry` in `lib/dsys/tools/_common.py` (importable by a future referee); enforcement in `init`/`advance` remains future work, as §7 already states.
9. **Integration note (not a delta — outside this build):** the built executor's flow driver does not yet seed the committing child's `ctx` (`flow_run_id`, `event_range`, `drive_identity`, `commit_authority`), inject `_commit_input`, or propagate an accumulator into child runs (each child starts with empty `ctx`). The tools accept both event channels and abort loudly on absent inputs, so they are ready; the drive/flow wiring is a follow-on matter. The A5 chain in the golden run therefore exercises the five run-books in flow order rather than a timer-triggered flow.
