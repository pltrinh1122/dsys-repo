"""Medallion store tests (SQLite semantics) -- all fixtures synthetic.

Ports the D1 hardening battery to the medallion store:

  * the workstation's lost-update probe, verbatim in spirit (two
    instances, one with a stale snapshot);
  * concurrent thread and process writers -- no lost records;
  * last-write-wins on overlapping upserts;
  * crash mid-transaction (fault-injected inside txn) leaves no partial
    rows;
  * busy contention fails LOUDLY (sqlite3.OperationalError after the
    busy timeout) -- never silently;
  * the sqlite file is created with mode 0600.

The fcntl lock-file tests are dropped: SQLite subsumes them.
"""

import hashlib
import multiprocessing as mp
import sqlite3
import threading
from pathlib import Path

import pytest

from taxprep.models import Document
from taxprep.store import DocumentStore


def _doc(doc_id, status="transcribed", **kw):
    args = dict(
        doc_id=doc_id,
        tax_year=2024,
        form_type="W-2",
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields={},
        status=status,
    )
    args.update(kw)
    return Document(**args)


# -- the workstation probe, verbatim -------------------------------------

def test_workstation_probe_no_lost_update(tmp_path):
    """seed 1 doc -> second instance (= review server) -> CLI ingests 2nd
    doc -> review instance validates 1st doc -> BOTH records survive."""
    data = tmp_path / "data"
    seeder = DocumentStore(data)
    seeder.upsert(_doc("doc-1"))

    review_server = DocumentStore(data)          # long-lived instance
    assert review_server.get("doc-1") is not None

    cli = DocumentStore(data)                    # CLI ingest, own instance
    cli.upsert(_doc("doc-2"))

    # review server validates doc-1 (reads are always current now)
    d1 = review_server.get("doc-1")
    d1.status = "validated"
    d1.validated_at = "2026-10-03T00:00:00+00:00"
    review_server.upsert(d1)

    fresh = DocumentStore(data)
    assert sorted(d.doc_id for d in fresh.list()) == ["doc-1", "doc-2"]
    assert fresh.get("doc-1").status == "validated"
    assert fresh.get("doc-2").status == "transcribed"


# -- concurrent writers ---------------------------------------------------

def _thread_worker(data_dir, worker_id, n, barrier, errors):
    try:
        barrier.wait(timeout=10)
        for i in range(n):
            store = DocumentStore(data_dir)     # fresh instance per write,
            store.upsert(_doc(f"w{worker_id}-{i}"))  # like separate processes
    except Exception as exc:  # noqa: BLE001 -- collected, then asserted
        errors.append(exc)


