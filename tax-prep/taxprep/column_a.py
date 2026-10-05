"""1040-X column-A builder (R21b + R23 stream D).

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

R23 stream D (this stream): after the legacy canonical-key lookup, each
entry ALSO resolves via the label dictionary (taxprep/label_dict.py):
for each of the entry's canonical keys, ``labels_for_canonical(key)``
gives the normalized printed labels, which are looked up in the doc's
machine pair-capture fields (stream A, taxprep/twocol.py --
``doc.fields[<NORMALIZED_LABEL>]``, ``pair:<label>``/``pair:<label>_2``
on collision) and in the linked OPERATOR_CSV document's fields (stream
B, R23 addendum medallion position). The Operator CSV is the Operator's
own final adjustment: when machine and Operator both carry the line and
disagree, the Operator value wins and the machine/operator corroboration
conflict raised at ingest (R16a) is surfaced on the entry -- never
re-raised here, never silently dropped. When a line is absent from every
validated doc but present on an unvalidated transcript/original doc (or
an unvalidated linked OPERATOR_CSV doc) for the year, the entry is
PENDING_VALIDATION (CA1) -- distinct from MISSING in status and in the
coverage counts.

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

import hashlib
from decimal import Decimal, InvalidOperation

from . import duplicates
from .label_dict import labels_for_canonical
from .operator_csv import latest_operator_csv_doc, values_agree
from .twocol import normalize_label

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

# R23 stream D: pair-capture source labels, _SOURCE_LABELS style.
_PAIR_SOURCE_LABELS = {
    _RETURN_TRANSCRIPT: "return_transcript_pairs",
    _RECORD_OF_ACCOUNT: "record_of_account_pairs",
    _ORIGINAL_RETURN: "original_return_pairs",
}
_OPERATOR_CSV_SOURCE = "operator_csv"

MISSING = "MISSING"
CONFLICT = "CONFLICT"
PRESENT = "present"
PENDING_VALIDATION = "PENDING_VALIDATION"


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
    link shape). Operator-CSV ``field`` keys resolve on the linked
    OPERATOR_CSV document (R23 addendum medallion position).
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


def _pending_candidates(store, year: int) -> list:
    """Unvalidated transcript/original docs for the year (CA1).

    These feed the PENDING_VALIDATION check, never the present/conflict
    resolution. Excluded docs are out-of-scope-person -- never
    candidates. Deterministic doc_id order. Read-only.
    """
    docs = [
        d for d in store.list(year=year)
        if d.status not in ("validated", "excluded")
        and d.form_type in (_RETURN_TRANSCRIPT, _RECORD_OF_ACCOUNT,
                            _ORIGINAL_RETURN)
    ]
    return sorted(docs, key=lambda d: d.doc_id)


def _line_hits(docs: list, keys: tuple[str, ...]) -> list[dict]:
    """Every (doc, key) hit for a line's transcript keys, doc_id order."""
    hits = []
    for doc in docs:
        for key in keys:
            f = (doc.fields or {}).get(key)
            if isinstance(f, dict) and f.get("value") not in (None, ""):
                hits.append({"doc": doc, "key": key, "field": f})
    return hits


def _r23_labels(keys: tuple[str, ...]) -> list[str]:
    """Normalized dictionary labels for a line's canonical keys.

    The normalized canonical key itself plus every
    ``labels_for_canonical`` label, deduplicated, deterministic order.
    """
    labels: list[str] = []
    for key in keys:
        for candidate in (normalize_label(key),
                          *(normalize_label(lab)
                            for lab in labels_for_canonical(key))):
            if candidate and candidate not in labels:
                labels.append(candidate)
    return labels


def _pair_field_for(doc, label: str) -> tuple[str | None, dict | None]:
    """Machine pair-capture field for a normalized label.

    Bare normalized key first, then the stream-A collision forms
    ``pair:<label>`` / ``pair:<label>_2`` (a colliding legacy parser key
    keeps the bare form). Returns (field_key, field) or (None, None).
    """
    fields = doc.fields or {}
    for key in (label, f"pair:{label}", f"pair:{label}_2"):
        f = fields.get(key)
        if isinstance(f, dict) and f.get("value") not in (None, ""):
            return key, f
    return None, None


def _op_field_for(csv_doc, label: str) -> dict | None:
    """Operator-CSV field for a normalized label on its own document.

    R23 addendum medallion position: operator fields live on the linked
    OPERATOR_CSV document (keyed by normalized label), not in a
    namespace on the transcript doc.
    """
    f = (csv_doc.fields or {}).get(label)
    if isinstance(f, dict) and f.get("value") not in (None, ""):
        return f
    return None


def _pair_hits(docs: list, keys: tuple[str, ...]) -> list[dict]:
    """Machine (two-column pair capture) hits for a line, doc order."""
    labels = _r23_labels(keys)
    hits = []
    for doc in docs:
        for label in labels:
            key, f = _pair_field_for(doc, label)
            if f is not None:
                hits.append({
                    "doc": doc, "label": label, "key": key, "field": f,
                    "source": _PAIR_SOURCE_LABELS[doc.form_type],
                })
    return hits


