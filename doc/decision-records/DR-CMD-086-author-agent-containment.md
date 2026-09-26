# DR-CMD-086 — author-agent containment: spec'd and built (C ratified)

- **Status:** ratified-under-088 (Peter rendered "ratify as recommended"
  on J-C1/J-C2/J-C3, 2026-09-26 ~14:51 PDT; body preserved as
  historical record)
- **Date:** 2026-09-26 ~14:55 PDT
- **Matter:** Half 1a of the containment matter — execution containment
  for the author-agent. (Half 1b — afferent/efferent channels — was
  spec'd/built as DR-CMD-085 and its J-calls ratified as DR-CMD-087.)

## The selection

Peter rendered "ratify: C" (~14:44 PDT 2026-09-26) on the containment
/pb-decide: **C = venv + subprocess discipline**.

- A (venv alone) was rejected in the decide: dependency isolation only,
  no execution boundary.
- B (Docker) was declined: real OS isolation, but heavyweight and
  contradicting the ratified installer non-goal "no Docker v1"
  (DR-CMD-056/057 arc); the authored-not-adversarial threat model does
  not justify overturning it.

## What was built (new files only; nothing committed/pushed)

- `core/package/author_contain.py` — launcher: harness-managed venv
  (`ensure_venv`, `~/.dsys/author-venv`, `--require-hashes` install,
  drift-reinstall), per-run scratch (`runs/contain-NNNN/`, gitignored),
  copy-in of the source tree (hash-pinned), scrubbed-env subprocess
  launch with wall-clock timeout, run records, and
  `adopt_verdict_records` (contained proposes → parent disposes into
  the live log; proposer != disposer).
- `core/package/author_contained_entry.py` — in-scratch entry:
  `commission.json` in, `result.json` out; modes probe / drive /
  attempt_write / hang. Zero inference inside.
- `core/package/author_contain_sitecustomize.py` — audit-hook source,
  placed at `<scratch>/pkg/sitecustomize.py`: refuses with reasons
  (`ContainmentRefusal`) filesystem writes outside scratch,
  subprocess spawning, and network use; reads allowed.
- `core/package/author_requirements.txt` — hash-pinned deps
  (pydantic 2.13.5 + transitives; the only third-party dep on the
  contained path).
- `core/package/author_contain_golden_run.py` — K1–K6 battery.
- `doc/author-agent-containment-spec.md` — self-contained spec with
  Glossary (threat model, cooperative discipline, non-goals stated
  plainly).

## Judgment calls

- **J-C1 — venv setup: harness-managed (adopted).** Creation,
  pin-verification, and drift-reinstall owned by `ensure_venv`; venv
  lives outside the repo (`~/.dsys/author-venv`) as infrastructure.
  Alternative (operator-run creation script): declined — manual step,
  drift risk.
- **J-C2 — source tree: copy-in (adopted).** The contained process's
  world is the scratch copy — structural isolation, hash-pinned replay.
  Alternative (run against the live tree "read-only"): declined —
  unenforceable without OS support; live tree mutates mid-run.
- **J-C3 — seam: reconciled, not provisional.** The file-based process
  seam (`commission.json`/`result.json`) stands as the transport
  *under* the ratified channel layer (spec §3.7).

## Seam reconciliation with DR-CMD-085/087

The channel layer operates at the *log* level (AP-A3 staged commission
queue canonical per J-CH1; AP-E2 `read_results`); the containment seam
operates at the *process* level underneath it. A drive commission names
a build-request already admitted through the AP-A3 gate; contained
verdicts are adopted into the live log where AP-E2 reads them.
J-CH1's "one ingress gate" holds across the seam: the contained drive
runs the ratified `drive_one`, which refuses unless staged bytes match
the pinned sha256 and the commission exists in the log — the seam adds
no second ingress path. The adopted channel vocabulary (J-CH2) is used
as settled; the DR-CMD-069 vocabulary item is disposed.

## Verification (exact)

Containment golden **6/6, twice consecutively**: K1 env scrubbed to
allowlist (planted canary invisible); K2 cwd==scratch, tmpdir/home
inside; K3 write outside scratch refused with reasons, no file created;
K4 hanging workload killed at timeout, partials quarantined (recorded,
never adopted); K5 two contained wright drives → `result.json`
byte-identical (1031 bytes), verdict `verified`; K6 synthetic-agent
round trip → `verified`, contained verdict adopted verbatim (fresh
seq).

Existing suites all green, baselines held: factory golden **183
passed** / 0 violations, agent-behavior golden ok, author-agent golden
ok, archetype self-test ok, bridge / updater / drive-contract /
acquisition / PVB-workflow / scenario-sim / playbook golden runs ok.

As-built findings (recorded in the spec, not bridged): (1) the shim
must live where PYTHONPATH points — for `python -m`, cwd reaches
sys.path only after site imports sitecustomize, so a scratch-root shim
loses to the stdlib's; (2) `TimeoutExpired` carries raw bytes even with
`text=True` — the launcher decodes quarantine output explicitly.

## Guarantees

No existing file modified (new files only); no new contracted tools;
the ratified factory tree untouched (183 baseline byte-held); nothing
committed, nothing pushed. Next free identifier: DR-CMD-088
(DR-CMD-059 still reserved for PVB DoD).
