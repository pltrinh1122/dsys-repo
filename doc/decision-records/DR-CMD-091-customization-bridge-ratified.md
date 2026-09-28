# DR-CMD-091 — customization bridge ratified (customizer as secondary agent)

- **Status:** ratified
- **Date:** 2026-09-27 ~12:15 PDT
- **Matter:** Ratify, amend, or refuse the customization bridge designed and
  built 2026-09-27: the customizer agent, the artifact registry, and the
  propose-customization / adopt-proposal channels. Separator: Peter.

## Disposition

Peter rendered "ratify" (~12:15 PDT 2026-09-27). The customization bridge
is **ratified as built**.

## What is ratified

1. **Customizer is a secondary, ambient-side agent — not a Factory mode.**
   Drafting customization proposals and compatibility analysis are
   inferential work; placing them inside the ratified D1 0.0 / D3 0.0
   factory would smuggle inference (and operator waiting) into the
   mechanical pipeline. The factory stays mechanical and supplies
   registry lookup, registration, and build services.
2. **Customizer profile** (`core/package/customizer.py`): archetypes
   staff + office; D1 0.0, D3 0.5 (replay supported), D4 1.0, D5 0.0
   (stage-only), D6 {OPERATOR, AGENT} via the DR-CMD-078 stigmergic
   staging trigger, D7 0.75 fail_closed. `CustomizationProposal` envelope
   + `validate_proposal_envelope()`; diagnostics E-C1..E-C11.
3. **Artifact registry** (`core/package/artifact_registry.py`):
   content-addressed, append-only JSONL, versioned; SHA-256 content pins;
   mechanical lookup / prove-absence; `register()` fail-closed: refuses
   empty artifacts, missing dispositions, duplicate identical bytes, and
   post-release structural change under the original commission.
4. **Channels** (`core/package/author_channels.py`):
   - `propose-customization`: validates the envelope, requires an
     operator-attributed commission, **re-runs the registry lookup**
     rather than trusting carried evidence, checks supersession/version
     rules, stages a bytes-pinned proposal. Registers nothing, builds
     nothing.
   - `adopt-proposal`: requires operator attribution and disposition
     reference; registers the artifact versioned and content-pinned;
     refuses duplicate adoption.
5. **Post-release rule (mechanical, not policy):** structural customization
   after Factory release invalidates the verified byte pin unless it
   enters a new authoring/build/verification cycle. A new version
   requires a new commission plus a `supersedes` claim naming the
   registered artifact, with `proposed_version == latest.version + 1`.
   Post-release binding *within declared bounds* remains configuration
   or personalization, not customization.
6. **Operating agents never customize in-execution.** An operating agent
   stages a re-authoring/customization need or refuses with reasons.

## Dialectic trail

- Peter's 2026-09-27 claim *"customization sequence happens after Factory
  release"* was **falsified** the same morning: structural change after
  release without a new build cycle breaks the verified pin; what
  survives post-release within declared bounds is configuration /
  personalization.
- Customization was classified as **customization** (not configuration or
  personalization) because the ambient invented new structure rather than
  selecting declared options or varying a declared shape per principal.

## Verification observed (under this record)

- `customizer_golden_run.py`: 10/10.
- Customizer authored end-to-end through the author-agent loop:
  commission → stage → drive → **verified** (11/11 factory diagnostics).
- Loader defect exposed and fixed: `author_agent._load_authored` now
  registers staged modules in `sys.modules` before exec (PEP 563 forward
  refs in staged pydantic models).
- Regressions green: author_agent, author_channels, factory (192 passed
  after DR-CMD-090).

## Consequences

- The customization sequence (detect → inspect → stage proposal →
  operator adopts/amends/refuses → register versioned+pinned → factory
  builds dependents → deliver verified only) is ratified procedure.
- The email-ingestion matter-record shape stays a temporary in-module
  dictionary contract — not a registered shared schema — until a
  customization proposal for it is adopted under this bridge.
- Work remains uncommitted on `build/half1` (no push authority granted).

## Uncertainties (G6)

- Orphan-triage timing for unmatched customization triggers (composes
  with the open Item-9 orphan-triage policy).
- Whether production Claude CLI backing for the customizer is ever
  implemented (currently a deterministic authoring loop).

Next free identifier: DR-CMD-092 (DR-CMD-059 still reserved for PVB DoD).
