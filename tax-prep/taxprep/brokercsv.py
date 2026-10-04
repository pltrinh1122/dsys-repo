"""Broker CSV ingest (R7): CSV rows -> 1099-B lot Documents.

Each data row becomes one 1099-B Document carrying a single-entry lot
table (``fields["lots"]["value"]`` = [lot dict]) -- the shape
carryforward.from_store() consumes. Documents are created with status
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
to short|long; anything else is kept verbatim (the carryforward guard
refuses on unknown terms with a loud blocker -- never guessed).

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
                    "date_acquired", "date_sold", "description",
                    "wash_1g", "fed_withheld_4",
                    "accrued_market_discount_1f")

# Canonical field -> key inside the per-lot dict on the Document's
# fields["lots"]["value"] table.
FIELD_CODES = {
    "proceeds": "proceeds_1d",
    "basis": "basis_1e",
    "term": "term",
    "date_acquired": "date_acquired",
    "date_sold": "date_sold",
    "description": "description",
    "wash_1g": "wash_1g",
    # B1F: box 1f is accrued market discount, NOT withholding;
    # federal income tax withheld is box 4.
    "fed_withheld_4": "fed_withheld_4",
    "accrued_market_discount_1f": "accrued_market_discount_1f",
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
        "wash sale loss disallowed": "wash_1g",
        "wash sale disallowed": "wash_1g",
        # B1F: federal income tax withheld is box 4; box 1f is
        # accrued market discount.
        "federal income tax withheld": "fed_withheld_4",
        "backup withholding": "fed_withheld_4",
        "accrued market discount": "accrued_market_discount_1f",
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
    with low confidence -- the carryforward guard refuses on them
    loudly (G2 blocker), never guessed."""
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
        lot: dict = {
            "description": None,
            "date_acquired": None,
            "date_sold": None,
            "proceeds_1d": None,
            "basis_1e": None,
            "wash_1g": None,
            "accrued_market_discount_1f": None,
            "fed_withheld_4": None,
            "term": None,
            "covered": None,
        }
        term_conf = "low"
        used_originals: set[str] = set()
        for norm_h, (orig_h, val) in normed.items():
            canon = col_map.get(norm_h)
            if canon is None or canon not in FIELD_CODES:
                continue
            used_originals.add(orig_h)
            key = FIELD_CODES[canon]
            if canon == "term":
                term, term_conf = _norm_term(val or "")
                lot[key] = term or None
            else:
                # Money/dates/descriptions: keep the broker's raw string
                # (Decimal-safe -- never floated); from_store coerces them.
                s = (val or "").strip()
                lot[key] = s or None
        fields: dict = {}
        # Unknown columns: kept aside, never dropped silently.
        extra = {orig: (row[orig] or "")
                 for orig in row if orig and orig not in used_originals}
        if extra:
            fields["extra_columns"] = _field(extra, "medium")
        if lot["proceeds_1d"] and lot["basis_1e"] and term_conf == "high":
            lots_conf = "high"
        elif not lot["proceeds_1d"] and not lot["basis_1e"]:
            lots_conf = "low"
        elif lot["term"] is not None and term_conf != "high":
            # Unknown term kept verbatim: the carryforward guard will
            # refuse on it (G2 blocker) -- flag it low for the reviewer.
            lots_conf = "low"
        else:
            lots_conf = "medium"
        fields["lots"] = {"value": [lot], "confidence": lots_conf,
                          "raw_text": ""}
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
