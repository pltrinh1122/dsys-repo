# taxprep — Phase 1

Local-only CLI to transcribe tax documents (PDFs + OCR text) into structured
digital form, for amended-return preparation (Form 1040-X).

**Privacy rule:** real taxpayer material never leaves the operator's
workstation. See [COLLABORATION.md](COLLABORATION.md) for the two-session
protocol: the Architect side works with synthetic fixtures only, the
workstation operates real documents locally under blind orchestration,
and discrepancy reports travel as shapes, never values. No network
calls. Everything runs locally.

## Setup

```bash
cd ~/workspace/dsys/tax-prep
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Packaging

A plain `pip install .` (non-editable, e.g. the workstation's gate
install) gets a working package with no repo checkout present:
`medallion_schema.sql` ships inside the wheel via
`[tool.setuptools.package-data]` (`taxprep = ["*.sql"]`), and
`mstore.py` loads it through `importlib.resources` — never a
source-tree-relative path. Runtime dependencies are declared in
`pyproject.toml`: `pypdf`, `cryptography`, `mcp<2`, `pdf2image`,
`pdfplumber` (the bbox source for native PDFs). `tests/test_packaging_smoke.py`
guards this: it builds a wheel from a clean export, installs it into a
throwaway venv, and opens a DocumentStore with the source tree nowhere
on `sys.path`.

## Usage

```bash
# Ingest a directory of PDFs / .txt OCR files (recursive)
.venv/bin/taxprep ingest ./fixtures --data-dir ./data

# List documents, optionally filtered
.venv/bin/taxprep list --year 2024 --form W-2

# Show one document's extracted fields
.venv/bin/taxprep show <doc_id>

# Serve the visual validation UI (localhost only, default port 8471)
.venv/bin/taxprep review --data-dir ./data [--port 8471]
# then open http://127.0.0.1:8471/ in a browser

# Capital-loss carryforward chain from validated 1099-Bs (2023-2026)
.venv/bin/taxprep carryforward --data-dir ./data --filing-status single
# single year: .venv/bin/taxprep carryforward --year 2024 --filing-status mfs
# seed a 2022 carryover: --prior-st 4500 --prior-lt 1200

# Run the local MCP server over stdio (for Claude Code / MCP clients)
.venv/bin/taxprep mcp --data-dir ./data

# Mechanical verification (PII-free output for the blind orchestrator)
.venv/bin/taxprep verify --data-dir ./data [--year 2024]

# Relevance triage (labels only: relevant | irrelevant | needs_human)
.venv/bin/taxprep relevance [--year 2024]

# Gap analysis: transcript expectations vs ingested docs (+ local report)
.venv/bin/taxprep gaps [--year 2024]

# Machine-local config (set once; never committed)
.venv/bin/taxprep config set source_dir ~/tax-docs
.venv/bin/taxprep config show

# Message bus: publish / listen / tune (broadcast = commit + push)
.venv/bin/taxprep bus publish --topic tax-prep.ops --type run-done --payload '{"n_docs": 3}'
.venv/bin/taxprep bus listen --once
.venv/bin/taxprep bus tune --topic tax-prep.build
.venv/bin/taxprep bus whoami

# Per-person scoping (R21a): opaque person ids; names stay local
.venv/bin/taxprep person register "Alex Rivera"          # -> person-1
.venv/bin/taxprep owner suggest <doc_id>                  # shown, never auto-applied
.venv/bin/taxprep owner set <doc_id> person-1
.venv/bin/taxprep scope apply --in-scope person-1,person-2
.venv/bin/taxprep return assign <doc_id> person-1 joint|own|election
.venv/bin/taxprep show <doc_id> --meta                    # PII-free metadata

# 1040-X column-A builder (R21b): read-model over validated docs
.venv/bin/taxprep column-a --year 2023
```

`ingest` prints a summary table (counts by form × year) plus the list of
documents flagged `needs_review`. OCR text is stored under
`data/ocr/<doc_id>.txt`; records live in `data/documents.jsonl`
(gitignored — never commit taxpayer material). On the OCR route the
stored text keeps page structure (pages joined with form-feed `\f`
separators), and tesseract word boxes persist to the
`data/ocr/<doc_id>.words.json` sidecar (0700 dir) so R15/R19 geometry
can resolve `bbox_source="tesseract"` after ingest. The extraction
text itself is always the `"\n"` join — unchanged.

## End-to-end pipeline (canonical stages)

The pipeline has one ordered stage registry (`taxprep/pipeline.py`;
`taxprep pipeline stages` prints it). CLI, docs, and accounting all
reference these names:

| # | stage | kind | what happens |
|---|-------|------|--------------|
| 1 | INGESTION | mechanical | `ingest`: intake PDFs / OCR text, native/sidecar/OCR routing, per-file R6 accounting |
| 2 | CLASSIFICATION | mechanical | form-type per page/section (runs inside ingestion) |
| 3 | EXTRACTION | mechanical | box-level fields / transcript parsing (runs inside ingestion) |
| 4 | RELEVANCE | mechanical | `assess_relevance`: relevant / irrelevant / needs_human labels |
| 5 | REVIEW | **human** | operator reviews each doc against source evidence in `taxprep review` |
| 6 | VALIDATION | mechanical | apply the operator's recorded corrections → validated |
| 7 | VERIFICATION | mechanical | `verify_all` gates; fail fast with reason codes |
| 8 | CARRYFORWARD | mechanical | Schedule D worksheet chain from validated 1099-Bs |

`GAP_ANALYSIS` rides alongside as kind=analysis — it uses transcripts,
is not a gate, and never blocks the pipeline.

The corrected order puts RELEVANCE (4) *before* REVIEW (5): it needs only
tax_year/form_type/OCR hash — all available post-extraction — so the
mechanical triage lands before the human looks at the queue, and
`irrelevant` documents are hidden from the review queue from the start
(auditable via `--include-irrelevant`, restorable via
`relevance-override`). A **validated** document is relevant by
definition — human judgment dominates mechanical rules; the mechanical
rules never demote it.

```bash
# List the canonical stages
.venv/bin/taxprep pipeline stages

