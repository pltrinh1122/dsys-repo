# K1 repair spec — the updater's accretion writer

**Status: ADOPTED (DR-CMD-039)** — framed as a governed matter
(narrowed claim, dual-scope decomposed at START, X1–X4 clear).
Evaluated against the adoption conditionals (draft verdict:
adopt-with-conditions); three evaluation findings remediated
(D2 reordered to `driving → verifying → committing → done`,
D3 authority named as extension, D5/D5a payload-envelope +
git dependency), plus the F-A amendment (D4 cumulative via
watermark, D4a abort, D4b bounded residual). Adopted 2026-09-21,
not built. I-18 (commit-completeness), I-19 (cumulative
payload-canonicity), I-20 (append-only) named; numbering
provisional pending no earlier claim.

## Glossary

- **Accretion repo:** the per-instance append-only git repository (the
  canonical label; `git-store` is a recorded alias) that journals accreted
  state. Initialized by the installer; identity `dsys-accretion`.
- **Accreted set:** the instance state that must survive reinstalls —
  `var/` contents (config, state, log, cache, manifest), as distinct from
  the software tree.
- **Commit authority:** whose authorization an accretion commit requires.
  *Standing authorization* (the default, ratified 2026-09-20): the
  operator's standing disposition covers journaling; commits happen without
  asking. *Operator authorization* (`--accretion-require-authorization` /
  `accretion.commit_authority: operator`): dirty state prompts; "no" refuses
  rather than clobbers or silently skips. (installer-spec.)
- **Drive:** one execution of the updater flow from `idle` through a
  terminal state (`done` / `failed`), triggered by the poll timer.
- **Event log:** the ordered record of a drive's flow-transition events —
  the R1 source of truth for deterministic replay.
- **Promotion record:** the `PromotionRecord` emitted when a version is
  adopted (the promotion bridge; step-change provenance).
- **R1:** the evaluated replay story (updater-spec §3): a drive replays by
  transcript re-validation, never by re-execution. Currently assumes a
  durable log it does not provide.
- **World:** in `core/package/updater.py`, everything outside the governed
  flow that the golden run scripts — the fixture stand-in for the
  production environment (filesystem, repo, installer).
- **Writer:** the component that commits the event log and promotion state
  to the accretion repo. The missing piece this spec designs.

## The kill restated

