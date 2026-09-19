# DR-DIALOG-001: Inference-request context transport

- **Matter:** How is an inference request's context transported —
  embed-by-value (dsys generates the context file, embedded with
  the request) or reference-by-pin (the request carries pins the
  ambient resolves)? Decided via the decision-making playbook,
  2026-09-19.
- **Disposition mode:** ratify. **Proposer:** Architect.
  **Disposer / selector:** Peter (ratified 2026-09-19).
- **Framing:** "The inference request's context should be
  transported embed-by-value rather than reference-by-pin."

## Options and gate trails

- **O1 — Embed-by-value.** dsys materializes pinned context into
  `pending/<turn_id>/context/` at issuance. G1–G4 pass.
- **O2 — Reference-by-pin.** Request carries pins (commit SHAs,
  state hashes); the ambient resolves. G1–G4 pass.
  **Killed by falsification:** the consistency hole is
  structural — resolution (which checkout? dirty tree?) happens
  in the ambient, the untrusted unconfigured party, placing the
  critical step outside the governed boundary.
- **O3 — Content-addressed manifest (synthesis of O1+O2).** dsys
  materializes once per unique context into
  `var/dialog/context/<sha>/`; the request embeds a manifest of
  hashes; the ambient reads store bytes; re-hash verifies.
  G1–G4 pass. **Selected.**
- **O4 — Ambient attestation.** Pins + ambient-attested
  `context_used`; dsys verifies after the fact. G1–G4 pass.
  **Killed as standalone** (detects divergence after inference
  rather than ensuring consistency before it — fails the
  matter's goal); **merged as supplement** into O3
  (`context_used` rides along as defense-in-depth).
- **O5 — Decide nothing.** G1–G4 pass. **Deferred** with revisit
  trigger: dialog-protocol implementation approval.

Industry sources (G2): RAG prompt-stuffing, MCP embedded
resource contents, `go mod vendor`, Anthropic prompt caching
(byte-stable prefix ⇒ cache hits) for O1; agentic RAG,
lockfile-resolve for O2; Nix store, OCI layers, git objects for
O3; `pip --require-hashes` for O4.

## Consequences

- Dialog spec §15.9: store layout `var/dialog/context/<sha>/`,
  embedded manifest schema, issuance validator (pins resolvable,
  materialization hash recorded), ambient read path = the store
  (no self-resolved pins), `context_used` ingest rule.
- Uniform rule: always store, always manifest — one code path.

## Uncertainties (G6)

- Store GC un-designed; until then orphaned contexts are
  surfaced, not reaped (dialog orphan policy).
- `context_used` remains declared trust; divergence surfaced,
  not auto-failed.
- Non-file context (the conversation as context) is declared,
  not pinned.
- The dialog protocol as a whole remains exploratory, not
  approved for implementation.
