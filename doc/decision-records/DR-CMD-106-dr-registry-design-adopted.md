# DR-CMD-106 — DR registry structure design adopted (held, not built)

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "Adopt the registry design (held, not built)", ~19:03 PDT)

## Matter

Dispose on the DR registry structure design (`doc/dr-registry-structure-design.md`),
taken up as its own matter under DR-CMD-105 (O2 of the next-best-action
/pb-decide): adopt, amend, or refuse.

## Design adopted (condensed)

A DEDICATED Decision Record registry:

- `doc/decision-records/registry.jsonl`, git-versioned beside the markdown files.
- A DR-specific `DecisionRecord` schema: `id`, `seq`, `sha256`, `status`,
  `supersedes[]`, `addendum_to`, `premise_refs[]`, `disposition_ref`, plus
  registry-level reservations metadata.
- Write-time invariants, enforced fail-closed: sequencing (no gaps, no
  duplicates), reservation honoring, chain integrity (supersedes/addendum
  targets exist), premise resolution, content-hash dedup, disposition gating.

DR-CMD-099's artifact-registry reuse does NOT generalize to DRs. DRs are
sequenced immutable records with reservations and chains; shoehorning them
into `ArtifactRecord` (sentinel `commission_id`, dead `version` field) is
exactly the substitution class the DR-CMD-096/097/100 deviations refused.
The artifact registry's mechanical pattern (JSONL append-only,
content-addressing, hermetic contracted tool) is ported; its schema is not.

## "Held, not built"

- Condition (i) (registry-structure design): MET by this adoption.
- Condition (ii) (demonstrated operational need for the DR registration
  channel): NOT MET — no draft producer exists. DRs flow at high rate but
  are written directly by ambient chat labor; there is no staging area, no
  draft queue, no mechanical draft producer. A registration channel with no
  producer is a bridge to nowhere.
- The trigger that changes this: the staged-draft discipline —
  processor/transcriber subagents stage drafts instead of writing registry
  files directly, and the registered `dr_registrar` vets them on standing
  disposition. Until the trigger fires, the design is held as the standing
  plan, not a build order.
- Tranche 2's DR channel does NOT collapse into `tool-register-artifact`:
  DR-specific refusal cases (not-next-in-sequence, reserved-number, dangling
  premise/supersedes/addendum targets) cannot be expressed without corrupting
  that tool's contract. What dissolves is the research risk: when the
  trigger fires, the channel is a small, fully precedented DR-CMD-055 build.
- Genesis import (backfill of the pre-registry DRs with honest provenance
  labeling) is scoped for the eventual build commission, not designed here.

## Consequences

- The design is the standing plan; NO build is authorized by this disposition.
- Tranche 2's DR registration channel (and the triage channels) remain
  conditional per DR-CMD-102; `triager` and `dr_registrar` remain honestly
  compile-refused.
- Nothing in the working tree changes from this disposition — it records a
  disposition, not a build.

Next free identifier: DR-CMD-107 (DR-CMD-059 still reserved for PVB DoD).
