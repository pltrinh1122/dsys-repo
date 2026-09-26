# DR-CMD-088 — author-agent containment J-calls ratified

- **Status:** ratified
- **Date:** 2026-09-26 ~14:51 PDT
- **Matter:** Ratification of the three judgment calls from DR-CMD-086
  (author-agent execution containment, spec'd/built under Peter's
  "ratify: C" selection — venv + subprocess discipline).

## Disposition

Peter rendered "ratify as recommended" (~14:51 PDT 2026-09-26) on
J-C1, J-C2, and J-C3. The containment matter (Half 1a of the falsified
"contained and invocable via CLI" claim) is now **ratified as built**.

## Ratified as built

- **J-C1 — venv: harness-managed.** `ensure_venv` owns creation,
  hash-pin verification, and drift-reinstall; the venv lives outside
  the repo (`~/.dsys/author-venv`) as infrastructure; it never falls
  back to the ambient environment. The operator-run creation script
  alternative stays declined (manual step, drift risk).
- **J-C2 — source tree: copy-in.** The contained process's world is the
  scratch copy, hash-pinned (`tree_sha256` in the run record) —
  structural isolation plus replayable bytes. The live-tree
  "read-only" alternative stays declined: unenforceable without OS
  support, and the live tree can mutate mid-run.
- **J-C3 — seam: reconciled under the channel layer.** The file seam
  (`commission.json` in, `result.json` out) is process-level transport
  *beneath* the ratified DR-CMD-087 channels, not a second ingress
  path: drive commissions derive from AP-A3-admitted log commissions,
  and contained verdicts flow back into the live log where AP-E2
  (`read_results`) reads them. J-CH1's one-ingress-gate holds across
  the seam because the contained drive runs the ratified `drive_one`,
  which refuses unstaged work.

## Honesty finding (recorded, not bridged)

During the DR-CMD-086 build, the first escape probe **succeeded**: the
audit-hook shim placed at the scratch root never loaded, because for
`python -m` the cwd reaches `sys.path` only after `site` imports
`sitecustomize` — the scratch-root shim lost to the stdlib's. The
shim was moved to `<scratch>/pkg/sitecustomize.py`, where PYTHONPATH
points, and the K1–K6 battery re-ran green (6/6, twice). The finding
is preserved unbridged in the containment spec (§ as-built findings);
the build was fixed, not the test.

## Resulting architecture

One contained execution story, end to end: the operator commissions
through the single AP-A3 ingress gate (DR-CMD-087); the launcher
(`core/package/author_contain.py`) provisions the harness-managed venv
and a per-run scratch dir, copies in the hash-pinned source tree, and
launches the contained entry point as a subprocess with scrubbed env,
cwd pinned to scratch, wall-clock timeout, and captured I/O; the
in-scratch audit hook refuses with reasons any write outside scratch,
subprocess spawning, or network use; `commission.json` in,
`result.json` out; contained verdicts are adopted into the live log by
the parent (`adopt_verdict_records` — contained proposes, parent
disposes; proposer != disposer). Zero inference inside the scratch.

Guarantees held: no existing file modified (new files only); no new
contracted tools; the ratified factory tree untouched (183 baseline
byte-held); nothing committed, nothing pushed.

## Verification (as built, unchanged by this ratification)

Containment golden 6/6 twice consecutively (env scrub, cwd/tmpdir/home,
write-refusal, timeout quarantine, wright replay byte-identical 1031
bytes `verified`, synthetic round trip adopted verbatim); factory
golden 183 passed / 0 violations; agent-behavior, author-agent,
archetype, bridge, updater, drive-contract, acquisition, PVB-workflow,
scenario-sim, playbook golden runs all green.

## Status updates

- `doc/author-agent-containment-spec.md`: IMPLEMENTED (DR-CMD-086) →
  **RATIFIED** (DR-CMD-088).
- `doc/decision-records/DR-CMD-086-author-agent-containment.md`: status
  → ratified-under-088 (body preserved as historical record).

Next free identifier: DR-CMD-089 (DR-CMD-059 still reserved for PVB
DoD).
