"""Broker CSV ingest (R7): CSV rows -> 1099-B lot Documents.

Each data row becomes one 1099-B Document whose fields are the lot
record that carryforward.from_store() consumes: ``term``,
``1d_proceeds``, ``1e_basis`` (+ ``date_acquired`` / ``date_sold`` when
the broker provides them). Documents are created with status
``needs_review`` -- the Operator validates them in the review UI
before from_store will consume them.

Per-broker column mapping: BROKER_MAPS maps a broker name to
{broker column name -> canonical lot field}. Headers are normalized
(stripped, casefolded, whitespace-collapsed) before lookup. Columns
that match no canonical field are NEVER dropped silently: they are
kept aside in an ``extra_columns`` field ({column: value}) on the
same document.

Identity: doc_id = <sha256(csv bytes)[:16]>-r<row> (1-based data row),
so re-ingesting the same CSV is idempotent and carries no filename.

Money values are kept as the broker's raw strings (Decimal-safe --
never floated); from_store coerces them. Term values are normalized
to short|long; anything else is kept verbatim (from_store excludes
unknown terms with a loud warning -- never guessed).

Synthetic fixtures only in tests. Fully local, deterministic.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .ingest import source_doc_id
from .models import Document
from .store import DocumentStore

# Canonical lot fields (what from_store reads, plus dates).
CANONICAL_FIELDS = ("proceeds", "basis", "term",
                    "date_acquired", "date_sold")

# Canonical field -> 1099-B field code on the Document.
FIELD_CODES = {
    "proceeds": "1d_proceeds",
    "basis": "1e_basis",
    "term": "term",
    "date_acquired": "date_acquired",
    "date_sold": "date_sold",
}

# Broker column name (normalized) -> canonical field. "generic" covers
# common header spellings; named brokers are best-effort provisional
# maps -- the Operator confirms every document in review before any
# figure is consumed.
BROKER_MAPS: dict[str, dict[str, str]] = {
    "generic": {
        "proceeds": "proceeds",
        "sales proceeds": "proceeds",
        "gross proceeds": "proceeds",
        "cost basis": "basis",
        "cost": "basis",
        "basis": "basis",
        "term": "term",
        "holding period": "term",
        "gain/loss term": "term",
        "date acquired": "date_acquired",
        "acquired": "date_acquired",
        "acquisition date": "date_acquired",
        "date sold": "date_sold",
        "sold": "date_sold",
        "sale date": "date_sold",
        "disposal date": "date_sold",
    },
    # Best-effort provisional maps (Operator-confirmed in review).
    "fidelity": {
        "proceeds": "proceeds",
        "cost basis": "basis",
        "term": "term",
        "date acquired": "date_acquired",
        "date sold": "date_sold",
        "description": "description",
    },
    "schwab": {
        "proceeds": "proceeds",
        "cost basis": "basis",
        "term": "term",
        "date acquired": "date_acquired",
        "date sold": "date_sold",
        "security description": "description",
    },
}

_TERM_MAP = {
    "short": "short", "s": "short", "st": "short",
    "long": "long", "l": "long", "lt": "long",
}


def _norm_header(h: str) -> str:
    return " ".join(h.strip().casefold().split())


def _norm_term(raw: str) -> tuple[str, str]:
    """(canonical_term, confidence). Unknown terms are kept verbatim
    with low confidence -- from_store excludes them loudly."""
    key = _norm_header(raw)
    if key in _TERM_MAP:
        return _TERM_MAP[key], "high"
    return raw.strip(), "low"


def _field(value, confidence="medium", raw_text=""):
    return {"value": value, "confidence": confidence, "raw_text": raw_text}


def ingest_csv(csv_path: str | Path, broker: str, year: int,
               store: DocumentStore) -> list[Document]:
    """Ingest a broker CSV into one 1099-B Document per data row.

    Raises ValueError for an unknown broker (naming the known ones --
    fail closed, never silently mis-mapped) or an unreadable file.
    """
    broker_key = broker.strip().casefold()
    if broker_key not in BROKER_MAPS:
        known = ", ".join(sorted(BROKER_MAPS))
        raise ValueError(f"unknown broker {broker!r}: known brokers: {known}")
    col_map = BROKER_MAPS[broker_key]

    path = Path(csv_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read CSV {path}: {exc}")
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ValueError(f"CSV {path} has no data rows")
    if not rows[0]:
        raise ValueError(f"CSV {path} has no header row")

    csv_sha = hashlib.sha256(raw).hexdigest()
    base_id = source_doc_id(raw)

    docs: list[Document] = []
    for n, row in enumerate(rows, start=1):
        # normalized header -> (original header, value)
        normed = {_norm_header(h or ""): (h, v)
                  for h, v in row.items() if h}
        fields: dict = {}
        used_originals: set[str] = set()
        for norm_h, (orig_h, val) in normed.items():
            canon = col_map.get(norm_h)
            if canon is None or canon not in FIELD_CODES:
                continue
            used_originals.add(orig_h)
            if canon == "term":
                term, conf = _norm_term(val or "")
                fields[FIELD_CODES[canon]] = _field(term, conf)
            else:
                # Money/dates: keep the broker's raw string (Decimal-safe).
                fields[FIELD_CODES[canon]] = _field((val or "").strip())
        # Unknown columns: kept aside, never dropped silently.
        extra = {orig: (row[orig] or "")
                 for orig in row if orig and orig not in used_originals}
        if extra:
            fields["extra_columns"] = _field(extra, "medium")
        fields["broker"] = _field(broker.strip(), "high")

        doc = Document(
            doc_id=f"{base_id}-r{n}",
            tax_year=year,
            form_type="1099-B",
            source_path=str(path),
            ocr_text_ref="",
            fields=fields,
            status="needs_review",
            text_source="broker-csv",
        )
        doc.source_sha256 = csv_sha
        doc.ocr_text_ref = store.save_ocr(doc.doc_id,
                                         "\n".join(f"{k}={v!r}"
                                                   for k, v in row.items()
                                                   if k))
        store.upsert(doc)
        docs.append(doc)
    return docs
