"""Relevance triage: relevant vs irrelevant vs needs_human (blind-orchestrator safe).

Deterministic, metadata-only rules. The verdict is a LABEL persisted on
the Document -- nothing is ever deleted or hidden. Conservative by
construction: anything ambiguous lands in ``needs_human``, never
``irrelevant``. Irrelevant means "provably outside the amendment task"
(year out of scope, or a byte-identical duplicate scan).

Reason codes (stable strings, safe for the blind orchestrator):
    year_out_of_scope   tax_year is not None and outside scope_years
    duplicate_of:<id>   sha256 of OCR text matches another doc; the
                        lexicographically-first doc_id is kept, the rest
                        are duplicates
    unclassified        form_type == UNKNOWN (needs a human, never auto-dropped)
    in_scope            default: a classified doc inside the scope years
"""

from __future__ import annotations

import hashlib

from .models import Document

_VERDICTS = ("relevant", "irrelevant", "needs_human")


def _ocr_sha256(store, doc: Document) -> str | None:
    """sha256 of the doc's OCR text; None when unavailable (never raises).

    A doc whose OCR cannot be loaded is never declared a duplicate --
    absence of evidence is not evidence of duplication.
    """
    try:
        text = store.load_ocr(doc.doc_id)
    except (FileNotFoundError, OSError):
        return None
    if not text or not text.strip():
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assess_relevance(store, scope_years: list[int],
                     docs: list[Document] | None = None,
                     persist: bool = True) -> dict[str, dict]:
    """Verdict per doc_id: {verdict, reasons[]}.

    When persist=True the verdicts are written back into the store
    (Document.relevance). Pass docs= to triage a subset (e.g. one year);
    unassessed docs are simply left alone.
    """
    scope = set(scope_years)
    docs = list(store.list()) if docs is None else list(docs)

    # duplicate groups by OCR hash (only docs with loadable OCR participate)
    by_hash: dict[str, list[str]] = {}
    for d in docs:
        h = _ocr_sha256(store, d)
        if h is not None:
            by_hash.setdefault(h, []).append(d.doc_id)
    duplicate_of: dict[str, str] = {}
    for ids in by_hash.values():
        if len(ids) > 1:
            keep = sorted(ids)[0]
            for dup in sorted(ids)[1:]:
                duplicate_of[dup] = keep

    verdicts: dict[str, dict] = {}
    for d in docs:
        if d.tax_year is not None and d.tax_year not in scope:
            verdicts[d.doc_id] = {
                "verdict": "irrelevant",
                "reasons": ["year_out_of_scope"],
            }
        elif d.doc_id in duplicate_of:
            verdicts[d.doc_id] = {
                "verdict": "irrelevant",
                "reasons": [f"duplicate_of:{duplicate_of[d.doc_id]}"],
            }
        elif d.form_type == "UNKNOWN":
            verdicts[d.doc_id] = {
                "verdict": "needs_human",
                "reasons": ["unclassified"],
            }
        else:
            verdicts[d.doc_id] = {"verdict": "relevant", "reasons": ["in_scope"]}

    if persist:
        for d in docs:
            v = verdicts[d.doc_id]["verdict"]
            if d.relevance != v:
                d.relevance = v
                store.upsert(d)
    return verdicts


def summarize(verdicts: dict[str, dict]) -> dict:
    """PII-free roll-up: counts per verdict plus id lists with reasons."""
    counts = {v: 0 for v in _VERDICTS}
    by_verdict: dict[str, list[dict]] = {v: [] for v in _VERDICTS}
    for doc_id in sorted(verdicts):
        v = verdicts[doc_id]
        counts[v["verdict"]] += 1
        by_verdict[v["verdict"]].append(
            {"doc_id": doc_id, "reasons": v["reasons"]})
    return {
        "n_docs": len(verdicts),
        "counts": counts,
        "relevant_ids": [e["doc_id"] for e in by_verdict["relevant"]],
        "irrelevant": by_verdict["irrelevant"],
        "needs_human": by_verdict["needs_human"],
    }
