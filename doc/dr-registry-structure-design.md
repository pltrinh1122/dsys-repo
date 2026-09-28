# DR registry structure — design spike

- Status: PROPOSED (design only; no build commissioned)
- Date: 2026-09-27
- Commissioned by: DR-CMD-105 (O2 of the "next best action" /pb-decide; Peter, ~19:00 PDT)
- Precondition for: tranche 2's DR registration channel (DR-CMD-102)
- Note: the DR registrar profile was renamed `dr_registrar` → `chronicler` (DR-CMD-107); this document uses the adopted name throughout.

## 1. Matter

Design the Decision Record (DR) registry as a contracted structure: the
machine-readable store against which the `chronicler` (DR-CMD-100) vets
staged DR drafts and into which well-formed records are registered
append-only. Today `doc/decision-records/` is a directory of markdown files
plus ambient-maintained conventions (the manually tracked next-free chain);
there is no contracted structure, so the chronicler's write channel
`decision-record-registry` names nothing and compile refuses at routing.

This spike answers four questions (§5) and renders a verdict on tranche 2's
two conditions (§8). It designs; it does not build. The DR recording any
disposition on this design comes when Peter disposes — it is not written
here.

**Key terms** (used inline throughout; full glossary in §10):

- *Contracted structure*: a store whose schema, invariants, and refusal cases
  are specified and verified, and whose writes go only through a contracted
  tool. (Precedent: the content-addressed append-only artifact registry,
  `core/package/artifact_registry.py`, built under DR-CMD-091.)
- *Contracted tool*: a `lib/dsys/tools/` module with `TOOL_NAME` and
  `run(ctx)`, admitted to the compiler's closed tool registry (J1) through
  the DR-CMD-055 tool discipline (spec + implementation + golden run).
- *Tip*: the registry's current head — the highest registered identifier
  number, from which the next assignable number derives.
- *Reservation*: a withheld identifier number (e.g. DR-CMD-059, reserved for
  the Product Vision Board Definition of Done) that the sequencing rule must
  skip and that only Operator business may redeem.

## 2. Requirements (from the chronicler's six vetting checks, DR-CMD-100)

The store must support, mechanically:

1. **Identifier sequencing** — tip tracking; next-in-sequence assignment;
   no gaps, no duplicates; reservations honored (059 and any future).
2. **Content-hash dedup** — sha256 pinned per record; duplicate hash under a
   new identifier detectable (the chronicler defers it; the store must be
   able to answer "hash already registered?").
3. **Supersedes/addendum chain integrity** — records carry `supersedes[]`
   and `addendum_to`; targets must exist at write time; chain traversal
   queryable.
4. **Cited-premise resolution** — every `premise_refs[]` entry must resolve
   to a registered identifier (by-id query).
5. **Append-only** — no row is ever mutated or deleted; corrections are new
   records (addenda) or supersessions.
6. **Query surface** — tip, by-id, by-hash, chain traversal
   (supersedes/addendum), reservations list. All computed from the store,
   never asserted.

Plus the standing disciplines: content-addressing (every record pins sha256
of the exact registered bytes), disposition-gated writes (registration rests
on a disposition ref, never on drafting alone), fail-closed refusals with
verbatim reasons, deterministic replay.

## 3. Options

### Option A — reuse the artifact registry literally

Register DRs as artifacts: `kind="decision-record"`, `name="DR-CMD-100"`,
via the existing `register()` and the newly landed `tool-register-artifact`.

Fit assessment:

- Identifier sequencing: the registry tracks `seq` (append order) and
  versions per `(kind, name)` — neither is DR numbering. "Next number",
  reservations, and no-gap enforcement would live entirely outside the
  store (in the chronicler's vetting). The store could not answer "what
  is the tip?" without a convention layered on top.
- Content-hash dedup: `find_by_sha256` exists — works.
- Chains: `ArtifactRecord` has no relation fields. Supersedes/addendum
  would need new fields (a schema change — at which point this is no
  longer "reuse") or a sidecar index (at which point the registry is not
  the store of record for chains).
- `commission_id`: DRs are not commissioned customizations; the field
  would take a sentinel or be left meaningless. The post-release
  commission rule (same commission + new bytes → refused) misfires on DRs:
  it is either dead weight or, worse, a refusal case that can trigger for
  the wrong reason.
- `version`: DRs are immutable; a DR never becomes v2. The field would sit
  at 1 forever — a second dishonest field.

Verdict: reuse-literally requires sentinel values and dead fields. It is
the channel-substitution class of workaround the DR-CMD-096/097/100
deviations refused, moved one layer down. **Not recommended.**

### Option B — dedicated DR registry structure (recommended)

A DR-specific contracted structure that ports the artifact registry's
*mechanical pattern* (JSONL append-only log, sha256 pinning, `seq`,
disposition-gated, fail-closed refusals, idempotent duplicate handling)
without inheriting its *schema*:

```json
{"id": "DR-CMD-100", "seq": 87, "sha256": "…", "bytes_len": 5120,
 "status": "adopted", "date": "2026-09-27",
 "supersedes": [], "addendum_to": null,
 "premise_refs": ["DR-CMD-096", "DR-CMD-097"],
 "disposition_ref": "chat 2026-09-27 ~18:29 PDT: proceed",
 "selector": "Peter"}
```

Plus registry-level metadata (reservations):

```json
{"registry": "decision-record-registry", "reserved": [59], "genesis": "…"}
```

Store-level invariants (enforced at write, fail-closed, reasons verbatim):

- `id` well-formed (`DR-CMD-###`); not already registered.
- `n == tip.next` **or** `n` redeems a reservation (redemption is
  operator business; the standing path refuses reserved numbers — this is
  the chronicler's check 2, re-enforced at the store as defense in depth).
- `sha256` not already registered under a different id.
- every `supersedes[]` / `addendum_to` / `premise_refs[]` entry resolves to
  a registered id.
- `disposition_ref` non-empty (registration rests on disposition).

Queries (§2.6) are pure functions over the log: tip = max id number;
by-id/by-hash via index; chains by traversing relation fields;
reservations from metadata.

Verdict: honest fields, DR-shaped invariants, no sentinels. The build is
small because the entire mechanical pattern is precedented. **Recommended.**

### Option C — hybrid: artifact registry + DR sidecar index

Store DR bytes in the artifact registry (content-addressing reuse) and keep
DR semantics (sequencing, chains, reservations) in a sidecar index file.

Verdict: two stores of record for one logical registry — the sidecar can
drift from the log, and every query needs a join. It splits the invariant
set across two structures with no single enforcement point. Worse than B,
more complex than A. **Not recommended.**

## 4. Proposed structure (Option B, detailed)

- **Location**: `doc/decision-records/registry.jsonl` — alongside the
  markdown files, versioned in git with them. The `.md` files remain the
  human-readable surface; the JSONL is the contracted structure (canonical
  for tip, by-id, by-hash, chains, reservations). The registry pins the
  sha256 of the exact markdown bytes, so the two cannot silently diverge:
  a `.md` file whose hash matches no row is unregistered, whatever the
  directory listing suggests.
- **Write path**: only through the future contracted tool
  `tool-register-decision-record` (tranche 2, not commissioned). Direct
  ambient/processor writes to the JSONL are refused by discipline — the
  same rule the artifact registry got when `tool-register-artifact`
  closed its direct-call gap. The tool is hermetic (no network, no clock);
  the registry root is passed in, never defaulted.
- **Who may invoke the tool**: the `chronicler` on its standing operator
  disposition (scheduled sweep of the staging area), or per-event operator
  disposition. Arrivals never trigger registration; malformed drafts defer
  for operator disposition (proposer≠disposer preserved).
- **Reservations**: registry metadata (`reserved: [59, …]`); redemption is
  an operator act recorded as its own registry event. The standing path
  refuses reserved numbers verbatim.
- **Migration (genesis import)** — open design point, not settled here:
  the ~105 existing DRs predate the registry. Options: (i) backfill in id
  order with provenance labeled `genesis-import` and disposition refs
  attested by git history; (ii) start the registry at the next free number
  and treat pre-registry DRs as implicitly registered (weaker — premise
  resolution needs them). (i) is favored; the exact genesis procedure is
  for the build commission, with the provenance labeling load-bearing:
  never present an imported row as tool-registered.

## 5. The four questions

**Q1 — reuse vs separate.** Separate (Option B). DR-CMD-099's reuse holds
for schema artifacts because they *are* versioned customizations —
`(kind, name, version)` fits them exactly. DRs are sequenced immutable
records with reservations and chains; the shapes differ, and the reuse
does not generalize. What generalizes is the mechanical pattern, not the
schema.

**Q2 — does tranche 2's DR channel collapse into `tool-register-artifact`
+ a schema?** No — stated plainly. Even maximal reuse of the pattern
leaves DR-specific refusal cases (not-next-in-sequence, reserved-number,
dangling premise/supersedes/addendum targets) that `tool-register-artifact`
cannot express without corrupting its own contract. A DR-specific
contracted tool remains required. What *does* dissolve is the research
risk: the tool is a small, fully precedented build (spec + golden run under
DR-CMD-055 discipline), because every mechanism it needs already exists
and is verified.

**Q3 — condition (ii): demonstrated operational need.** The honest answer
is **not yet**. Facts: DRs are produced at high rate (~105 in ~10 days),
but the production path is ambient chat labor writing markdown directly to
`doc/decision-records/` — there is no staging area, no draft queue, and no
mechanical producer of DR drafts. A registration channel with no producer
is a bridge to nowhere; building it now would be speculative tooling
(the G5 concern from DR-CMD-102). **The trigger that changes this**: adopt
the staged-draft discipline — processor/transcriber subagents (which
already exist as a standing pattern after each disposition) stage *drafts*
(markdown + metadata) into a staging area instead of writing registry
files directly; the `chronicler`, once registered, vets on standing
disposition and the tool registers. Volume exists; the staging discipline
is what's missing. Name it: condition (ii) is met when DR drafts flow
through a staged pipeline that the chronicler services.

**Q4 — location and writers.** `doc/decision-records/registry.jsonl`,
git-versioned beside the markdown; writes only through the future
contracted tool, invoked on standing or per-event operator disposition
(§4). Direct JSONL writes refused by discipline.

## 6. What this design does not do

- Commission the build (no code, no tool, no registry file — this spike is
  design only, per commission).
- Settle the genesis import procedure (open, §4).
- Authorize tranche 2 (conditional per DR-CMD-102; condition (ii) assessed
  above as unmet).
- Write the disposition DR (that comes when Peter disposes on this design).

## 7. Recommendation

Adopt Option B as the design: a dedicated content-addressed append-only
DR registry at `doc/decision-records/registry.jsonl` with the
`DecisionRecord` schema and store-level sequencing/reservation/chain
invariants (§4), porting the artifact registry's mechanical pattern field
for field in discipline but not in schema. Do not shoehorn DRs into
`ArtifactRecord`. When condition (ii)'s trigger fires (staged-draft
discipline adopted), commission `tool-register-decision-record` under
DR-CMD-055 discipline — a small precedented build — plus the genesis
import with honest provenance labeling.

## 8. Verdict on the tranche-2 conditions

- **Condition (i) — DR-registry-structure design: MET by this document.**
  The design is complete at the spike level; the remaining open point is
  the genesis import procedure, scoped for the build commission.
- **Condition (ii) — demonstrated operational need: NOT MET.** No
  staged-draft pipeline exists; DRs are written directly by ambient labor.
  Trigger: adopt the staged-draft discipline (§5 Q3). Until then, building
  the DR registration channel is premature — the design above is held as
  the standing plan, not a build order.

## 9. Open questions

1. Genesis import procedure: exact provenance labeling and whether
   pre-registry DRs' disposition refs (chat renders) are recorded verbatim
   or normalized.
2. Whether the `.md` file landing in `doc/decision-records/` is part of
   the tool's effect or stays with the banking flow (recommended: banking
   flow; the tool stays hermetic to the registry root).
