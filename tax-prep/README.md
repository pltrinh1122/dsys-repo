# taxprep — Phase 1

Local-only CLI to transcribe tax documents (PDFs + OCR text) into structured
digital form, for amended-return preparation (Form 1040-X).

**Privacy rule:** Phase 1 works exclusively with **synthetic fixture
documents**. No real PII. No network calls. Everything runs locally.

## Setup

```bash
cd ~/workspace/tax-prep
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

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
```

`ingest` prints a summary table (counts by form × year) plus the list of
documents flagged `needs_review`. OCR text is stored under
`data/ocr/<doc_id>.txt`; records live in `data/documents.jsonl`
(gitignored — never commit taxpayer material).

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
  IRS wage & income transcript, 1-cent tolerance), and
  carryforward-readiness. Every check returns counts/ids/booleans
  only. A FAILED check means "needs human eyes", not "wrong".
- **CLI blind mode (defense in depth).** With `TAXPREP_BLIND=1`,
  `taxprep show` redacts field values (box_code + confidence +
  has_value only). The workstation session should export
  `TAXPREP_BLIND=1` in its shell.

The agent may see: doc_ids, tax_year, form_type, box codes, confidence
levels, has_value flags, counts, statuses, pass/fail results, report
file paths, refusal messages. It must never see: field values,
raw_text, OCR text, dollar amounts, payer/employer names, EINs,
addresses.

## Layout

```
taxprep/
  models.py      Document record: {doc_id, tax_year, form_type, source_path,
                 ocr_text_ref, fields: {box: {value, confidence, raw_text}},
                 status: transcribed|needs_review|validated}
  store.py       JSONL store (append/upsert/list/query by year+form)
  ingest.py      directory walk, PDF text extraction (pypdf, pdfplumber
                 fallback), .txt OCR sidecars, classification, year detection
  extractors.py  box-level field extractors (regex/positional heuristics)
  transcript.py  IRS Tax Return Transcript + Wage & Income Transcript parsers
  review.py      localhost-only visual validation UI (queue, per-doc review,
                 POST /api/validate); binds 127.0.0.1 only
  carryforward.py  capital-loss carryforward engine: per-year Schedule D
                 worksheet logic (Decimal-only), 2023-2026 chaining,
                 from_store() adapter over validated 1099-Bs
  mcp_server.py  local MCP server (FastMCP, stdio transport only):
                 blind-orchestrator contract -- show_document scrubs fields
                 to {box_code, confidence, has_value}; compute_carryforward
                 writes the full report to data/reports/ and returns only
                 {report_path, years_covered, n_warnings, status}; no
                 validate tool (human-only validation); verify_* tools
                 wrap verify.py
  verify.py      mechanical verification suite (blind-safe): completeness,
                 validation gate, 1099-B lot integrity, transcript
                 reconciliation (EIN/name/1:1 matching, 1-cent tolerance),
                 carryforward-readiness; all outputs counts/ids/booleans
  cli.py         argparse CLI: ingest | list | show | review | carryforward | mcp | verify
                 (TAXPREP_BLIND=1 redacts `show` field values)
tests/
  test_extractors.py   synthetic fixtures per form type
  test_transcript.py   synthetic transcript samples
  test_review.py       review server: queue, filters, review page,
                       validate API, loopback-only binding

## Phase 2 scope

- Visual validation UI (this phase): queue + per-document review pages +
  correction write-back.
- opentax bridge, export generation: later phases.

## Phase 3 — capital-loss carryforward engine

`taxprep carryforward` chains the Schedule D Capital Loss Carryover
Worksheet across 2023→2024→2025→2026 from **validated** 1099-B lots
only — any unvalidated 1099-B for a chained year is a hard error, and
lots with unknown term or missing proceeds/basis are excluded with a
warning (never guessed).

Typical loop: `ingest` → `review` (validate everything) →
`carryforward`. The 2023-2025 rows drive the 1040-X amendments; the
`Carryforward into 2026` line is the figure to enter in the upcoming
TurboTax return (2026 lots are partial-year until December).

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
- Out of scope (flagged via warnings when indicated): unrecaptured
  section 1250 gain (25%), 28% collectibles rate,
  qualified-dividend interactions. Wash-sale adjustments are
  assumed already in 1099-B basis. State rules not modeled.

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

Sessions collaborate through a git-backed broadcast bus instead of
hand-carried prompts: publishing writes a JSON file under
`tax-prep/bus/<topic>/`, **broadcasting** is commit + push, listening
is pull + read. Poll-scale latency (tens of seconds) fits build
notifications and discrepancy reports. Listeners tune in by topic.

```bash
.venv/bin/taxprep bus publish --topic tax-prep.ops --type run-done \
    --payload '{"n_docs": 3}' [--correlation-id C]
.venv/bin/taxprep bus listen [--topic T]... [--timeout S] [--once] [--include-own]
.venv/bin/taxprep bus topics
.venv/bin/taxprep bus tune --topic tax-prep.build [--off]
.venv/bin/taxprep bus whoami
```

Well-known topics: `tax-prep.build` (architect → workstation/human:
code landed, pull and re-run), `tax-prep.ops` (workstation →
architect/human: run completions, discrepancy shapes), `tax-prep.review`
(human → all: decisions/approvals). Topics are otherwise free-form
(lowercase alphanumerics, dots, dashes).

- **Shapes only.** The repo is public, so `publish` hard-refuses
  payloads matching SSN (`\d{3}-\d{2}-\d{4}`) or EIN (`\d{2}-\d{7}`)
  patterns. Payloads carry ids, counts, enums, statuses — never values,
  names, or amounts. This is the same blind-orchestrator guarantee as
  the MCP boundary, enforced at the publish call.
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
> built-in default. The config file lives outside the repo and is
never committed. `taxprep ingest` with no directory argument uses the
configured `source_dir`; `--data-dir` still overrides everywhere.

## Relevance & gap intelligence

`taxprep relevance` triages every document into
**relevant | irrelevant | needs_human** with deterministic,
metadata-only rules: tax year outside the configured scope →
`irrelevant` (`year_out_of_scope`); byte-identical OCR (sha256) →
`irrelevant` (`duplicate_of:<doc_id>`, first kept); unclassified form
→ `needs_human` (never auto-dropped). Anything ambiguous lands in
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

MCP tools: `assess_relevance(tax_year?)` → `{n_docs, counts,
relevant_ids, irrelevant, needs_human}`; `analyze_gaps(tax_year?)` →
per-year shapes + `report_path`. Both are covered by the recursive
PII sweep in `tests/test_mcp_server.py`.
