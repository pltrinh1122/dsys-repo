"""JSONL document store.

Layout under <data_dir>/:
    documents.jsonl        one JSON object per line (upsert by doc_id)
    ocr/<doc_id>.txt       extracted / sidecar OCR text per document
    store.lock             mutual-exclusion lock for writers (D1)

D1 concurrency model (2026-10-03): the CLI, the MCP stdio server, and
the review server all write directly to the same data dir, each with
its own in-memory DocumentStore. To prevent lost updates:

  - every mutating operation takes an exclusive ``fcntl.flock`` on
    ``store.lock`` (created mode 0600 if missing), blocking up to
    _LOCK_TIMEOUT seconds, then failing LOUDLY (TimeoutError) -- a
    write is never silently skipped;
  - under the lock the operation RELOADS the JSONL from disk first,
    then merges (by doc_id, this write wins for its own record), then
    writes -- so a long-lived instance (review server) never clobbers
    records written by another process with a stale snapshot;
  - writes are atomic: records go to a temp file in the same directory
    (fsync'd), then ``os.replace`` swaps it in. A crash mid-write
    leaves the previous documents.jsonl intact.

Reads (get/list/counts/needs_review) are LOCK-FREE against the
in-memory snapshot: they never tear (atomic replace guarantees a
whole-file read) but may lag writers in another process until this
instance's next mutating op refreshes the snapshot. This is
documented, not hidden: D1 fixes lost writes, not read freshness.

Fully local, deterministic. PII note: this module never logs or
prints document content -- only doc_ids and counts.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
from pathlib import Path

from .models import Document

# How long a writer blocks on a contended store.lock before failing
# loudly. Never silently skip the write.
_LOCK_TIMEOUT = 30.0
_LOCK_POLL = 0.05


class DocumentStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.ocr_dir = self.data_dir / "ocr"
        self.db_path = self.data_dir / "documents.jsonl"
        self._lock_path = self.data_dir / "store.lock"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, Document] = {}
        self._load()

    # -- D1: locking -------------------------------------------------
    @contextlib.contextmanager
    def _write_locked(self):
        """Hold an exclusive flock on store.lock (blocking with timeout).

        Fails loudly with TimeoutError on contention -- never silently
        skips the write.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + _LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"store lock busy > {_LOCK_TIMEOUT:g}s "
                            f"(another writer holds {self._lock_path}); "
                            "write refused, nothing was lost"
                        )
                    time.sleep(_LOCK_POLL)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # -- persistence -------------------------------------------------
    def _load(self) -> None:
        """(Re)read the JSONL into the in-memory snapshot."""
        docs: dict[str, Document] = {}
        if self.db_path.exists():
            for line in self.db_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                doc = Document.from_dict(json.loads(line))
                docs[doc.doc_id] = doc
        self._docs = docs

    def _dump(self, fh) -> None:
        """Write every in-memory record, one JSON object per line.

        Hook point for the crash-mid-write test (fault injection
        overrides this to raise partway through).
        """
        for doc in self._docs.values():
            fh.write(json.dumps(doc.to_dict()) + "\n")

    def _save(self) -> None:
        """Atomic replace: temp file in the same directory, fsync, then
        os.replace. A crash mid-write leaves the old file intact; the
        temp file is removed on failure."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.data_dir), prefix="documents.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                self._dump(fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.db_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- OCR text ----------------------------------------------------
    def save_ocr(self, doc_id: str, text: str) -> str:
        """Persist OCR text; returns the ocr_text_ref stored on the Document."""
        ref = f"ocr/{doc_id}.txt"
        (self.ocr_dir / f"{doc_id}.txt").write_text(text, encoding="utf-8")
        return ref

    def load_ocr(self, doc_id: str) -> str:
        return (self.ocr_dir / f"{doc_id}.txt").read_text(encoding="utf-8")

    # -- CRUD --------------------------------------------------------
    def upsert(self, doc: Document) -> None:
        """Insert or replace one record.

        D1: takes the store lock, reloads from disk (merging anything
        another writer committed since this instance loaded), applies
        this write, and persists atomically. Last write wins per
        doc_id; records written by others are never silently dropped.
        """
        with self._write_locked():
            self._load()
            self._docs[doc.doc_id] = doc
            self._save()

    def get(self, doc_id: str) -> Document | None:
        # Lock-free snapshot read (see module docstring).
        return self._docs.get(doc_id)

    def list(self, year: int | None = None, form: str | None = None) -> list[Document]:
        # Lock-free snapshot read (see module docstring).
        docs = list(self._docs.values())
        if year is not None:
            docs = [d for d in docs if d.tax_year == year]
        if form is not None:
            docs = [d for d in docs if d.form_type == form]
        return sorted(docs, key=lambda d: (d.tax_year or 0, d.form_type, d.doc_id))

    def counts(self) -> dict[tuple[int | None, str], int]:
        out: dict[tuple[int | None, str], int] = {}
        for d in self._docs.values():
            key = (d.tax_year, d.form_type)
            out[key] = out.get(key, 0) + 1
        return out

    def needs_review(self) -> list[Document]:
        return [d for d in self._docs.values() if d.status == "needs_review"]

    def refresh(self) -> None:
        """Re-read the JSONL from disk into this instance's snapshot.

        Lock-free. Convenience for long-lived readers (review server)
        that want a fresher view without writing.
        """
        self._load()

    def __len__(self) -> int:
        return len(self._docs)
