# DR-CMD-101 — bootstrap loop closed: `rb-profile-build` run-book (wiring, not an agent)

- **Status:** adopted (built per Operator disposition; no as-built deviation)
- **Date:** 2026-09-27 ~18:40 PDT
- **Matter:** "Close the gap per analysis."
  Separator: Peter (operator default, designated at START; proposer =
  ambient agent, so external separation holds — not rehearsal).

## Disposition

Peter rendered "close the gap per analysis" (~18:40 PDT 2026-09-27),
implementing the just-completed falsification of the builder-agent
claim: no `builder` agent is to be designed or built; the real gap — the
unclosed bootstrap loop (commission → wright authors → factory driver
builds → staging for disposition), previously closed by hand-driven
ambient subagents — is closed with wiring. The wiring is
`rb-profile-build`: a strictly-sequential run-book
(`core/package/rb_profile_build.py` + `core/package/rb_profile_build_golden_run.py`)
that consumes a build-request and drives the factory pipeline
end-to-end. No new agent profile, no wright runtime, no tool invented,
J1 untouched.

## Background: the falsification it implements (condensed)

Peter proposed: "for the bootstrapping process, we need to design and
build a `builder` agent first." Falsified on three grounds:

1. **Empirical.** The bootstrap already runs without one — three clerk
   profiles designed, authored, and gated in one day; exemplars 7→9; DRs
   092→100. "Needed first" is falsified by done-without.
2. **No gap.** The role is filled twice: wright authors (drafts profile
   modules, stages build-requests — staff+office, never disposes), the
   factory driver builds (validate→compile→verify), ambient subagents
   supply labor. No unfilled gap was named.
3. **Inversion.** A builder is a *product* of bootstrapping, not its
   precondition — and a may-act builder running before governance is the
   hazard, not the bootstrap. Gates-then-builders is the safe order, and
   is what we did (DR-CMD-069, then the factory, then profiles).

The steelmanned residue: the loop needs *closing* — commission → wright
authors → factory driver builds → staging for disposition as one
orchestrated flow rather than hand-driven subagents. That is wiring, not
a profile. (Fourth instance of the day's pattern, after the router, the
clerk-monitor, and the dedicated schema registrar: new-agent proposals
collapsing into wiring, scoping, or an existing role.)

## Why a run-book and not an agent

- DR-CMD-064 Q2-B: flows for the factory's own build pipeline (step-5
  implementation). This run-book is that pipeline's executable unit; a
  flow wrapper is future work if disposed, not built here.
- v1 commitments: run-books strictly sequential; zero inference inside
  execution; deterministic replay mandatory. The loop-closing is
  mechanical driving, not judgment — an agent would smuggle discretion
  into exactly the place the architecture keeps discretion out of.

## Design

**The seam (load-bearing).** The wright's defined output is a staged
*build-request* for the factory driver. The run-book's input contract IS
that build-request:

    {commission_ref, profile_name, authored_module_bytes, content_hash,
     declared_archetypes}

**Six steps, fail-closed at every gate** (refusals staged with exact
reasons, never worked around):

1. **RECEIVE** — accept the injected build-request; sha256 over the
   authored bytes must equal `content_hash` (tamper → refuse,
   fail-closed — the verified-build hash-pinning precedent). The
   module's own `ARCHETYPES` must agree with `declared_archetypes`
   (charter disagreement → refuse). Builder resolved as
   `<profile_name>_profile`.
