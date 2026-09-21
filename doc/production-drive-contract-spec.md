# Production-drive contract spec

**Status: ADOPTED (DR-CMD-050)** — disposed 2026-09-21.
The operator selected "Adopt the spec." Build follows on
the operator's separate direction; the build is not
authorized by this record.

**Parent:** `doc/production-driver-matter.md` — ADOPTED
(narrowed, with conditions, DR-CMD-049) 2026-09-21. The
adopted-now Y: *named initiator, authorized principal,
Harness invocation, verified handle — no ambient initiation.*

**Scope:** the production-drive *contract* — initiation,
authority, and handle-bearing for production drives of the
updater flow (`flow-release-monitor`, 9 states, 16
transitions). Not a driver entity (refused, F1/A2). Not
stepping machinery (AX2's strapped-Harness walker and the
automaton-executor spec own that, F2). Not handle
acquisition/lifetime mechanics — the (b)-half (boundary
settled below).

## The contract

- **D1 — the initiator is the operator.** A production drive
  is initiated by the operator principal: the human operator,
  or the ambient acting on the operator's explicit
  instruction — the operator's act through the ambient's
  hands (the dialog protocol's write-gated authority,
  applied to initiation). The ambient may never initiate on
  its own authority.
- **D2 — invocation is through the CLI's flow-drive surface,
  which straps a Harness.** The operator initiates via
  `dsys automaton init-flow --flow flow-release-monitor`
  and `dsys automaton advance --flow-run <id>`
  (cli-interface-spec §3.7; specified, not implemented).
  Per AX1, invocation is always through a Harness; per AX2,
  the walker is a strapped Harness instance. The CLI
  surface is the vehicle; this contract is the
  authorization.
- **D3 — the principal binding.** The drive runs under the
  dyad-or-human principal, agents excluded (the dialog
  protocol's principal binding). For initiation
  specifically, the initiator is the human operator (D1) —
  the dyad's ambient side may execute on instruction but
  may not initiate.
- **D4 — the K3 tripwire.** Any initiation path the ambient
  can program or trigger is K3 revived and terminally
  invalid (DR-CMD-040). This includes a wrapper, cron, or
  scheduler the ambient writes or configures. No scheduler
  exists in the design; if one is ever framed, it must
  satisfy this tripwire or be refused.
- **D5 — the manifest is read at initiation; the tool
  verifies per write.** The drive resolves the
  manifest-recorded accretion-repo identity
  (`accretion_repo.identity`) from the installation
  manifest once, at initiation (process side). The
  committing tool's pre-write identity check (K1 Q3(a)
  spec D3 — verify the handle's identity against the
  manifest before every write, fail closed,
  abort-not-retry) is a pure comparison against the
  drive-resolved identity (governed side — no file I/O in
  the tool). The process side reads the world; the
  governed side compares. This preserves D7's
  governed/process split.
- **D6 — full profile only.** The drive contract is
  full-profile machinery. Base refuses with exit 1 naming
  the component (cli-interface-spec §3.7; the executor
  spec §4 — the same pattern as `session`).
- **D7 — after fail-closed: no retry, record, surface.**
  When the D3 check aborts the drive (`ToolAborted`,
  `run_aborted → failed`): the drive ends in `failed`; it
  does not retry within the drive, does not heal, does not
  re-initiate. The failure is recorded in the drive
  transcript and surfaced to the operator. The next drive
  requires a new initiation (D1). Abort-not-retry is the
  tool's; no-reinitiation is the drive's.

## I-26 — authorized initiation (R3)

`i26_authorized_initiation` is a predicate over the drive's
initiation record (predicates, not procedures):

- the initiator is the operator principal (D1, D3), and
- the initiation origin is not the ambient acting on its
  own authority (D4), and
- the drive was invoked through a strapped Harness
  (AX1/AX2, D2).

Violation → the drive is refused: it does not start. A
drive found post-hoc to violate I-26 is invalid. (At
spec stage the predicate is defined; enforcement at
initiation belongs to the CLI surface, and the golden
run checks the predicate — R2.)

