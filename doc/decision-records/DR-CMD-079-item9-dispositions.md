# DR-CMD-079 — Item 9 dispositions (ratified)

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~11:57 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (selection among /pb-decide variants)
- **Matter:** Item 9 — the three remaining items (D6 agent source left Item 9
  as its own matter under DR-CMD-078; advisor/author separation recorded
  moot per DR-CMD-077).

## Dialectic trail

Item 9's five defect findings were framed for /pb-decide disposition
earlier on 2026-09-26. Two were resolved before this disposition: the
D6 `agent` source gap (F1) was ratified OPEN NOW as a standalone design
matter (DR-CMD-078 — Peter: "coordinator needs to be able to operate
autonomously upon state changes"), and the advisor/author thin separation
was recorded MOOT — dissolved by the D2 binary enum (DR-CMD-077), both
profiles `principal_wins_ties`. Peter then disposed the three live items
in one terse selection: remediate / defer / remediate.

## Decisions

### 1. REFERENCE bind-time validation — REMEDIATE

The schema declares that PERSONAL/REFERENCE bindings are validated when
referenced, but no such validation is implemented. Declared-but-unimplemented
is a defect, not an open question: the promise is made in the schema, the
machinery does not exist, and silence at the read sites would be a lie.
Remediation: implement validation at the sites where PERSONAL/REFERENCE
bindings are consumed (accretion var/ reads). Failure mode is honest by
construction: a dangling or invalid reference refuses-or-stages with
reasons, never silently passes. Scope is minimal — implement what the
declaration promises, nothing more.

### 2. D4 `records_*` per-profile override — DEFER as G6

`records_*` stays `FACTORY_CONFIG` (factory-wide). No concrete use case
currently justifies weakening the machine-governor instrumentation
guarantee, and weakening it on no evidence is the wrong direction.
Sharpened revisit tripwire (per the G6 hygiene rule): revisit **only when
a concrete profile genuinely needs less instrumentation than the
factory-config guarantee** — e.g., forever-retention provably infeasible
at field volume — and not before. An abstract desire for per-profile
flexibility does not trip the wire.

### 3. Archetype self-test `model_copy(update=)` — REMEDIATE

Mechanical rewrite to a validating
`Model.model_validate({**m.model_dump(), ...})`. Existing passing behavior
is insufficient as evidence: `model_copy(update=)` bypasses pydantic
validation (AGENTS.md lesson, caught 2026-09-21), which would make the
negative control vacuous — a synthetic write_scope violation that was
never genuinely validated could pass the gate for the wrong reason. After
the rewrite the self-test's green verdict is earned: six profiles conform,
synthetic violation refused with reasons, unknown archetype rejected.

## Uncertainties (G6)

- D4 `records_*` override question, with the tripwire above. The orphan-triage
  policy (Item 5b) remains open with Peter's timing disposition pending.
- Item 10 (final factory ratify) follows after remediation verification.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- DR-CMD-078's "remaining Item 9 items untouched" note is superseded by
  this disposition (recorded here, not rewritten there).
- Next disposition identifier: DR-CMD-080.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the three
selections only): this record. The two remediations (REFERENCE validation
implementation; `model_copy` rewrite) were authorized as follow-on build
under the ambient's hand and return with verification counts. Commit and
push return as follow-on dispositions.