def _op_hits(store, docs: list, keys: tuple[str, ...]) -> list[dict]:
    """Operator-CSV hits for a line: validated CSV docs linked to the
    given transcript/original docs (R23 addendum medallion position).

    Each hit carries both the CSV doc (the value's source) and the PDF
    doc (for machine-field corroboration lookup). Doc order follows the
    input docs. Operator decision: unvalidated CSV docs never supply
    values here (they surface via PENDING_VALIDATION instead).
    """
    labels = _r23_labels(keys)
    hits = []
    for doc in docs:
        csv_doc = latest_operator_csv_doc(store, doc.doc_id)
        if csv_doc is None or csv_doc.status != "validated":
            continue
        for label in labels:
            f = _op_field_for(csv_doc, label)
            if f is not None:
                hits.append({
                    "doc": csv_doc, "pdf_doc": doc, "label": label,
                    "key": label, "field": f,
                    "source": _OPERATOR_CSV_SOURCE,
                })
    return hits


def _machine_operator_conflict_id(store, label: str) -> str | None:
    """Id of the ingest-raised machine/operator corroboration conflict.

    Recomputes the deterministic id (duplicates contract section 6:
    sha256("corroboration:<field>:machine,operator_csv")[:32]) -- the
    exact (class, field, option keys) ``ingest_operator_csv`` raises
    with -- and returns it only if that conflict row exists (values
    agreed at ingest -> never raised -> None). Read-only: conflict
    payloads (values) are never read here (blind-orchestrator
    contract); the conflict is never re-raised (this is a read-model).
    """
    cid = hashlib.sha256(
        f"corroboration:{label}:machine,operator_csv".encode("utf-8")
    ).hexdigest()[:32]
    with store.txn() as conn:
        row = conn.execute(
            "SELECT 1 FROM conflict WHERE conflict_id = ?", (cid,)
        ).fetchone()
    return cid if row else None


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


def _formatted_value(field: dict) -> str:
    """Decimal-safe string for a sourced field value."""
    val = _as_decimal(field["value"])
    return format(val, "f") if val is not None else str(field["value"])


