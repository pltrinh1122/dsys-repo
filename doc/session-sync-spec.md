# dsys Session Sync Protocol — Design Spec

Status: draft — approved for spec 2026-09-19; not implemented.

Scope: how session state moves between writers (devices, fleet nodes) via a
hosted sync service, with seamless switching for one operator and safe
multi-writer convergence for many. **Client-side protocol only** — the
hosted service implementation is a separate build.

Builds on: the provenance-log proposal (2026-09-19). The per-writer
hash-chained segments defined here are its normative transport
realization. The durability half of that proposal (atomic writes,
transcript custody, end-marked transcripts) is separate and still pending.

## 0. Background and non-goals

Motivating cases: (a) one operator across mobile + desktop, switching
fluidly with no sync ceremony; (b) a dsys with many nodes, hence many
writers, converging on shared session state.

Non-goals: multi-principal sharing / access control (deferred — touches
DR-1 and disposition scoping); the hosted service build (API, auth,
storage); checkpoint/compaction of logs (§12); real-time streaming
(poll-based, consistent with the system's scheduled checks).

## 1. Concepts

- **Writer**: a device or node holding a `writer_id` (uuid) and a key.
  Every mutation is attributed to exactly one writer.
- **Entry**: one mutation record (§3).
- **Segment**: a writer's append-only, hash-chained entry sequence.
- **Session**: the set of segments for one `session_id`.
- **Converged view**: the deterministic merge of a known segment set (§6).
- **Divergence**: two entries mutating the same entity with no causal
  relation between them (§7).

## 2. Writer identity and enrollment

- `dsys session init`: mints `session_id`, a session key (Secure Vault),
  and this device's `writer_id`; writes `var/sync.json`
  (`session_id`, `writer_id`, service). The init entry is the session's
  genesis anchor.
- `dsys session join SESSION_ID`: enrolls this device as a new writer.
  v1: the session key arrives via the Secure Vault (same account), so
  joining is near-automatic for the operator's own devices. The join
  entry's `observed` (§3) is set to the current tips: a new writer starts
  causally *after* all known history, so enrollment never manufactures
  spurious conflicts.
- Writer metadata (device label) is advisory. Identity is `writer_id` +
  key. Key rotation, revocation, and cross-principal enrollment are
  deferred (§12).

## 3. Entry format (normative)

Canonical JSON. Fields:

- `writer_id`, `writer_seq`: `writer_seq` starts at 1, increments by 1,
  gapless per writer.
- `prev_hash`: hash of the writer's previous entry; null at genesis.
- `observed`: map of `writer_id` → `entry_hash` of the tip that writer
  had observed when this entry was written. These are the causal edges
  (Lamport-style, no clock). May be partial — only writers with known
  tips at write time.
- `kind`: `state_write` | `transcript_sealed` | `disclosure_written` |
  `disclosure_triaged` | `disposition_recorded` | `divergence_resolved` |
  `checkpoint` (reserved, §12).
- `entity_ref`: `{collection, id}` — the entity mutated, when applicable.
- `payload`, `payload_hash`: the mutation itself (v1: inline).
- `entry_hash`: sha256 over the canonical entry excluding `entry_hash`.

### 3.1 Record identity and labels

- **Identity.** Record IDs are uuid4 or content-derived, minted
  uncoordinated across writers — no sequential or global ID assignment
  (per the id-minting falsification, 2026-09-19). Order is per-writer
  seq (§6); identity never encodes order and never needs coordination.
- **Labels (required).** Every record carries a human-readable `label`
  in its payload, *associated with* the ID, never replacing it.
  Example: record `9f2c…` labeled `cos-rule-1`.
  - Syntax: `[a-z0-9][a-z0-9-]*`; convention `{kind}-{slug}`
    (`cos-rule-1`, `disclosure-drain-3`).
  - Assigned by the creating writer at creation; changed by writing a
    new entry against the same record — renames ride §7's conflict
    machinery, so concurrent renames of one record diverge like any
    other mutation.
  - **Reference rule.** Durable references (entries, dispositions,
    provenance) cite **IDs**. Human interfaces (CLI args, prompts, CTA
    responses) accept **labels** and resolve them to IDs at the
    boundary. A renamed label never breaks a recorded reference.
  - **Uniqueness, per session.** The converged-view computation builds a
    label index alongside the entity merge; duplicate labels surface as
    `label-ambiguities` next to `open-divergences`. Resolution: the
    owning writer relabels (causally ordered, no governance needed);
    contested renames fall back to §7.

Encryption: entries are encrypted with the session key *before* transport.
The service sees only `session_id`, `writer_id`, seq ranges, and blob
sizes — never plaintext, never semantics.

## 4. Segment rules

- **Append-only.** A writer never mutates, reorders, or rewrites its
  segment. There is no edit and no delete.
- **Gapless per writer.** A gap in a pulled segment means incomplete
  sync — detectable, and the client backfills before converging.
- **Chain verification on every pull**: recompute each `entry_hash` and
  each `prev_hash` linkage; check per-writer seq monotonicity. A break is
  an integrity event: the segment is excluded from the converged view
  and surfaced via `session status` and `doctor` — never silently
  dropped, never silently accepted.

## 5. Transport (dumb by design)

- The service is an authenticated opaque blob store: put/get of segments
  keyed by `(session_id, writer_id)`. No server-side merge, no ordering,
  no interpretation. "Trust nothing the service says" — the client
  verifies everything (§4).
- `push`: client sends `(writer_id, entries from last_acked_seq+1..tip)`;
  service acks the tip.
- `pull`: client sends known tips `{writer_id: tip_hash}`; service
  returns entries after those tips.
- Poll-based; no streaming in v1. Client lifecycle rule (the
  seamless-switching rule): a client SHOULD push on background and pull
  on foreground.

## 6. Converge rules (deterministic)

- The converged view over a known segment set contains all entries,
  ordered as a linear extension of the causal partial order — causality
  from the transitive closure of `observed` edges plus per-writer
  `prev_hash` chains — with ties broken deterministically by
  `(writer_id, writer_seq, entry_hash)`. Same segment set → same view,
  on every client. No clock anywhere.
- Causally-ordered appends merge **mechanically**, no governance needed.
  This is the common case: DR-1 already partitions work per
  (principal, authority-scope), so writers overwhelmingly touch disjoint
  entities.
- Per-writer seq replaces the global counter: order is *derived*, not
  minted. Interaction note: DR-5's global `Disclosure.seq` and I-10's
  per-scope seq were designed single-writer. Within one writer the
  existing rules are unchanged; in converged views, cross-writer ordering
  uses the `(writer_id, writer_seq)` composite. Full migration of DR-5
  counters to composite keys is noted, not done here.

## 7. Divergence → disposition (never silent merge)

- **Mechanical conflict rule.** Entries e1, e2 conflict iff they carry
  the same `entity_ref` and neither causally precedes the other (via the
  closure in §6) within the known segment set.
- **Granularity is load-bearing.** `entity_ref` must name the finest
  natural unit mutated — an individual disclosure, a single run's state —
  never "the session," "the ledger," or a whole snapshot. A coarse
  `entity_ref` recreates the single-file magnet at the semantic level:
  two writers touching disjoint parts of one coarse entity would
  false-conflict on every write. The protocol removes mechanical
  contention; only fine-grained refs keep semantic contention honest.
- Conflicting entries are **excluded** from the converged view and
  appear in the `open-divergences` view:
  `{divergence_id, entity_ref, entries[], writers[]}` — computed, like
  `verification_view()`, as a pure function over known segments.
- Resolution is a `divergence_resolved` entry authored **through the
  existing governance**: a triage or overrule disposition,
  human-terminal, citing the `divergence_id` and the surviving entry
  (or a disposer-authored merged payload). The resolution entry
  causally follows all conflicting entries (`observed` includes their
  tips), so the conflict closes deterministically on every client
  thereafter.
- This is I-15 ("no silent resolution") applied to sync. GitHub
  auto-merges text; we never auto-merge meaning.

## 8. Single-operator regime (the degenerate case)

- Pull-on-foreground + push-on-background keeps branches
  fast-forwardable: each new entry's `observed` includes the other
  device's tip, so no divergence arises. **No lease, no checkout
  ceremony** — the lease model is superseded by this section.
- True concurrency (both clients foreground, appends interleaved with no
  pull between) produces a genuine divergence → surfaced per §7. Rare
  for one human; visible when it happens, which is the standing rule.

## 9. Validation pinning

- Every validation cites its segment set: `{writer_id: tip_hash}`.
  `referee` records the pins in its output envelope. Deterministic
  replay = same segments → same converged view → same verdict.
  "Latest" is never an input; an unpinned validation is refused.

## 10. CLI surface

- `dsys session init` — create session, print `session_id`.
- `dsys session join SESSION_ID` — enroll this device as a writer.
- `dsys session push` / `dsys session pull` — manual; automatic per the
  lifecycle rule in §5.
- `dsys session status` — tips per writer, ack state, divergence count,
  integrity findings.
- `dsys session divergences` — the `open-divergences` view.
- Converge is a pure client-side function, not a command. Divergence
  resolution goes through governance, not through a sync command.
- **Profile**: full only — sync needs network. Base profile → clean
  refusal naming the profile (exit 1, per §10 of the installer spec).
- **Config**: `sync_service:` URL in `etc/config.yaml` (inert in base);
  the session binding in `var/sync.json`, preserved across
  upgrade/uninstall like `var/state`.

## 11. Trust model

- End-to-end: the service is a blind store (§3, §5). Keys live in the
  Secure Vault per device; v1 key distribution assumes the operator's
  own vault (same account). Cross-principal key sharing is deferred
  with multi-principal sharing.
- The client verifies chains, hashes, and per-writer seq on every pull
  (§4); validations cite pins (§9). A compromised or buggy service can
  withhold data (visible as stalled tips) but cannot forge history
  (breaks the chain → integrity event).

## 12. Open / deferred

- **Checkpoint/compaction.** Append-only logs grow unboundedly. A future
  `checkpoint` entry (converged snapshot + "entries before N absorbed")
  — not spec'd here.
- **Enrollment beyond same-account vault**: new principal's device, key
  rotation, writer revocation.
- **Multi-principal sharing**: access control and disposition scoping
  across principals.
- **The hosted service build**: API, authn/authz, storage backend —
  separate project. This spec is the client side only.

## 13. Falsifiers (pre-registered)

- **F-S1.** "Converged views are identical on all nodes." False —
  convergence is eventual; transient divergence is normal; validations
  pin their segment sets (§9).
- **F-S2.** "The service orders or merges entries." False — dumb
  transport; order is derived client-side (§5, §6).
- **F-S3.** "Conflicts auto-resolve (last-writer-wins / CRDT merge)."
  False — semantic conflicts route to disposition; only
  causally-ordered appends merge mechanically (§7).
- **F-S4.** "A writer can rewrite history." False — append-only; a
  rewritten prefix breaks the chain and is rejected + surfaced on pull
  (§4).
