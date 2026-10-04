"""1040-X column-A builder (R21b).

A READ-MODEL over validated documents + transcripts: given a store and
a tax year, it builds the "original amount" (column A) lines for
Form 1040-X. It never mutates gold or the document store -- the only
write it can ever perform is the 2025 corroboration conflict raise
(which is the point: a disagreement is never silently resolved).

Line universe (Form 1040-X, December 2025 revision -- the continuous-use
form used to amend 2023/2024/2025; verified against the IRS Instructions
for Form 1040-X (12/2025), https://www.irs.gov/instructions/i1040x):
each entry maps from IRS Tax Return Transcript parser keys
(taxprep/transcript.py). Lines the transcripts do not carry are flagged
MISSING -- first-class output, never defaulted, never zero-filled, and
never computed from other lines.

Sources of record:
* 2023/2024 -- the Operator has no original returns: the IRS Tax Return
  Transcript (+ Record of Account) is the SOURCE OF RECORD.
* 2025 -- the original 1040 (R20 box/line extraction; designed for its
  absence) corroborated with the 2025 transcripts. A line present in
  both with disagreeing values raises an R16a ``corroboration``
  conflict to the Operator; the entry is flagged CONFLICT and carries
  no chosen value.

Return-transcript line coverage is small (~2.5% of 1040 lines mapped),
so most entries are MISSING on real-shaped data. That is correct
behavior: the tests assert MISSING rather than treating it as failure.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from . import duplicates

# Column-A line universe: (code, label, transcript keys by priority).
# Computed lines (L8, L19, L21) and reserved lines (L9) are NOT entries:
# the builder sources original amounts, never derives them.
COLUMN_A_LINES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("L1", "Adjusted gross income (AGI)", ("agi",)),
    ("L2", "Itemized deductions or standard deduction", ()),
    ("L4a", "Qualified business income deduction", ()),
    ("L4b", "Schedule 1-A deductions: tips, overtime, car loan interest, "
            "seniors (2025+)", ()),
    ("L5", "Taxable income", ("taxable_income",)),
    ("L6", "Tax", ()),
    ("L7", "Nonrefundable credits", ()),
    ("L10", "Other taxes", ()),
    ("L11", "Total tax", ("total_tax",)),
    ("L12", "Withholding (federal income tax + excess SS/RRTA)", ("withholding",)),
    ("L13", "Estimated tax payments", ("estimated_payments",)),
    ("L14", "Earned income credit (EIC)", ()),
    ("L15", "Refundable credits", ()),
    ("L16", "Amount paid with extension or tax return", ()),
    ("L17", "Total payments", ("total_payments",)),
    ("L18", "Overpayment (as shown on original return)", ("refund",)),
    ("L20", "Amount you owe", ("amount_owed",)),
    ("L22", "Overpayment received as refund", ()),
    ("L23", "Overpayment applied to estimated tax", ()),
)

# Source form types the builder reads (validated documents only).
_RETURN_TRANSCRIPT = "RETURN_TRANSCRIPT"
_RECORD_OF_ACCOUNT = "RECORD_OF_ACCOUNT"
_ORIGINAL_RETURN = "1040"

# Source labels carried on each line entry.
_SOURCE_LABELS = {
    _RETURN_TRANSCRIPT: "return_transcript",
    _RECORD_OF_ACCOUNT: "record_of_account",
    _ORIGINAL_RETURN: "original_return",
}

MISSING = "MISSING"
CONFLICT = "CONFLICT"
PRESENT = "present"


def _as_decimal(value) -> Decimal | None:
    """Decimal-safe parse; None when the value is not a number.

    Values are Decimal-safe strings end to end -- never floats.
    """
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _provenance_for(field: dict, doc_id: str, key: str) -> dict:
    """R15/R19 provenance shape for one sourced line.

    Reuses the existing field-provenance shapes: the R15 geometry dict
    recorded at extraction (``field["provenance"]``), the verbatim
    source line (``raw_text``), the extraction span, and the confidence
    -- plus an ``evidence_ref`` pointer (doc_id + field key) the
    Operator can open in the review evidence pane (the existing R19
    link shape).
    """
    return {
        "confidence": field.get("confidence"),
        "raw_text": field.get("raw_text"),
        "char_span": field.get("char_span"),
        "geometry": field.get("provenance") or field.get("geometry"),
        "evidence_ref": {"doc_id": doc_id, "field": key},
    }


def _validated_sources(store, year: int) -> list:
    """Validated transcript/original docs for the year.

    Ordered by source authority, then doc_id: the return transcript is
    the source of record (R21b), then the record of account, then the
    original 1040. Out-of-scope-person docs are status "excluded", never
    "validated", so the scope filter is honored structurally. Read-only.
    """
    docs = [
        d for d in store.list(year=year)
        if d.status == "validated"
        and d.form_type in (_RETURN_TRANSCRIPT, _RECORD_OF_ACCOUNT,
                            _ORIGINAL_RETURN)
    ]
    priority = {_RETURN_TRANSCRIPT: 0, _RECORD_OF_ACCOUNT: 1,
                _ORIGINAL_RETURN: 2}
    return sorted(docs, key=lambda d: (priority[d.form_type], d.doc_id))


def _line_hits(docs: list, keys: tuple[str, ...]) -> list[dict]:
    """Every (doc, key) hit for a line's transcript keys, doc_id order."""
    hits = []
    for doc in docs:
        for key in keys:
            f = (doc.fields or {}).get(key)
            if isinstance(f, dict) and f.get("value") not in (None, ""):
                hits.append({"doc": doc, "key": key, "field": f})
    return hits


