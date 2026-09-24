# DR-CMD-056 — Production-tools spec ADOPTED (build contract)

- **Status:** authorized (disposition)
- **Date:** 2026-09-23 ~20:20 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held; the check ran undiminished)
- **Disposition mode:** authorize
- **Matter:** *production-tools* — spec adoption: `doc/production-tools-spec.md` (the spec stage authorized by DR-CMD-055) adopted as the contract against which the eight executor tools are built (`tool-fetch-feed`, `tool-compare-versions`, `tool-verify-checksum`, `tool-read-policy`, `tool-invoke-installer`, `tool-run-doctor`, `tool-record-promotion`, `tool-commit-accretion`), because the spec was checked against every DR-CMD-055 spec-stage condition before adoption and covers them all, and the A4 gate (spec before build) is the standing guardrail.

## Pre-adoption check (2026-09-23, before the disposition)

The spec was checked against DR-CMD-055's spec-stage conditions:

- **F2 as (a):** applied — §2 states the scoped exception verbatim ("no network in the executor or tools, except the release-check poll (updater-spec §5 P2), whose result enters only as external trigger payload"), confined to `tool-fetch-feed`.
- **World→system interface mapping per tool:** §4, per tool — incl. `w.surfaced` → the disclosure outbox `var/disclosures/`, and the installed-version source via `DSYS_HOME`.
- **Failure-record schema on the disclosure path:** §5 — `step_failed: {step_seq, tool, error, malformed}` with the built executor's abort-reason preservation (F1c).
- **Subprocess scope against §8:** §2 — "tools run in-process" governs invocation (importlib-loaded, `run(ctx)` called in the executor's process), not what a tool may spawn; `install.sh` and `git` explicitly permitted (F1d).
- **Per-tool idempotency arguments (F-E3):** §4, commit-accretion first — the watermark re-check makes crash re-invocation non-duplicating.
- **R1 replay:** §6 — replay never reinvokes tools; the poll result is recorded data.
- **R2 golden runs:** §9 — nine cases incl. the checksum-tamper refusal, the D3 wrong-identity refusal, and the network-disabled → `retry:3` → abort path.
- **R3 (I-31 candidate):** §7 — every step's tool resolves to the pinned release's registry.
- **R5 trust declared:** §8 — the feed-URL pin in operator config, transport trust.
- **A5 acceptance:** §9 — the 7b case becomes the acceptance (a drive with production tools gets past `checking`).
- **Self-containment:** the document carries a Glossary defining every acronym and specialized term inline.

One inconsistency was found and resolved before adoption: the run-book step-count line ("six run-books, nine steps") under-counted the table's bindings; the line now states the table's count ("six run-books, eight tool steps, eight tools"). No unsupported interface assumptions survived; the executor's `load_tools` contract and `DSYS_HOME` resolution (C4) are cited from built work, not asserted.

## Decision

**ADOPTED** — `doc/production-tools-spec.md` is the build contract for the eight production tools. Adoption only: the tools are not authorized to be built by this disposition.

**Not adopted:** the eight tool builds (no build work was done — the tree carries the spec only); any build-stage mechanism not in the spec.

**The build stage is not authorized; it returns as a follow-on disposition (no reframing needed — this spec is its terms of reference).**

Adopted bytes: `doc/production-tools-spec.md` sha256 `8b7f70e000343d9b453bc0da707a23542597b925d7e51723f9f80aa1ff8de40a` (spec stage completed 2026-09-23; working tree, uncommitted at disposition). Next disposition identifier: DR-CMD-057.
