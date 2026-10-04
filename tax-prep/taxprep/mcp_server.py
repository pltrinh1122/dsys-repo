"""Local MCP server for the tax-prep agent (Phase 6+).

BLIND-ORCHESTRATOR CONTRACT
----------------------------
The workstation agent that calls these tools must NEVER see PII in its
context. It orchestrates BLIND:

  MAY see:  doc_ids, tax_year, form_type, box codes, confidence levels,
            has_value flags, counts, statuses, pass/fail results,
            report file paths, refusal/error messages.
  NEVER:    field values, raw_text snippets, OCR text, dollar amounts,
            payer/employer names, EINs, addresses.

Enforcement points (defense in depth):

  1. show_document scrubs every field to {box_code, confidence,
     has_value}; payer names embedded in transcript field codes
     ("payer1.ACME CORP.1") are redacted to "payer1.[payer].1"; the
     source_path / ocr_text_ref are dropped (local paths can leak
     usernames and are not needed for box inventory). R5 provenance
     (text_source, reason_code, ocr_engine, engine_version, ocr_mode,
     attempts, mean_confidence) is operational metadata, not taxpayer
     data, and is exposed as non-PII keys.
  2. compute_carryforward writes the full PII-bearing report to a
     local file under data/reports/ (gitignored, operator's eyes
     only); the tool returns only {report_path, years_covered,
     n_warnings, status}.
  3. There is NO validate tool: validation is human-only, in the
     localhost review UI. An agent that cannot see content can never
     supply corrections -- so it is not given the chance.
  4. All verify_* tools return counts/ids/booleans only (see verify.py).

Transport: stdio only. The HTTP/SSE transports are deliberately NOT
exposed: taxpayer PII must never traverse a socket, and this server
has no reason to listen on any port. ``taxprep mcp`` runs ``mcp.run()``
with FastMCP's default stdio transport; there is no code path that
starts a network listener.

Privacy: same rules as the CLI -- synthetic fixtures in development,
real taxpayer material only ever on the operator's own machine, and
``data/`` stays gitignored.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .ingest import ingest_dir
from .store import DocumentStore

mcp = FastMCP("taxprep")

# Transcript field codes embed the payer name: "payer1.ACME CORP.1".
# Redact the name segment so PII never leaks through a key.
_PAYER_CODE_RE = re.compile(r"^payer\d+$")


def _scrub_code(code: str) -> str:
    parts = code.split(".")
    if len(parts) >= 3 and _PAYER_CODE_RE.fullmatch(parts[0]):
        return f"{parts[0]}.[payer].{parts[-1]}"
    return code


# R5 provenance keys: operational metadata, not taxpayer data -- safe
# to expose to the blind orchestrator (no values, names, or paths).
PROVENANCE_KEYS = ("text_source", "reason_code", "ocr_engine",
                   "engine_version", "ocr_mode", "attempts",
                   "mean_confidence", "encryption")


def _scrub_doc(doc_dict: dict) -> dict:
    """Strip PII from a document record for the blind orchestrator.

    Every field becomes {box_code, confidence, has_value}; value and
    raw_text are dropped, payer names in transcript field codes are
    redacted, and source_path / ocr_text_ref are dropped. The R5
    provenance keys (PROVENANCE_KEYS) are operational metadata, not
    taxpayer data, and are passed through.
    """
    fields = {}
    for code, f in (doc_dict.get("fields") or {}).items():
        if not isinstance(f, dict):
            continue
        v = f.get("value")
        fields[_scrub_code(code)] = {
            "confidence": f.get("confidence"),
            "has_value": v is not None and v != "",
        }
    out = {
        "doc_id": doc_dict.get("doc_id"),
        "tax_year": doc_dict.get("tax_year"),
        "form_type": doc_dict.get("form_type"),
        "status": doc_dict.get("status"),
        "validated_at": doc_dict.get("validated_at"),
        "fields": fields,
    }
    for key in PROVENANCE_KEYS:
        out[key] = doc_dict.get(key)
    return out


def _store(data_dir: str | None) -> DocumentStore:
    """Resolve the data dir: explicit arg -> TAXPREP_DATA_DIR env ->
    config file. N1: there is no package default -- an unset data_dir
    raises (fail closed), and site-packages locations are refused."""
    from . import config as _cfg
    return DocumentStore(_cfg.resolve("data_dir", cli_value=data_dir))


def _jsonable(v):
    """Recursively convert to JSON-safe values. Decimals become strings --
    raw Decimals must never leak into tool output (MCP serializes to JSON)."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


