"""Medallion storage foundation (Arc B, W1).

SQLite-backed store at <data_dir>/medallion.sqlite (WAL,
busy_timeout=5000, mode 0600 on creation). Two faces:

  * Document-compatible facade -- upsert/get/list/counts/needs_review/
    refresh/__len__/save_ocr/load_ocr behave as the old JSONL store did
    (reads are now always current; there is no stale snapshot).
  * Medallion API -- txn() with savepoint nesting, bronze registration,
    content-addressed bronze bytes, silver docs + artifacts, append-only
    decision log, digests.

Migration: on first open, if medallion.sqlite is absent and
documents.jsonl exists, the JSONL is migrated inside one transaction
(bronze rows, aliases, silver docs, mirror artifacts, synthesized
validate decisions). The JSONL is then left in place as a backup and
is never written again.

Load-bearing rules: deterministic, local-only, synthetic fixtures.
This module never logs or prints document content -- only doc_ids,
hashes, and counts (blind-orchestrator contract).

Schema note: contract §3 v1 has no doc-level text-provenance columns,
so W1 adds one table, doc_provenance (doc_id PK -> silver_doc), carrying
text_source/reason_code/ocr_engine/engine_version/ocr_mode/attempts/
mean_confidence. Additive only -- no §3 table is altered, so W2/W3/W4
reads are unaffected -- and it keeps the Document facade round-tripping
provenance exactly as the JSONL store did.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from .models import Document


def _load_schema_sql() -> str:
    # Packaged resource, not a source-tree-relative path: the
    # [tool.setuptools.package-data] taxprep = ["*.sql"] entry ships
    # medallion_schema.sql inside the wheel, so importlib.resources finds
    # it in a pip-installed copy where no source tree exists.
    return files("taxprep").joinpath("medallion_schema.sql").read_text(encoding="utf-8")

# How long a writer waits on a contended database before failing loudly.
# A write is never silently skipped. Monkeypatchable in tests.
_BUSY_TIMEOUT_MS = 5000

# Facade / migration writes are pre-medallion-era derivations (contract §7:
# "1" is the pre-medallion era; "2"+ belongs to W2's extractor versions).
_FACADE_DERIVATION_VERSION = "1"
_FACADE_CONFIG_HASH = hashlib.sha256(b"{}").hexdigest()

# Tombstone bronze ids for legacy docs whose source bytes are unrecoverable.
_TOMBSTONE_PREFIX = "legacy-"
_TOMBSTONE_BLOCKED_REASON = "legacy-no-source"
_UNKNOWN_SIZE = -1

# Decision kinds admitted by log_decision (contract §9). Anything else is
# refused loudly -- the log's vocabulary is closed.
_DECISION_KINDS = frozenset({
    "validate",
    "edit",
    "exclude",
    "duplicate_ruling",
    "supersedes_ruling",
    "conflict_choice",
    "relevance_override",
    # R19: the Operator's explicit "verified against original" verdict --
    # the fail-closed escape hatch for confirming a field with no visual
    # evidence. Append-only like every other decision kind.
    "verify_original",
    # R13 (Arc C, W1): per-document lifecycle events
    # {event, from, to, reason_code} (metadata only) -- the append-only
    # event log the lifecycle state machine replays.
    "lifecycle",
    # R21a: the Operator's owner assignment {person_id, previous} and
    # return assignment {person_id, assignment} -- opaque ids only.
    "owner_assignment",
    "return_assignment",
})

# Columns hashed by db_digest(), per table. Volatile bookkeeping columns
# (first_seen/last_seen/ts/created_at/updated_at) are EXCLUDED so that
# ingest-twice idempotency comparisons stay stable: re-ingesting the same
# bytes may only bump "seen at" bookkeeping (I2).
_DIGEST_COLS = {
    "bronze": ["hash", "size", "source_root", "source_relpath",
               "selection_state", "encryption", "text_fingerprint",
               "blocked_reason"],
    "bronze_alias": ["hash", "path"],
    "bronze_bytes_ref": ["hash", "rel_path"],
    "bronze_text": ["hash", "page", "text_source", "engine",
                    "engine_version", "ocr_mode", "derivation_version",
                    "config_hash", "text"],
    "silver_doc": ["doc_id", "bronze_hash", "form_type", "tax_year",
                   "status", "status_reason", "page_range", "parent_doc_id",
                   "relevance", "validated_at", "re_review",
                   "derivation_version", "config_hash", "derivation_digest",
                   "fields_json",
                   # R21a: operator-assigned owner metadata (opaque ids only,
                   # PII-free for the blind sweep).
                   "owner_person_id", "owner_suggestion",
                   "owner_suggestion_basis"],
    "silver_artifact": ["artifact_id", "doc_id", "bronze_hash", "page",
                        "artifact_type", "anchor", "value_json",
                        "offsets_json", "derivation_version", "config_hash",
                        # R21a: per-artifact owner (joint allocation).
                        "owner_person_id", "owner_suggestion"],
    "decision_log": ["actor", "kind", "artifact_id", "doc_id", "group_id",
                     "payload_json"],
    "dup_group": ["group_id", "class", "status", "disposed_at"],
    "dup_member": ["group_id", "member_key", "role"],
    "conflict": ["conflict_id", "class", "field", "status", "disposed_at"],
    "conflict_option": ["conflict_id", "option_key", "value_json",
                        "evidence_ref"],
    "field_fingerprint": ["artifact_id", "fp_hash", "salt_id"],
    "gold_run": ["run_id", "ts", "kind", "params_json", "input_digest",
                 "output_json", "output_digest"],
    # W1 addition (additive; see schema header).
    "doc_provenance": ["doc_id", "text_source", "reason_code", "ocr_engine",
                       "engine_version", "ocr_mode", "attempts_json",
                       "mean_confidence"],
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon(obj) -> str:
    """Canonical JSON: sorted keys, compact separators, deterministic."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _q(name: str) -> str:
    """Quote a SQLite identifier."""
    return '"' + name.replace('"', '""') + '"'


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _derivation_digest(fields: dict) -> str:
    """Stable digest of a doc's operational fields."""
    return _sha256_bytes(_canon(fields).encode("utf-8"))


