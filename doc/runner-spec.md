# `runner` — design reference (spec)

2026-09-20. Not implemented. Not ratified — ratification is a
disposition, not a document. Companion to `factory-spec.md`: the
runner executes the BuildRun phase. The factory authors and governs;
the runner derives.

## 1. Position

The runner is the derivation executor: it takes a hermetic input
closure (draft bytes + pinned toolchain + derivation manifest) and
returns release bytes plus a receipt — purely, deterministically.
Build-time; the automaton is run-time.

What it is not: not the automaton executor (scheduler/flows run
AutomatonRuns); not `dsys execute` (harness-plane, inference
allowed); not the ambient (no inference); not the factory
(authorship and governance live there).

**The runner takes no dispositions.** It exercises zero discretion —
it executes authorized derivations and attests the conditions. Its
refusals (unpinned toolchain, underspecified input) are check
results, not dispositions: refusals are data, like referee exit
codes. Anything requiring judgment is a factory matter, never a
runner matter.

## 2. Data entities

- **DerivationManifest** — the hermetic input closure:
  content-addressed draft refs (+ hashes), toolchain pin (version +
  hash), derivation parameters. Content-addressed; the cache key and
  the double-derive comparator both key on it. Assembled by the
  factory *before* submission — closure assembly is part of becoming
  buildable (factory C-1).
- **RunnerReceipt** — the runner's own record, cited by the
  factory's BuildRun: input manifest hash, runner identity,
  toolchain pin verified, hermeticity attestation (no network
  observed, fixed environment fingerprint, no wall-clock
  dependence), output bytes hash, double-derive comparison result,
  pass/fail. Separate record, separate accountability: the factory
  says "derive this," the runner says "I derived that, under these
  conditions" (F-RUN-1). One BuildRun may cite multiple receipts
  (diversity).
- **DerivationCache** — content-addressed memoization: input
  manifest hash → (output bytes hash, original receipt ref). A hit
  returns the original receipt's output and cites the original
  receipt — it never mints fresh attestation (F-RUN-3).

No timestamps on receipts — the architecture has no clock (DR-5).
Ordering by manifest hash + runner identity.

## 3. Process

Receive manifest → verify toolchain pin → seal environment →
derive → derive again → compare hashes → attest → receipt. Failure
is deterministic: same inputs, same failure, every time. No
retries-with-variance (pointless for pure functions); retry only on
attested environment faults, recorded as violations, never silently
absorbed.

## 4. Invariants

- **R-1 hermetic seal.** The derivation sees only the input closure
  + pinned toolchain. Attested in the receipt — measured, not merely
  constructed. The seal is mechanism-agnostic: the spec constrains
  the *property*, never the mechanism. Containerization, jails,
  VMs, a functional build store — or no isolation at all for
  identity derivations — are all conforming implementations; the
  chosen mechanism is declared in the receipt's environment
  fingerprint. Seal attestation is declared trust (gameability
  noted, cf. DR-5's `open_seq`) — checkable via diversity, not
  proven.
- **R-2 pin enforced.** The runner refuses unpinned or unknown
  toolchains. The factory records the version; the runner enforces
  the pin.
- **R-3 determinism acceptance.** Every derivation runs twice;
  hashes must match. Mismatch = environment fault → attested
  failure, never a silent pass. Catches nondeterminism, not
  dishonesty (F-RUN-4).
- **R-4 no judgment in the derivation path.** Underspecified input
  fails deterministically; the runner never resolves ambiguity.
- **R-5 cache soundness.** Hits require exact manifest-hash match
  (toolchain pin in the key), inherit the original receipt's
  attestation, and cite the original receipt. Sound only given a
  complete closure (C-1) and an intact seal at derivation time
  (R-1).

## 5. Trust

The runner sits *in* the trust base by declaration — like the AST
allowlist — subject to the factory's amendment procedure (§8 of
factory-spec): a runner change is a trust-boundary change
(`touches_trust_boundary`, declared guarantees, verifier lineage,
no retroactive re-adjudication). Mitigation for a lying or
correlated-buggy runner is **diversity**: independent re-derivation
by a second runner implementation, receipts compared. Diversity is
a disposition / standing-policy choice — e.g. required for
trust-boundary builds — not a hard invariant (cost is 2×
derivation).

Provisioning is outside the runner. Hosts, containers, images,
toolchains — the runner never installs or configures any of them;
provisioning is a deployment/installation concern under its own
authority, and appears to the runner only as pinned, verifiable
input (R-2: verify the pin, refuse the unknown — never fetch and
install). The receipt therefore attests *observed conditions of
given material*, never conditions of self-made material; a runner
that built its own seal could attest it only circularly
(falsified 2026-09-20).

## 6. Constraints on the factory (C-1–C-6)

1. **Hermetic input closure.** A draft is buildable only if its
   derivation inputs are completely declared and content-addressed
   — the factory assembles the closure as an artifact before
   submission. Tightens the Buildable DoD.
2. **Draft completeness.** Per R-4, "to be decided at build time" is
   a buildability violation. Constrains authoring: the ambient's
   proposals must be fully determined; deferred judgment can't be
   smuggled past the factory into the runner.
3. **Toolchain governance.** The toolchain is a first-class
   versioned artifact the factory provides pinnable — it joins the
   factory trust base, not just a version string on the record.
4. **Receipt citation.** BuildRun records cite the RunnerReceipt(s).
   I-F2 graduates from construction claim to measured property.
5. **Cache-aware identity.** Rebuilding identical inputs is a cache
   hit, not a re-derivation — "build" is idempotent by input hash.
6. **Failure determinism.** Derivation failure is deterministic
   information (same inputs → same failure). Factory retry posture:
   only on attested environment faults.

## 7. Falsification register

- **F-RUN-1** "The receipt can live on BuildRun." **Falsified.**
  Record-writer principle (records cite records; writers own their
  records) plus the decisive case: diversity means N runners → N
  receipts for one BuildRun — two attestations can't own the same
  fields. Survivor: separate RunnerReceipt, cited by BuildRun;
  receipt multiplicity supported.
- **F-RUN-2** "The runner is trustworthy because it's simple."
  **Falsified.** F-FACT-5's lesson, inherited: never trusted, only
  checkable; simplicity is not a verification method. Survivor:
  trust via attested receipts + double-derive + diversity; runner in
  trust base by declaration.
- **F-RUN-3** "Caching is safe because pure." **Falsified as
  stated.** Purity is necessary, not sufficient: an incomplete
  closure lets two real input sets share one manifest hash (stale
  output, straight face); a seal violation at derivation time bakes
  the leak into the cached bytes. Survivor (narrowed): cache sound
  iff manifest complete (C-1) + seal held at derivation (R-1,
  attested) + pin in key; hits cite the original receipt, never mint
  attestation.
- **F-RUN-4** "A lying runner is caught by double-derive."
  **Falsified.** A runner controlling its execution lies
  consistently. Double-derive catches nondeterminism (accidental),
  not dishonesty (systematic) — different threat models. Survivor:
  R-3 stays as the nondeterminism check; dishonesty mitigated by
  diversity, a disposition / standing-policy choice.