# Run the mechanical stages in order (REVIEW prints an OPERATOR STEP
# marker and is skipped -- it is never executed by the runner)
.venv/bin/taxprep pipeline run --data-dir ./data [./fixtures] [--from STAGE] [--to STAGE] [--year Y]

# Explicit operator override of a relevance verdict (recorded with
# reason + timestamp in relevance_overrides.jsonl; honored on re-runs)
.venv/bin/taxprep relevance-override <doc_id> relevant|irrelevant|needs_human --reason "..."

# The human validation queue (irrelevants excluded by default)
.venv/bin/taxprep validation-queue [--year Y] [--form F] [--include-irrelevant]
```

`pipeline run` prints a banner per stage (`── STAGE 4/8: RELEVANCE ──`)
plus each stage's own accounting, and stops at the first failure with
the stage's reason code. `--from`/`--to` slice the sequence
(case-insensitive stage names). All pipeline output is PII-free
(stage names, counts, doc_ids, reason codes only); the full
PII-bearing carryforward report stays operator-local.

### Medallion storage & the silver layer (Arc B)

Ingested bytes land in a medallion store (`<data_dir>/medallion.sqlite`,
WAL; DDL in `taxprep/medallion_schema.sql`):

- **bronze** — exact source bytes, content-addressed by sha256, with
  one alias row per path the bytes were seen at. Same bytes under any
  name or path = one bronze object (I1/I3): re-ingesting is a no-op
  for state (I2), and duplicates can never double-count.
- **silver** — one `silver_doc` per document (mirrors the operational
  field store in `fields_json`) plus typed **artifacts**
  (`taxprep/silver.py`, W2): `field` per fields-dict key, `payer` per
  payer block, `lot` per 1099-B lot, `section` per R1 split section.
  Artifact ids are stable —
  `sha256(doc_id:bronze_hash:page:type:anchor)[:32]` (the doc_id is
  included because one bronze routinely feeds many silver docs: R1 split
  children, CSV rows) — so re-running a
  derivation reproduces byte-identical rows (I5).
- **decision log** — append-only: every validate/edit (review),
  exclusion, duplicate/supersedes ruling, conflict choice, and
  relevance override is recorded with actor + timestamp. Decisions
  survive re-derivation (I6).

Derivations are versioned: `EXTRACTOR_VERSION` (`taxprep/extractors.py`,
currently `"2"`; `"1"` is the pre-medallion era) plus a config hash over
the derivation config (`taxprep/silver.py: derivation_config()`).
Ingest skips derivation entirely on a cache hit for
`(bronze, EXTRACTOR_VERSION, config_hash)`. On a version bump, silver is
rebuilt with Operator decisions preserved: validated values win over
re-derived values (changed → keep + `re_review` flag); a validated
field that vanished from the new extraction is dropped and its
decisions are flagged `orphaned` in the log (rows are never deleted).

`taxprep sync` applies the bronze-level orphan rule: a bronze object
with zero on-disk alias paths has its silver docs flipped to
`ORPHANED` (values preserved). The duplicate-assessment hooks
(`taxprep/duplicates.py`: `assess_new_bronze`, `assess_silver_doc`) run
after every ingest; they are advisory and never fail the ingest.

### Encrypted PDFs

Encryption is detected with pypdf and the **empty password is tried
first**. Owner-password-only PDFs (empty user password — common on
government and financial PDFs) proceed normally: the document ingests
and records `encryption="owner-only"` as provenance (operational
metadata, blind-orchestrator safe, same class as `text_source` /
`ocr_engine`; it crosses the MCP boundary). The OCR route applies the
same try-empty-password-first logic — it hands the engine an
unencrypted copy in a private temp dir and never touches `src`.

A PDF that still needs a **user** password becomes BLOCKED with
reason code `"encrypted"` for the Operator to decrypt. Passwords are
never handled here — no password flag, prompt, or storage exists in
the codebase. (AES-encrypted PDFs need the `cryptography` package,
a hard dependency.)

## Review workflow (Phase 2)

`taxprep review` starts a localhost-only HTTP server (binds 127.0.0.1;
any other bind address is refused):

- `/` — validation queue: documents with status `transcribed` or
  `needs_review`, filterable by `?tax_year=` and `?form_type=`, with a
  per-year validated/total progress header.
- `/doc/<doc_id>` — two-column review page. Left: source evidence —
  OCR text with each extracted field's `raw_text` span highlighted
  (PDF page images when pdf2image+poppler are available, text fallback
  otherwise). Right: editable field table with confidence badges
  (high=green pre-confirmed, medium=amber pre-confirmed, low=red
  prominent and unchecked). The "Mark validated" button enables only
  when every field is confirmed or edited.
- `POST /api/validate` — writes corrections back to the store, sets
  `status=validated` and stamps `validated_at`.

Typical loop: `ingest` → `review` in the browser → validated.
Validated documents leave the queue; nothing is deleted.

## Blind-orchestrator contract

The workstation agent (Claude Code) operates this system **blind**: it
must never see PII in its context. Enforcement is layered:

- **MCP tool boundary (primary).** `show_document` scrubs every field
  to `{box_code, confidence, has_value}` — values, `raw_text`, payer
  names (even inside transcript field codes), and source paths are
  stripped. `compute_carryforward` writes the full PII-bearing report
  to `data/reports/carryforward_YYYYMMDD_HHMMSS.txt` (gitignored,
  operator's eyes only) and returns only
  `{report_path, years_covered, n_warnings, status}`. There is **no**
  validate tool: validation is human-only in the review UI, because an
  agent that cannot see content can never supply corrections.
- **Mechanical verification** (`taxprep/verify.py`, `taxprep verify`).
  The agent verifies structurally instead of reading content:
  completeness (known form/year), the validation gate (all validated),
  1099-B lot integrity (present/non-negative boxes, valid term,
  parseable dates), transcript reconciliation (validated docs vs the
  IRS wage & income transcript, 1-cent tolerance),
  carryforward-readiness, and source-evidence coverage (the check
  descends into the 1099-B lot table: every per-lot computed gain/loss
  must carry its lineage). Every check returns counts/ids/booleans
  only. A FAILED check means "needs human eyes", not "wrong".
- **CLI blind mode (defense in depth).** With `TAXPREP_BLIND=1`,
  `taxprep show` redacts field values (box_code + confidence +
  has_value only). The workstation session should export
  `TAXPREP_BLIND=1` in its shell.

The agent may see: doc_ids, tax_year, form_type, box codes, confidence
levels, has_value flags, counts, statuses, pass/fail results, report
file paths, refusal messages, opaque owner ids (`person-1..n`, R21a).
It must never see: field values,
raw_text, OCR text, dollar amounts, payer/employer names, EINs,
addresses, or person (owner) names.

## Layout

```
taxprep/
  models.py      Document record: {doc_id, tax_year, form_type, source_path,
                 ocr_text_ref, fields: {box: {value, confidence, raw_text}},
                 status: transcribed|needs_review|validated}
  store.py       thin shim: DocumentStore = MedallionStore (mstore.py)
  mstore.py      medallion storage (Arc B, W1): SQLite
                 <data_dir>/medallion.sqlite (WAL, busy_timeout, mode 0600),
                 bronze/silver/decision_log/gold tables per
                 medallion_schema.sql; Document-compatible facade +
                 medallion API (txn, register_bronze, artifacts, decisions)
  medallion_schema.sql  DDL for the medallion store (single source of truth)
  ingest.py      directory walk, PDF text extraction (pypdf, pdfplumber
                 fallback), .txt OCR sidecars, classification, year detection;
                 repeated transcript TC codes get ordinal-suffixed field
                 keys (X4): tc_806, tc_806_2, ... -- never silently
                 overwritten; one ordinal namespace spans both ROA sections
  extractors.py  box-level field extractors (regex/positional heuristics).
                 OCR-accuracy: on `text_source=ocr:*` the 1099-B box-token
                 fallbacks tolerate 1/l/I and 0/O confusions (labeled
                 patterns stay primary; native text is byte-identical);
                 the fallback gap allows newlines (real tesseract often
                 puts box tokens and amounts on separate lines);
                 the 1099-B lots field drops to `low` with reason
                 `lot_count_mismatch` (+ counts-only expected/extracted)
                 when fewer lots extract than the "Lot N" markers or
                 row-shaped lines signal -- never `transcribed` while
                 rows are missing
  transcript.py  IRS Tax Return Transcript + Wage & Income Transcript parsers
                 Record of Account: block model (X3b) -- anchor-event scan
                 over the whole text (return headers + account anchors, no
                 ordering assumption); summary lines route by grammar,
                 transactions by their span's block section
  review.py      localhost-only visual validation UI (queue, per-doc review,
                 POST /api/validate); binds 127.0.0.1 only
  carryforward.py  capital-loss carryforward engine: per-year Schedule D
                 worksheet logic (Decimal-only), 2023-2026 chaining,
                 from_store() adapter over validated 1099-Bs
  gold.py        gated gold layer (Arc B): gate_check refuses with
                 structured reason codes while any duplicate/supersedes/
                 conflict/blocked/excluded-lot/incomplete-lot item is
                 unresolved; gated_carryforward records input/output
                 digests and persists gold_run rows; blind_audit exposes
                 the workstation's five metadata-only invariants
  mcp_server.py  local MCP server (FastMCP, stdio transport only):
                 blind-orchestrator contract -- show_document scrubs fields
                 to {box_code, confidence, has_value}; compute_carryforward
                 writes the full report to data/reports/ and returns only
                 {report_path, years_covered, n_warnings, status}; no
                 validate tool (human-only validation); verify_* tools
                 wrap verify.py
  duplicates.py  duplicate taxonomy L0-L4 + conflicts (Arc B, W3):
                 normalize/text fingerprints (L2), salted field + lot
                 fingerprints (L3), corroboration groups, supersedes (L4),
                 conflict raising; explicit-only rule_on_group /
                 choose_conflict; blind-safe open_groups/open_conflicts
                 counts
  persons.py     R21a per-person scoping: person registry (opaque
                 person-1..n ids, names local-only), owner assignment +
                 suggestions (shown, never auto-applied), out-of-scope
                 exclusion filter, joint-allocation conflicts, return
                 assignments
  column_a.py    R21b 1040-X column-A builder: read-model over validated
                 transcripts/originals; MISSING is first-class output;
                 2025 original-vs-transcript disagreements raise
                 corroboration conflicts
  verify.py      mechanical verification suite (blind-safe): completeness,
                 validation gate, 1099-B lot integrity, transcript
                 reconciliation (EIN/name/1:1 matching, 1-cent tolerance;
                 "partial" transcripts compare on mapped lines with
                 unparsed counts as coverage, never skipped outright),
                 carryforward-readiness; all outputs counts/ids/booleans
  cli.py         argparse CLI: ingest | list | show | review | carryforward | mcp | verify
                 (TAXPREP_BLIND=1 redacts `show` field values)