def _artifact_id(doc_id: str, bronze_hash: str, page: int,
                 artifact_type: str, anchor: str) -> str:
    # Contract §6 as amended (coordinator): doc_id joins the hash --
    # one bronze feeds many docs (R1 children, CSV rows).
    return hashlib.sha256(
        f"{doc_id}:{bronze_hash}:{page}:{artifact_type}:{anchor}".encode(
            "utf-8")
    ).hexdigest()[:32]


class _TxnHandle:
    """What ``MedallionStore.txn()`` yields.

    Attribute access delegates to the store (so ``handle.register_bronze``
    etc. keep working), and ``execute()`` exposes the underlying
    connection for workstream-owned tables (duplicates, gold). The
    append-only decision log is still protected by DB triggers even
    through raw SQL.
    """

    __slots__ = ("_store",)

    def __init__(self, store: "MedallionStore") -> None:
        object.__setattr__(self, "_store", store)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_store"), name)

    def execute(self, *args, **kwargs):
        return object.__getattribute__(self, "_store")._conn.execute(
            *args, **kwargs
        )


class MedallionStore:
    """SQLite medallion store + Document-compatible facade."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.ocr_dir = self.data_dir / "ocr"
        self.db_path = self.data_dir / "medallion.sqlite"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        # One connection per instance (contract §2); check_same_thread=False
        # so the instance lock below is the only serialization point.
        self._op_lock = threading.RLock()
        self._txn_depth = 0
        self._connect()

    # -- open / schema / migration ------------------------------------
    def _connect(self) -> None:
        # First-open init is serialized across threads AND processes by an
        # init lock (init-only; steady-state writes rely on SQLite itself).
        # The lock is taken on every open -- uncontended it is cheap -- so
        # no opener can see a half-initialized database: the file either
        # exists fully formed or it does not exist at all.
        #
        # Exactly one initializer builds the database in a temp file and
        # publishes it with an atomic os.replace; a crash (even kill -9)
        # can only litter the temp file, never a partial medallion.sqlite.
        lock_path = self.data_dir / ".medallion-init.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                if self.db_path.exists():
                    self._open_existing()
                    return
                tmp = self.data_dir / (
                    f".medallion-init.{os.getpid()}.{threading.get_ident()}")
                try:
                    self._init_at(tmp)
                    os.replace(str(tmp), str(self.db_path))
                finally:
                    for p in (tmp,):
                        try:
                            os.unlink(p)
                        except OSError:
                            pass
                self._open_existing()
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _open_existing(self) -> None:
        # isolation_level=None: autocommit mode; txn() manages BEGIN/COMMIT
        # explicitly (BEGIN IMMEDIATE). Never rely on implicit transactions.
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()
        self._migrate_columns()

    # Additive, idempotent column migrations for databases created by an
    # older DDL. Each ALTER is guarded by PRAGMA table_info, so opening
    # an up-to-date database is a no-op.
    _COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
        ("bronze", "source_relpath", "TEXT"),     # R15 source identity
        ("bronze", "source_mtime", "INTEGER"),    # R15 source identity
        # R21a: per-person scoping -- opaque operator-assigned owner id +
        # system-derived (never auto-applied) suggestion. NULL = unassigned.
        ("silver_doc", "owner_person_id", "TEXT"),
        ("silver_doc", "owner_suggestion", "TEXT"),
        ("silver_doc", "owner_suggestion_basis", "TEXT"),
        # R21a: artifact-level owner for documents covering several people
        # (joint/multi-owner items are allocated per artifact by the
        # Operator; never mechanically split).
        ("silver_artifact", "owner_person_id", "TEXT"),
        ("silver_artifact", "owner_suggestion", "TEXT"),
    )

    def _migrate_columns(self) -> None:
        with self._op_lock:
            for table, column, ddl in self._COLUMN_MIGRATIONS:
                cols = {r["name"] for r in self._conn.execute(
                    f"PRAGMA table_info({table})")}
                if column not in cols:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _init_at(self, tmp: Path) -> None:
        """Build a fully-initialized database at `tmp`.

        Uses rollback-journal mode during the build so no -wal/-shm
        sidecars exist; the file is self-contained and safe to publish
        with os.replace. Mode 0600 from creation; SQLite propagates the
        db file's mode to the -wal/-shm files it later creates.
        """
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        self._conn = sqlite3.connect(str(tmp), isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=DELETE;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._init_schema()
            # Column migrations must run before the JSONL migration: the
            # migration's writes go through upsert_silver_doc /
            # replace_artifacts, which reference the migrated columns.
            self._migrate_columns()
            self._migrate_jsonl()
        finally:
            self._conn.close()

    def _apply_pragmas(self) -> None:
        with self._op_lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS};")
            self._conn.execute("PRAGMA foreign_keys=ON;")

    def _init_schema(self) -> None:
        # NOTE: executescript() implicitly COMMITs any pending transaction
        # (Python 3.12), so the schema is applied outside txn(). A failure
        # propagates to _connect, which drops the temp file so the next
        # open retries from scratch.
        sql = _load_schema_sql()
        with self._op_lock:
            self._conn.executescript(sql)

    def _migrate_jsonl(self) -> None:
        """One-time migration from the legacy documents.jsonl.

        Runs inside a single transaction on first open. Bronze rows from
        source_sha256 (re-hashing the source file when present, else a
        "legacy-<doc_id>" tombstone with
        blocked_reason="legacy-no-source"); aliases from source_path;
        silver_doc rows with fields_json = the fields dict; one 'field'
        artifact per fields key plus 'lot' artifacts for fields["lots"];
        a synthesized validate decision for docs with validated_at set.
        """
        legacy = self.data_dir / "documents.jsonl"
        if not legacy.exists():
            return
        with self.txn():
            for line in legacy.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                doc = Document.from_dict(json.loads(line))
                self._migrate_one_doc(doc)

    def _migrate_one_doc(self, doc: Document) -> None:
        sha = self._ensure_bronze_for_doc(doc)
        doc = replace(doc, source_sha256=sha)
        self.upsert_silver_doc(
            doc,
            derivation_version=_FACADE_DERIVATION_VERSION,
            config_hash=_FACADE_CONFIG_HASH,
            derivation_digest=_derivation_digest(doc.fields),
        )
        self.replace_artifacts(
            doc.doc_id,
            _mirror_artifacts(doc.doc_id, sha, doc.fields,
                              _FACADE_DERIVATION_VERSION,
                              _FACADE_CONFIG_HASH),
        )
        if doc.validated_at:
            self.log_decision(
                actor="operator",
                kind="validate",
                doc_id=doc.doc_id,
                payload={
                    "doc_id": doc.doc_id,
                    "validated_fields": sorted(doc.fields.keys()),
                    "ts": doc.validated_at,
                },
            )

    def close(self) -> None:
        with self._op_lock:
            self._conn.close()

    # -- transactions --------------------------------------------------
    @contextlib.contextmanager
    def txn(self):
        """A single SQLite transaction (I7). Nested txn() uses SAVEPOINTs.

        Yields a handle exposing both the store's public API (attribute
        delegation) and ``execute()`` for workstream-owned tables
        (duplicates, gold). The append-only decision log stays protected
        by DB-level triggers (decision_log_no_update/_no_delete) even
        through raw SQL. An exception rolls the (sub-)transaction back
        and propagates; nothing partial survives.
        """
        with self._op_lock:
            if self._txn_depth == 0:
                self._conn.execute("BEGIN IMMEDIATE")
                self._txn_depth = 1
                try:
                    yield _TxnHandle(self)
                except BaseException:
                    self._conn.execute("ROLLBACK")
                    raise
                else:
                    self._conn.execute("COMMIT")
                finally:
                    self._txn_depth = 0
            else:
                sp = f"w1_sp_{self._txn_depth}"
                self._conn.execute(f"SAVEPOINT {_q(sp)}")
                self._txn_depth += 1
                try:
                    yield _TxnHandle(self)
                except BaseException:
                    self._conn.execute(f"ROLLBACK TO {_q(sp)}")
                    self._conn.execute(f"RELEASE {_q(sp)}")
                    raise
                else:
                    self._conn.execute(f"RELEASE {_q(sp)}")
                finally:
                    self._txn_depth -= 1

    # -- bronze ----------------------------------------------------------
    def register_bronze(self, sha: str, size: int, source_root: str | None = None,
                        encryption: str | None = None,
                        source_relpath: str | None = None,
                        source_mtime: int | None = None) -> bool:
        """Register a bronze object. True if newly created.

        Re-registering the same bytes is a no-op for state (I2): only
        last_seen is bumped. Never changes selection/blocked state.
        R15 source identity (source_relpath/source_mtime) is recorded on
        first insert; re-registering never clobbers it.
        """
        now = _utcnow()
        with self.txn():
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO bronze "
                "(hash, size, source_root, source_relpath, source_mtime, "
                " first_seen, last_seen, encryption) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sha, size, source_root, source_relpath, source_mtime,
                 now, now, encryption),
            )
            if cur.rowcount == 1:
                return True
            self._conn.execute(
                "UPDATE bronze SET last_seen = ? WHERE hash = ?",
                (now, sha),
            )
            return False

    def bronze_hashes(self) -> list[str]:
        """All bronze content hashes, ordered. Metadata only."""
        with self._op_lock:
            return [r["hash"] for r in self._conn.execute(
                "SELECT hash FROM bronze ORDER BY hash")]

    def _set_blocked_reason(self, sha: str, reason: str) -> None:
        self.set_blocked_reason(sha, reason)

    def set_blocked_reason(self, sha: str, reason: str) -> None:
        """Record why a bronze object cannot be derived (public API).

        Only sets when no reason is recorded yet -- the first blocker
        wins; clearing a block is a re-derivation event, not an update.
        """
        with self.txn():
            self._conn.execute(
                "UPDATE bronze SET blocked_reason = ? "
                "WHERE hash = ? AND blocked_reason IS NULL",
                (reason, sha),
            )

    def write_bronze_text(
        self,
        sha: str,
        page: int,
        *,
        text_source: str,
        engine: str | None = None,
        engine_version: str | None = None,
        ocr_mode: str | None = None,
        derivation_version: str,
        config_hash: str,
        text: str,
    ) -> None:
        """Upsert one bronze-derived per-page text row (I5 cache key).

        PRIMARY KEY (hash, page, derivation_version, config_hash): writing
        the same derivation twice is a no-op; a version bump adds rows.
        """
        with self.txn():
            self._conn.execute(
                "INSERT INTO bronze_text "
                "(hash, page, text_source, engine, engine_version, ocr_mode, "
                " derivation_version, config_hash, text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(hash, page, derivation_version, config_hash) "
                "DO UPDATE SET text_source = excluded.text_source, "
                "engine = excluded.engine, "
                "engine_version = excluded.engine_version, "
                "ocr_mode = excluded.ocr_mode, text = excluded.text",
                (
                    sha, page, text_source, engine, engine_version, ocr_mode,
                    derivation_version, config_hash, text,
                ),
            )

    def read_bronze_text(
        self,
        sha: str,
        *,
        derivation_version: str,
        config_hash: str,
    ) -> list[dict]:
        """Per-page derived text rows for one derivation (page order)."""
        with self._op_lock:
            cur = self._conn.execute(
                "SELECT page, text_source, engine, engine_version, ocr_mode, "
                "text FROM bronze_text WHERE hash = ? "
                "AND derivation_version = ? AND config_hash = ? "
                "ORDER BY page",
                (sha, derivation_version, config_hash),
            )
            return [dict(r) for r in cur.fetchall()]

    def add_alias(self, sha: str, path: str) -> None:
        """Record that `path` was seen holding bronze `sha` (upsert)."""
        now = _utcnow()
        with self.txn():
            self._conn.execute(
                "INSERT INTO bronze_alias (hash, path, last_seen) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(hash, path) DO UPDATE "
                "SET last_seen = excluded.last_seen",
                (sha, path, now),
            )

    def store_bronze_bytes(self, sha: str, data: bytes) -> str:
        """Content-addressed copy under <data_dir>/bronze/xx/<sha>.

        Atomic write, mode 0400. Idempotent: an existing identical file
        is left untouched. A sha mismatch raises loudly (never stores
        bytes under the wrong address). Registers the bronze row
        (idempotent) so the bytes_ref foreign key always holds. Returns
        the relative path.
        """
        if _sha256_bytes(data) != sha:
            raise ValueError(
                f"bytes do not hash to {sha[:16]}...: refusing to store "
                "under the wrong content address"
            )
        rel = f"bronze/{sha[:2]}/{sha}"
        target = self.data_dir / rel
        if target.exists():
            if _sha256_file(target) != sha:
                raise IOError(
                    f"corrupt bronze object at {rel}: on-disk bytes do "
                    "not match the content address"
                )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o700)
            fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                         0o400)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
            except BaseException:
                try:
                    os.unlink(target)
                except OSError:
                    pass
                raise
        with self.txn():
            self.register_bronze(sha, len(data))
            self._conn.execute(
                "INSERT OR IGNORE INTO bronze_bytes_ref (hash, rel_path) "
                "VALUES (?, ?)",
                (sha, rel),
            )
        return rel

    def get_bronze(self, sha: str) -> dict | None:
        """Bronze row plus its alias paths, or None. Metadata only."""
        with self._op_lock:
            row = self._conn.execute(
                "SELECT * FROM bronze WHERE hash = ?", (sha,)
            ).fetchone()
            if row is None:
                return None
            out = dict(row)
            out["aliases"] = [
                r["path"] for r in self._conn.execute(
                    "SELECT path FROM bronze_alias WHERE hash = ? "
                    "ORDER BY path",
                    (sha,),
                )
            ]
            return out

    # -- silver ----------------------------------------------------------
    def upsert_silver_doc(self, doc: Document, *, derivation_version: str,
                          config_hash: str, derivation_digest: str) -> None:
        """Insert or replace one silver_doc row (full-row upsert)."""
        now = _utcnow()
        with self.txn():
            self._conn.execute(
                "INSERT INTO silver_doc "
                "(doc_id, bronze_hash, form_type, tax_year, status, "
                " status_reason, page_range, parent_doc_id, relevance, "
                " validated_at, re_review, derivation_version, config_hash, "
                " derivation_digest, fields_json, created_at, updated_at, "
                " owner_person_id, owner_suggestion, owner_suggestion_basis) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                " ?, ?, ?) "
                "ON CONFLICT(doc_id) DO UPDATE SET "
                "bronze_hash = excluded.bronze_hash, "
                "form_type = excluded.form_type, "
                "tax_year = excluded.tax_year, "
                "status = excluded.status, "
                "status_reason = excluded.status_reason, "
                "page_range = excluded.page_range, "
                "parent_doc_id = excluded.parent_doc_id, "
                "relevance = excluded.relevance, "
                "validated_at = excluded.validated_at, "
                "re_review = excluded.re_review, "
                "derivation_version = excluded.derivation_version, "
                "config_hash = excluded.config_hash, "
                "derivation_digest = excluded.derivation_digest, "
                "fields_json = excluded.fields_json, "
                "owner_person_id = excluded.owner_person_id, "
                "owner_suggestion = excluded.owner_suggestion, "
                "owner_suggestion_basis = excluded.owner_suggestion_basis, "
                "updated_at = excluded.updated_at",
                (
                    doc.doc_id,
                    doc.source_sha256,
                    doc.form_type,
                    doc.tax_year,
                    doc.status,
                    doc.status_reason,
                    doc.page_range,
                    doc.parent_doc_id,
                    doc.relevance,
                    doc.validated_at,
                    int(bool(doc.re_review)),
                    derivation_version,
                    config_hash,
                    derivation_digest,
                    _canon(doc.fields),
                    now,
                    now,
                    doc.owner_person_id,
                    doc.owner_suggestion,
                    doc.owner_suggestion_basis,
                ),
            )
            # Doc-level text provenance (R5; W1's doc_provenance table).
            # Written on every silver upsert so the facade round-trips it
            # exactly as the JSONL store did.
            self._conn.execute(
                "INSERT INTO doc_provenance "
                "(doc_id, text_source, reason_code, ocr_engine, "
                " engine_version, ocr_mode, attempts_json, mean_confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(doc_id) DO UPDATE SET "
                "text_source = excluded.text_source, "
                "reason_code = excluded.reason_code, "
                "ocr_engine = excluded.ocr_engine, "
                "engine_version = excluded.engine_version, "
                "ocr_mode = excluded.ocr_mode, "
                "attempts_json = excluded.attempts_json, "
                "mean_confidence = excluded.mean_confidence",
                (
                    doc.doc_id,
                    doc.text_source,
                    doc.reason_code,
                    doc.ocr_engine,
                    doc.engine_version,
                    doc.ocr_mode,
                    _canon(doc.attempts or []),
                    doc.mean_confidence,
                ),
            )

    def replace_artifacts(self, doc_id: str, artifacts: list[dict]) -> None:
        """Full replace of a doc's artifacts for one derivation.

        Every existing artifact row for the doc is deleted first, so
        vanished anchors leave no stale rows; then the new set is
        inserted. Each artifact dict carries artifact_id/page/
        artifact_type/anchor/value_json/offsets_json/derivation_version/
        config_hash.

        R21a: per-artifact owner assignments (Operator decisions) are
        preserved across the replace: an artifact_id that survives the
        re-derivation keeps its owner_person_id/owner_suggestion;
        incoming dicts may also carry them explicitly (explicit wins).
        """
        now = _utcnow()
        with self.txn():
            row = self._conn.execute(
                "SELECT bronze_hash FROM silver_doc WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"no silver_doc for {doc_id!r}")
            bronze_hash = row["bronze_hash"]
            carried = {
                r["artifact_id"]: (r["owner_person_id"], r["owner_suggestion"])
                for r in self._conn.execute(
                    "SELECT artifact_id, owner_person_id, owner_suggestion "
                    "FROM silver_artifact WHERE doc_id = ?",
                    (doc_id,),
                )
            }
            self._conn.execute(
                "DELETE FROM silver_artifact WHERE doc_id = ?",
                (doc_id,),
            )
            for a in artifacts:
                old_pid, old_sug = carried.get(a["artifact_id"], (None, None))
                owner_person_id = a.get("owner_person_id", old_pid)
                owner_suggestion = a.get("owner_suggestion", old_sug)
                self._conn.execute(
                    "INSERT INTO silver_artifact "
                    "(artifact_id, doc_id, bronze_hash, page, artifact_type, "
                    " anchor, value_json, offsets_json, derivation_version, "
                    " config_hash, created_at, updated_at, "
                    " owner_person_id, owner_suggestion) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        a["artifact_id"],
                        doc_id,
                        bronze_hash,
                        a["page"],
                        a["artifact_type"],
                        a["anchor"],
                        a["value_json"],
                        a.get("offsets_json"),
                        a["derivation_version"],
                        a["config_hash"],
                        now,
                        now,
                        owner_person_id,
                        owner_suggestion,
                    ),
                )

    def get_artifacts(self, doc_id: str,
                      artifact_type: str | None = None) -> list[dict]:
        """Artifact rows for a doc, optionally filtered by type."""
        with self._op_lock:
            if artifact_type is None:
                cur = self._conn.execute(
                    "SELECT * FROM silver_artifact WHERE doc_id = ? "
                    "ORDER BY artifact_type, anchor",
                    (doc_id,),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM silver_artifact WHERE doc_id = ? "
                    "AND artifact_type = ? ORDER BY anchor",
                    (doc_id, artifact_type),
                )
            return [dict(r) for r in cur]

    # -- decision log ------------------------------------------------------
    def log_decision(self, *, actor: str, kind: str, artifact_id: str | None = None,
                     doc_id: str | None = None, group_id: str | None = None,
                     payload: dict) -> int:
        """Append one decision. Returns the seq. Append-only (I6).

        Unknown kinds are refused loudly; UPDATE/DELETE are refused by
        database triggers (see medallion_schema.sql).
        """
        if kind not in _DECISION_KINDS:
            raise ValueError(
                f"unknown decision kind {kind!r}; "
                f"must be one of {sorted(_DECISION_KINDS)}"
            )
        with self.txn():
            cur = self._conn.execute(
                "INSERT INTO decision_log "
                "(ts, actor, kind, artifact_id, doc_id, group_id, "
                " payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_utcnow(), actor, kind, artifact_id, doc_id, group_id,
                 _canon(payload)),
            )
            return cur.lastrowid

    def decisions_for(self, artifact_id: str | None = None,
                      doc_id: str | None = None,
                      kind: str | None = None) -> list[dict]:
        """Decision rows matching all given filters, oldest first."""
        clauses, params = [], []
        if artifact_id is not None:
            clauses.append("artifact_id = ?")
            params.append(artifact_id)
        if doc_id is not None:
            clauses.append("doc_id = ?")
            params.append(doc_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._op_lock:
            cur = self._conn.execute(
                f"SELECT seq, ts, actor, kind, artifact_id, doc_id, group_id, "
                f"payload_json FROM decision_log {where} ORDER BY seq ASC",
                params,
            )
            out = []
            for r in cur:
                d = dict(r)
                d["payload"] = json.loads(d.pop("payload_json"))
                out.append(d)
            return out

    # -- digests / counts ----------------------------------------------------
    def table_counts(self) -> dict[str, int]:
        """Row count per table (alphabetical). Counts only, no content."""
        with self._op_lock:
            tables = [r[0] for r in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            return {
                t: self._conn.execute(
                    f"SELECT COUNT(*) FROM {_q(t)}").fetchone()[0]
                for t in tables
            }

    def db_digest(self) -> dict:
        """Per-table row counts plus a content digest per table.

        Digests exclude volatile bookkeeping columns (see _DIGEST_COLS),
        so identical logical writes produce identical digests (ingest-twice
        idempotency). Digests and counts only -- never values.
        """
        counts = self.table_counts()
        tables = {}
        with self._op_lock:
            for table, cols in _DIGEST_COLS.items():
                if table not in counts:
                    continue
                sel = ", ".join(_q(c) for c in cols)
                order = ", ".join(_q(c) for c in cols)
                rows = self._conn.execute(
                    f"SELECT {sel} FROM {_q(table)} ORDER BY {order}"
                ).fetchall()
                canon = _canon([list(r) for r in rows])
                tables[table] = _sha256_bytes(canon.encode("utf-8"))
        return {"counts": counts, "tables": tables}

    # -- Document-compatible facade ------------------------------------------
    def _ensure_bronze_for_doc(self, doc: Document) -> str:
        """Register bronze + alias for a facade upsert; return bronze hash.

        Legacy path: if doc.source_sha256 is set and the source file is
        present, the bytes are verified against it; if the sha is missing,
        the source file is re-hashed when present; otherwise a
        "legacy-<doc_id>" tombstone with blocked_reason="legacy-no-source".
        """
        sha = doc.source_sha256
        size = _UNKNOWN_SIZE
        blocked: str | None = None
        src = Path(doc.source_path) if doc.source_path else None
        data: bytes | None = None
        if sha:
            if src is not None and src.is_file():
                data = src.read_bytes()
                if _sha256_bytes(data) != sha:
                    raise ValueError(
                        f"source file {src} does not hash to the recorded "
                        f"source_sha256 for {doc.doc_id}: refusing upsert"
                    )
                size = len(data)
        elif src is not None and src.is_file():
            data = src.read_bytes()
            sha = _sha256_bytes(data)
            size = len(data)
        else:
            sha = f"{_TOMBSTONE_PREFIX}{doc.doc_id}"
            blocked = _TOMBSTONE_BLOCKED_REASON
        with self.txn():
            created = self.register_bronze(
                sha, size, source_root=None, encryption=doc.encryption)
            if blocked and created:
                self._set_blocked_reason(sha, blocked)
            if data is not None:
                self.store_bronze_bytes(sha, data)
            self.add_alias(sha, doc.source_path)
        return sha

    def upsert(self, doc: Document) -> None:
        """Insert or replace one Document (last write wins per doc_id).

        Atomic: the bronze/alias/silver/artifact writes all land in one
        transaction. Concurrent instances never lose each other's records
        -- SQLite serializes writers; a contended write waits up to
        busy_timeout then fails LOUDLY (OperationalError), never silently.
        """
        with self.txn():
            sha = self._ensure_bronze_for_doc(doc)
            # Persist the RESOLVED bronze hash (re-hash or tombstone may
            # differ from doc.source_sha256); get() maps the legacy
            # tombstone back to None.
            doc = replace(doc, source_sha256=sha)
            # The facade path is a pre-medallion derivation ("1").
            self.upsert_silver_doc(
                doc,
                derivation_version=_FACADE_DERIVATION_VERSION,
                config_hash=_FACADE_CONFIG_HASH,
                derivation_digest=_derivation_digest(doc.fields),
            )
            # Contract §5: every mutation path updates fields_json and the
            # mirror artifacts together, in one txn.
            self.replace_artifacts(
                doc.doc_id,
                _mirror_artifacts(doc.doc_id, sha, doc.fields,
                                  _FACADE_DERIVATION_VERSION,
                                  _FACADE_CONFIG_HASH),
            )

    # -- R21a: per-person scoping --------------------------------------
    def set_doc_owner(self, doc_id: str, *, owner_person_id: str | None,
                      owner_suggestion: str | None = None,
                      owner_suggestion_basis: str | None = None) -> None:
        """Targeted write of the R21a owner columns on silver_doc.

        Used for Operator owner assignment and system suggestion writes;
        unlike upsert() it touches nothing else (no artifact rebuild, no
        derivation restamp). Raises KeyError for an unknown doc_id.
        """
        with self.txn():
            row = self._conn.execute(
                "SELECT doc_id FROM silver_doc WHERE doc_id = ?",
                (doc_id,)).fetchone()
            if row is None:
                raise KeyError(f"no silver_doc for {doc_id!r}")
            self._conn.execute(
                "UPDATE silver_doc SET owner_person_id = ?, "
                "owner_suggestion = ?, owner_suggestion_basis = ?, "
                "updated_at = ? WHERE doc_id = ?",
                (owner_person_id, owner_suggestion, owner_suggestion_basis,
                 _utcnow(), doc_id),
            )

    def set_artifact_owner(self, artifact_id: str, *,
                           owner_person_id: str | None,
                           owner_suggestion: str | None = None) -> None:
        """Targeted write of the R21a owner columns on one artifact row.

        Per-artifact owners exist for documents covering several people:
        the Operator allocates joint/multi-owner items per artifact (never
        mechanically split). Raises KeyError for an unknown artifact_id.
        """
        with self.txn():
            row = self._conn.execute(
                "SELECT artifact_id FROM silver_artifact WHERE artifact_id = ?",
                (artifact_id,)).fetchone()
            if row is None:
                raise KeyError(f"no silver_artifact for {artifact_id!r}")
            self._conn.execute(
                "UPDATE silver_artifact SET owner_person_id = ?, "
                "owner_suggestion = ?, updated_at = ? WHERE artifact_id = ?",
                (owner_person_id, owner_suggestion, _utcnow(), artifact_id),
            )

    # silver_doc + bronze (encryption, blocked_reason) + doc_provenance,
    # so the facade reconstructs the full Document record.
    _DOC_SELECT = (
        "SELECT s.*, b.encryption AS bronze_encryption, b.blocked_reason, "
        "p.text_source, p.reason_code, p.ocr_engine, p.engine_version, "
        "p.ocr_mode, p.attempts_json, p.mean_confidence "  # R15/R5 doc provenance
        "FROM silver_doc s "
        "JOIN bronze b ON b.hash = s.bronze_hash "
        "LEFT JOIN doc_provenance p ON p.doc_id = s.doc_id"
    )

    def _row_to_doc(self, row: sqlite3.Row) -> Document:
        sha = row["bronze_hash"]
        alias = self._conn.execute(
            "SELECT path FROM bronze_alias WHERE hash = ? "
            "ORDER BY last_seen DESC LIMIT 1",
            (sha,),
        ).fetchone()
        source_sha256 = (None if row["blocked_reason"]
                         == _TOMBSTONE_BLOCKED_REASON else sha)
        return Document(
            doc_id=row["doc_id"],
            tax_year=row["tax_year"],
            form_type=row["form_type"],
            source_path=alias["path"] if alias else "",
            ocr_text_ref=f"ocr/{row['doc_id']}.txt",
            fields=json.loads(row["fields_json"]),
            status=row["status"],
            validated_at=row["validated_at"],
            relevance=row["relevance"],
            page_range=row["page_range"],
            parent_doc_id=row["parent_doc_id"],
            source_sha256=source_sha256,
            status_reason=row["status_reason"],
            re_review=bool(row["re_review"]),
            text_source=row["text_source"],
            reason_code=row["reason_code"],
            ocr_engine=row["ocr_engine"],
            engine_version=row["engine_version"],
            ocr_mode=row["ocr_mode"],
            attempts=json.loads(row["attempts_json"] or "[]"),
            mean_confidence=row["mean_confidence"],
            encryption=row["bronze_encryption"],
            owner_person_id=row["owner_person_id"],
            owner_suggestion=row["owner_suggestion"],
            owner_suggestion_basis=row["owner_suggestion_basis"],
        )

    def get(self, doc_id: str) -> Document | None:
        with self._op_lock:
            row = self._conn.execute(
                self._DOC_SELECT + " WHERE s.doc_id = ?", (doc_id,)
            ).fetchone()
            return self._row_to_doc(row) if row is not None else None

    def list(self, year: int | None = None,
             form: str | None = None) -> list[Document]:
        clauses, params = [], []
        if year is not None:
            clauses.append("s.tax_year = ?")
            params.append(year)
        if form is not None:
            clauses.append("s.form_type = ?")
            params.append(form)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._op_lock:
            cur = self._conn.execute(
                f"{self._DOC_SELECT} {where} "
                f"ORDER BY COALESCE(s.tax_year, 0), s.form_type, s.doc_id",
                params,
            )
            return [self._row_to_doc(r) for r in cur]

    def counts(self) -> dict[tuple[int | None, str], int]:
        out: dict[tuple[int | None, str], int] = {}
        for d in self.list():
            key = (d.tax_year, d.form_type)
            out[key] = out.get(key, 0) + 1
        return out

    def needs_review(self) -> list[Document]:
        return [d for d in self.list() if d.status == "needs_review"]

    def refresh(self) -> None:
        """Kept for compatibility. Reads now hit SQLite directly, so the
        view is always current -- there is no stale snapshot to reload."""
        return None

    def __len__(self) -> int:
        with self._op_lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM silver_doc").fetchone()[0]

    # -- OCR text ------------------------------------------------------------
    def save_ocr(self, doc_id: str, text: str,
                 pages: list[str] | None = None) -> str:
        """Persist OCR text; returns the ocr_text_ref stored on the Document.

        ``pages`` (O2): when given, the per-page texts are stored joined
        by form-feed separators (``"\\f"``) so page structure survives
        in the stored text -- R15/R19 can map pages on OCR'd docs. The
        EXTRACTION text is always the ``"\\n"`` join and is unchanged.
        Default None keeps the legacy behavior (``text`` stored
        verbatim) for the section-text call sites.
        """
        ref = f"ocr/{doc_id}.txt"
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        stored = "\f".join(pages) if pages is not None else text
        (self.ocr_dir / f"{doc_id}.txt").write_text(stored, encoding="utf-8")
        return ref

    def load_ocr(self, doc_id: str) -> str:
        return (self.ocr_dir / f"{doc_id}.txt").read_text(encoding="utf-8")

    def _ensure_private_ocr_dir(self) -> None:
        """The ocr/ dir at 0700 (PII-adjacent word boxes live here)."""
        self.ocr_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # mkdir(mode=...) is a no-op for existing dirs; tighten when a
        # permissive umask widened it.
        try:
            st = self.ocr_dir.stat()
            if st.st_mode & 0o077:
                os.chmod(self.ocr_dir, st.st_mode & ~0o077)
        except OSError:
            pass

    def save_ocr_words(self, doc_id: str,
                       words: dict[int, list[dict]] | None) -> str | None:
        """Persist tesseract TSV word boxes as a JSON sidecar (O2/R15/R19).

        ``words`` is ``{page_0based: [word, ...]}`` with each word
        ``{"text", "bbox": [x0,y0,x1,y1] (PDF points, bottom-left),
        "conf", "page"}`` -- the ``ocr._run_tesseract`` shape, and the
        same shape ``provenance.GeometryResolver`` consumes in memory.
        Written to ``ocr/<doc_id>.words.json`` (0700 dir), JSON with
        sorted keys (deterministic). Returns the sidecar ref, or None
        when ``words`` is empty/None (nothing stored).

        Geometry is PII-adjacent (positions, not values): it is stripped
        from every MCP/bus output, like all provenance (blind-orchestrator
        contract).
        """
        if not words:
            return None
        ref = f"ocr/{doc_id}.words.json"
        self._ensure_private_ocr_dir()
        serial = {str(p): ws for p, ws in sorted(words.items())}
        (self.ocr_dir / f"{doc_id}.words.json").write_text(
            json.dumps(serial, sort_keys=True), encoding="utf-8")
        return ref

    def load_ocr_words(self, doc_id: str) -> dict[int, list[dict]] | None:
        """Load the word-box sidecar; None when absent or unreadable.

        Keys come back as ints (0-based pages); word dicts are the
        stored ``{"text", "bbox", "conf", "page"}`` records.
        """
        try:
            raw = (self.ocr_dir / f"{doc_id}.words.json").read_text(
                encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        try:
            return {int(p): ws for p, ws in data.items()}
        except (TypeError, ValueError):
            return None


# Back-compat alias: taxprep.store re-exports this as DocumentStore.
DocumentStore = MedallionStore


def _mirror_artifacts(doc_id: str, bronze_hash: str, fields: dict,
                      derivation_version: str, config_hash: str) -> list[dict]:
    """Artifact dicts mirroring a fields dict (contract §5).

    One 'field' artifact per fields-dict key (anchor=key, page=0) plus
    one 'lot' artifact per fields["lots"] entry (anchor=f"lot:{i}",
    page=0). Used by the facade upsert and the JSONL migration.
    """
    out = []
    for key, value in fields.items():
        out.append({
            "artifact_id": _artifact_id(doc_id, bronze_hash, 0, "field",
                                        key),
            "page": 0,
            "artifact_type": "field",
            "anchor": key,
            "value_json": _canon(value),
            "offsets_json": None,
            "derivation_version": derivation_version,
            "config_hash": config_hash,
        })
    lots = fields.get("lots")
    if isinstance(lots, dict):
        lot_list = lots.get("value")
    elif isinstance(lots, list):
        lot_list = lots
    else:
        lot_list = None
    if isinstance(lot_list, list):
        for i, lot in enumerate(lot_list):
            anchor = f"lot:{i}"
            out.append({
                "artifact_id": _artifact_id(doc_id, bronze_hash, 0, "lot",
                                            anchor),
                "page": 0,
                "artifact_type": "lot",
                "anchor": anchor,
                "value_json": _canon(lot),
                "offsets_json": None,
                "derivation_version": derivation_version,
                "config_hash": config_hash,
            })
    return out
