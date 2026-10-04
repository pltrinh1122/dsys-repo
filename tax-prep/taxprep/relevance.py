"""Relevance triage: relevant vs irrelevant vs needs_human (blind-orchestrator safe).

Deterministic, metadata-only rules. The verdict is a LABEL persisted on
the Document -- nothing is ever deleted or hidden. Conservative by
construction: anything ambiguous lands in ``needs_human``, never
``irrelevant``. Irrelevant means "provably outside the amendment task"
(year out of scope). Text-duplicate scans are NOT auto-dropped: they are
raised to the operator as needs_human (see duplicate_of below).

Reason codes (stable strings, safe for the blind orchestrator):
    year_out_of_scope   tax_year is not None and outside scope_years
    carryover_seed      tax_year below min(scope_years) but the form can
                        seed the capital-loss carryforward chain -- kept
                        relevant (N2), never year_out_of_scope
    duplicate_of:<id>   sha256 of OCR text matches another doc. Raised to
                        the operator as needs_human -- never auto-resolved.
                        (Arc B: L1 byte-identical duplicates are solved
                        structurally by bronze aliases -- one bronze row,
                        N aliases, counted once -- so there is no second
                        doc to judge; L2 text-identical duplicates are
                        raised via duplicates.dup_group and disposed by
                        explicit operator ruling. This rule keeps the
                        detection signal but must not double-handle what
                        the medallion duplicate machinery owns.)
    unclassified        form_type == UNKNOWN (needs a human, never auto-dropped)
    validated_by_operator
                        status == validated: human judgment dominates --
                        the mechanical rules never demote a validated
                        document to irrelevant (adopted falsification
                        fix). Dominates even a recorded override.
    operator_override   an explicit relevance_override record names this
                        verdict (explicit operator direction)
    in_scope            default: a classified doc inside the scope years
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Document

_VERDICTS = ("relevant", "irrelevant", "needs_human")

# N2: form types that can seed the capital-loss carryforward chain
# (--prior-st/--prior-lt). The Capital Loss Carryover Worksheet lives
# with the prior-year return package, so the prior-year 1040 (or an
# amended 1040-X carrying the same worksheet), Schedule D itself, and
# the IRS return transcript for the seed year all count. A wage &
# income transcript does NOT seed the chain -- it is ground truth for
# gap analysis, not a carryover source -- so it stays year_out_of_scope.
CARRYOVER_SEED_FORMS = frozenset(
    {"1040", "1040-X", "SCHEDULE_D", "RETURN_TRANSCRIPT"}
)


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
    seed_floor = min(scope)  # N2: seed years live strictly below this
    # Explicit operator overrides (relevance_override): these apply to
    # non-validated docs; validated docs are dominated by the
    # validated_by_operator rule above instead.
    overrides = _load_overrides(store)

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
        if d.status == "validated":
            # Falsification fix (adopted): a validated document is
            # relevant BY DEFINITION -- human judgment dominates
            # mechanical rules. The mechanical assessor never demotes a
            # validated doc; duplicates and year-out-of-scope never apply.
            # This dominates even a recorded override: validation is the
            # strongest operator signal available.
            verdicts[d.doc_id] = {
                "verdict": "relevant",
                "reasons": ["validated_by_operator"],
            }
        elif d.doc_id in overrides:
            # Explicit operator direction (recorded via relevance_override).
            rec = overrides[d.doc_id]
            verdicts[d.doc_id] = {
                "verdict": rec["verdict"],
                "reasons": ["operator_override"],
            }
        elif d.doc_id in duplicate_of:
            # Text-identical to an earlier doc: RAISED to the operator as
            # needs_human, never auto-resolved. Arc B owns L1/L2
            # disposition (bronze aliases; dup_group + explicit ruling);
            # the mechanical relevance triage must not double-handle it
            # by dropping the loser. Precedence over year/seed rules is
            # kept: the duplication signal is still detected first.
            verdicts[d.doc_id] = {
                "verdict": "needs_human",
                "reasons": [f"duplicate_of:{duplicate_of[d.doc_id]}"],
            }
        elif (
            d.tax_year is not None
            and d.tax_year < seed_floor
            and d.form_type in CARRYOVER_SEED_FORMS
        ):
            # N2: a carryover-seed source for the year before the scope
            # stays relevant -- dropping it would silently break the
            # carryforward chain's --prior-st/--prior-lt seed.
            verdicts[d.doc_id] = {
                "verdict": "relevant",
                "reasons": ["carryover_seed"],
            }
        elif d.tax_year is not None and d.tax_year not in scope:
            verdicts[d.doc_id] = {
                "verdict": "irrelevant",
                "reasons": ["year_out_of_scope"],
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


# -- explicit operator override ---------------------------------------

_OVERRIDES_FILENAME = "relevance_overrides.jsonl"


def _overrides_path(store) -> Path:
    return Path(store.data_dir) / _OVERRIDES_FILENAME


def _load_overrides(store) -> dict[str, dict]:
    """Read the append-only override registry: {doc_id: latest record}.

    Malformed lines are skipped, never fatal (the sidecar is operator
    bookkeeping, not store data). Records are {doc_id, verdict, reason,
    ts}; the last record per doc_id wins.
    """
    out: dict[str, dict] = {}
    path = _overrides_path(store)
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if (isinstance(rec, dict)
                and rec.get("doc_id")
                and rec.get("verdict") in _VERDICTS):
            out[rec["doc_id"]] = rec
    return out


def list_relevance_overrides(store) -> list[dict]:
    """Audit view of the override registry (latest record per doc_id).

    PII shape: doc_id, verdict, reason (operator's own words), ts.
    """
    overrides = _load_overrides(store)
    return [overrides[k] for k in sorted(overrides)]


def relevance_override(store, doc_id: str, verdict: str,
                       reason: str) -> dict:
    """Record an explicit operator override of a document's relevance.

    This is the RESTORE / re-triage path: it records {doc_id, verdict,
    reason, ts} in the append-only registry (``relevance_overrides.jsonl``
    next to the store), applies the verdict to the document immediately,
    and is honored by :func:`assess_relevance` on future runs.

    Authority ordering (documented, stable):

    * The mechanical assessor NEVER demotes a validated document --
      validated ⇒ relevant (``validated_by_operator``). An override
      recorded against a validated doc is kept in the registry but the
      applied verdict stays ``relevant`` while the doc is validated
      (the record is marked ``suppressed``); it takes effect if the
      doc ever leaves the validated state.
    * For non-validated docs the override verdict applies immediately
      and dominates every mechanical rule on the next
      :func:`assess_relevance` run (``operator_override``).

    Raises ValueError on a bad verdict or empty reason, KeyError on an
    unknown doc_id. The mechanical pipeline never calls this function --
    it exists only for explicit operator direction.
    """
    if verdict not in _VERDICTS:
        raise ValueError(
            f"override verdict must be one of {_VERDICTS}, got {verdict!r}")
    if not reason or not reason.strip():
        raise ValueError("override requires a non-empty --reason (audit trail)")
    doc = store.get(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "doc_id": doc.doc_id,
        "verdict": verdict,
        "reason": reason.strip(),
        "ts": ts,
    }
    path = _overrides_path(store)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    suppressed = doc.status == "validated" and verdict != "relevant"
    applied = "relevant" if doc.status == "validated" else verdict
    if doc.relevance != applied:
        doc.relevance = applied
        store.upsert(doc)
    return {"record": record, "applied_verdict": applied,
            "suppressed": suppressed}
