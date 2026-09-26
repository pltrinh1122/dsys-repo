# DR-CMD-068 — six-profile set and org-function labels ratified

- **Status:** ratified (disposition)
- **Date:** 2026-09-26 ~08:59 PDT
- **Selector:** Peter (operator; proposer = ambient agent — proposer≠disposer held)
- **Disposition mode:** ratify
- **Matter:** *the six agent profiles as a set* (analyst, advisor,
  author, executor, monitor, coordinator) *and their labels* — the
  org-function theme proposed after the orthogonality/coherence
  evaluation and the label-theme selection matter.

## Decision

**ADOPTED — the six-profile set is ratified as built, and the
org-function labels are ratified as the standard.** Two dispositions in
one record:

1. **The set.** The six profiles constructed, compiled, and verified
   through the step-5 machinery are ratified as a coherent,
   near-orthogonal mediation ensemble: afferent-relay (monitor),
   afferent-synthesize (analyst), reflexive (advisor), efferent-synthesize
   (author), efferent-relay (executor), inter-agent (coordinator).
2. **The labels.** The org-function theme is the standard label form:
   plain nouns drawn from jobs every organization has.

## Label mapping (old → new)

| old        | new          | the familiar job (why it fits)                              |
|------------|--------------|--------------------------------------------------------------|
| diverge    | **analyst**  | gathers intel: researches, observes, brings back findings    |
| converge   | **advisor**  | synthesizes into recommendations — advises, never decides    |
| author     | **author**   | unchanged — produces the documents, specs, plans             |
| execute    | **executor** | carries out what was decided                                 |
| sentinel   | **monitor**  | watches the dials, raises the flag on change                 |
| coordinator| **coordinator** | unchanged — keeps the moving parts in sequence            |

**Why this theme:** it is familiar across organizations of all types
(company, nonprofit, agency, hospital, military unit) — no metaphor to
learn, no genre to buy into. And it is self-justifying: anyone who has
worked anywhere knows what an advisor is *not* allowed to do, which is
precisely what the advisor profile is not allowed to do. The theme
teaches the architecture — proposer≠disposer is encoded in the most
load-bearing label.

**Label-only rename:** no facet value, derived position, or
verification-logic change. Labels are part of the profile, so the four
renamed agents' artifact hashes changed as expected (pre-rename hashes
superseded); author and coordinator hashes are unchanged. Applied in
`core/package/factory_profile_set_001.py` (builders, `PROFILE_SET_001`
keys, docstrings, `__all__`) and `doc/factory-profile-set-001.md`
(title, table, sections, judgment calls, hashes).

## Final vectors (derived from facets, DR-CMD-062; unchanged by rename)

| agent       | D1   | D2  | D3  | D4  | D5   | D6         | D7   | verdict  |
|-------------|------|-----|-----|-----|------|------------|------|----------|
| analyst     | 0.0  | 0.7 | 0.5 | 1.0 | 0.0  | structural | 1.0  | verified |
| advisor     | 0.0  | 0.2 | 0.5 | 1.0 | 0.0  | structural | 0.75 | verified |
| author      | 0.0  | 0.1 | 0.5 | 1.0 | 0.0  | structural | 0.75 | verified |
| executor    | 0.25 | 0.0 | 0.0 | 1.0 | 0.4  | structural | 1.0  | verified |
| monitor     | 0.0  | 0.7 | 0.0 | 1.0 | 0.0  | structural | 1.0  | verified |
| coordinator | 0.0  | 0.2 | 0.5 | 1.0 | 0.0  | structural | 0.75 | verified |

## Verification evidence (post-rename re-run)

`cd ~/workspace/dsys && python3 -m core.package.factory_profile_set_001`,
run twice 2026-09-26:

- All six: verdict **`verified`**, operable; **zero warnings**, zero
  advisories. Static checks 19–30 per agent, all passed; 10/10 probes
  green per agent (P-D6-trigger, P-D5-scope, P-D1-disposition,
  P-D7-boundary, P-D4-trace, P-D3-replay, P-D2-fidelity, P-Q2-routing,
  P-C1, P-C3).
- Deterministic: byte-identical artifact hashes across both runs
  (sha256 prefixes: analyst `132a0fb3e65f4885`, advisor
  `9015e0b0fcecaa94`, author `604b21562784f2e9`, executor
  `d0a75f48657e9c07`, monitor `a7ac321220017d8b`, coordinator
  `6f9acf8b20225331`).

## Relation to DR-CMD-067

DR-CMD-067 ratified the coordinator profile *individually* and
explicitly left the set's "unratified as a set" status unchanged. This
record supersedes that reservation: **the set as a whole is now
ratified.** DR-CMD-067's other holdings stand — in particular, the D6
"agent" source is still NOT added (schema change, deferred), and
F1-CONFIRMED remains the recorded finding.

## Consequences (per G4)

- The six-profile set is a ratified ensemble; the org-function labels
  are the standard form for these profiles going forward.
- `doc/factory-profile-set-001.md` records the ratified status, the
  label mapping, post-rename hashes, and the unchanged vectors,
  rationales, judgment calls (J-A–J-F), and findings (F1-CONFIRMED).
- This ratification covers the set and its labels only — not the
  factory implementation, not step-6 sufficiency (reserved for step 7).

## Uncertainties (G6)

- Whether to add a D6 "agent" source (or a D7 provenance target) for
  inter-agent afferents remains deferred; the coordinator's
  self/operator mislabeling stands as the mechanical evidence
  motivating it.
- The advisor/author separation is the thinnest in the set (D2 0.2 vs
  0.1; orthogonality by role/facets, not scalars) — recorded in the
  evaluation, not re-litigated here.
- Future factory-minted profiles take their plain org-function noun;
  no standing rule beyond the theme is ratified for novel roles that
  fit no familiar job.

## Identifier discipline

- DR-CMD-068 consumed by this record. DR-CMD-059 remains earmarked for
  the PVB Definition of Done — **not consumed**.
- Next disposition identifier: **DR-CMD-069**.

## State

**The tree is UNCOMMITTED at disposition** (Peter disposed the matter
only): this record; `core/package/factory_profile_set_001.py`
(label rename + ratification note); `doc/factory-profile-set-001.md`
(labels, ratified status, post-rename hashes). Commit and push return
as follow-on dispositions.