3. Reservation redemption record shape (registry event vs. DR itself).
4. Whether `status` transitions (e.g. proposed → adopted) are new rows or
   metadata — the chronicler only registers adopted records; proposed
   drafts live in the staging area, not the registry. Confirm.

## 10. Glossary

- **Addendum**: a new DR that amends an existing registered DR without
  replacing it; recorded via `addendum_to`.
- **Append-only**: rows are never mutated or deleted; correction is by new
  rows (addenda, supersessions).
- **Chain traversal**: following `supersedes[]` / `addendum_to` links
  across records (e.g. DR-CMD-094 supersedes DR-CMD-093's deferral).
- **Content-addressed**: each record pins the sha256 of the exact bytes
  registered; identity derives from content, not from filename.
- **Contracted structure**: a store with specified schema, invariants, and
  refusals, writable only through a contracted tool.
- **Contracted tool**: a `lib/dsys/tools/` module admitted to the
  compiler's closed tool registry (J1) via the DR-CMD-055 discipline.
- **Disposition-gated**: registration requires a `disposition_ref` — it
  rests on an operator disposition, never on drafting alone.
- **Fail-closed**: invalid input is refused with verbatim reasons; nothing
  is defaulted, invented, or silently repaired.
- **Genesis import**: the one-time backfill of pre-registry DRs into the
  new structure, with honest provenance labeling.
- **J1**: the compiler's closed-registry discipline — write-scope channels
  resolve only against contracted tools; unknown channels refuse loudly.
- **Reservation**: a withheld identifier number redeemable only by
  operator business (e.g. DR-CMD-059).
- **Standing disposition**: a pre-authorized instruction class under which
  an agent may act without per-event operator approval (D1).
- **Supersession**: a new DR replacing the force of an earlier one,
  recorded via `supersedes[]`; one supersession chain per domain.
- **Tip**: the highest registered identifier number; `tip.next` is the
  next assignable number.
- **Tranche 2**: the conditional second half of the tool-channel
  disposition (DR-CMD-102): triage channel tools + DR registration channel.