# -- tools ------------------------------------------------------------


@mcp.tool()
def ingest_directory(input_dir: str, data_dir: str | None = None) -> dict:
    """Ingest PDFs / .txt OCR files from a directory (recursive) into the
    document store. Returns document counts by form x year and the ids of
    documents flagged as needing review. No PII in the output."""
    store = _store(data_dir)
    docs = ingest_dir(input_dir, store)
    counts = [
        {"tax_year": y, "form_type": f, "count": c}
        for (y, f), c in sorted(store.counts().items(),
                                key=lambda kv: (kv[0][0] or 0, kv[0][1]))
    ]
    return _jsonable({
        "n_docs": len(docs),
        "counts": counts,
        "needs_review_ids": [d.doc_id for d in store.needs_review()],
        "store": str(store.db_path),
    })


@mcp.tool()
def list_documents(tax_year: int | None = None, form_type: str | None = None,
                   data_dir: str | None = None) -> list:
    """List ingested documents, optionally filtered by tax year and form
    type. Returns one PII-free summary dict per document."""
    store = _store(data_dir)
    return _jsonable([
        {
            "doc_id": d.doc_id,
            "tax_year": d.tax_year,
            "form_type": d.form_type,
            "status": d.status,
            "n_fields": len(d.fields),
        }
        for d in store.list(year=tax_year, form=form_type)
    ])


@mcp.tool()
def show_document(doc_id: str, data_dir: str | None = None) -> dict:
    """Show one document's scrubbed record: box codes present, confidence
    per box, and whether each box has a value -- but NEVER the values
    themselves, raw_text, payer names, or source paths (blind-orchestrator
    contract). Raises a tool error when the doc_id is unknown."""
    store = _store(data_dir)
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(f"unknown doc_id: {doc_id}")
    return _jsonable(_scrub_doc({
        "doc_id": doc.doc_id,
        "tax_year": doc.tax_year,
        "form_type": doc.form_type,
        "status": doc.status,
        "validated_at": doc.validated_at,
        "fields": doc.fields,
        # R5 provenance: operational metadata, not taxpayer data.
        "text_source": doc.text_source,
        "reason_code": doc.reason_code,
        "ocr_engine": doc.ocr_engine,
        "engine_version": doc.engine_version,
        "ocr_mode": doc.ocr_mode,
        "attempts": doc.attempts,
        "mean_confidence": doc.mean_confidence,
    }))


@mcp.tool()
def validation_queue(tax_year: int | None = None, form_type: str | None = None,
                     data_dir: str | None = None,
                     include_irrelevant: bool = False) -> dict:
    """The human validation queue: documents with status transcribed or
    needs_review, optionally filtered. Documents with relevance verdict
    ``irrelevant`` are EXCLUDED by default (never in the way, never
    invisible -- they remain listed/auditable with their reason codes via
    ``include_irrelevant=True`` and restorable through the
    ``relevance_override`` tool). Includes per-year validated/total
    progress. Nothing downstream may consume unvalidated documents."""
    store = _store(data_dir)
    from . import lifecycle as _lifecycle
    queue = [d for d in store.list(year=tax_year, form=form_type)
             if d.status in _lifecycle.UNVALIDATED_EXTRACTED]
    excluded = sum(1 for d in queue if d.relevance == "irrelevant")
    if not include_irrelevant:
        queue = [d for d in queue if d.relevance != "irrelevant"]
    years = sorted({d.tax_year for d in store.list() if d.tax_year is not None})
    progress = {}
    for y in years:
        all_y = store.list(year=y)
        done = sum(1 for d in all_y if d.status == "validated")
        progress[str(y)] = {"validated": done, "total": len(all_y)}
    return _jsonable({
        "queue": [
            {
                "doc_id": d.doc_id,
                "tax_year": d.tax_year,
                "form_type": d.form_type,
                "status": d.status,
                "relevance": d.relevance,
                "n_fields": len(d.fields),
                "low_confidence_fields": sum(
                    1 for f in d.fields.values()
                    if isinstance(f, dict) and f.get("confidence") == "low"),
            }
            for d in queue
        ],
        "irrelevant_excluded": 0 if include_irrelevant else excluded,
        "progress": progress,
    })


