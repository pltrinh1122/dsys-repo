# DR-CMD-021 — Playbook inventory: hybrid pointer (ratified)

- **Status:** ratified
- **Date:** 2026-09-21 ~05:11 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** Should the Architecture list all playbooks explicitly, or just reference the directory containing them?

## Options and gate trails (from `/pb-decide` START/STOP)

Inventory grounded 2026-09-21: five playbook specs in `doc/` (no playbooks-only directory exists), with differing standing — `decision-making-playbook-spec.md` (ratified, implemented), `dsys-mutation-playbook-spec.md` (ratified policy, implemented), `dsys-transcription-playbook-spec.md` (not ratified, exploratory), `feature-expansion-playbook-spec.md` (DRAFT), `dialectic-enhancements-spec.md` (spec-only).

- **O1 — list all in the Architecture:** survived gates; not selected. G3 weak: the directory is the list — enumeration adds no information beyond curation, duplicates per-file status claims (DR-CMD-006 drift risk), and mixes DRAFT/exploratory specs into the normative Architecture, implying standing they lack.
- **O2 — reference the directory only:** killed at G1. No such directory exists — `doc/` (35 files) is not "the directory containing all of the playbooks"; the option has no referent as stated. Variant O2' (create `doc/playbooks/`, move five files, update cross-refs) survives G1 but is pure churn: a bare directory reference cannot distinguish ratified from draft, which is the actual information need.
- **O3 — hybrid:** survived; selected. The Architecture names the ratified playbooks (it already does: §8.2, §8.4) and adds one pointer line to the draft/exploratory specs, with standing declared in the files themselves. G1 ✓, G3 ✓ (bind-don't-restate, no duplication), G4 ✓. Matches the consolidation pattern (DR-CMD-019/020 era: §8.2/§8.3 as pointers).
- **O4 — decide nothing:** survived as the null. Not selected: the question is live and the answer costs one line.

## Decision

**Ratified O3.** Architecture §8.2 gains the playbook-inventory pointer line: ratified playbooks named in the Architecture (§8.2, §8.4); draft/exploratory specs named by file in `doc/`, standing declared in the files.

## Consequences (G4)

One pointer line added to `doc/dyad-architecture-doc.md` §8.2. No file moves, no status restatement, no new maintenance beyond the author's update discipline when a draft's standing changes.

## Checkability (G5)

Binding. Checkable: the pointer line is present in §8.2 (or not); each named file declares its own standing (or not).

## Uncertainties (G6)

- The pointer names draft files explicitly — mild drift if a new draft playbook appears or a draft is ratified. Mitigation: the ratifying/disposing act updates the line (same discipline as any doc change). Revisit trigger: a playbook spec whose standing changes.
- Numbering (disposition order): this ratification takes **DR-CMD-021**.