## Replay (R1)

The drive's initiation metadata — initiator, principal,
the drive-resolved manifest identity — is recorded in the
drive transcript envelope. Replay is transcript
re-validation (AX2's consequence: "the driver inherits
Harness discipline: strapped operation, transcript as the
run record, replay by re-validation"). The wall-clock
time of initiation must not enter guard evaluation or the
committed payload (the executor spec's clock boundary:
"No wall-clock value may enter guard evaluation or
replay"). The D3 check precedes payload construction and
does not enter the payload (K1 Q3(a) R1, built). So:
initiation is recorded, and the replay-identity is
unchanged — re-validation of the transcript reproduces
the verdict.

## Trust declared (R5)

- **The operator as initiator** (D1): trusted to initiate
  only authorized drives — the same trust class as the
  dialog protocol's write disposition (the operator's
  instruction is authority).
- **The installation manifest's integrity**: trusted —
  the manifest-recorded identity is the binding's root
  (declared in K1 Q3(a) R5, reaffirmed here).
- **The Harness strapping** (AX2): trusted to walk the
  flow deterministically under the strap.
- **Explicitly not trusted with initiation:** the ambient
  (D4); any wrapper or scheduler (none exists; D4's
  tripwire governs any future one).

## Acceptances (R2)

Checkable acceptances; golden-run cases at build:

1. An operator-initiated drive via the flow-drive surface
   runs to completion bearing the D3-verified handle; the
   transcript records the initiator and principal.
2. An ambient-originated initiation (no operator
   instruction) is refused — the drive does not start
   (the K3 tripwire as a negative case).
3. Identity mismatch mid-drive → D3 aborts → the drive
   ends `failed`; no retry within the drive, no
   re-initiation; the failure is recorded and surfaced.
4. Base-profile invocation → refused with exit 1 naming
   the component.
5. Replay: the drive transcript re-validates; initiation
   metadata does not break the replay-identity.

## The (b)-half boundary (G6 Q3 — settled)

This contract names the bearer — the strapped Harness
instance walking the drive's FlowRun, initiated per
D1–D3 — and the bearer's duties (D5–D7), and bounds the
handle's lifetime to the drive: the step-function model
(the executor spec §1 — "each invocation loads state,
advances as far as mechanically determined, appends
events, exits") means there is no long-lived bearer; the
handle cannot outlive the drive because the bearer
doesn't. The (b)-half designs, within that bound: how the
bearer acquires the handle at drive start (resolution
mechanics — which repo, via the manifest identity) and
any rotation or revocation. Acquisition mechanics and
rotation are the (b)-half's; initiation, authority,
bearing, and the drive-bounded lifetime are this
contract's.

## G6 residuals

- The automaton-executor spec is specified-not-disposed
  ("awaiting Peter's approval," 2026-09-20) — a
  neighboring thread. This contract composes with it
  (stepping) but does not dispose it.
- No scheduler exists; framing one would be a new matter,
  subject to D4's tripwire.
- The CLI's `automaton init-flow` / `advance --flow-run`
  surface is specified-not-implemented — the vehicle for
  D2 awaits implementation.

## Glossary

- **Production drive:** one initiated run of the updater
  flow (`flow-release-monitor`) against the real
  accretion repo, from initiation to a terminal state.
- **Initiator:** the operator principal that starts the
  drive (D1).
- **Bearer:** the strapped Harness instance walking the
  drive's FlowRun (AX2) — the holder of the D3-verified
  handle for the drive's lifetime.
- **Initiation record:** the drive transcript envelope's
  record of initiator, principal, and drive-resolved
  manifest identity (checked by I-26).
- **Flow-drive surface:** the CLI's `automaton init-flow`
  / `advance --flow-run` commands (cli-interface-spec
  §3.7) — the vehicle for D2.
- **The (b)-half:** the refused-not-ready acquisition +
  lifetime design (DR-CMD-046, F4) — returns as a
  follow-on matter; its boundary with this contract is
  settled above.