def test_concurrent_thread_writers_no_lost_records(tmp_path):
    data = tmp_path / "data"
    n_workers, n_each = 8, 25
    barrier = threading.Barrier(n_workers)
    errors: list = []
    threads = [
        threading.Thread(target=_thread_worker,
                         args=(str(data), w, n_each, barrier, errors))
        for w in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "writer threads hung"
    assert not errors, f"writer errors: {errors[:3]}"

    fresh = DocumentStore(data)
    ids = {d.doc_id for d in fresh.list()}
    expected = {f"w{w}-{i}" for w in range(n_workers) for i in range(n_each)}
    assert ids == expected, f"lost {len(expected - ids)} records"


def _proc_worker(data_dir, worker_id, n, start_evt):
    start_evt.wait(timeout=30)
    for i in range(n):
        store = DocumentStore(data_dir)
        store.upsert(_doc(f"p{worker_id}-{i}"))


def test_concurrent_process_writers_no_lost_records(tmp_path):
    """Cross-process contention exercises SQLite's writer serialization."""
    data = tmp_path / "data"
    DocumentStore(data).upsert(_doc("seed"))
    n_procs, n_each = 4, 15
    ctx = mp.get_context("fork")
    start_evt = ctx.Event()
    procs = [ctx.Process(target=_proc_worker,
                         args=(str(data), p, n_each, start_evt))
             for p in range(n_procs)]
    for pr in procs:
        pr.start()
    start_evt.set()
    for pr in procs:
        pr.join(timeout=180)
    assert all(pr.exitcode == 0 for pr in procs), \
        f"worker exit codes: {[pr.exitcode for pr in procs]}"
    fresh = DocumentStore(data)
    ids = {d.doc_id for d in fresh.list()}
    expected = {"seed"} | {f"p{p}-{i}" for p in range(n_procs)
                           for i in range(n_each)}
    assert ids == expected, f"lost {len(expected - ids)} records"


def test_overlapping_upserts_last_write_wins(tmp_path):
    data = tmp_path / "data"
    a = DocumentStore(data)
    b = DocumentStore(data)
    a.upsert(_doc("shared", status="transcribed"))
    # b read before a wrote; b's write must win, not resurrect old state
    b.upsert(_doc("shared", status="validated"))
    fresh = DocumentStore(data)
    assert len(fresh) == 1
    assert fresh.get("shared").status == "validated"


# -- crash mid-transaction -------------------------------------------------

def test_crash_mid_transaction_leaves_no_partial_rows(tmp_path, monkeypatch):
    data = tmp_path / "data"
    store = DocumentStore(data)
    store.upsert(_doc("doc-1"))
    before = store.table_counts()

    def _boom(self, doc, **kw):
        # write something, THEN crash: the row must not survive
        self.register_bronze("bb" * 32, 10)
        raise RuntimeError("simulated crash mid-txn")

    monkeypatch.setattr(DocumentStore, "upsert_silver_doc", _boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        store.upsert(_doc("doc-2"))

    # no partial rows anywhere: the bronze row from _boom is gone too
    assert store.get("doc-2") is None
    assert store.get_bronze("bb" * 32) is None
    assert store.table_counts() == before
    # store still usable afterwards
    monkeypatch.undo()
    store.upsert(_doc("doc-2"))
    assert sorted(d.doc_id for d in store.list()) == ["doc-1", "doc-2"]


def test_nested_txn_rolls_back_inner_only(tmp_path):
    """An exception in a nested txn() rolls back to the savepoint; the
    outer transaction still commits."""
    data = tmp_path / "data"
    store = DocumentStore(data)
    with store.txn():
        store.register_bronze("dd" * 32, 5)
        with pytest.raises(RuntimeError, match="inner boom"):
            with store.txn():
                store.register_bronze("ee" * 32, 5)
                raise RuntimeError("inner boom")
    assert store.get_bronze("dd" * 32) is not None
    assert store.get_bronze("ee" * 32) is None


# -- busy contention --------------------------------------------------------

def test_busy_contention_fails_loudly_not_silently(tmp_path, monkeypatch):
    """A second writer blocked by an open write txn waits for the busy
    timeout, then raises sqlite3.OperationalError -- the write is never
    silently skipped."""
    monkeypatch.setattr("taxprep.mstore._BUSY_TIMEOUT_MS", 100)
    data = tmp_path / "data"
    writer = DocumentStore(data)
    blocker = DocumentStore(data)
    writer.upsert(_doc("seed"))

    with blocker.txn():
        blocker.register_bronze("cc" * 32, 1)  # holds the write lock
        with pytest.raises(sqlite3.OperationalError, match="[Ll]ocked"):
            writer.upsert(_doc("doc-x"))
    # nothing was written by the failed attempt, nothing lost
    assert writer.get("doc-x") is None
    assert sorted(d.doc_id for d in writer.list()) == ["seed"]


# -- file protections ---------------------------------------------------------

def test_sqlite_file_created_with_restricted_mode(tmp_path):
    data = tmp_path / "data"
    DocumentStore(data).upsert(_doc("doc-1"))
    st = (data / "medallion.sqlite").stat()
    assert st.st_mode & 0o777 == 0o600


def test_bronze_bytes_stored_read_only(tmp_path):
    data = tmp_path / "data"
    store = DocumentStore(data)
    payload = b"synthetic source bytes"
    sha = hashlib.sha256(payload).hexdigest()
    rel = store.store_bronze_bytes(sha, payload)
    target = Path(data) / rel
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o777 == 0o400
    # idempotent: storing the same bytes again changes nothing
    assert store.store_bronze_bytes(sha, payload) == rel
    # wrong address refused loudly
    with pytest.raises(ValueError, match="do not hash"):
        store.store_bronze_bytes("00" * 32, payload)
