# DR-CMD-040 — K3 (governed check-now path) INVALID

- **Status:** ratified (disposition)
- **Date:** 2026-09-21 ~07:44 PDT
- **Selector:** Peter (operator; the matter was operator-directed — conditional design)
- **Disposition mode:** ratify (the feature-expansion playbook's §7 normal mode; the invalid terminal is a KEEP finding the operator ratifies)
- **Discriminator:** feature-expansion (shared machinery)
- **Matter:** K3 — "*if* disposed, dsys should gain a governed check-now path such that an out-of-cycle check runs without touching the drive authority, because the operator has no governed way to check immediately on learning of a release out-of-band."

## Verdict trail

The matter was a conditional design (adopt-the-design never adopts the expansion). After the playbook's "Z bites hardest" amendment (S5 load-bearing; misplaced Z → the complete request is INVALID, terminal), the operator directed a stress test of K3's motivation. Findings, cited:

- **M-A:** the motivating scenario says the operator already learned of the release; the check supplies no knowledge — the alleged need is latency to governed action, not knowledge.
- **M-B:** `updater.poll_interval` is configurable (default 3600s, updater-spec.md); a shorter governed timer interval is existing recourse for freshness.
- **M-C:** the mutating drive is governed regardless of trigger provenance; the gap reduces to timing provenance.
- **M-D:** the motivation was authored after the design — solution-first with a post-hoc Z, the playbook's explicit misplaced-motivation pattern.

Elicitation then surfaced the operator's actual motivation (ambient-driven simulation testing across scenarios), which became a **new matter** (new Z = new matter, per the amended playbook) — the scenario simulation matter, DR-CMD-041 — rather than a reframing of K3.

## Decision

**INVALID** — the operator's "invalid": the complete K3 extension request is invalid. Terminal and distinct from killed: K3 returns only as a new matter with new S1–S5 and lineage.

The draft is marked INVALID and **preserved as prior art** (`doc/k3-repair-spec.md` sha256 `2de8446ce09e7262a5d791c8e75e2759ccfedbbf3167135bdc2320581ba0d198`): the Harness-held trigger design, the check-vs-drive distinction, and the dual trigger record are cited by DR-CMD-041. **AX1** (invocation always through a Harness, never directly to an Automaton) and **AX2** (the Automaton driver — not the unittest suites — is a strapped Harness instance) survive independently as the operator's disposed architectural premises; they are not invalidated with the matter. Next disposition identifier: DR-CMD-041.