def _raise_corroboration_conflict(store, *, line: str, label: str,
                                  transcript_hit: dict,
                                  original_hit: dict) -> str:
    """Raise the 2025 original-vs-transcript disagreement (R16a).

    Options are the two disagreeing values (Decimal-safe strings);
    evidence_refs point at the source docs. Idempotent on re-raise.
    """
    tdoc = transcript_hit["doc"]
    odoc = original_hit["doc"]
    return duplicates.raise_conflict(
        store, cls="corroboration", field=line,
        options=[
            {"option_key": "return_transcript",
             "value_json": str(transcript_hit["field"]["value"]),
             "evidence_ref": tdoc.doc_id},
            {"option_key": "original_return",
             "value_json": str(original_hit["field"]["value"]),
             "evidence_ref": odoc.doc_id},
        ])


def build_column_a(store, year: int) -> dict:
    """Build the 1040-X column-A lines for ``year`` (read-model).

    Returns ``{"tax_year", "lines": [...], "conflicts_raised": [...],
    "coverage": {...}}``. Each line entry::

        {"line", "label", "status": "present"|"MISSING"|"CONFLICT",
         "value": <Decimal-safe str> | None,
         "source": "return_transcript"|"record_of_account"|
                   "original_return" | None,
         "source_doc_id": <doc_id> | None,
         "provenance": {...} | None,      # R15/R19, present lines only
         "also_seen": [...],              # other docs carrying the line
         "conflict_id": <id> | None}      # 2025 corroboration only

    MISSING lines carry value None, source None, provenance None --
    never zero, never an error. The store is not mutated (no document
    or gold writes); the sole exception is the 2025 corroboration
    conflict raise, reported in ``conflicts_raised``.
    """
    docs = _validated_sources(store, year)
    transcripts = [d for d in docs
                   if d.form_type in (_RETURN_TRANSCRIPT, _RECORD_OF_ACCOUNT)]
    originals = [d for d in docs if d.form_type == _ORIGINAL_RETURN]

    lines = []
    conflicts_raised = []
    n_present = 0
    for code, label, keys in COLUMN_A_LINES:
        entry = {"line": code, "label": label, "status": MISSING,
                 "value": None, "source": None, "source_doc_id": None,
                 "provenance": None, "also_seen": [], "conflict_id": None}
        if not keys:
            lines.append(entry)
            continue
        t_hits = _line_hits(transcripts, keys)
        o_hits = _line_hits(originals, keys)
        if not t_hits and not o_hits:
            lines.append(entry)
            continue
        # 2025 corroboration: an original-return line and a transcript
        # line for the same column-A line must agree; disagreement is
        # raised, never picked.
        if t_hits and o_hits:
            t_val = _as_decimal(t_hits[0]["field"]["value"])
            o_val = _as_decimal(o_hits[0]["field"]["value"])
            if t_val is not None and o_val is not None and t_val != o_val:
                cid = _raise_corroboration_conflict(
                    store, line=code, label=label,
                    transcript_hit=t_hits[0], original_hit=o_hits[0])
                entry["status"] = CONFLICT
                entry["conflict_id"] = cid
                entry["also_seen"] = [
                    {"source": _SOURCE_LABELS[h["doc"].form_type],
                     "source_doc_id": h["doc"].doc_id,
                     "value": str(h["field"]["value"])}
                    for h in (t_hits + o_hits)]
                conflicts_raised.append(
                    {"line": code, "conflict_id": cid,
                     "transcript_doc": t_hits[0]["doc"].doc_id,
                     "original_doc": o_hits[0]["doc"].doc_id})
                lines.append(entry)
                continue
        # Source of record: the return transcript when present (2023/2024
        # rule), else the record of account, else the original return
        # alone (2025 without transcripts). Alternates that disagree
        # are surfaced in also_seen -- never silently resolved.
        primary = t_hits[0] if t_hits else o_hits[0]
        primary_val = _as_decimal(primary["field"]["value"])
        entry["status"] = PRESENT
        entry["value"] = (format(primary_val, "f")
                          if primary_val is not None
                          else str(primary["field"]["value"]))
        entry["source"] = _SOURCE_LABELS[primary["doc"].form_type]
        entry["source_doc_id"] = primary["doc"].doc_id
        entry["provenance"] = _provenance_for(
            primary["field"], primary["doc"].doc_id, primary["key"])
        for h in (t_hits[1:] + o_hits if t_hits else o_hits[1:]):
            hv = _as_decimal(h["field"]["value"])
            entry["also_seen"].append({
                "source": _SOURCE_LABELS[h["doc"].form_type],
                "source_doc_id": h["doc"].doc_id,
                "value": (format(hv, "f") if hv is not None
                          else str(h["field"]["value"])),
                "agrees": hv == primary_val,
            })
        n_present += 1
        lines.append(entry)

    return {
        "tax_year": year,
        "lines": lines,
        "conflicts_raised": conflicts_raised,
        "coverage": {
            "n_lines": len(lines),
            "n_present": n_present,
            "n_missing": sum(1 for e in lines if e["status"] == MISSING),
            "n_conflict": sum(1 for e in lines if e["status"] == CONFLICT),
            "n_source_docs": len(docs),
        },
    }
