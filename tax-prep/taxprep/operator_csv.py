"""R23 addendum (Operator-approved 2026-10-04): Operator CSV format v2
and medallion repositioning.

PART 1 -- CSV FORMAT v2. UTF-8, header row "label,value", one file per
transcript PDF. Label-column prefixes:
  "@page N"  page marker: rows that follow come from PDF page N.
  "# "       heading level 1 (form / schedule / section).
  "## "      heading level 2.
  "% "       boilerplate (banner, dates, tracking number, footers,
             repeated headers) -- ignored entirely.
  "! "       Operator-marked SOURCE ERROR: the transcript itself is wrong
             here. The row text is kept for the record; never ingested.
  "\\"       escape: a real label that starts with # @ % ! or \\.
INVARIANT: prefixed rows have an empty value (their full text is in the
label). An unprefixed row is a data row: non-empty value, except a field
the transcript printed blank, which keeps its trailing ":" with an empty
value. Labels have trailing ":" removed (blank-printed fields keep it);
a label wrapping across PDF lines is one joined label (Operator-joined).
"# TRANSACTIONS" opens a transaction table: header row
CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT, then 5-cell rows led
by a 3-digit CODE; multi-line explanations stay in the EXPLANATION cell
(CSV quoting); @page/% rows may sit inside the table; the table ends at
the first unprefixed row not starting with a CODE.

PART 2 -- MEDALLION POSITION. Falsified: "producing these CSVs is
Raw -> Bronze". The Operator CSV is a NEW source document: its exact
bytes land in Bronze (content hash, idempotent), linked to the source
PDF's doc_id, the extractor version, and the Operator rule files that
produced it. Its data rows become Silver fields with provenance to the
CSV row and, via @page, to the PDF page; the PDF page image remains the
evidence snapshot. Prefixed rows never become fields; "!" rows are kept
only as audit notes. A CSV value disagreeing with a PDF-extracted value
is raised to the Operator (R16a), never mechanically resolved. A
re-edited CSV (new hash) supersedes the earlier CSV of the same PDF.
Operator decision: CSV-derived fields STILL go through the review UI
before gold -- the CSV edits validate the ingestion FORM, not the values.

Shared contract with taxprep.twocol: pair fields and operator fields are
both keyed by the normalized printed label (UPPERCASE, collapsed
whitespace) via :func:`taxprep.twocol.normalize_label`, imported here and
never redefined. Transaction rows use the X4 key scheme (tc_<code>,
tc_<code>_2, ...) so amounts corroborate against the machine's
transaction fields.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import duplicates
from .models import Document
from .twocol import TWOCOL_EXTRACTOR_ID, normalize_label

__all__ = [
    "OPERATOR_CSV_VERSION",
    "TEXT_SOURCE_OPERATOR_CSV",
    "FORM_TYPE_OPERATOR_CSV",
    "CSV_META_KEY",
    "AUDIT_NOTES_KEY",
    "SUPERSEDED_BY_KEY",
    "parse_operator_csv",
    "ingest_operator_csv",
    "latest_operator_csv_doc",
    "csv_import_hash",
    "values_agree",
]

# CSV format version produced/consumed by this module.
OPERATOR_CSV_VERSION = "2.0"

# text_source vocabulary: names WHICH text was used -- here, the
# Operator's adjusted CSV (cf. ingest.py TS_* / "broker-csv").
TEXT_SOURCE_OPERATOR_CSV = "operator-csv"

# Form type for the CSV-as-source-document (models.FORM_TYPES).
FORM_TYPE_OPERATOR_CSV = "OPERATOR_CSV"

# Reserved field keys on the CSV document (lowercase: cannot collide
# with UPPERCASE normalized label keys or tc_<code> keys).
CSV_META_KEY = "_csv_meta"
AUDIT_NOTES_KEY = "_audit_notes"
SUPERSEDED_BY_KEY = "_superseded_by"
_RESERVED_KEYS = frozenset({CSV_META_KEY, AUDIT_NOTES_KEY,
                            SUPERSEDED_BY_KEY})

# v2 label prefixes.
_PAGE_MARKER_RE = re.compile(r"^@page\s+(\d+)\s*$", re.IGNORECASE)
_CODE_RE = re.compile(r"^\d{3}$")
_TRANSACTIONS_TITLE = "TRANSACTIONS"
_ESCAPABLE = "#@%!\\"


def csv_import_hash(csv_text: str) -> str:
    """sha256 of the normalized CSV text (CRLF-tolerant, trailing
    whitespace-insensitive). Deterministic; no wall-clock input."""
    lines = csv_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = "\n".join(line.rstrip() for line in lines).rstrip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for cells in csv.reader(io.StringIO(
            text.replace("\r\n", "\n").replace("\r", "\n"))):
        if not cells or all(not c.strip() for c in cells):
            continue  # blank line
        rows.append([c for c in cells])
    return rows


def _classify_label(label: str) -> tuple[str, str]:
    """Classify a stripped label cell.

    Returns (kind, text): kind is one of "page", "h1", "h2",
    "boilerplate", "source_error", "data". ``text`` is the prefix-stripped
    remainder (page number for "page"), or the full label for "data"
    (escape already resolved).
    """
    if (label.startswith("\\") and len(label) > 1
            and label[1] in _ESCAPABLE):
        return ("data", label[1:])
    m = _PAGE_MARKER_RE.match(label)
    if m:
        return ("page", m.group(1))
    if label == "##" or label.startswith("## "):
        return ("h2", label[2:].strip())
    if label == "#" or label.startswith("# "):
        return ("h1", label[1:].strip())
    if label == "%" or label.startswith("% "):
        return ("boilerplate", label[1:].strip())
    if label == "!" or label.startswith("! "):
        return ("source_error", label[1:].strip())
    return ("data", label)


def _strip_trailing_colon(label: str) -> str:
    """Remove one trailing ':' (LABELS: trailing ':' removed)."""
    return label[:-1].rstrip() if label.endswith(":") else label


def parse_operator_csv(text: str) -> dict:
    """Parse an Operator CSV (format v2) into structured rows.

    Returns {"format": "v2", "pages", "data_rows", "transaction_rows",
    "source_errors", "headings"}. ``data_rows`` carry label/value/page/
    csv_row/printed_label/normalized/is_blank; ``transaction_rows`` carry
    code/explanation/cycle/date/amount/page/csv_row; ``source_errors``
    are audit notes (never fields); ``headings`` are structural.
    Raises ValueError on malformed rows (fail loud, never silently
    misparsed).
    """
    rows = _read_rows(text)
    if not rows:
        raise ValueError("operator CSV is empty")
    header = [c.strip().lower() for c in rows[0]]
    if len(header) < 2 or header[0] != "label" or header[1] != "value":
        raise ValueError(
            "operator CSV must start with a 'label,value' header row, "
            f"got {rows[0]!r}")

    data_rows: list[dict] = []
    transaction_rows: list[dict] = []
    source_errors: list[dict] = []
    headings: list[dict] = []
    pages: list[int] = [1]
    current_page = 1
    in_table = False
    expect_table_header = False

    for csv_row, cells in enumerate(rows[1:], start=2):
        # Spreadsheet saves may pad rows with empty trailing cells.
        while len(cells) > 1 and cells[-1].strip() == "":
            cells.pop()
        label = cells[0].strip() if cells else ""
        value = cells[1].strip() if len(cells) > 1 else ""
        extra = [c for c in cells[2:] if c.strip()]

        kind, ptext = _classify_label(label)

        # INVARIANT: prefixed rows have an empty value (their full text
        # is in the label).
        if kind in ("page", "h1", "h2", "boilerplate",
                    "source_error") and value:
            raise ValueError(
                f"CSV row {csv_row}: prefixed row must have an empty "
                f"value: {cells!r}")

        if kind == "page":
            current_page = int(ptext)
            if current_page not in pages:
                pages.append(current_page)
            continue  # page markers may sit inside a transaction table
        if kind == "boilerplate":
            continue  # ignored entirely; may sit inside a table
        if kind == "h1":
            headings.append({"level": 1, "text": ptext,
                             "page": current_page, "csv_row": csv_row})
            if ptext.upper() == _TRANSACTIONS_TITLE:
                in_table = True
                expect_table_header = True
            else:
                in_table = False
            continue
        if kind == "h2":
            headings.append({"level": 2, "text": ptext,
                             "page": current_page, "csv_row": csv_row})
            in_table = False
            continue
        if kind == "source_error":
            # The row's text is kept for the record; never a field.
            source_errors.append({"text": label, "page": current_page,
                                  "csv_row": csv_row})
            in_table = False
            continue

        # kind == "data" (ptext has the \-escape resolved)
        if expect_table_header:
            if not cells or cells[0].strip().upper() != "CODE":
                raise ValueError(
                    f"CSV row {csv_row}: expected the transaction-table "
                    f"header row after '# TRANSACTIONS', got {cells!r}")
            expect_table_header = False
            continue

        if in_table:
            if _CODE_RE.match(ptext):
                if len(cells) < 5:
                    raise ValueError(
                        f"CSV row {csv_row}: transaction row needs 5 "
                        f"cells: {cells!r}")
                if any(c.strip() for c in cells[5:]):
                    raise ValueError(
                        f"CSV row {csv_row}: unexpected extra cells: "
                        f"{cells!r}")
                transaction_rows.append({
                    "code": ptext,
                    "explanation": cells[1].strip(),
                    "cycle": cells[2].strip() or None,
                    "date": cells[3].strip() or None,
                    "amount": cells[4].strip() or None,
                    "page": current_page,
                    "csv_row": csv_row,
                })
                continue
            # The table ends at the first unprefixed row that does not
            # start with a CODE; fall through to data-row handling.
            in_table = False

        if extra:
            raise ValueError(
                f"CSV row {csv_row}: unexpected extra cells: {cells!r}")
        if not ptext:
            if value:
                raise ValueError(
                    f"CSV row {csv_row}: value without label: {cells!r}")
            continue
        if value == "":
            if ptext.endswith(":"):
                # Blank-printed field: keeps its trailing ":" per spec.
                data_rows.append({
                    "label": ptext,
                    "printed_label": ptext,
                    "value": None,
                    "is_blank": True,
                    "page": current_page,
                    "csv_row": csv_row,
                    "normalized": normalize_label(ptext),
                })
            else:
                raise ValueError(
                    f"CSV row {csv_row}: unprefixed label with an empty "
                    f"value must keep its trailing ':' (blank-printed "
                    f"field) or use a '# ' heading: {cells!r}")
        else:
            clean = _strip_trailing_colon(ptext)
            data_rows.append({
                "label": clean,
                "printed_label": ptext,
                "value": value,
                "is_blank": False,
                "page": current_page,
                "csv_row": csv_row,
                "normalized": normalize_label(clean),
            })

    if expect_table_header:
        raise ValueError(
            "operator CSV ends after '# TRANSACTIONS' with no header row")

    return {
        "format": "v2",
        "pages": pages,
        "data_rows": data_rows,
        "transaction_rows": transaction_rows,
        "source_errors": source_errors,
        "headings": headings,
    }


def _as_decimal(value) -> Decimal | None:
    """Decimal-safe parse; None when the value is not a number."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def values_agree(machine_value, operator_value) -> bool:
    """Money compares Decimal-safe; anything else compares exact."""
    m_dec, o_dec = _as_decimal(machine_value), _as_decimal(operator_value)
    if m_dec is not None and o_dec is not None:
        return m_dec == o_dec
    return str(machine_value) == str(operator_value)


