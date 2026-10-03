"""Local MCP server for the tax-prep agent (Phase 6).

Exposes the tax-prep pipeline as Model Context Protocol tools over the
**stdio transport only**. The HTTP/SSE transports are deliberately NOT
exposed: taxpayer PII must never traverse a socket, and this server has
no reason to listen on any port. ``taxprep mcp`` runs ``mcp.run()``
with FastMCP's default stdio transport; there is no code path that
starts a network listener.

Privacy: same rules as the CLI -- synthetic fixtures in development,
real taxpayer material only ever on the operator's own machine, and
``data/`` stays gitignored.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .ingest import ingest_dir
from .review import apply_validation
from .store import DocumentStore

mcp = FastMCP("taxprep")

PACKAGE_DEFAULT_DATA_DIR = str(Path(__file__).resolve().parent.parent / "data")


def _store(data_dir: str | None) -> DocumentStore:
    """Resolve the data dir: explicit arg -> TAXPREP_DATA_DIR env -> package default."""
    return DocumentStore(data_dir or os.environ.get("TAXPREP_DATA_DIR")
                         or PACKAGE_DEFAULT_DATA_DIR)


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
    documents flagged as needing review."""
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
    type. Returns one summary dict per document."""
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
    """Show one document's full record: extracted fields (value, confidence,
    raw_text), status, and validation timestamp. Raises a tool error when
    the doc_id is unknown."""
    store = _store(data_dir)
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(f"unknown doc_id: {doc_id}")
    return _jsonable({
        "doc_id": doc.doc_id,
        "tax_year": doc.tax_year,
        "form_type": doc.form_type,
        "source_path": doc.source_path,
        "ocr_text_ref": doc.ocr_text_ref,
        "status": doc.status,
        "validated_at": doc.validated_at,
        "fields": doc.fields,
    })


@mcp.tool()
def validation_queue(tax_year: int | None = None, form_type: str | None = None,
                     data_dir: str | None = None) -> dict:
    """The human validation queue: documents with status transcribed or
    needs_review, optionally filtered. Includes per-year validated/total
    progress. Nothing downstream may consume unvalidated documents."""
    store = _store(data_dir)
    queue = [d for d in store.list(year=tax_year, form=form_type)
             if d.status in ("transcribed", "needs_review")]
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
                "n_fields": len(d.fields),
                "low_confidence_fields": sum(
                    1 for f in d.fields.values()
                    if isinstance(f, dict) and f.get("confidence") == "low"),
            }
            for d in queue
        ],
        "progress": progress,
    })


@mcp.tool()
def compute_carryforward(filing_status_by_year: dict,
                         prior_st: str | None = None,
                         prior_lt: str | None = None,
                         data_dir: str | None = None) -> dict:
    """Run the capital-loss carryforward chain (IRS Schedule D worksheet,
    lines 1-13, Decimal-exact) for each tax year 2023-2026 present in the
    store, from validated 1099-B lots only.

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
    return _jsonable({
        "table": result["table"],
        "years": result["years"],
        "warnings": result["warnings"],
        "lot_notes": lot_notes,
        "carryforward_into_2026": result["carryforward_into_2026"],
    })


@mcp.tool()
def validate_document(doc_id: str, corrections: dict, confirmed: list,
                      data_dir: str | None = None) -> dict:
    """Apply field corrections to one document and mark it validated.

    HUMAN-GATED WRITE TOOL: this is the only tool that mutates review
    state. MCP clients MUST require explicit user approval for every
    call -- never auto-approve it. The localhost review UI
    (`taxprep review`) remains the primary validation surface; this
    tool exists for corrections the operator directs explicitly.

    corrections maps box codes to corrected values
    (e.g. {"box1_wages": "105000.00"}); confirmed lists box codes the
    human verified as-is. Returns the updated status."""
    store = _store(data_dir)
    doc = apply_validation(store, doc_id, corrections, confirmed or [])
    return _jsonable({
        "doc_id": doc.doc_id,
        "status": doc.status,
        "validated_at": doc.validated_at,
        "n_fields": len(doc.fields),
    })
