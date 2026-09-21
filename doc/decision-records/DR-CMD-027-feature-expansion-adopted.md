# DR-CMD-027 — Feature-expansion playbook adopted (O1)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:36 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the operator's explicit verb — selection among the surviving options)
- **Matter:** Adopt the feature-expansion playbook
  (`doc/feature-expansion-playbook-spec.md`, as remediated
  2026-09-21) as a standing playbook, or not.

## Options and gate trails (from `/pb-decide` START/STOP, 2026-09-21)

- **O1 — Adopt.** Ratify the remediated spec as standing policy;
  `/pb-extend` leaves rehearsal-only → governed. G1 ✓ G2 ✓
  (source: operator-directed remediation + `/eval-pb`
  conforms 10/10 + DR-CMD-026 rehearsal) G3 ✓ G4 ✓.
- **O2 — Adopt with conditions** (e.g., X2-at-KEEP confirmed by
  the first governed runtime matter, else return to DRAFT).
  G1–G4 ✓. Not selected — no condition was found necessary.
- **O3 — Refuse.** Decline adoption. G1–G4 ✓. Not selected —
  no evidence supported refusal (eval-pb conforms, rehearsal
  executed).
- **O4 — Defer.** G1–G4 ✓. Not selected — strands the playbook
  and the undisposed 'updater' matter.
- **O5 — Decide nothing.** The null. Not selected.

No STOP kills; all options survived gating.

## Decision

**Ratified O1 — the feature-expansion playbook is adopted.**

## Consequences (G4)

1. `doc/feature-expansion-playbook-spec.md` is standing policy
   (adopted bytes pinned: sha256
   `8a002679f2b6292c8fda912c5b5991405ad3f9f84b0a21c5537e00438353bdf2`,
   working tree at disposition; commit to follow).
2. `/pb-extend` runs **governed** from here: STOP kills
   enforced, KEEP verdicts feed the shared disposition
   machinery, records written on disposition.
3. §10 bootstrap satisfied: the draft's adoption ran its
   decision procedure (`/pb-decide`, this record), survived
   validation (`/eval-pb` conforms 10/10 on the remediated
   bytes, 2026-09-21), and is disposed by the operator here —
   the circle is broken by the operator's act.

## Checkability (G5)

Binding. Checkable: this record exists; the spec header no
longer reads DRAFT; the `/pb-extend` contract no longer
declares rehearsal; the next `/pb-extend` run carries
`Mode: governed — playbook adopted DR-CMD-027` (or not).

## Premises

- DR-CMD-026 (O2 exercise-then-remediate; the rehearsal).
- `/eval-pb` report 2026-09-21: conforms 10/10 on the
  remediated bytes.
- `/pb-decide` option/gate analysis, 2026-09-21 chat.

## Uncertainties (G6)

- Adopted bytes are working-tree modified and uncommitted —
  pinned by sha256 above; the commit records them.
- Adopting the playbook does not dispose the 'updater' matter
  (still proposed, never evaluated, never disposed).
- Numbering (disposition order): this ratification takes
  **DR-CMD-027**. Next identifier: **DR-CMD-028**.
