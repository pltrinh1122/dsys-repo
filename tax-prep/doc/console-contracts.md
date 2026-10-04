# Console integration contracts (R12 / R13 / R19)

The R12 Operator console (`taxprep/console.py`, served through the
R10-hardened `taxprep/review.py` server) consumes two sibling-owned
modules. These contracts are the ONLY coupling; the console degrades
honestly (a "pending" note, never invented content) when a sibling
module is not installed.

## R19/R19a — evidence pane (`taxprep/evidence_pane.py`)

Owned by the evidence-pane workstream. The console provides the view
shell and navigation; the pane provides the evidence rendering.

Contract:

- Module: `taxprep/evidence_pane.py`
- Function: `pane_html(store, doc) -> str`
  - `store`: `DocumentStore` (the medallion store)
  - `doc`: `models.Document`
  - Returns: self-contained HTML for the source-evidence pane
    (rendered pages + bbox overlays + per-field snapshots, R19a).
  - The console mounts the returned HTML verbatim inside
    `<section id="evidence-pane" data-doc-id="<doc_id>">` on
    `GET /console/doc/<doc_id>`.
  - The HTML must be self-contained: inline styles or its own
    `<style>` block; no assumption about the console's CSS.
  - Must not raise for documents with unavailable/degraded evidence —
    render the blocked state instead (the console never catches pane
    exceptions as control flow, but a pane that 500s the page breaks
    the Queue & Review view).
- Detection: `taxprep.console.evidence_pane_html(store, doc)` returns
  `None` when the module (or `pane_html`) is absent; the console then
  shows a "pane pending" note linking to the legacy `/doc/<id>` page
  (whose evidence rendering in `review.py` is unchanged).

## R13 — document lifecycle (`taxprep/lifecycle.py`)

Owned by the lifecycle workstream. The console consumes the event log
and records select→ingest transitions for checked-file ingest; it does
NOT implement the state machine.

Contract:

- Module: `taxprep/lifecycle.py`
- `STATES: tuple[str, ...]` — the valid lifecycle states.
- `record_event(store, *, doc_id, event, actor, from_state, to_state, reason_code) -> bool`
  - Records one transition. Returns truthy on success.
  - `reason_code` is a stable machine code (e.g. `operator_checked`,
    `checked_file_ingest`), never free text with PII.
  - Called by `taxprep/sources.py::ingest_checked` for the
    select→ingest transitions of Operator-checked files.
- `events_for(store, *, doc_id=None, limit=200) -> list[dict]`
  - Per-document event log (all documents when `doc_id=None`),
    oldest first.
  - Each dict carries EXACTLY these keys:
    `{ts, doc_id, event, actor, from, to, reason_code}`.
    Missing keys are normalized to `None` by the console — the
    contract names the keys, not their presence.
- `state_of(store, doc_id) -> str | None`
  - Current lifecycle state of one document; `None` when unknown.

Consumed through `taxprep/sources.py`:

- `lifecycle_record(store, *, doc_id, event, actor, from_state, to_state, reason_code) -> bool`
  — `False` when the R13 module is absent (the console surfaces
  "lifecycle pending", never silent drops).
- `lifecycle_events(store, *, doc_id=None, limit=200) -> list[dict] | None`
  — `None` when the R13 module is absent.
- `lifecycle_state(store, doc_id) -> str | None`.

## Values-plane boundary (both directions)

- The console is OPERATOR-ONLY (loopback, R10-hardened). Filenames,
  values, and page images may appear in console views.
- Agent surfaces stay metadata-only: MCP tools (`taxprep/mcp_server.py`)
  and bus payloads never carry paths, filenames, amounts, or page
  images. `tests/test_values_plane.py` pins this.
- The R11 roots registry (`~/.config/taxprep/source_roots.json`, mode
  0600) is machine-local and never committed; scan results are computed
  on demand and never persisted.