tests/
  test_extractors.py   synthetic fixtures per form type
  test_transcript.py   synthetic transcript samples
  test_review.py       review server: queue, filters, review page,
                       validate API, loopback-only binding

### Storage layer — medallion (Arc B)

SQLite at `<data_dir>/medallion.sqlite` (WAL, `busy_timeout=5000`, file
mode 0600) subsumes the old JSONL + fcntl lock-file store. DDL lives in
`taxprep/medallion_schema.sql` (single source of truth):

- **bronze**: content-addressed source objects (`hash` = sha256 of source
  bytes); `bronze_alias` records every path a hash was seen at (I1–I3);
  `bronze_bytes_ref` points at the read-only bytes under
  `<data_dir>/bronze/xx/<sha>` (mode 0400); `bronze_text` holds per-page
  derived text keyed per I5 (W2's ingestion path).
- **silver**: `silver_doc` mirrors the Document record (`fields_json` is
  the operational field store); `silver_artifact` mirrors fields as typed
  artifacts with stable ids
  (`sha256(doc_id:bronze_hash:page:type:anchor)[:32]` — doc_id included
  so one bronze's many docs never collide);
  `doc_provenance` carries doc-level R5 text provenance (additive only
  — no contract §3 table altered).
- **decisions**: `decision_log` is append-only (I6) — enforced by DB
  triggers, not just the API; `dup_group`/`dup_member` and
  `conflict`/`conflict_option` are W3's.
- **gold**: `gold_run` records gated outputs with input digests (W4).

`MedallionStore` (`taxprep/mstore.py`; `taxprep/store.py` is a thin
`DocumentStore` shim) offers the Document-compatible facade
(`upsert`/`get`/`list`/`counts`/`needs_review`/`refresh`/`__len__`/
`save_ocr`/`load_ocr` — same behavior as before; reads are now always
current) plus the medallion API: `txn()` (single transaction, nested =
savepoint), `register_bronze`/`add_alias`/`store_bronze_bytes`/
`get_bronze`, `upsert_silver_doc`/`replace_artifacts`/`get_artifacts`,
`log_decision`/`decisions_for`, `db_digest`/`table_counts`.
Concurrency: SQLite serializes writers; a contended write waits for the
busy timeout then fails loudly (`OperationalError`) — never silently.

First open migrates a legacy `documents.jsonl` inside one transaction
(bronze rows, aliases, silver docs, mirror artifacts, synthesized
validate decisions; unrecoverable sources become `legacy-<doc_id>`
tombstones with `blocked_reason="legacy-no-source"`). The JSONL is left
in place as a backup and never written again.

Blind-orchestrator note: `db_digest()`/`table_counts()` expose digests
and counts only — never values.

### Arc B integration notes (coordinator amendments to the workstream contract)

- **Artifact ids include doc_id** (`sha256(doc_id:bronze_hash:page:type:anchor)[:32]`).
  The contract's bronze-only formula collided for multi-doc bronzes (R1
  split children, one-doc-per-CSV-row); doc_id is content-derived and
  stable, so I5 determinism holds.
- **`txn()` yields a handle** exposing both the store API and `execute()`
  for workstream-owned tables (duplicates, gold). The append-only decision
  log stays protected by DB triggers even through raw SQL.
- **`replace_artifacts` is a true full replace** (delete-all-then-insert);
  `field_fingerprint` cascades on artifact delete (fingerprints are
  derived data, recomputed per assessment).
- **Gold is ruling-aware**: disposed `keep_one`/`merge`/`authoritative`
  rulings remove the losing members' docs from gold's input (input
  digest, gate G2 wire-through, and sums); `distinct`/`corroborates`
  count every member. `carryforward.from_store` /
  `carryforward_blockers` take an optional `exclude_doc_ids` set for this.
- **L4 is order-independent** (a CORRECTED doc ingested before its
  original still raises supersedes) and 1099-B changed values are
  compared at lot level (box-level key boxes carry no amounts).

## Phase 2 scope

- Visual validation UI (this phase): queue + per-document review pages +
  correction write-back.
- opentax bridge, export generation: later phases.

## Phase 3 — capital-loss carryforward engine

`taxprep carryforward` chains the Schedule D Capital Loss Carryover
Worksheet across 2023→2024→2025→2026 from **validated** 1099-B lots
only — any unvalidated 1099-B for a chained year is a hard error.
Lots with unknown term or missing proceeds/basis are **blockers**
(`lot_term_unknown` / `lot_missing_amounts`): the carryforward
refuses until the Operator disposes (supplies the term/amounts or
records an exclusion with a reason) — never a silent omission.

Typical loop: `ingest` → `review` (validate everything) →
`carryforward`. The 2023-2025 rows drive the 1040-X amendments; the
`Carryforward into 2026` line is the figure to enter in the upcoming
TurboTax return (2026 lots are partial-year until December).

**Computed-field lineage (LINEAGE-1).** Every computed number carries
its lineage (formula + input references) in the R19a consumer shape
`{"computed": True, "formula": ..., "inputs": [...]}`:

- Each 1099-B lot's `gain_loss` is tagged at extraction with the single
  formula `1d - 1e + 1g` (inputs `proceeds_1d`, `basis_1e`, `wash_1g`;
  tagged only when 1d and 1e are present). The formula lives in exactly
  one place (`carryforward.lot_gain_loss_decimal`): `from_store` reads
  the lot's tag when well-formed and recomputes identically for
  legacy/CSV lots without it, so the two paths cannot drift.
- `from_store` / `compute_year` / `compute_chain` results carry a
  `"lineage"` entry alongside the numeric values (which stay Decimals
  for downstream arithmetic) — `st_current`/`lt_current`, the worksheet
  lines, and the carryforward-into-2026 pair.
- The evidence pane renders one lineage sub-row per tagged lot
  (formula + input links); the blind `verify_evidence` check descends
  into the lot table, so a computed field without lineage fails
  `n_computed_fields_without_lineage`.

All money stays Decimal-safe strings end to end; computed entries
carry no bbox (no source region) and never render the "no visual
evidence" state.

## Duplicates & conflicts (Arc B)

`taxprep/duplicates.py` implements the R16a taxonomy and the conflicts
absolute rule. Ingest calls two hooks (contract §8):

- `assess_new_bronze(store, bronze_hash)` — after bronze registration:
  L2 (text-identical, different bytes → `dup_group` class `L2`,
  status `open`, never auto-merged) and L4 (`CORRECTED` marker or same
  payer/form/year with changed values → class `supersedes`). L1
  (byte-identical) is structural — one bronze row, N aliases — and
  creates no group.
- `assess_silver_doc(store, doc_id)` — after the silver write: L3
  salted field fingerprints per form type
  (form, year, normalized payer EIN/name, masked recipient digits, key
  boxes) at doc level, plus per-lot fingerprints
  (description, dates, proceeds, basis) at lot level → class `L3`;
  Wage & Income transcript entries vs same-payer/year source docs →
  class `corroboration` (**never** `duplicate`).

Fingerprints are `sha256(salt + ":" + canonical_input)`; the salt is
generated once per store (`secrets.token_hex(32)`) and persisted in the
module-owned `dup_salt` table (`salt_id='v1'`) — W1's
`medallion_schema.sql` is untouched. All group/conflict ids are stable
hashes (contract §6); re-running an assess is idempotent.

**Absolute rule:** conflicting field values are raised to the Operator
and never mechanically resolved — no precedence, latest-wins,
confidence-wins, averaging, first-match-wins, or default preselection,
anywhere. Triggers: field disagreement inside L2/L3/corroboration
groups (`duplicate`/`corroboration` conflicts), re-extraction vs a
validated value (`flag_reextract` → `reextract` conflict,
options `validated`/`re-extracted`; W2 sets `re_review`),
and parser ambiguity (`parser_ambiguity` → `parser` conflict, for
transcript.py/extractors.py call sites). Disposition is always
explicit: `rule_on_group(store, group_id, *, ruling, primary, reason)`
writes `duplicate_ruling`/`supersedes_ruling` to the decision log and
disposes the group; `choose_conflict(store, conflict_id, *, choice,
reason)` validates the choice against the recorded options (no
default — a missing choice is a `TypeError`) and writes
`conflict_choice` `{options_shown, choice, reason, ts}`. Gold refuses
while anything is undisposed.

Blind contract: `open_groups(store)` / `open_conflicts(store)` return
`{class: count}` — counts only, never values or member keys (covered by
the recursive PII sweep in `tests/test_medallion_w3.py`). E2's old
`duplicate_of` relevance rule no longer auto-drops text-duplicates: it
now yields `needs_human` (detection signal kept; disposition belongs to
the medallion machinery).

## Gold gate (Arc B)

`taxprep carryforward` routes through `gold.gated_carryforward`. The
gate (R16 I8, extending R3) refuses — loudly, with structured reason
codes, exit code 3 — while any of these touch the year's documents:

- `unresolved_duplicate` — an open L2/L3 probable-duplicate group
- `unresolved_supersedes` — an open supersedes group (corrected forms)
- `unresolved_conflict` — an open conflict, or an open corroboration
  group with a disagreeing member (all-agree corroboration does NOT block)
- `blocked_document` — a silver_doc with status BLOCKED
- `excluded_lot` / `incomplete_lot` — the G2 lot-integrity blockers from
  `carryforward.carryforward_blockers`, wired through; an operator
  exclusion recorded in the decision log that the sum path cannot yet
  honor is `excluded_lot` (fail-closed)

Gold is a pure function of (validated silver, decisions, parameters):
every output records `input_digest` (sha256 over canonical validated
silver rows + relevant decision-log rows + params, deduped by
bronze_hash so L1-merged aliases count once) and `output_digest`;
recomputing with identical inputs yields identical digests, and a
`gold_run` row (kind=carryforward) is persisted per run.

`gold.blind_audit` exposes the workstation's five metadata-only
invariants — `bronze_accounted`, `files_accounted`,
`lot_sums_reconciled` (1-cent tolerance; no statement totals means
not_evaluated, never a vacuous pass), `gold_inputs_validated`,
`zero_unresolved_before_gold` — each returning
`{status: pass|fail|not_evaluated, counts...}` with ids only, never
values. All gold outputs are covered by the recursive PII sweep in
`tests/test_medallion_w4.py`.

Worksheet assumptions and limitations (see `carryforward.py`
docstring for the full statement):

- Implements the IRS Capital Loss Carryover Worksheet literally,
  lines 1-13 (verified against the 2024 Schedule D instructions;
  the 2023/2025/2026 worksheets are structurally identical).
  Sign conventions: carry-ins are positive loss magnitudes; yearly
  amounts are signed (negative = loss), so Schedule D line 7 =
  `st_current - st_carry_in`.
- Cross-term absorption is per the worksheet: an LT gain reduces
  the ST loss pool on line 6 *before* any carryover is figured
  (and symmetrically line 10 for LT). A net gain leaves nothing
  to deduct or carry.
- The low-taxable-income path (worksheet lines 1-4) needs Form
  1040 line 15 per year; until Phase 4 builds the 1040s, line 4
  is set to line 2 and a warning is recorded on every year.
- Per-lot gain/loss on 1099-B lots is `1d − 1e + 1g`: box 1g (wash
  sale loss disallowed) is extracted per lot and added back to the
  lot's gain/loss. Box 1f is **accrued market discount** (NOT federal
  income tax withheld) — Schedule B interest income, never part of
  gain/loss and never a withholding credit; it is summed separately
  for Phase 4 visibility. Box 4 (federal income tax withheld) is the
  withholding credit, never part of gain/loss; it is summed separately
  for the 1040 withholding line (Phase 4).
