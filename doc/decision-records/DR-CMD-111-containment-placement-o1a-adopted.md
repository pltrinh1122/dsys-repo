# DR-CMD-111 — Build-path containment placement: O1a ADOPTED

- **Status:** adopted (selection among /pb-decide variants)
- **Date:** 2026-09-27 ~21:00 PDT
- **Selector:** Peter (operator; rendered "proceed with O1a"; proposer =
  ambient agent — proposer≠disposer held)
- **Disposition mode:** select (selection among /pb-decide variants)
- **Matter:** which containment placement to implement — O1a (narrow:
  exec + builder call in a supervised child, vetting stays ambient-side)
  vs O1b (whole `drive_build` in a supervised child) — decided on the
  outcome of the commissioned cheap experiment.

## Sequence

1. DR-CMD-110 commissioned the containment design spike. The spike
   (`doc/build-path-containment-design.md`) recommended O1b: run
   `drive_build` wholesale in a supervised child, relocating
   GATE/COMPILE/VERIFY into the child, on the claim that the vetting
   chain is "unchanged in *what* it checks" (§4).
2. /pb-decide framed O1b vs O1a vs both. The ambient's recommendation
   was O1a — contain what is arbitrary, witness what is deterministic —
   disagreeing with the spike on placement: O1b relocates the vetting
   chain into the process the commissioned bytes share, so a builder
   that mutates imported factory module state corrupts the vetting the
   transcript claims.
3. Peter asked whether runs could compare the designs. The ambient
   recommended the cheap adversarial experiment first (golden-suite
   green on both would discriminate nothing — table stakes); Peter
   rendered "proceed as recommended with cheap experiment".
4. The experiment ran: three arms, each in a fresh subprocess, repo
   untouched. See Premises.
5. /pb-decide re-run on the experiment outcome; Peter rendered
   "proceed with O1a".

## Premises (the experiment's exact observations)

Saboteur builder: two lines mutating
`factory_compiler.CHANNEL_ALIASES` in-process
(`CHANNEL_ALIASES["decision-record-registry"] =
["tool-register-artifact"]`), then returning an otherwise-valid
clerk-archetype profile whose write scope names
`decision-record-registry`.

- **Arm 0 — control (honest builder, co-located):** terminal
  `refused`, at step `rb-profile-build-s4` (compile), reason:
  `compile refused at routing: write-scope channel
  'decision-record-registry' names no registered contracted tool or
  alias (B-3 analog)`. Honest baseline confirmed.
- **Arm 1 — saboteur, co-located (= O1b's placement: builder and
  vetting share a process):** terminal `staged`, all six steps ok.
  The compile routing refusal was bypassed AND verify passed; the
  transcript is well-formed and claims staged. A parent relaying it
  (O1b's supervision shape) would have no way to tell.
- **Arm 2 — saboteur, split (= O1a's placement: builder in the child,
  parent revalidates the JSON profile and runs
  validate/gate/compile faithfully, including
  `bind_personalization`):** terminal `refused` at compile with the
  **byte-identical** honest reason to Arm 0. The identical attack is
  inert.

Verdict recorded from the experiment: the spike's §4 claim — the
vetting chain relocated into the child is safe because it is unchanged
in what it checks — is **falsified** for co-located execution. The
attack needs no compromised commission chain: any builder, buggy or
hostile, that mutates imported factory module state corrupts the
vetting it shares a process with. That is in-scope A1/A2, not
governance's problem.

## Disposition

Peter selected **O1a**. The placements dispose as follows:

- **O1a — ADOPTED for implementation.** Exec + builder call move into
  the supervised child; the profile crosses the boundary as JSON and
  is revalidated; GATE/COMPILE/VERIFY/STAGE stay ambient-side and
  witnessed. Its residual (hostile data-origin, revalidated by
  `model_validate`) is thin and was not breached in the experiment.
- **O1b — REFUSED.** The experiment demonstrated it fails *open with
  a well-formed transcript* — the worst failure shape in this
  architecture: a staged record the operator cannot distinguish from
  an honest one. The only repairs converge on separating the vetting
  from the builder's process, which is O1a's shape by another name.
- **"Both" — DECLINED in all forms.** Nested (O1a inside O1b) is
  redundant — O1b already contains everything O1a contains, so a
  second boundary buys nothing. Sequential (O1a now, O1b later) pays
  for the boundary twice and migrates the golden runs twice.
  Dual-execution (child runs the drive AND the parent re-derives the
  vetting, refusing on disagreement) is the only non-redundant form
  but is O1a's benefit at O1b's price plus a new agreement invariant,
  defending against out-of-scope or thin scenarios — disproportionate.

The spike's design document (`doc/build-path-containment-design.md`)
stands as the design basis; its placement recommendation (O1b) is
**superseded by this record**. The experiment is recorded as the
falsification of the §4 relocation claim, not as a change to the
design doc itself.

## Consequences

- **O1a implementation is commissioned as the build.** Scope: the
  supervision layer (spawn child, enforce timeout, relay
  profile-JSON), the parent-side pipeline unchanged in what it
  checks, verbatim refusal reasons across the boundary, byte-equal
  deterministic replay re-verified by the golden run's replay checks
  (B-1, B-4) at build time — green required, not assumed. Open
  implementation questions from the spike carry over: timeout value,
  POSIX-only resource limits, child-interpreter pinning, exact
  deterministic handling of crashes/signals/malformed child output.
- **Staged artifacts remain unregistered until Operator
  disposition** — the standing profile-build rule is unchanged: a
  green build is staged for Operator disposition, never self-adopted
  or self-registered.
- **Factory 192 is unaffected** — it does not invoke `drive_build`;
  the build must re-run `rb-profile-build` 7/7 with refusal reasons
  relayed verbatim.
- **No push authorized** under this record.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-112.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the
selection only): this record. Commit and push return as follow-on
dispositions.
