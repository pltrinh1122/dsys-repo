# DR-CMD-038 — K2 repair (explicit accretion adoption + fail-closed drive) ADOPTED with conditions

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~06:58 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify (the feature-expansion playbook's §7 normal mode for expansion matters; authorize/set_standing/triage excluded)
- **Discriminator:** feature-expansion (shared machinery)
- **Matter:** the K2 repair — "the updater's drive explicitly resumes the previous installation's accretion repository when invoking the installer, and the unwritable-accretion-path edge refuses the drive rather than warn-and-continue under autonomous operation — so history is never silently lost."

## Verdict trail (governed `/pb-extend` evaluation, this session)

- **Gates:** X1 clear (dual-scope, decomposed at START, conjunctive); X2 clear (D7 — precondition is pre-drive, the evaluated R1 re-derivation story untouched; durability premise stays K1's); X3 clear (pre-build); X4 clear (not K1 — D6 boundary on the record; installer-spec §13 enshrines warn-and-continue, so the repair confronts rather than duplicates it).
- **Conditionals holding:** A1–A5 (F1–F4 genuine ambient attempts; five new terms glossary-defined; no plane crossing; spec exists; five checkable acceptances); R1 (story stated); R3 (vacuous at entity level — no new states/transitions; invocation contract golden-run-asserted); R4; R5 (never-`--overwrite`, refuse-rather-than-fabricate declared); P1 (`--accretion-required` joins the `--accretion-require-*` flag family); P2 (no widening).
- **Conditionals specified-but-unexecuted (build-time):** R2 (acceptances 1–5 as golden-run cases), P3 (installer-spec §13 fail-closed carve-out; updater-spec §9 K2 → repair), P4 (flag's nonzero exit verified).
- **Draft verdict:** adopt-with-conditions.

## Decision

**ADOPTED** — the operator's "Adopt, refuse-the-drive": adoption under the verdict's four conditions, with the D3 rule disposed as **refuse-the-drive**:

1. Acceptances 1–5 executed as golden-run cases (unwritable → failed with the flag + explicit path recorded; config-overridden path pinned; first-install fresh; no `--overwrite`; replay re-derivation).
2. `--accretion-required` implemented in `install.sh`: nonzero exit naming the reason when accretion cannot be enabled; no manifest written on the failed install.
3. Docs converge: installer-spec §13 gains the fail-closed carve-out; updater-spec §9 K2 points at the repair.
4. The build implements refuse-the-drive (D3 disposed — loud-surface rejected under autonomy; re-arguable only if a watching channel with teeth ever exists).

Adopted bytes: `doc/k2-repair-spec.md` sha256 `462bfe4211b00839787400a6f0eb3c5c591ed43b934a3139d51c2a5464a0f919` (adopted header, D3 disposed; working tree, uncommitted at disposition). G6 carried: K1's writer, when built, writes to the repo this repair adopts (neither subsumes the other); the previous-home config key naming is build detail. Next disposition identifier: DR-CMD-039.
