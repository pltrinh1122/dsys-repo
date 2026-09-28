# DR-CMD-103 — `tool-register-artifact` built (tranche 1)

- **Status:** built-and-verified (adoption of the build was DR-CMD-102;
  registration of `registrar_clerk` is a separate pending disposition)
- **Date:** 2026-09-27 ~18:55 PDT
- **Selector:** Peter (operator; Peter rendered "proceed as recommended"
  ~18:52 PDT on the DR-CMD-102 /pb-decide, commissioning tranche 1)

## Commission

DR-CMD-102 adopted O1 tranched: tranche 1 — build the contracted
`tool-register-artifact` now, per DR-CMD-055 tool discipline. Tranche 2
(triage channels, DR registration channel) is conditional and was
explicitly NOT commissioned; it is not built here.

## What was built

`tool-register-artifact`: the contracted write channel for the
content-addressed append-only artifact registry
(`core/package/artifact_registry.py`, DR-CMD-091). Given artifact bytes
plus metadata, it computes the content hash, appends to the registry,
and returns a receipt. Duplicate content-hash returns the existing
receipt — no second row, no tip advance (DR-CMD-099's no-duplicate-hash
criterion, made mechanical). Append-only: never overwrites; new bytes
for an existing `(kind, name)` become version N+1. Registration rests on
disposition: `disposition_ref` is required, and the registry's own
refusals (no-disposition, post-release-commission rule) are preserved
verbatim. Pure mechanical, deterministic, zero inference.

Per DR-CMD-055 discipline, three artifacts:

- Contract spec: `doc/tool-register-artifact-spec.md` (self-contained,
  glossary; inputs/outputs/refusals, idempotency argument, module-layout
  note, and the J1-addition point below).
- Implementation: `lib/dsys/tools/register_artifact.py`
  (`TOOL_NAME = "tool-register-artifact"`, `run(ctx)` returning the
  `{ok, result, ctx_delta}` envelope; loads through
  `executor.load_tools` like the eight production tools).
- Dedicated golden run:
  `lib/dsys/tools/_register_artifact_golden_run.py` — 29 cases, PASS.

One additive registry helper, `find_by_sha256`, joined
`core/package/artifact_registry.py` so the tool can return the existing
receipt on duplicates. No existing registry behavior changed.

## J1 registration: addition, not amendment

- `tool-register-artifact` joined `AGENT_TOOL_IDS` in
  `core/package/factory_compiler.py`.
- New channel alias: `artifact-registry` → [`tool-register-artifact`],
  so `registrar_clerk`'s `write_scope=["artifact-registry"]` resolves at
  the routing stage.
- `TOOL_REGISTRY_PIN` recomputed from the id list automatically — the
  pin mechanism is the established path for membership changes. The J1
  discipline (channels resolve against the *closed* registry; unknown
  channels refuse loudly) is unchanged: the registry stays closed, it
  now has nine members. This is the addition O1 commissioned; O3
  (amending the discipline) was refused and is not what this is.
- No schema-enum or schema-field change, so no minor schema bump under
  the DR-CMD-082 rule; the pin digest captures the membership change
  inside `FactoryVersion`.

## Verification per criterion

1. **Tool golden run green:** 29/29 PASS — clean registration (receipt
   fields, one row appended); duplicate content-hash returns the
   existing receipt with no new row and no tip advance; new bytes for
   the same `(kind, name)` version append-only (v1 row intact); all
   eight malformed-input classes refused fail-closed; the
   post-release-commission refusal preserved verbatim (and a new
   commission honestly versions); the channel resolves through the J1
   registry; the tool loads by `TOOL_NAME` through the real
   `executor.load_tools` path; byte-identical receipts across fresh
   roots (determinism).
2. **B-1 flipped — the mechanical unblock:** `registrar_clerk` run
   through `rb-profile-build`'s `drive_build` now goes
   RECEIVE → VALIDATE → GATE → COMPILE → VERIFY → STAGE, all six steps
   ok, verify `verified`+`operable`, byte-equal transcripts across two
   runs. The DR-CMD-101 regression pin detected the unblock exactly as
   designed: the `rb-profile-build` golden run's B-1 expectation was
   updated from refused-at-COMPILE to staged (7/7 green), and B-1's
   prior byte-equal refusal assertion is retired as history.
3. **B-2/B-3 still refused, byte-equal:** `triager` and `dr_registrar`
   still refuse at COMPILE with reasons byte-equal to the
   direct-compile oracle and the DR-CMD-097/100 literals. Tranche 2 was
   not built; the deviation class stands for those two channels.
4. **Not registered:** the green build stages `registrar_clerk` for
   Operator disposition only — `CLERK.members` stays `()`,
   `PROFILE_SET_002` unchanged (`wright`, `registrar`). Registration
   is Peter's pending disposition.
5. **No regressions:** set-001 run ok, set-002 run ok, archetype
   self-test ok (9 exemplars, negative controls unchanged), factory
   golden run 192 passed, `rb-profile-build` golden run 7/7 green.

## Pending dispositions

- **Registration of `registrar_clerk`** — the profile is staged and
  green; adopting/registering it into set-002 and `CLERK.members` is
  Peter's call.
- **Tranche 2** — triage channels + DR registration channel, gated on
  (i) the DR-registry-structure disposition and (ii) demonstrated
  operational need (DR-CMD-102).

Nothing committed or pushed (branch `build/half1`; working tree carries
the build).

Next free identifier: DR-CMD-104 (DR-CMD-059 still reserved for PVB DoD).
