# DR-CMD-057 — Production-tools build AUTHORIZED (O1)

- **Status:** authorized (disposition)
- **Date:** 2026-09-23 ~20:21 PDT (selection); build completed 2026-09-23
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held; the build ran undiminished)
- **Disposition mode:** authorize
- **Matter:** *production-tools* — build authorization: **O1**, authorize the build stage for all eight executor tools at once against the adopted spec (DR-CMD-056), with mechanical verification as the acceptance bar — because DR-CMD-055 authorized the spec stage, DR-CMD-056 adopted the spec as the build contract after a full pre-adoption check, the registry contract's conditions (F2(a), World→system mapping, failure-record schema, subprocess scope, per-tool idempotency with commit-accretion first, R1/R2/R3/R5, A5) are all build-verifiable, and coupling the eight tools into one build is safe against a settled contract.

## Decision

**AUTHORIZED (build)** — the eight production tools are built against the adopted spec as dist-shipped `lib/dsys/tools/` modules:

- `tool-fetch-feed` (`fetch_feed.py`) — the sole scoped network touch (DR-CMD-055 F2(a)); bounded 30s GET of the operator-pinned feed; no default feed URL — missing pin aborts.
- `tool-compare-versions` (`compare_versions.py`)
- `tool-verify-checksum` (`verify_checksum.py`)
- `tool-read-policy` (`read_policy.py`) — pins exactly what it read into `ctx_delta` (F-E2, G6 Q5 answered)
- `tool-invoke-installer` (`invoke_installer.py`) — spawns `install.sh` bounded at 600s; does not record `installed_version` (installer convergence owns that)
- `tool-run-doctor` (`run_doctor.py`) — non-strict posture, CLI default; `doctor_ok` true iff no check fails
- `tool-record-promotion` (`record_promotion.py`) — version restricted to `[A-Za-z0-9._-]+`
- `tool-commit-accretion` (`commit_accretion.py`) — built and verified **first** per the DR-CMD-055 condition; K1 watermark re-check before writing makes crash re-invocation non-duplicating; git author identity via `-c` flags (envelope, never replay identity — K1 D5)

Support: `lib/dsys/tools/_common.py` (I-31 `i31_pinned_registry`, importable by a future referee; enforcement in `init`/`advance` remains future work, as spec §7 states). Verification: `lib/dsys/tools/_production_tools_golden_run.py`.

**Not authorized by this disposition:** committing the build (commit needs Peter's explicit word — a chat response is not authority); pushing (separate explicit authorization); the flow-driver/drive wiring follow-on (see the integration note, stated not bridged); any build outside the adopted spec.

## Build evidence (mechanical, 2026-09-23)

- **`_production_tools_golden_run.py` RESULT: PASS — 73 cases, 0 violations** (exit 0; re-run by the transcriber at record time — held green). Sections: A commit-accretion first (D3 wrong-identity refusal, watermark crash-recovery, append-only), B release-check (checksum-tamper refusal, network-disabled → `retry:3` → abort), C policy gate, D installer, E doctor + promotion, F replay (tools never reinvoked — R1), G I-31 pinned-registry predicate, H the five-run-book chain in flow order (A5 acceptance).
- Existing suites all green (builder's report): bridge drift guard holds (byte-for-byte on run-book specs + tool ids), updater, main, drive-contract, scenario-sim, acquisition, `tests/test-executor-driver.py` 13 passed.

## As-built deltas (recorded, not bridged — spec §11)

The spec's §11 ("As-built (build DR-CMD-057, 2026-09-23)") records nine deltas pinned by the golden run: feed document JSON format (self-describing content hash), tool timeouts (30s/600s/120s), no default feed URL, direct `updater:` config parsing, promotion version restriction, doctor posture, commit-accretion's seven build-settled details (accretion-path resolution, event-log channel precedence, watermark walk past installer snapshots, initial watermark −1, `accretion/<payload_hash>.json` path, `source_state` from the file channel, `commit_authority` defaulting to `standing`), and I-31's implementation location.

**Stated, not silently bridged** (spec §11, item 9): the built executor's flow driver does not yet seed the committing child's `ctx` (`flow_run_id`, `event_range`, `drive_identity`, `commit_authority`), inject `_commit_input`, or propagate an accumulator into child runs — each child starts with empty `ctx`. The tools accept both event channels and abort loudly on absent inputs, so they are ready; the drive/flow wiring is a follow-on matter. The A5 chain therefore exercises the run-books in flow order rather than a timer-triggered flow. The 7b acceptance stands: a drive with production tools gets past `checking`.

## State

Authorized bytes: `doc/production-tools-spec.md` sha256 `1fdaadca8ceb8939…` (adopted at `8b7f70e000343d9b453bc0da707a23542597b925d7e51723f9f80aa1ff8de40a` under DR-CMD-056; the delta is the §11 as-built record — the standing form for build deltas). Ten new modules under `lib/dsys/tools/` (~1,818 lines incl. the golden run).

**The tree is UNCOMMITTED at disposition** (Peter authorized the build only): DR-CMD-056's two files (spec + record), this record, the spec's §11, the ten new tool modules + golden run, and the matter-doc update below. Commit and push return as follow-on dispositions. Next disposition identifier: DR-CMD-058.
