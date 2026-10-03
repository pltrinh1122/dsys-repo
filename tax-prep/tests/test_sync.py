"""R4 sync tests: `taxprep sync` CLI + sync() orphan handling.

All fixtures synthetic.
"""

import hashlib
from pathlib import Path

import pytest

from taxprep.cli import main
from taxprep.ingest import source_doc_id, sync
from taxprep.store import DocumentStore

W2_TEXT = (
    "Form W-2 Wage and Tax Statement\n"
    "Tax Year 2024\n"
    "Box 1 Wages, tips, other compensation $10,000.00\n"
    "Box 2 Federal income tax withheld $1,500.00\n"
)


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    src = tmp_path / "incoming"
    src.mkdir()
    monkeypatch.setenv("TAXPREP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("TAXPREP_SOURCE_DIR", raising=False)
    return {"src": src, "data": tmp_path / "data"}


def _run(*argv):
    return main(list(argv))


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_sync_marks_missing_source_orphaned(iso):
    _write(iso["src"] / "keep.txt", W2_TEXT)
    gone = _write(iso["src"] / "gone.txt", W2_TEXT + " extra")
    sync(iso["src"], DocumentStore(iso["data"]))
    assert len(DocumentStore(iso["data"])) == 2
    gone.unlink()

    result = sync(iso["src"], DocumentStore(iso["data"]))
    assert result["orphaned"] == [source_doc_id((W2_TEXT + " extra").encode())]
    store = DocumentStore(iso["data"])
    doc = store.get(result["orphaned"][0])
    assert doc.status == "ORPHANED"
    assert doc.status_reason == "source-missing"
    kept = store.get(source_doc_id(W2_TEXT.encode()))
    assert kept.status != "ORPHANED"


def test_sync_ingests_new_and_is_idempotent(iso):
    _write(iso["src"] / "w2.txt", W2_TEXT)
    r1 = sync(iso["src"], DocumentStore(iso["data"]))
    _write(iso["src"] / "w2b.txt", W2_TEXT + "more")
    r2 = sync(iso["src"], DocumentStore(iso["data"]))
    assert r1["ingested"] == 1 and r2["ingested"] == 2
    assert len(DocumentStore(iso["data"])) == 2
    assert r2["orphaned"] == []


def test_sync_orphan_keeps_validated_values(iso):
    """ORPHANED flips status+reason; validated values are untouched."""
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    store = DocumentStore(iso["data"])
    from taxprep.ingest import ingest_file
    doc = ingest_file(src, store)[0]
    doc.status = "validated"
    store.upsert(doc)
    src.unlink()

    result = sync(iso["src"], DocumentStore(iso["data"]))
    assert len(result["orphaned"]) == 1
    d = DocumentStore(iso["data"]).get(result["orphaned"][0])
    assert d.status == "ORPHANED"
    assert d.status_reason == "source-missing"
    assert d.fields == doc.fields  # values preserved


def test_cli_sync_reports_accounting_and_orphans(iso, capsys):
    _write(iso["src"] / "w2.txt", W2_TEXT)
    _write(iso["src"] / "notes.docx", "nope")
    assert _run("sync", str(iso["src"])) == 0
    out = capsys.readouterr().out
    assert "files_seen=2" in out and "ingested=1" in out
    assert "unsupported-type" in out
    assert "no orphaned documents" in out

    (iso["src"] / "w2.txt").unlink()
    assert _run("sync", str(iso["src"])) == 0
    out = capsys.readouterr().out
    assert "ORPHANED" in out


def test_cli_sync_blind_hides_filenames(iso, capsys, monkeypatch):
    import taxprep.cli as cli_mod

    _write(iso["src"] / "notes.docx", "nope")
    monkeypatch.setattr(cli_mod, "BLIND", True)
    assert _run("sync", str(iso["src"])) == 0
    out = capsys.readouterr().out
    assert "unsupported-type" in out
    assert "notes.docx" not in out