- Verification semantics: the summary reconciliation reports
  `evaluated: false` (and fails) when a statement shows totals but no
  comparable keys — a vacuous check is not a pass.
- Out of scope (flagged via warnings when indicated): unrecaptured
  section 1250 gain (25%), 28% collectibles rate,
  qualified-dividend interactions. State rules not modeled.

## Per-person scoping (R21a)

A document set can span several household members. The Operator assigns
each document an owner on `/console/sources` and in review (CLI:
`taxprep person register <name>` → opaque `person-N`; `taxprep owner set
<doc> <person-N>`; `taxprep owner suggest <doc>` derives a suggestion
from recipient text). Rules:

- **The system never infers the owner silently.** `owner_suggestion` is
  shown to the Operator and never auto-applied (R16a rule); a suggestion
  is "un-disposed" exactly while `owner_person_id` is unset, and the
  Operator's assignment consumes it (logged as `owner_assignment` in
  the decision log, with whether the suggestion was accepted).
- **Scope filter.** `taxprep scope apply --in-scope person-1,person-2`
  routes every document whose owner is outside the scope through the
  R13 lifecycle `exclude` event with the machine reason
  `out-of-scope-person` — the existing `status_reason` taxonomy, not a
  parallel mechanism. Excluded documents are never deleted, and the
  gold gate already treats `excluded` as exempt.