def _machine_field_for(doc, key: str) -> dict | None:
    """The machine-captured field under a key, if it carries a value.

    Checks the bare key plus the stream-A collision forms
    ``pair:<key>`` / ``pair:<key>_2`` (a colliding legacy parser key
    keeps the bare form). Reserved operator keys are excluded.
    """
    if key in _RESERVED_KEYS:
        return None
    fields = doc.fields or {}
    for k in (key, f"pair:{key}", f"pair:{key}_2"):
        f = fields.get(k)
        if isinstance(f, dict) and f.get("value") not in (None, ""):
            return f
    return None


def _resolve_pdf_doc(store, doc_id: str, filename: str):
    """Return the transcript doc iff the CSV filename's stem matches the
    doc's bronze source stem; otherwise None (never guess)."""
    doc = store.get(doc_id)
    if doc is None or not doc.source_path:
        return None
    if Path(doc.source_path).stem != Path(filename).stem:
        return None
    return doc


def _csv_docs_for_pdf(store, pdf_doc_id: str) -> list:
    """All OPERATOR_CSV docs linked to a PDF doc (any supersede state)."""
    return [d for d in store.list(form=FORM_TYPE_OPERATOR_CSV)
            if d.parent_doc_id == pdf_doc_id]


def latest_operator_csv_doc(store, pdf_doc_id: str):
    """The current (non-superseded) OPERATOR_CSV doc for a PDF doc.

    None when no CSV was ingested. Deterministic tiebreak on doc_id;
    the ingest supersede logic maintains at most one non-superseded
    doc per PDF.
    """
    cands = [d for d in _csv_docs_for_pdf(store, pdf_doc_id)
             if not (d.fields or {}).get(SUPERSEDED_BY_KEY)]
    if not cands:
        return None
    return sorted(cands, key=lambda d: d.doc_id)[0]