def build_column_a(store, year: int) -> dict:
    """Build the 1040-X column-A lines for ``year`` (read-model).

    Returns ``{"tax_year", "lines": [...], "conflicts_raised": [...],
    "coverage": {...}}``. Each line entry::

        {"line", "label",
         "status": "present"|"MISSING"|"CONFLICT"|"PENDING_VALIDATION",
         "value": <Decimal-safe str> | None,
         "source": "return_transcript"|"record_of_account"|
                   "original_return"|"return_transcript_pairs"|
                   "record_of_account_pairs"|"original_return_pairs"|
                   "operator_csv" | None,
         "source_doc_id": <doc_id> | None,
         "provenance": {...} | None,      # R15/R19, present lines only
         "also_seen": [...],              # other docs carrying the line
         "conflict_id": <id> | None,      # 2025 corroboration, or the
                                          # ingest-raised machine/operator
                                          # conflict on operator-wins lines
         "pending_doc_ids": [...]}        # PENDING_VALIDATION only

    MISSING lines carry value None, source None, provenance None --
    never zero, never an error. PENDING_VALIDATION lines carry value
    None, source None, the first candidate doc as ``source_doc_id``,
    and every unvalidated candidate doc in ``pending_doc_ids``. The
    store is not mutated (no document or gold writes); the sole
    exception is the 2025 corroboration conflict raise, reported in
    ``conflicts_raised``.

    Resolution order per line (deterministic):
    1. legacy 2025 transcript-vs-original disagreement -> CONFLICT
       (byte-identical to pre-R23 behavior);
    2. Operator-CSV hits -- the Operator's own final adjustment wins
       over machine capture for the line (see precedence note below);
    3. legacy transcript/original hits (source-of-record order),
       R23 hits surfacing in also_seen;
    4. machine pair-capture hits;
    5. CA1: the line's dictionary keys on an unvalidated doc ->
       PENDING_VALIDATION, else MISSING.
    """
    docs = _validated_sources(store, year)
    transcripts = [d for d in docs
                   if d.form_type in (_RETURN_TRANSCRIPT, _RECORD_OF_ACCOUNT)]
    originals = [d for d in docs if d.form_type == _ORIGINAL_RETURN]
    candidates = _pending_candidates(store, year)

    lines = []
    conflicts_raised = []
    n_present = 0
    n_pending = 0
    for code, label, keys in COLUMN_A_LINES:
        entry = {"line": code, "label": label, "status": MISSING,
                 "value": None, "source": None, "source_doc_id": None,
                 "provenance": None, "also_seen": [], "conflict_id": None}
        if not keys:
            lines.append(entry)
            continue
        t_hits = _line_hits(transcripts, keys)
        o_hits = _line_hits(originals, keys)
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
        pair_hits = _pair_hits(transcripts + originals, keys)
        op_hits = _op_hits(store, transcripts + originals, keys)
        if op_hits:
            # PRECEDENCE (R23): the Operator CSV is the Operator's own
            # final adjustment -- when machine and Operator both carry
            # the line, the Operator value wins. Agreement collapses to
            # one entry; disagreement surfaces the ingest-raised
            # machine/operator corroboration conflict on the entry (the
            # conflict already exists from ingest -- it is looked up,
            # never re-raised here, so this stays a read-model).
            primary = op_hits[0]
            primary_val = _as_decimal(primary["field"]["value"])
            entry["status"] = PRESENT
            entry["value"] = _formatted_value(primary["field"])
            entry["source"] = _OPERATOR_CSV_SOURCE
            entry["source_doc_id"] = primary["doc"].doc_id
            entry["provenance"] = _provenance_for(
                primary["field"], primary["doc"].doc_id, primary["key"])
            _, mfield = _pair_field_for(primary["pdf_doc"], primary["label"])
            if (mfield is not None
                    and not values_agree(mfield.get("value"),
                                         primary["field"].get("value"))):
                entry["conflict_id"] = _machine_operator_conflict_id(
                    store, primary["label"])
            for h in (t_hits + o_hits + pair_hits + op_hits[1:]):
                hv = _as_decimal(h["field"]["value"])
                entry["also_seen"].append({
                    "source": h.get("source")
                    or _SOURCE_LABELS[h["doc"].form_type],
                    "source_doc_id": h["doc"].doc_id,
                    "value": (format(hv, "f") if hv is not None
                              else str(h["field"]["value"])),
                    "agrees": hv == primary_val,
                })
            n_present += 1
            lines.append(entry)
            continue
        if t_hits or o_hits:
            # Source of record: the return transcript when present
            # (2023/2024 rule), else the record of account, else the
            # original return alone (2025 without transcripts).
            # Alternates that disagree are surfaced in also_seen --
            # never silently resolved. R23 hits ride along as alternates
            # (new data; legacy-only fixtures produce byte-identical
            # also_seen).
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
            for h in pair_hits:
                hv = _as_decimal(h["field"]["value"])
                entry["also_seen"].append({
                    "source": h["source"],
                    "source_doc_id": h["doc"].doc_id,
                    "value": (format(hv, "f") if hv is not None
                              else str(h["field"]["value"])),
                    "agrees": hv == primary_val,
                })
            n_present += 1
            lines.append(entry)
            continue
        if pair_hits:
            primary = pair_hits[0]
            primary_val = _as_decimal(primary["field"]["value"])
            entry["status"] = PRESENT
            entry["value"] = _formatted_value(primary["field"])
            entry["source"] = primary["source"]
            entry["source_doc_id"] = primary["doc"].doc_id
            entry["provenance"] = _provenance_for(
                primary["field"], primary["doc"].doc_id, primary["key"])
            for h in pair_hits[1:]:
                hv = _as_decimal(h["field"]["value"])
                entry["also_seen"].append({
                    "source": h["source"],
                    "source_doc_id": h["doc"].doc_id,
                    "value": (format(hv, "f") if hv is not None
                              else str(h["field"]["value"])),
                    "agrees": hv == primary_val,
                })
            n_present += 1
            lines.append(entry)
            continue
        # CA1: absent from every validated doc, but the line's
        # dictionary keys are present on unvalidated transcript/original
        # docs for the year -- or on unvalidated OPERATOR_CSV docs linked
        # to this year's transcripts (R23 addendum: CSV-derived fields
        # need review-UI validation before gold). Scoped to R23
        # machine/operator capture keys (pair fields + operator CSV):
        # legacy parser keys on unvalidated docs keep the pre-R23
        # MISSING-first-class behavior (test_column_a_ignores_unvalidated
        # pins it).
        pending_ids: list[str] = []
        for d in candidates:
            if _pair_hits([d], keys):
                pending_ids.append(d.doc_id)
        labels = _r23_labels(keys)
        for pdf_doc in transcripts + originals + candidates:
            csv_doc = latest_operator_csv_doc(store, pdf_doc.doc_id)
            if csv_doc is None or csv_doc.status == "validated":
                continue
            if any(_op_field_for(csv_doc, lab) is not None
                   for lab in labels):
                if csv_doc.doc_id not in pending_ids:
                    pending_ids.append(csv_doc.doc_id)
        if pending_ids:
            entry["status"] = PENDING_VALIDATION
            entry["source_doc_id"] = pending_ids[0]
            entry["pending_doc_ids"] = pending_ids
            n_pending += 1
            lines.append(entry)
            continue
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
            "n_pending_validation": n_pending,
            "n_source_docs": len(docs),
        },
    }