- **Joint / multi-owner items** are raised to the Operator for
  allocation via the R16a conflict pattern (class `allocation`,
  options = opaque person ids) and are **never mechanically split**.
  Per-artifact owners (`taxprep owner` allocation per artifact) let the
  Operator allocate a joint document piece by piece; allocations survive
  re-derivation.
- **Return assignment.** `taxprep return assign <doc> <person-N>
  joint|own|election` records, as an Operator decision
  (`return_assignment` in the decision log), which return each in-scope
  person's documents feed.
- **Opaque-id discipline.** Agent surfaces (MCP tools, `taxprep show
  --meta`, bus payloads) carry `person-1..n` ids and counts only. Names
  live solely in the local `<data_dir>/persons.json` registry and never
  cross the boundary — pinned by the blind sweep in
  `tests/test_values_plane.py`.

## 1040-X column-A builder (R21b)

`taxprep column-a --year 2023` builds the "original amount" (column A)
lines for Form 1040-X as a read-model over validated documents plus
transcripts — it never mutates gold or the document store.

- **Sources of record.** 2023/2024: the IRS Tax Return Transcript (plus
  Record of Account) — the Operator has no original returns. 2025: the
  original 1040 (R20 box/line extraction; designed for its absence)
  corroborated with the 2025 transcripts.