K1 (updater-spec §9): "updater accretion should not be transient and is
persisted to accretion repo" — **KILLED**. The build persists nothing; the
driver's events live in an in-memory `SystemState`. The spec had assigned
accretion persistence to the installer ("the installer's own doing, not the
automaton's") — but the installer's pre/post snapshots commit at
install-time only. The updater's event log accrues *between* installs with
no writer. A crash between installs loses replay. R1's durability premise
is unevaluated and currently false.

## Narrowed claim

The updater's inter-install event log and promotion state are durably
committed by an updater-owned writer to the instance's accretion
repository, so that a crash between installs cannot lose replay and the R1
durability premise holds.

## Scope (dual, decomposed at START — conjunctive adoption)

- **Runtime scope:** the flow gains a `committing` task state (9 states, 16
  transitions); the drive's durability guarantee becomes "every terminal
  drive leaves a commit." Alters what the machine guarantees.
- **Package scope:** the writer as a flow tool, golden-run cases, validators
  for the new invariant. `updater.py` / `updater_golden_run.py` change; no
  validator weakened.

## Decisions

- **D1 — commit-step-in-the-drive (not a standing cadence).** Every drive
  that completes verification commits before terminating: the commit
  captures the full event log including the verification outcome, the
  promotion record, and the policy-gate decision record. One writer, one
  cadence (the drive), no concurrent committers. *Narrowed at evaluation:*
  a drive that aborts in `driving` or `verifying` never reaches the commit
  step — its events live in the flow log and surface via the `failed`
  terminal state, and a crash mid-drive loses that drive's events. Accepted
  residual: R1 replays transcripts of drives, and an incomplete drive has
  no complete transcript; the durability guarantee attaches to completed
  drives, which is the inter-install unit the narrowed claim covers.
  *Recommendation; disposition open.*
- **D2 — a new `committing` task state, in the flow table.** Placed
  `driving → verifying → committing → done`: the commit is governed, not
  ambient, and it captures the *complete* record — the verification outcome
  is known before the commit is written. (`driving → committing →
  verifying` was considered and rejected at evaluation: the terminal state
  isn't known at commit time, so the commit message couldn't name it
  honestly, and a post-commit doctor failure would leave a promotion
  record in the repo with no covering failure commit.) Transitions:
  `verifying` keeps three out-edges (`run_completed`[doctor_ok] →
  `committing`; `run_completed`[¬doctor_ok] → `failed`; `run_aborted` →
  `failed`); `committing` adds two (`run_completed`[commit confirmed] →
  `done`; `run_aborted` → `failed`, the existing edge). The alternative —
  folding the commit into `verifying`'s run-book — mixes verification with
  mutation (plane-discipline smell); explicitness wins. 8→9 states, 14→16
  transitions; I-14/I-15 hold by the same construction as every other task
  state.
- **D3 — standing commit authority; operator mode fails closed.** The
  2026-09-20 ratification covers *the installer's* journaling — extending
  standing authorization to the updater's writer is a scope extension this
  disposition is asked to grant explicitly, not a direct application: same
  repo, same `dsys-accretion` identity, same operator disposition, a new
  writer. If granted, the writer commits without asking. If the instance
  config sets `accretion.commit_authority: operator`, the autonomous drive
  cannot prompt (no terminal) — so the commit step **refuses** via
  `run_aborted → failed`: no prompt, no silent skip. This composes with the
  K2 fail-closed philosophy (DR-CMD-038): autonomy never degrades to
  silence. *Recommendation; disposition open.*
- **D4 — what commits (cumulative, per F-A).** All events since the last
  commit — not just the current run's. Per-run coverage orphans events:
  a drive that fails at `committing` would leave its events uncommitted
  forever, and every drive's terminal transition (which occurs after the
  payload is written) would never be committed by anyone. The writer
  locates the frontier via a **watermark**: each commit's payload records
  the event-range it covers, and the writer diffs the flow log against the
  last commit's watermark. Commit skipped when there is nothing new —
  the installer's existing rule ("a commit is skipped when there is
  nothing to commit," installer-spec §12). The payload comprises the
  run's transition events (the R1 replay source), the promotion
  record(s), the policy-gate decision record, and the verification
  outcome, serialized as canonical JSON (sorted keys), content-hash
  named; the commit message names the flow-run id and the source state
  (`verifying`) — terminality follows from the transition taken out of
  `committing`, so the message never claims a terminal state the drive
  hasn't reached. The exact canonical form is build detail.
- **D4a — Q2 resolved: abort, not retry (per F-B).** The `committing` step
  policy is abort (the "others abort" default, updater-spec §1 — like
  `driving`, a failed commit is never blindly retried). A half-written
  commit (git succeeded, tool crashed before reporting) therefore cannot
  double-commit: at most one commit attempt per drive, and the next
  drive's cumulative commit is the retry. I-18's exactly-one holds by
  construction.
- **D4b — bounded residual (per F-C).** Drive N's terminal edge
  (`committing → done`) rides drive N+1's cumulative commit. A crash in
  the inter-drive window loses at most the terminal edge — never the
  payload. (No clean alternative: end states have no run-books.)
