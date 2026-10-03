"""D1 store hardening tests -- all fixtures synthetic.

Covers the workstation's lost-update probe verbatim, a concurrent
writer stress test, and a crash-mid-write simulation (fault-injected
_dump). Also pins the lock-contention timeout behavior.
"""

import json
import multiprocessing as mp
import os
import threading
import time
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


def _doc_ids_on_disk(data_dir):
    path = Path(data_dir) / "documents.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["doc_id"]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


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
    assert sorted(_doc_ids_on_disk(data)) == ["doc-1", "doc-2"]

    # review server validates doc-1 with its STALE snapshot
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
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "writer threads hung"
    assert not errors, f"writer errors: {errors[:3]}"

    fresh = DocumentStore(data)
    ids = {d.doc_id for d in fresh.list()}
    expected = {f"w{w}-{i}" for w in range(n_workers) for i in range(n_each)}
    assert ids == expected, f"lost {len(expected - ids)} records"
    # the file on disk is whole and valid JSONL
    lines = (data / "documents.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([ln for ln in lines if ln.strip()]) == n_workers * n_each
    for ln in lines:
        if ln.strip():
            Document.from_dict(json.loads(ln))  # raises if corrupt


def _proc_worker(data_dir, worker_id, n, start_evt):
    start_evt.wait(timeout=30)
    for i in range(n):
        store = DocumentStore(data_dir)
        store.upsert(_doc(f"p{worker_id}-{i}"))


def test_concurrent_process_writers_no_lost_records(tmp_path):
    """Cross-process contention exercises the real fcntl lock."""
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
        pr.join(timeout=120)
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
    d_a = _doc("shared", status="transcribed")
    d_b = _doc("shared", status="validated")
    a.upsert(d_a)
    b.upsert(d_b)  # b's snapshot predates a's write; must not resurrect it
    fresh = DocumentStore(data)
    assert len(fresh) == 1
    assert fresh.get("shared").status == "validated"


# -- crash mid-write -------------------------------------------------------

def test_crash_mid_write_leaves_old_file_intact(tmp_path, monkeypatch):
    data = tmp_path / "data"
    store = DocumentStore(data)
    store.upsert(_doc("doc-1"))
    before = (data / "documents.jsonl").read_bytes()

    def _boom(self, fh):
        fh.write('{"doc_id": "partial"}\n')
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(DocumentStore, "_dump", _boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        store.upsert(_doc("doc-2"))

    # old file byte-identical; no temp litter left behind
    assert (data / "documents.jsonl").read_bytes() == before
    assert list(data.glob("documents.*.tmp")) == []
    # store still usable afterwards (lock was released)
    monkeypatch.undo()
    store.upsert(_doc("doc-2"))
    assert sorted(_doc_ids_on_disk(data)) == ["doc-1", "doc-2"]


# -- lock contention --------------------------------------------------------

def test_lock_contention_fails_loudly_not_silently(tmp_path, monkeypatch):
    import fcntl as _fcntl

    data = tmp_path / "data"
    store = DocumentStore(data)
    monkeypatch.setattr("taxprep.store._LOCK_TIMEOUT", 0.2)

    held_fd = os.open(str(data / "store.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    _fcntl.flock(held_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    try:
        with pytest.raises(TimeoutError, match="store lock busy"):
            store.upsert(_doc("doc-x"))
    finally:
        _fcntl.flock(held_fd, _fcntl.LOCK_UN)
        os.close(held_fd)
    # nothing was written, nothing lost
    assert list(store.list()) == []
    assert not (data / "documents.jsonl").exists()


def test_lock_file_created_with_restricted_mode(tmp_path):
    data = tmp_path / "data"
    DocumentStore(data).upsert(_doc("doc-1"))
    st = (data / "store.lock").stat()
    assert st.st_mode & 0o777 == 0o600
