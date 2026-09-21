# DR-CMD-051 — NBA: frame the (b)-half (handle acquisition + lifetime)

- **Status:** recorded
- **Date:** 2026-09-21 ~13:23 PDT
- **Selector:** Peter (operator)
- **Disposition mode:** triage (the `/pb-decide` next-best-action machinery)
- **Discriminator:** feature-expansion (shared machinery)

## The decision

Peter invoked `/pb-decide` narrowed to "O3 (frame the
b-half follow-on) or O4 (executor-spec)". The ambient
recommended O3 — the (b)-half is the direct continuation
of the K1 Q3 line, newly unblocked with a settled
boundary (DR-CMD-046's return condition satisfied; the
drive-contract spec's G6 Q3 settled the edge), while the
executor spec is an independent thread nothing changed —
and Peter said "O3: frame the (b)-half follow-on."

## What was framed

`doc/k1-q3b-handle-acquisition-matter.md` — **Status:
FRAMED** (not evaluated, not disposed).

- **Matter:** *k1-q3b-handle-acquisition* — how the
  production drive's bearer acquires the repository handle
  at drive start (resolution mechanics) and how handles
  rotate and revoke, within the drive-bounded lifetime the
  adopted drive contract sets.
- **Lineage:** K1's G6 Q3 → DR-CMD-039 → K1 Q3
  (DR-CMD-045/046/047; (a)-half adopted, spec'd, built)
  → DR-CMD-046 F4 (the (b)-half refused not-ready;
  "returns as a follow-on matter once the production
  driver is framed") → the production driver framed
  (DR-CMD-048), adopted (DR-CMD-049), spec'd and
  spec-adopted (DR-CMD-050), built and committed
  (`8b61695`) → this framing, which discharges DR-CMD-046's
  return condition.
- **S5 (because-Z):** no acquisition design exists anywhere
  in the design (checkable world-claim, true on cited
  evidence: DR-CMD-046; the drive-contract spec's G6
  residuals; the binding spec's D4 "Rotation is not
  defined"); without acquisition the drive cannot run
  against the real accretion repo.
- **Hard constraints carried into the frame:** the adopted
  drive-contract boundary (the handle's lifetime is bounded
  to the drive — no long-lived bearer); the binding spec's
  D1/D2 (installer mints both sides; identity is a UUID,
  not a path); the K3 tripwire (acquisition must not
  become an ambient-programmable initiation path); A2's
  no-new-entity discipline (the survivor should be a
  contract, not a thing).
- **G6:** resolution mechanics (Q1), who resolves (Q2),
  rotation triggers + minter + manifest mutability (Q3),
  revocation (Q4), absence at drive start (Q5), the K3
  edge on acquisition (Q6).
- **What it is not:** not the binding (built); not the
  drive contract (built); not a handle-manager entity;
  not a scheduler or daemon.

## What this authorizes

Framing only. Evaluation (`/pb-decide`, falsification
pipeline) and disposition are separate operator decisions.
Next disposition identifier: DR-CMD-052.