- **D5 — the commit is a pure function of the logged events.** Deterministic
  bytes from deterministic events: replay re-validates the transcript
  against the committed bytes (hash equality). **Payload/envelope
  distinction (evaluation):** determinism attaches to the canonical
  *payload* bytes (D4's content hash). The git envelope — author/committer
  timestamps, commit hash — is transport, not replay identity: two runs of
  one drive produce different commit hashes, and replay must validate the
  payload bytes, never the git hash. R1's evaluated story stands
  unchanged; the repair makes its durability premise true.
- **D5a — git is a hard dependency of the updater flow (evaluation, R5).**
  The flow previously had no git dependency; the installer did. Declared:
  the drive's durability guarantee rests on git being present and the
  accretion path writable. If git is absent from PATH at commit time, the
  commit tool aborts → `run_aborted → failed` — fail-closed, composing
  with K2 (DR-CMD-038). The updater's drive never silently skips the
  commit the way interactive installs may skip accretion.
- **D6 — the writer never rewrites history.** Append-only commits; no
  amend, no rebase. (In the spirit of K2's D5 "never `--overwrite`" — the
  updater's tools don't do destructive git operations.)
- **D7 — K3 boundary premise (explicit, like K2's D6).** The writer is a
  flow *tool* — it needs no ambient hand; the commit step is in the table.
  But the production process that runs the flow and holds the repo handle
  is K3-unbuilt; the fixture models it as a World fact. This spec designs
  the governed side; the process side composes with K3.

## Falsification

- **F1 — "the installer's snapshots already cover this."** Killed by K1
  itself: install-time only; inter-install accrual has no writer.
- **F2 — "put the writer in the driver, outside the flow."** Killed: the
  driver is K3-unbuilt and ambient; a writer outside the flow table escapes
  I-14/I-15/totality. If the commit isn't in the table, it isn't governed.
- **F3 — "the modeled `promotion_recorded` fact is enough."** Killed: a
  World fact is not a commit; a crash loses it. The `verifying` run-book's
  "confirm the accretion commit" is currently a modeled fact — the repair
  makes it real, and the `verifying → done` guard requires the confirmation.
- **F4 — "commits break deterministic replay."** Killed by construction
  (D5): pure function of events, replay by transcript re-validation. The
  golden run will pin hash equality across commit and replay.

## Acceptance (checkable sequences)

**New validators (R3, evaluation):** the expansion introduces three
invariants, each with a validator predicate — **I-18** commit-completeness
(every drive reaching `committing` leaves exactly one commit);
**I-19** payload-canonicity (the committed payload is byte-equal to the
canonical serialization of the events since the last commit); **I-20** append-only (no
committed payload is ever mutated — amend/rebase refuse). (I-17 is taken
by the mutation playbook's reason requirement.)

1. A drive reaching `done` leaves exactly one commit in the accretion repo
   containing all events since the last commit (the cumulative frontier —
   I-18), content-hash named; the commit message names the flow-run id
   and `verifying`.
2. A drive that aborts in `driving` or `verifying` reaches `failed` with no
   commit — and the golden run asserts exactly that (acceptance of the D1
   narrowing: durability attaches to completed drives; the incomplete
   drive's events surface via the `failed` terminal state).
3. Crash simulation: wipe the World between drives except the accretion
   repo; the replayed transcript validates byte-equal against the committed
   payload (acceptance of the narrowed claim — the R1 premise made true).
4. Flow table: 9 states, 16 transitions; `_flow_totality` and
   `_transition_determinism` pass over the new table (acceptance of D2).
5. `committing → done` requires commit confirmation in the guard — a drive
   whose commit step was skipped or aborted cannot reach `done`
   (acceptance of F3's kill; note the guard moved from `verifying → done`
   with the D2 reordering).
6. `accretion.commit_authority: operator` + updater drive → the commit step
   refuses via `run_aborted → failed`; no prompt attempted, nothing
   silently skipped (acceptance of D3).

## Open questions (G6)

- Q1: the exact canonical serialization of the committed payload (build
  detail, but the golden run must pin it).
- Q2: **resolved** — abort, not retry (D4a per F-B). A transient lockfile
  failure surfaces via `run_aborted → failed`; the next drive's cumulative
  commit retries it. No step-level retry fork remains.
- Q3: the production repo-handle holder — composes with K3 (D7); this spec
  does not design it.
