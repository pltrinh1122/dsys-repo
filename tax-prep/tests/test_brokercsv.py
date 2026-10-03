"""R7 broker CSV tests: brokercsv.ingest_csv + `taxprep ingest-csv`,
`taxprep exclude` / `taxprep exclusions`. All fixtures synthetic.
"""

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from taxprep import brokercsv
from taxprep.brokercsv import BROKER_MAPS, ingest_csv
from taxprep.carryforward import from_store
from taxprep.cli import main
from taxprep.store import DocumentStore

CSV_GENERIC = """Proceeds,Cost Basis,Term,Date Acquired,Date Sold,Description
1000.00,600.00,Short,01/15/2024,06/20/2024,10 SHARES XYZ SYNTHETIC
2500.00,3000.00,Long,03/01/2023,07/11/2024,5 SHARES ABC SYNTHETIC
"""


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("TAXPREP_DATA_DIR", str(tmp_path / "data"))
    return {"data": tmp_path / "data", "tmp": tmp_path}


def _run(*argv):
    return main(list(argv))


def _csv(path: Path, text: str = CSV_GENERIC) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_ingest_csv_creates_lot_documents(iso):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    store = DocumentStore(iso["data"])
    docs = ingest_csv(csv_path, "generic", 2024, store)
    assert len(docs) == 2
    base = hashlib.sha256(CSV_GENERIC.encode()).hexdigest()[:16]
    assert [d.doc_id for d in docs] == [f"{base}-r1", f"{base}-r2"]
    d1 = docs[0]
    assert d1.form_type == "1099-B" and d1.tax_year == 2024
    assert d1.status == "needs_review"
    assert d1.text_source == "broker-csv"
    assert d1.fields["1d_proceeds"]["value"] == "1000.00"
    assert d1.fields["1e_basis"]["value"] == "600.00"
    assert d1.fields["term"]["value"] == "short"   # normalized
    assert d1.fields["date_acquired"]["value"] == "01/15/2024"
    assert d1.fields["date_sold"]["value"] == "06/20/2024"
    assert docs[1].fields["term"]["value"] == "long"


def test_unknown_columns_kept_aside_never_dropped(iso):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    docs = ingest_csv(csv_path, "generic", 2024, DocumentStore(iso["data"]))
    extra = docs[0].fields["extra_columns"]["value"]
    assert extra == {"Description": "10 SHARES XYZ SYNTHETIC"}


def test_term_variants_normalized(iso):
    csv = ("proceeds,basis,term\n"
           "10,5,ST\n"
           "10,5,lt\n"
           "10,5,L\n")
    docs = ingest_csv(_csv(iso["tmp"] / "t.csv", csv), "generic", 2024,
                      DocumentStore(iso["data"]))
    assert [d.fields["term"]["value"] for d in docs] == [
        "short", "long", "long"]


def test_unknown_term_kept_verbatim_low_confidence(iso):
    csv = "proceeds,basis,term\n10,5,maybe\n"
    docs = ingest_csv(_csv(iso["tmp"] / "t.csv", csv), "generic", 2024,
                      DocumentStore(iso["data"]))
    assert docs[0].fields["term"]["value"] == "maybe"
    assert docs[0].fields["term"]["confidence"] == "low"


def test_unknown_broker_fails_closed(iso):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    with pytest.raises(ValueError, match="unknown broker"):
        ingest_csv(csv_path, "acme-brokerage", 2024,
                   DocumentStore(iso["data"]))


def test_csv_reingest_is_idempotent(iso):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    store = DocumentStore(iso["data"])
    ingest_csv(csv_path, "generic", 2024, store)
    ingest_csv(csv_path, "generic", 2024, store)
    assert len(store) == 2


def test_csv_lots_consumed_by_from_store(iso):
    """End to end: CSV rows -> validated 1099-B docs -> from_store sums."""
    csv_path = _csv(iso["tmp"] / "lots.csv")
    store = DocumentStore(iso["data"])
    for d in ingest_csv(csv_path, "generic", 2024, store):
        d.status = "validated"   # operator validated in the review UI
        store.upsert(d)
    r = from_store(store, 2024)
    assert r["lots_included"] == 2
    assert r["lots_excluded"] == 0
    assert r["st_current"] == Decimal("400.00")
    assert r["lt_current"] == Decimal("-500.00")


def test_broker_maps_shape():
    assert "generic" in BROKER_MAPS
    for _broker, m in BROKER_MAPS.items():
        assert set(m.values()) <= set(brokercsv.CANONICAL_FIELDS) | \
            {"description"}


def test_cli_ingest_csv(iso, capsys):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    assert _run("ingest-csv", "--broker", "generic", "--file", str(csv_path),
                "--year", "2024") == 0
    out = capsys.readouterr().out
    assert "ingested 2 lot(s)" in out
    assert len(DocumentStore(iso["data"])) == 2
    # blind-safe: no dollar amounts in the output
    assert "$" not in out and "1000.00" not in out


def test_cli_ingest_csv_unknown_broker(iso, capsys):
    csv_path = _csv(iso["tmp"] / "lots.csv")
    assert _run("ingest-csv", "--broker", "nope", "--file", str(csv_path),
                "--year", "2024") == 2
    assert "unknown broker" in capsys.readouterr().err


def test_cli_exclude_and_exclusions(iso, capsys):
    store = DocumentStore(iso["data"])
    from taxprep.models import Document
    store.upsert(Document(doc_id="doc-abc", tax_year=2024, form_type="W-2",
                         source_path="x.pdf", ocr_text_ref="",
                         status="needs_review"))
    assert _run("exclude", "doc-abc", "--reason", "duplicate scan") == 0
    out = capsys.readouterr().out
    assert "excluded doc-abc" in out

    assert _run("exclusions") == 0
    out = capsys.readouterr().out
    assert "doc-abc" in out and "duplicate scan" in out


def test_cli_exclude_prefix_match_and_missing(iso, capsys):
    store = DocumentStore(iso["data"])
    from taxprep.models import Document
    store.upsert(Document(doc_id="abcdef1234567890", tax_year=2024,
                         form_type="W-2", source_path="x.pdf",
                         ocr_text_ref="", status="needs_review"))
    assert _run("exclude", "abcdef12", "--reason", "r") == 0
    assert "excluded abcdef1234567890" in capsys.readouterr().out
    with pytest.raises(SystemExit) as ei:
        _run("exclude", "no-such-doc", "--reason", "r")
    assert ei.value.code == 1
    assert "No document" in capsys.readouterr().err


def test_cli_exclude_requires_reason(iso):
    with pytest.raises(SystemExit) as ei:
        _run("exclude", "doc-abc")
    assert ei.value.code == 2  # argparse: --reason is required
