# DR-CMD-107 — Profile renames adopted: `recorder` and `chronicler`

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "proceed as recommended: `recorder` and
  `chronicler`", ~20:43 PDT)

## Matter

Permanent names to replace the provisional working names `registrar_clerk`
and `dr_registrar` (both provisional-in-name-only since adoption;
DR-CMD-096, DR-CMD-100).

## Ground (the three charters)

- `registrar` (staff+office, DR-CMD-083): watches factory verdict records;
  when a build verifies, **stages** a registry-update proposal (agent,
  artifact hash, verdict ref) for the registry of verified built agents.
  Keeps its name — not in scope for this disposition.
- `registrar_clerk` (clerk = may-act x office): the minimal pair with the
  staff registrar — same office reading (D7 0.75, validates presented
  documents, never investigates the world), flipped acting posture
  (D1 0.5 / D5 0.15): sweeps the staged area for verified build notices
  and adopted customization proposals, validates each against office
  criteria, and **records the survivors directly** into the
  content-addressed append-only artifact registry; refuses the rest with
  reasons.
- `dr_registrar` (clerk): the dog-food clerk — on the operator's schedule
  (CL4), sweeps staged DR drafts, vets each against the commissioned
  mechanical criteria, registers the well-formed append-only, defers the
  malformed for operator disposition. Never judges a DR's *truth* (a DR's
  truth is the operator's disposition, not an external fact).

## Naming criteria (from the corpus)

Single lowercase word; no confusable pairs (the
registrar/`registrar_clerk` collision was the defect); function-honest
about the bounded scope; no borrowed authority.

## The /pb-decide (condensed)

### `registrar_clerk` → O1 `recorder` — adopted

The exact verb of the job: records the survivors into the artifact
registry. Corpus-clean (verified before selection), and the kinship with
`registrar` honestly signals the minimal pair across the acting axis.

- O2 `scribe` — refused: craft flavor, but a scribe transcribes; this
  profile validates and registers. Dishonest about the work.
- O3 `notary` — refused: implies attestation it never performs. Borrowed
  authority.

### `dr_registrar` → O1 `chronicler` — adopted

Keeper of the decision chronicle — the architecture's governance memory.
Matches the corpus's role-noun pattern (analyst, author, executor,
registrar: the noun is the output), corpus-clean, unmistakable next to
registrar/recorder.

- O2 `keeper` — refused: "keeper of the record" is evocative but
  objectless; fails the scope-honesty criterion.
- O3 `examiner` — refused: names the vetting means, not the registering
  end.

## Peter's selection

"proceed as recommended: `recorder` and `chronicler`."

## Consequences

A rename is an identity change, not a label swap: each profile gets new
authored module bytes (the `agent=` identity, docstrings, and working-name
notes), rebuilt through `rb-profile-build` per the standing profile-build
rule (DR-CMD-101) — authored and staged by a builder subagent, never
hand-driven, green runs staged for disposition, never self-registered.
Commissioned as follow-on build under the ambient's hand,
commission_ref DR-CMD-107.

- `recorder`: re-registered into `PROFILE_SET_002` +
  `PROFILE_ARCHETYPES_002` + `CLERK.members`, replacing `registrar_clerk`.
- `chronicler`: remains unregistered pending tranche 2 (DR-CMD-102);
  expected outcome is the honest compile refusal with the same
  missing-channel reasons `dr_registrar` carries.
- The old working-name modules are replaced, not kept: the history lives
  in the DRs, not the code.

Build outcomes and verification counts are NOT claimed here; the builder
returns those separately.

## Identifier discipline

- DR-CMD-059 remains reserved for the Product Vision Board Definition of
  Done — not consumed.
- Next free identifier: DR-CMD-108.
