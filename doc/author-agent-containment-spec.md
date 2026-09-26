# Author-Agent Execution Containment — Specification

Status: RATIFIED (DR-CMD-088). Matter: Half 1 of the falsified
"contained and invocable via CLI" claim — the containment half.
Ratified choice: **C — venv + subprocess discipline**
(Peter, "ratify: C", 2026-09-26; J-C1/J-C2/J-C3 ratified "as
recommended", 2026-09-26).

## 1. Glossary

**Containment.** The boundary around author-agent *execution*
(the harness, factory driver, and diagnostics runner — never the
authoring inference, which stays outside per DR-CMD-083 J0). Containment
answers: *where* did this run, *on what inputs*, and *what could it
touch*.

**venv.** A Python virtual environment: an isolated `site-packages`
directory plus an interpreter shim. A venv isolates *packages*
(dependencies), not *effects* (filesystem, processes, network).

**Subprocess discipline.** Running the contained entry point as a child
process with: cwd pinned to a per-run scratch dir, environment scrubbed
to an explicit allowlist, wall-clock timeout, all stdio captured. The
execution boundary — cooperative, not an OS sandbox (see §4).

**Scratch dir.** A per-run directory (`runs/contain-NNNN/`, gitignored)
holding the commission, the copied source tree, the audit-hook shim,
and the run's outputs. The contained process's whole world.

**Copy-in.** The source tree (`core/`) is copied into the scratch dir
before the run, and the contained process imports from the copy. The
copy is hash-pinned (`tree_sha256` in the run record).

**Audit hook.** A `sys.addaudithook` installed at interpreter startup
(via `sitecustomize.py` placed where `PYTHONPATH` points) that
*refuses with reasons*: filesystem writes outside the scratch dir,
subprocess spawning, and network use. Reads anywhere are allowed.

**Hermetic replay.** Re-running the same pinned inputs produces
byte-identical outputs. The containment's primary guarantee.

**Audit boundary.** The recorded claim "this ran inside, on these
inputs": the run record pins commission bytes, tree bytes, venv
packages, and the result.

**Authored-not-adversarial.** The threat model (§4): contained code is
authored by the verified wright and gated by the factory verifier. It
may be *buggy*; it is not *hostile*.

**Cooperative discipline.** Enforcement that works because the contained
code cooperates at the interpreter level (it does not try to evade the
audit hook). Sufficient for authored-not-adversarial; insufficient for
adversarial code — which is an explicit non-goal.

**Seam.** The containment boundary's process-level I/O: commission in
(`commission.json`), results out (`result.json`). It is the *transport*
for the ratified channel layer (DR-CMD-085/087): a drive commission is
derived from an AP-A3-admitted log commission, and contained verdicts
flow back into the live log where AP-E2 (`read_results`) reads them.
The seam is not itself a principal/world channel — it sits below the
channel layer, carrying channel payloads across the subprocess
boundary.

**Quarantine.** Timeout/crash partial outputs: recorded in the run
record, never adopted as results.

**Run record.** The parent-side record of a contained run: spec
version, inputs (hashes), result, stdio, quarantine if any. Everything
except `run_local` (scratch path) is deterministic.

## 2. Decision

The /pb-decide offered three hosts for author-agent execution:

- **A — venv alone.** Rejected: a venv isolates packages, not effects.
  Dependency hermeticity without an execution boundary.
- **B — Docker.** Declined: real OS isolation, but heavyweight (daemon,
  builds, latency) and contradicts the ratified installer non-goal
  ("no Docker v1", DR-CMD-056/057 arc). The threat model
  (authored-not-adversarial) does not justify overturning it.
- **C — venv + subprocess discipline (RATIFIED).** The venv gives
  dependency hermeticity (hash-pinned requirements); the subprocess
  discipline gives the execution boundary (scratch cwd, scrubbed env,
  timeout, captured stdio, audit hook). No new dependencies, no
  non-goal violation, matched to the actual threat.

## 3. Architecture

### 3.1 venv (J-C1: harness-managed)

`author_contain.ensure_venv()` creates `~/.dsys/author-venv` on first
use (outside the repo: infrastructure, not content) and installs
`core/package/author_requirements.txt` with `--require-hashes` — every
wheel verified against its recorded sha256. On later runs it verifies
installed pins against the requirements file and reinstalls on drift;
a contained run never falls back to the ambient interpreter. The
venv's path, interpreter version, and package versions are fingerprinted
into every run record.

Only third-party dependency of the contained path: `pydantic`
(plus its transitive deps). Everything else is stdlib.

### 3.2 Subprocess discipline

`author_contain.run_contained(commission, ...)`:

1. Ensures the venv; builds the scratch dir (`runs/contain-NNNN/`).
2. Writes `commission.json`; copies the source tree in (§3.3); writes
   the audit-hook shim (§3.4); creates `tmp/` and `home/` inside scratch.
3. Launches `<venv-python> -m core.package.author_contained_entry`
   with cwd=scratch, the scrubbed environment (§3.5), `timeout=timeout_s`
   (default 120s), all stdio captured.
4. On success reads `result.json`; on `TimeoutExpired` kills the child
   and quarantines partial stdio (recorded, never adopted).

### 3.3 Source tree: copy-in (J-C2)

The whole `core/` tree (~1.6M; `__pycache__`/`*.pyc` excluded) is
copied to `<scratch>/pkg/core/`, and the contained process imports
from the copy (`PYTHONPATH=<scratch>/pkg`). The authored modules'
absolute-import convention (`from core.package.…`, DR-CMD-083) resolves
to the copy without modification.

Adopted over read-only-mount-of-live-tree because: (a) read-only cannot
be enforced without OS support the project declined (Docker); (b) the
live tree can mutate mid-run, breaking hermeticity; (c) copy-in makes
"the process's world is the scratch copy" *structural*, with the audit
hook as defense-in-depth for absolute-path escapes. The copy is
hash-pinned: `tree_sha256` (sorted relative paths + bytes) is recorded
in the run record, so a replay copies — and verifies — the same bytes.

### 3.4 Audit hook

`<scratch>/pkg/sitecustomize.py` (source:
`core/package/author_contain_sitecustomize.py`) installs a
`sys.addaudithook` at interpreter startup. It refuses with reasons
(`ContainmentRefusal`, a `PermissionError`):

- filesystem writes outside the scratch dir: `open` for write/append/
  exclusive/create, mkdir/makedirs, unlink/remove/rmdir,
  rename/replace, symlink/link, truncate, mkfifo/mknod — resolved via
  `os.path.realpath`, so `..` and symlink escapes are covered;
- subprocess spawning (`subprocess.Popen`, `os.system`, `os.spawn*`,
  `os.fork*`, `os.exec*`);
- network use (`socket.*`).

Reads anywhere are allowed (the interpreter reads the venv, stdlib,
`/proc` outside scratch). As-built note: the shim MUST live where
`PYTHONPATH` points, not in the scratch root — for `python -m`, cwd
reaches `sys.path` only after `site` has already imported
`sitecustomize`, so a scratch-root shim loses to the stdlib's own
(`apport`) sitecustomize and never loads. `PYTHONPATH` precedes the
stdlib on the startup path.

### 3.5 Scrubbed environment (allowlist)

Exactly: `PATH=/usr/bin:/bin`, `PYTHONPATH=<scratch>/pkg`,
`PYTHONHASHSEED=0` (deterministic ordering), `PYTHONDONTWRITEBYTECODE=1`,
`TMPDIR=<scratch>/tmp` (stdlib temp files land inside scratch),
`LANG=C`, `LC_ALL=C`, `TZ=UTC`, `HOME=<scratch>/home`,
`AUTHOR_CONTAIN_SCRATCH=<scratch>`. Nothing is inherited — a planted
ambient-only variable is invisible inside (golden K1).

### 3.6 Contained entry and modes

`core/package/author_contained_entry.py` reads `commission.json` and
writes `result.json` (sorted keys — deterministic). Modes:

- `probe`: report environment facts (containment self-test).
- `drive`: run the ratified factory-driver pipeline (`drive_one`) on
  the scratch authored root; verdict records are *proposed* in the
  scratch log — the parent adopts them into the live log via
  `adopt_verdict_records` (re-seq; proposer != disposer).
- `attempt_write`: try `open(path, "w")` outside scratch (golden K3).
- `hang`: sleep (timeout golden K4).

### 3.7 Seam (reconciled with DR-CMD-085/087)

Commission in: `commission.json` (mode + drive parameters, or probe
payload). Results out: `result.json` (verdict records or environment
facts). Reconciled against the ratified channel architecture:

- The channel layer (085/087) operates at the *log* level:
  principal-afferent is the staged commission queue (AP-A3 canonical,
  J-CH1), principal-efferent is `read_results` (AP-E2).
- The seam operates at the *process* level, underneath it: a drive
  commission names a staged build-request already admitted through the
  AP-A3 gate, and the contained verdicts are adopted back into the live
  log where AP-E2 reads them.
- J-CH1's "one ingress gate" holds across the seam: the contained drive
  runs the ratified `drive_one`, which refuses unless the staged bytes
  match the pinned sha256 and the commission exists in the log. The
  seam adds no second ingress path — it cannot build what staging did
  not admit.

The adopted channel vocabulary (AP/AW/E codes, "afferent–efferent
triad" — J-CH2, ratified, disposing the DR-CMD-069 open item) is not
re-stated here; this spec uses it as settled.

## 4. Threat model

Contained code is **authored-not-adversarial**: written by the verified
wright (staff, stage-only, D5 0.0), gated by the factory verifier
(archetype gate → validate → compile → verify) before its diagnostics
ever run. It may be buggy — a diagnostic may `open()` the wrong path,
loop forever, or leak ambient state. It is not trying to evade the
hook, escalate, or exfiltrate.

Containment therefore buys, honestly:

- **hermetic replay**: pinned commission + pinned tree + pinned venv →
  byte-identical results (golden K5);
- **repo-tree protection**: buggy writes land in scratch or are
  refused with reasons (golden K3);
- **an audit boundary**: the run record states what ran, on what, with
  what result — "this ran inside, on these inputs".

**Non-goal: sandboxing adversarial code.** An interpreter-level hook
cannot stop a deliberately evasive same-user process. That would be
Docker (declined, §2). The spec states this plainly so no reader
mistakes cooperative discipline for a security boundary.

## 5. Judgment calls

- **J-C1 — venv setup: harness-managed (adopted).** `ensure_venv`
  owns creation, pin-verification, and drift-reinstall; the venv is
  infrastructure at `~/.dsys/author-venv`, outside the repo.
  Alternative — operator-run creation script: declined (manual step,
  drift risk, less deterministic).
- **J-C2 — source tree: copy-in (adopted).** Structural isolation +
  hash-pinned replay (§3.3). Alternative — run against the live tree
  "read-only": declined (unenforceable without OS support; live tree
  mutates mid-run).
- **J-C3 — seam: file-based process transport, reconciled.** The
  `commission.json` / `result.json` seam stands as the process-level
  transport *under* the ratified channel layer (085/087, §3.7) — not a
  competing channel, and not a second ingress path. The boundary's-only-I/O
  invariant is kept: every crossing passes the AP-A3 gate (via
  `drive_one`'s staging checks) on the way in and the live log (via
  AP-E2) on the way out.

## 6. Verification

`core/package/author_contain_golden_run.py` — 6/6, twice consecutively:

- **K1** env scrub: planted `DSYS_CONTAIN_TEST_CANARY` invisible;
  contained env exactly the allowlist.
- **K2** probe: cwd == scratch; tmpdir and home inside scratch.
- **K3** write outside scratch refused (`ContainmentRefusal: write
  outside scratch refused: '/tmp/author-contain-escape-probe'`); no
  file created.
- **K4** timeout: hanging workload killed at 3s; partial stdout
  quarantined (recorded, not adopted); no result consumed.
- **K5** two contained wright drives → `result.json` byte-identical
  (1031 bytes), verdict `verified`.
- **K6** round trip: synthetic staff+office agent driven in
  containment → `verified`; contained verdict adopted into a live log
  verbatim (fresh seq) — proposer != disposer across the boundary.

Existing suites (all green, unchanged): factory golden **183 passed**,
agent-behavior golden ok, author-agent golden ok, archetype self-test
ok, bridge / updater / drive-contract / acquisition / PVB workflow /
scenario-sim / playbook golden runs ok (rc=0).

As-built findings (recorded, not bridged): (1) the sitecustomize
placement rule (§3.4) — discovered when K3's write succeeded because
the stdlib sitecustomize shadowed a scratch-root shim; (2)
`TimeoutExpired` carries raw bytes even with `text=True` — the
launcher decodes quarantine output explicitly.

## 7. Files

- `core/package/author_contain.py` — launcher (venv, scratch,
  subprocess, run records, adoption).
- `core/package/author_contained_entry.py` — in-scratch entry
  (probe/drive/attempt_write/hang).
- `core/package/author_contain_sitecustomize.py` — audit-hook source
  (copied to `<scratch>/pkg/sitecustomize.py`).
- `core/package/author_requirements.txt` — hash-pinned dependencies.
- `core/package/author_contain_golden_run.py` — K1–K6.
- `doc/author-agent-containment-spec.md` — this spec.
- `doc/decision-records/DR-CMD-086-author-agent-containment.md`