def _render_carryforward_report(result: dict, filing_status_by_year: dict,
                                lot_notes: list[str]) -> str:
    """Full PII-bearing report text. Written to a local file for the
    operator's eyes only -- never returned over the tool boundary."""
    lines = [
        "taxprep carryforward report",
        f"generated: {datetime.now().isoformat(timespec='seconds')}",
        "filing statuses: " + ", ".join(
            f"{y}={filing_status_by_year.get(y, '?')}"
            for y in sorted(result["years"])),
        "",
        result["table"],
        "",
        "per-year detail:",
    ]
    for y in sorted(result["years"]):
        r = result["years"][y]
        lines.append(
            f"  {y}: deductible={r['deductible_loss']} "
            f"st_out={r['st_carry_out']} lt_out={r['lt_carry_out']}")
    lines.append("")
    lines.append("lots: " + "; ".join(lot_notes))
    if result["warnings"]:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"  ! {w}" for w in result["warnings"])
    return "\n".join(lines) + "\n"


@mcp.tool()
def compute_carryforward(filing_status_by_year: dict,
                         prior_st: str | None = None,
                         prior_lt: str | None = None,
                         data_dir: str | None = None) -> dict:
    """Run the capital-loss carryforward chain (IRS Schedule D worksheet,
    lines 1-13, Decimal-exact) for each tax year 2023-2026 present in the
    store, from validated 1099-B lots only.

    The full report (dollar amounts included) is written to a local file
    under data/reports/ for the operator's eyes only. The tool itself
    returns ONLY {report_path, years_covered, n_warnings, status} -- no
    amounts cross the tool boundary (blind-orchestrator contract).

    filing_status_by_year maps year to status, e.g.
    {"2023": "single", "2024": "mfj"} (keys are strings because JSON
    object keys are strings; they are coerced to int). prior_st/prior_lt
    seed the 2022 carryover into the first year.

    Raises a tool error -- with the message intact -- when any 1099-B for
    a chained year is not yet validated, or when a filing status is
    missing or unknown. Lots with unknown term or missing proceeds/basis
    are excluded with warnings, never guessed."""
    from .carryforward import compute_chain, from_store

    store = _store(data_dir)
    years = sorted({d.tax_year for d in store.list()
                    if d.tax_year in (2023, 2024, 2025, 2026)})
    if not years:
        raise ValueError("no documents for tax years 2023-2026 in the store")
    statuses: dict[int, str] = {}
    for k, v in filing_status_by_year.items():
        statuses[int(k)] = v
    yearly: dict[int, dict] = {}
    lot_notes: list[str] = []
    for y in years:
        # from_store raises loudly on unvalidated 1099-Bs -- let it propagate.
        r = from_store(store, y)
        yearly[y] = {"st_current": r["st_current"], "lt_current": r["lt_current"]}
        lot_notes.append(
            f"{y}: {r['lots_included']} lot(s) in, {r['lots_excluded']} excluded")
        lot_notes.extend(f"{y}: {w}" for w in r["warnings"])
    result = compute_chain(
        yearly,
        statuses,
        prior_carryover={"st": prior_st or "0", "lt": prior_lt or "0"},
    )
    reports_dir = Path(store.data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"carryforward_{stamp}.txt"
    report_path.write_text(
        _render_carryforward_report(result, filing_status_by_year, lot_notes),
        encoding="utf-8",
    )
    return _jsonable({
        "report_path": str(report_path),
        "years_covered": years,
        "n_warnings": len(result["warnings"]),
        "status": "ok",
    })


# -- mechanical verification tools (blind-orchestrator safe) ---------


@mcp.tool()
def verify_completeness(data_dir: str | None = None) -> dict:
    """Mechanical check: every document has a known form_type and a
    non-null tax_year. Returns counts and doc_ids only -- no PII."""
    from .verify import verify_completeness as _v
    return _jsonable(_v(_store(data_dir)))


@mcp.tool()
def verify_validation_gate(tax_year: int | None = None,
                           data_dir: str | None = None) -> dict:
    """Mechanical check: all documents (optionally filtered to a year)
    have status validated. Returns counts and unvalidated doc_ids."""
    from .verify import verify_validation_gate as _v
    return _jsonable(_v(_store(data_dir), tax_year))


@mcp.tool()
def verify_lot_integrity(tax_year: int, data_dir: str | None = None) -> dict:
    """Mechanical check: structural integrity of 1099-B lots for a year
    (proceeds/basis present and non-negative, term in {short, long},
    dates parseable when present). Returns counts and failing doc_ids --
    never the offending values."""
    from .verify import verify_lot_integrity as _v
    return _jsonable(_v(_store(data_dir), tax_year))


@mcp.tool()
def verify_transcript_reconciliation(tax_year: int,
                                     data_dir: str | None = None) -> dict:
    """Mechanical check: reconcile validated W-2/1099 docs against the
    IRS wage & income transcript for a year. Payers matched on normalized
    EIN, then normalized name, then unambiguous 1:1 form_type; headline
    amounts compared with 1-cent tolerance. Returns counts and doc_ids
    only -- never names or amounts. Unvalidated docs are skipped."""
    from .verify import verify_transcript_reconciliation as _v
    return _jsonable(_v(_store(data_dir), tax_year))


@mcp.tool()
def verify_all(tax_year: int | None = None,
               data_dir: str | None = None) -> dict:
    """Run every mechanical verification check. With tax_year=None the
    per-year checks run for each year present. Returns {passed, checks} --
    all PII-free."""
    from .verify import verify_all as _v
    return _jsonable(_v(_store(data_dir), tax_year))


# -- message bus tools (blind-orchestrator safe) ------------------------


@mcp.tool()
def bus_publish(topic: str, type: str, payload: dict,
                correlation_id: str | None = None) -> dict:
    """Publish one message to the broadcast bus (accretes to dsys-store).
    Broadcasting itself is commit + push of the dsys-store repo (the
    session's job after this call).

    Payloads go through bus.publish's PII guard -- SSN/EIN patterns are
    refused, and the shapes-only rule applies: ids, counts, statuses,
    never values or names. Returns {message_id, path, topic, from}."""
    import json as _json
    from . import bus as _bus
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object (dict)")
    path = _bus.publish(topic, type, payload, correlation_id=correlation_id)
    msg = _json.loads(path.read_text(encoding="utf-8"))
    return _jsonable({
        "message_id": msg["id"],
        "path": str(path),
        "topic": msg["topic"],
        "from": msg["from"],
    })


@mcp.tool()
def bus_poll(topic: str | None = None, timeout_seconds: float = 0) -> dict:
    """Poll the broadcast bus for new messages.

    With no topic, polls this session's subscribed topics (local tuning).
    This session's own broadcasts are always excluded (tune-out). A
    failed git pull records a warning instead of failing -- offline
    work still reads local messages.

    timeout_seconds=0 (default): single pass, return immediately.
    timeout_seconds>0: keep polling until the timeout (capped at 300s).
    Returns {messages, warnings, topics}. Messages are full message
    dicts -- their payloads are shapes-only by the publish-side guard."""
    import time as _time
    from . import bus as _bus

    tuning = _bus.load_tuning()
    topics = [topic] if topic else _bus.subscribed_topics(tuning)
    exclude = tuning["session"]["id"] or None
    try:
        bus_dir = _bus.resolve_bus_dir()
        repo = _bus.resolve_pull_target()
    except (FileNotFoundError, ValueError) as exc:
        return _jsonable({"messages": [], "warnings": [f"bus unavailable: {exc}"],
                          "topics": topics})
    interval = int(tuning["tuning"].get("poll_interval_seconds", 30))
    timeout = max(0.0, min(float(timeout_seconds), 300.0))

    messages: list = []
    warnings: list = []
    start = _time.monotonic()
    first_pass = True
    while True:
        for i, t in enumerate(topics):
            result = _bus.poll_once(
                t, repo or bus_dir, bus_dir=bus_dir,
                do_pull=repo is not None and i == 0,  # one pull per pass
                exclude_from=exclude)
            messages.extend(result)
            warnings.extend(result.warnings)
        if not first_pass or (_time.monotonic() - start) >= timeout:
            break
        first_pass = False
        _time.sleep(min(interval, max(1, timeout - (_time.monotonic() - start))))
    return _jsonable({"messages": messages, "warnings": warnings,
                      "topics": topics})


# -- relevance + gap intelligence (blind-orchestrator safe) -------------


@mcp.tool()
def assess_relevance(tax_year: int | None = None,
                     data_dir: str | None = None) -> dict:
    """Triage documents: relevant | irrelevant | needs_human.

    Deterministic metadata-only rules: year outside the configured
    scope -> irrelevant; byte-identical OCR duplicate -> irrelevant
    (first kept); unclassified form -> needs_human (never auto-dropped).
    Authority: a VALIDATED document is relevant by definition
    (validated_by_operator) -- the mechanical rules never demote it;
    explicit operator overrides (recorded via relevance_override) are
    honored for non-validated docs (operator_override). Verdicts are
    persisted as labels on the documents; nothing is deleted. Returns
    counts and id lists -- no PII."""
    from . import config as _cfg
    from .relevance import assess_relevance as _a, summarize as _s

    store = _store(data_dir)
    scope = _cfg.resolve("scope_years")
    docs = store.list(year=tax_year) if tax_year is not None else None
    verdicts = _a(store, scope, docs=docs, persist=True)
    return _jsonable(_s(verdicts))


@mcp.tool()
def relevance_override(doc_id: str, verdict: str, reason: str,
                       data_dir: str | None = None) -> dict:
    """Record an explicit operator override of a document's relevance
    verdict (relevant | irrelevant | needs_human) with a required
    reason. The override is appended to the audit registry
    (relevance_overrides.jsonl next to the store) as {doc_id, verdict,
    reason, ts}, applied to the document, and honored by assess_relevance
    on future runs (operator_override).

    OPERATOR-ONLY SURFACE: this tool acts ONLY on explicit operator
    direction. The mechanical pipeline never calls it. A validated
    document stays relevant even against an override
    (validated_by_operator dominates; the record is marked suppressed).
    Restoring an irrelevant document to the review queue is exactly
    what this tool is for. Returns {record, applied_verdict, suppressed}
    -- ids and reason codes only, no PII."""
    from .relevance import relevance_override as _o

    store = _store(data_dir)
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(f"unknown doc_id: {doc_id}")
    return _jsonable(_o(store, doc.doc_id, verdict, reason))


@mcp.tool()
def analyze_gaps(tax_year: int | None = None,
                 data_dir: str | None = None) -> dict:
    """Gap analysis: IRS wage & income transcript expectations vs
    ingested documents, per year.

    Returns PII-free shapes: {year: {expected_forms, missing_forms,
    n_transcript_payers, n_document_payers, transcript_forms,
    schedules_seen, n_docs, has_transcript}, report_path}. Per-payer
    detail (names) goes ONLY to the local report file for the
    operator's eyes. A year with no parsed transcript reports
    expected_forms=[] -- no ground truth, never a false all-clear."""
    from . import config as _cfg
    from .gaps import analyze_gaps as _g

    store = _store(data_dir)
    scope = _cfg.resolve("scope_years")
    return _jsonable(_g(store, scope, year=tax_year))