2. **VALIDATE** — construct via the builder; build-time personalization
   binding (DR-CMD-070; `principal_id="factory-build-time"`,
   `disposition_ref="commission:<commission_ref>"`, gate=None — the
   archetype gate is the run-book's own step 3 by design); zero
   warnings; revalidation.
3. **GATE** — `check_profile` over `declared_archetypes`; violations →
   refuse with exact strings.
4. **COMPILE** — `compile_profile`; `CompileRefused` → refuse with the
   EXACT reason string. This is where honesty is tested.
5. **VERIFY** — factory verifier; anything but verified+operable →
   refuse with verdict and failure reason.
6. **STAGE** — all green → stage content hashes + full build transcript
   for Operator disposition, labeled NOT published / NOT registered /
   NOT disposed. The run-book never publishes, registers, or disposes.

**Entities** follow the updater.py convention: `RunBook`/`Step`/`Tool`
entities (`rb-profile-build-s1..s6`, expr `"True"`, unconditional —
strictly sequential), a `TOOLS` dict, and `drive_build(build_request)`
→ transcript. The transcript is canonical JSON (no timestamps, no temp
paths, no randomness): same build-request bytes → byte-equal transcript.

**Honest boundaries (not bridged):**

- The wright side stays ambient labor. No wright runtime exists; the
  run-book does not invoke one and does not invoke any LLM. The
  authored bytes arrive as an injected discrete step-change (the v1
  commitment), labeled as such. The wright-invocation half of the loop
  remains open work — recorded, not built.
- As-built: authored bytes execute in-process (`exec` in a fresh
  namespace, no `sys.modules` pollution). This is the recorded open
  gap "contain proposed authored code during stage-profile" — same
  trust posture as today's hand-driven builds; containment is NOT
  claimed.
- The build-time binding is not a deployment personalization: it
  satisfies DR-CMD-070's compiler contract while keeping the gate as
  the run-book's own step. The `commission_ref` is the Operator
  disposition authorizing the build (dispositions are never invented).
- Profile-level `diagnostic_cases()` (e.g. the triager's T-D1..T-D8)
  are authoring-time checks; the pipeline-time check is the factory
  verifier (step 5).

## Verification (acceptance criteria were provisional until Peter ratifies)

1. **Golden run green, refusal reasons exact** (`rb_profile_build_golden_run.py`,
   7 cases, `ok: true`):
   - B-1/B-2/B-3: registrar_clerk, triager, dr_registrar build-requests
     refuse at COMPILE (s4) with reasons byte-equal to the
     direct-compile oracle AND to the DR-CMD-096/097/100 literals:
     `compile refused at routing: write-scope channel 'artifact-registry' …`,
     `… 'quarantine' …`, `… 'decision-record-registry' …` (each suffixed
     `names no registered contracted tool or alias (B-3 analog)`).
     Receive/validate/gate pass first — the profiles are well-formed;
     only the channel is missing. The deviation class is handled
     honestly, never routed around.
   - B-4: wright (clean) runs RECEIVE→STAGE, all six ok,
     verify=verified+operable (23 static, 10 probes); staged bundle
     carries content/profile/plan/artifact hashes and the
     not-published/not-registered/not-disposed disclaimer.
   - B-5: tampered bytes (hash mismatch) refuse at RECEIVE — one step
     total, no code executed.
   - B-6: builder yielding `conflict_rule="commission_wins_ties"` (the
     DR-CMD-093 D2 correction) refuses at VALIDATE with the pydantic
     reason.
   - B-7: staff-declared module with a may-act (triager) shape validates
     then refuses at GATE with the exact oracle strings
     (`[staff/S1]…`, `[staff/S2]…`, `[staff/S4]…` — the DR-CMD-096
     negative control, reproduced mechanically).
2. **Deterministic replay:** two runs on the same bytes → byte-equal
   transcripts, in-process and cross-process (golden-run outputs diff
   clean across processes).
3. **Zero inference:** `drive_build` is a pure function of the
   build-request — no LLM calls, no ambient discretion, no network, no
   timestamps in the transcript path. (The verifier was separately
   confirmed deterministic: two runs, identical verdict records.)
4. **Existing suites unaffected:** set-001 7/7 verified; set-002 2/2
   verified; archetype self-test ok (9 exemplars, zero violations,
   negative controls); factory golden run 192 passed.
5. **No new agent profile, no wright runtime, no tool invented, J1
   untouched.** `git status` shows only the two new files (plus the
   pre-existing uncommitted work); nothing committed or pushed.

## Consequences

- The bootstrap loop is closed at the contract level: any future
  profile build goes commission → (ambient) wright authorship →
  build-request → `rb-profile-build` → staged-for-disposition, with
  every refusal loud and exact.
- The three clerk profiles' compile refusals are now regression-pinned:
  if contracted tools ever land for their channels, B-1..B-3 will flip
  from refused-at-COMPILE to staged — the golden run detects the
  unblock mechanically.
- `CLERK.members` remains `()`; registration still awaits the
  consolidated tool-channel disposition (DR-CMD-096/097/100).

## Uncertainties (G6)

- The wright-invocation half (commission → authored bytes) is still
  ambient labor; closing it mechanically (a wright runtime or a
  governed authoring flow) is undisposed future work.
- Whether `rb-profile-build` should gain an AutomatonFlow wrapper per
  DR-CMD-064 Q2-B, or stay a bare run-book, is undisposed.
- The in-process `exec` containment gap stays open (pre-existing,
  now also covering this run-book).

## Premises

- DR-CMD-064 (Q2-B: flows for the factory's own build pipeline),
  DR-CMD-069 (archetype as checked authoring constraint),
  DR-CMD-070 (build-time personalization binding),
  DR-CMD-096/097/100 (the three clerk routing refusals, verbatim),
  DR-CMD-028 (pydantic-as-source), the v1 run-book commitments
  (strictly sequential, zero inference, deterministic replay).
- Code: `core/package/rb_profile_build.py` (new),
  `core/package/rb_profile_build_golden_run.py` (new);
  exercised against `core/package/factory_compiler.py`,
  `core/package/factory_verifier.py`,
  `core/package/factory_archetypes.py`, and the authored fixtures
  `registrar_clerk.py`, `triager.py`, `dr_registrar.py`, `wright.py`.

Next free identifier: DR-CMD-102 (DR-CMD-059 still reserved for PVB DoD).