- Each line carries its source (`return_transcript` /
  `record_of_account` / `original_return`), the source doc id, and R15
  field provenance plus an R19 evidence-pane link (`evidence_ref`).
- **MISSING is first-class output.** Return-transcript line coverage is
  small, so most column-A lines are MISSING on real-shaped data — that
  is correct behavior, never defaulted, never zero-filled, and computed
  lines (L8/L19/L21) are never derived.
- **2025 corroboration.** An original-return line and a transcript line
  that disagree raise an R16a `corroboration` conflict to the Operator;
  the entry is flagged CONFLICT and carries no chosen value. (The
  conflict raise is the builder's only write; everything else is
  read-only — pinned by a digest-identity test.)

## Phase 6 — local MCP server (stdio only)

`taxprep mcp` exposes the pipeline as Model Context Protocol tools for
MCP clients (e.g. Claude Code on the operator's workstation), over the
**stdio transport only**. The HTTP/SSE transports are deliberately not
exposed anywhere in `mcp_server.py`: taxpayer PII must never traverse
a socket, and this server has no reason to listen on any port.

Tools (blind-orchestrator contract — see below):

- `ingest_directory(input_dir)` — ingest PDFs/OCR text; returns counts
  and the needs-review id list.
- `list_documents(tax_year?, form_type?)` — per-document summaries.
- `show_document(doc_id)` — **scrubbed** record: box codes, confidence,
  has_value per box. Never values, raw_text, names, or paths.
- `validation_queue(tax_year?, form_type?)` — the human review queue
  plus per-year validated/total progress.
- `compute_carryforward(filing_status_by_year, prior_st?, prior_lt?)` —
  the 2023-2026 worksheet chain from validated 1099-Bs; writes the full
  report (amounts included) to `data/reports/` and returns only
  `{report_path, years_covered, n_warnings, status}`. Raises the
  loud unvalidated-document refusal as a tool error.
- `verify_completeness()` / `verify_validation_gate(tax_year?)` /
  `verify_lot_integrity(tax_year)` /
  `verify_transcript_reconciliation(tax_year)` / `verify_all(tax_year?)`
  — mechanical checks; counts/ids/booleans only. `verify_all` also runs
  `no_silent_drops` (every doc carries an explicit relevance verdict).
- `bus_publish(topic, type, payload, correlation_id?)` — publish one
  bus message; the PII guard (SSN/EIN patterns refused, shapes only)
  is enforced here. Returns `{message_id, path, topic, from}`.
- `bus_poll(topic?, timeout_seconds?)` — poll subscribed topics (local
  tuning), always excluding this session's own broadcasts.
- `assess_relevance(tax_year?)` — relevance triage; counts/id lists.
- `analyze_gaps(tax_year?)` — gap shapes + local report path.

There is deliberately **no** `validate_document` tool. Validation is
human-only in the localhost review UI: an agent that cannot see
content can never supply corrections, so it is not given the chance.

All money figures cross the tool boundary as strings (raw Decimals
never leak into tool output); every return value is JSON-serializable.

Connect from Claude Code (on the machine holding the data):

```bash
claude mcp add taxprep -- /path/to/tax-prep/.venv/bin/taxprep mcp --data-dir /path/to/data
```

`--data-dir` may also be supplied via the `TAXPREP_DATA_DIR` env var.

## Message bus (multi-session collaboration)

Sessions collaborate through a broadcast bus instead of hand-carried
prompts. **Two-repo topology:** dsys-repo is software (code, specs,
tests); broadcast messages accrete to a separate repo,
**dsys-store** (`https://github.com/pltrinh1122/dsys-store`), under
`bus/<topic>/`. The code repo never carries message files.

Publishing writes a JSON file under `<dsys-store>/bus/<topic>/`,
**broadcasting** is commit + push of the store repo, listening is pull
+ read. Poll-scale latency (tens of seconds) fits build notifications
and discrepancy reports. Listeners tune in by topic.

On a new machine, clone the store repo first:

```bash
git clone https://github.com/pltrinh1122/dsys-store ~/workspace/dsys-store
```

Bus dir resolution: `--bus-dir` > `TAXPREP_BUS_DIR` >
`<store>/bus`, where the store checkout resolves as `--store-dir` >
`TAXPREP_STORE_DIR` > config `store_dir` > `~/workspace/dsys-store`.
A missing store checkout fails fast with the clone command.

```bash
.venv/bin/taxprep bus publish --topic tax-prep.ops --type run-done \
    --payload '{"n_docs": 3}' [--correlation-id C] [--store-dir D]
.venv/bin/taxprep bus listen [--topic T]... [--timeout S] [--once | --wait-first] [--include-own]
.venv/bin/taxprep bus topics
.venv/bin/taxprep bus tune --topic tax-prep.build [--off]
.venv/bin/taxprep bus whoami   # shows resolved store dir
```

Well-known topics: `tax-prep.build` (architect → workstation/human:
code landed, pull and re-run), `tax-prep.ops` (workstation →
architect/human: run completions, discrepancy shapes), `tax-prep.review`
(human → all: decisions/approvals). Topics are otherwise free-form
(lowercase alphanumerics, dots, dashes).

- **Shapes only.** `publish` hard-refuses payloads matching SSN
  (`\d{3}-\d{2}-\d{4}`), EIN (`\d{2}-\d{7}`), unhyphenated 9-digit-run,
  masked-SSN (`XXX-XX-dddd`, any case), long-digit-run (10+ digits), or
  currency-amount (`$N.NN`) patterns, and the blind-orchestrator rule
  applies end to end: payloads carry ids, counts, enums, statuses —
  never values, names, or amounts. Enforced at the publish call, so
  neither the repo nor any listening agent ever sees PII.
- **Wake-on-delivery.** `bus listen --wait-first` blocks until the first
  delivery arrives, then exits — for waking a background process when a
  message lands (`--timeout` still bounds the wait).
- **Session identity + echo tune-out.** Every message carries a unique
  broadcaster id (`<role>-<6 hex>`, e.g. `workstation-a1b2c3`,
  generated on first publish). Listeners exclude their own broadcasts
  by default (`--include-own` opts back in).
- **Local-only tuning (never committed).** Session id, subscribed
  topics, and poll interval live in `~/.config/taxprep/bus.toml`
  (`XDG_CONFIG_HOME` respected); the listen cursor in
  `~/.config/taxprep/bus_cursor.json`, keyed by session id inside the
  file so N listeners on one machine each keep an independent position
  and every broadcast reaches every listener. The repo carries
  messages, never listener state.

MCP tools: `bus_publish(topic, type, payload, correlation_id?)` →
`{message_id, path, topic, from}`; `bus_poll(topic?, timeout_seconds?)`
→ `{messages, warnings, topics}` honoring the local tuning
(subscribed topics, echo exclusion). `timeout_seconds=0` (default) is a
single pass; positive values long-poll up to 300s.

## Local workstation config

Machine-local paths are set once, not passed per command:

```bash
.venv/bin/taxprep config set source_dir ~/tax-documents
.venv/bin/taxprep config set data_dir ~/.local/share/taxprep
.venv/bin/taxprep config set scope_years 2023,2024,2025,2026
.venv/bin/taxprep config show
```

Resolution order per key: CLI flag > env var (`TAXPREP_SOURCE_DIR`,
`TAXPREP_DATA_DIR`, `TAXPREP_SCOPE_YEARS`) > `~/.config/taxprep/config.toml`
> built-in default. `data_dir` has no default — it is required; set it
once via `taxprep config set data_dir <path>` (paths inside
site-packages are refused). The config file lives outside the repo and is
never committed. `taxprep ingest` with no directory argument uses the
configured `source_dir`; `--data-dir` still overrides everywhere.

## Relevance & gap intelligence

`taxprep relevance` triages every document into
**relevant | irrelevant | needs_human** with deterministic,
metadata-only rules: tax year outside the configured scope →
`irrelevant` (`year_out_of_scope`) — except carryover-seed sources
(prior-year 1040 / 1040-X, Schedule D, return transcript) dated before
the scope, which stay `relevant` (`carryover_seed`) so the
capital-loss chain's prior-year seed is never silently dropped;
byte-identical OCR (sha256) → `irrelevant` (`duplicate_of:<doc_id>`,
first kept); unclassified form → `needs_human` (never auto-dropped). Anything ambiguous lands in
`needs_human` — the human, not the agent, is the arbiter. Verdicts are
labels persisted on the document (`Document.relevance`, default
`unassessed`); nothing is ever deleted. `verify_no_silent_drops`
(fails until every doc carries a verdict) is wired into `verify_all`,
so the triage can never be silently skipped.

`taxprep gaps` cross-checks the IRS wage & income transcript against
ingested documents per year: expected form types come from transcript
payer blocks plus schedule mentions in the return transcript
(Schedule D → 1099-B, B → 1099-INT/DIV, C → 1099-NEC/MISC); missing =
expected forms with zero ingested docs that year. The CLI/MCP return
value is PII-free (form types, counts, report path); per-payer detail
(names → missing forms) goes only to `data/reports/gaps_*.txt` for the
operator's eyes. A year with no parsed transcript reports
`expected_forms=[]` — no ground truth, never a false all-clear.

**Authority rule (adopted):** a *validated* document is relevant by
definition — `assess_relevance` returns `relevant` with reason code
`validated_by_operator`, and the mechanical rules (year, duplicates)
never demote it. Human judgment dominates mechanical rules.

**Explicit override:** `taxprep relevance-override <doc_id>
<relevant|irrelevant|needs_human> --reason "..."` records an explicit
operator direction (`{doc_id, verdict, reason, ts}` in the append-only
`relevance_overrides.jsonl` next to the store); the verdict applies
immediately and is honored on future `assess_relevance` runs
(`operator_override`). The mechanical pipeline never calls the override
path itself. MCP: `relevance_override(doc_id, verdict, reason)`
(operator-only surface).

**Queue filtering:** the validation queue (CLI `validation-queue`, MCP
`validation_queue`, and the `taxprep review` UI queue) *excludes*
`irrelevant` verdicts by default — never in the way, never invisible:
the excluded count is always noted, irrelevants are listed/auditable
with their reason codes (`--include-irrelevant`, `?include_irrelevant=1`,
or the MCP flag), and restorable via `relevance-override`.

MCP tools: `assess_relevance(tax_year?)` → `{n_docs, counts,
relevant_ids, irrelevant, needs_human}`; `analyze_gaps(tax_year?)` →
per-year shapes + `report_path`. Both are covered by the recursive
PII sweep in `tests/test_mcp_server.py`.