def _dedup_key(counts: dict, base: str) -> str:
    """Deterministic ordinal-suffixed key (X4 scheme): base, base_2, ..."""
    counts[base] = counts.get(base, 0) + 1
    n = counts[base]
    return base if n == 1 else f"{base}_{n}"


def ingest_operator_csv(store, doc_id: str, csv_text: str, filename: str,
                        *, rule_files: list[str] | None = None) -> dict:
    """Ingest an Operator-adjusted transcript CSV (format v2).

    The CSV becomes a NEW source document: its exact bytes land in
    Bronze (content hash, idempotent), linked to the source PDF's doc_id,
    the extractor version, and the Operator rule files. Its data rows
    become Silver fields with provenance to the CSV row and, via @page,
    to the PDF page; the PDF page image remains the evidence snapshot.
    Prefixed rows never become fields; "!" rows are audit notes only.

    Every operator value is corroborated (R16a) against the machine
    field under the same key on the PDF doc (data rows) or the
    machine's transaction field (tc_<code> rows). Disagreements are
    raised via duplicates.raise_conflict -- never silently resolved on
    either side. A re-edited CSV (new hash) supersedes the earlier CSV
    of the same PDF.

    Returns {"doc_id", "pdf_doc_id", "n_rows", "n_conflicts",
    "csv_hash", "superseded": [...]}, {"duplicate_import": True,
    "doc_id": ...} on hash-identical re-import, or {"unresolved":
    filename} when the filename does not resolve to the doc.
    """
    pdf_doc = _resolve_pdf_doc(store, doc_id, filename)
    if pdf_doc is None:
        return {"unresolved": filename}

    # Bronze: the exact CSV bytes, content-addressed (idempotent).
    csv_bytes = csv_text.encode("utf-8")
    sha = hashlib.sha256(csv_bytes).hexdigest()
    store.store_bronze_bytes(sha, csv_bytes)
    csv_doc_id = sha[:16]  # R4: doc_id derives from the source bytes

    existing = store.get(csv_doc_id)
    if existing is not None and existing.form_type == FORM_TYPE_OPERATOR_CSV:
        # Same bytes re-ingested: no-op (supersede state untouched --
        # re-ingesting an old CSV never un-supersedes a newer one).
        return {"duplicate_import": True, "doc_id": csv_doc_id}

    parsed = parse_operator_csv(csv_text)

    fields: dict = {}
    key_counts: dict = {}
    n_rows = 0
    for row in parsed["data_rows"]:
        key = _dedup_key(key_counts, row["normalized"])
        fields[key] = {
            "value": row["value"],
            "confidence": "medium",
            "text_source": TEXT_SOURCE_OPERATOR_CSV,
            "page": row["page"],
            "csv_row": row["csv_row"],
            "printed_label": row["printed_label"],
            "is_blank": row["is_blank"],
            "raw_text": (f"{row['printed_label']}: {row['value']}"
                         if row["value"] is not None
                         else row["printed_label"]),
            "provenance": {"csv_row": row["csv_row"], "page": row["page"],
                           "pdf_doc_id": doc_id},
        }
        n_rows += 1
    for trow in parsed["transaction_rows"]:
        key = _dedup_key(key_counts, f"tc_{trow['code']}")
        fields[key] = {
            "value": trow["amount"],
            "confidence": "medium",
            "text_source": TEXT_SOURCE_OPERATOR_CSV,
            "page": trow["page"],
            "csv_row": trow["csv_row"],
            "printed_label": f"Transaction {trow['code']}",
            "raw_text": " ".join(
                p for p in (trow["code"], trow["explanation"],
                            trow["amount"] or "") if p),
            "transaction": {k: trow[k] for k in
                             ("code", "explanation", "cycle", "date",
                              "amount")},
            "provenance": {"csv_row": trow["csv_row"], "page": trow["page"],
                           "pdf_doc_id": doc_id},
        }
        n_rows += 1
    if parsed["source_errors"]:
        fields[AUDIT_NOTES_KEY] = [
            {"kind": "source_error", "text": e["text"],
             "page": e["page"], "csv_row": e["csv_row"]}
            for e in parsed["source_errors"]
        ]
    fields[CSV_META_KEY] = {
        "pdf_doc_id": doc_id,
        "filename": filename,
        "csv_hash": sha,
        "csv_format_version": OPERATOR_CSV_VERSION,
        "machine_extractor": TWOCOL_EXTRACTOR_ID,
        "rule_files": list(rule_files or []),
        "n_data_rows": len(parsed["data_rows"]),
        "n_transaction_rows": len(parsed["transaction_rows"]),
        "n_source_errors": len(parsed["source_errors"]),
    }

    csv_doc = Document(
        doc_id=csv_doc_id,
        tax_year=pdf_doc.tax_year,
        form_type=FORM_TYPE_OPERATOR_CSV,
        source_path=filename,
        ocr_text_ref="",
        fields=fields,
        source_sha256=sha,
        parent_doc_id=doc_id,
        text_source=TEXT_SOURCE_OPERATOR_CSV,
        # Operator decision: CSV-derived fields still go through the
        # review UI before gold (needs_review is the default; explicit).
        status="needs_review",
    )

    # Supersede: a re-edited CSV (new hash) supersedes the earlier
    # CSV(s) of the same PDF. The old docs keep their bytes and audit
    # notes; only the lookup skips them.
    superseded: list[str] = []
    for old in _csv_docs_for_pdf(store, doc_id):
        if old.doc_id == csv_doc_id:
            continue
        old_fields = dict(old.fields or {})
        if old_fields.get(SUPERSEDED_BY_KEY):
            continue
        old_fields[SUPERSEDED_BY_KEY] = csv_doc_id
        old.fields = old_fields
        store.upsert(old)
        superseded.append(old.doc_id)

    # R16a corroboration against the PDF doc's machine fields. The
    # operator value is never silently overwritten, nor the machine's.
    n_conflicts = 0
    for key, field in fields.items():
        if key in _RESERVED_KEYS:
            continue
        if field.get("value") in (None, ""):
            continue
        machine = _machine_field_for(pdf_doc, key)
        if machine is not None and not values_agree(
                machine.get("value"), field.get("value")):
            duplicates.raise_conflict(
                store, cls="corroboration", field=key,
                options=[
                    {"option_key": "machine",
                     "value_json": str(machine.get("value")),
                     "evidence_ref": doc_id},
                    {"option_key": "operator_csv",
                     "value_json": str(field.get("value")),
                     "evidence_ref": csv_doc_id},
                ])
            n_conflicts += 1

    store.upsert(csv_doc)
    return {"doc_id": csv_doc_id, "pdf_doc_id": doc_id, "n_rows": n_rows,
            "n_conflicts": n_conflicts, "csv_hash": sha,
            "superseded": superseded}
