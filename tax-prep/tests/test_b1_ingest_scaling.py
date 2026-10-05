"""B1 ingest scaling: L4 indexed same-payer lookup, single-txn ingest_dir,
indexed counts()/needs_review()/docs_for_bronze.

Every assertion is on SQL execute counts, EXPLAIN QUERY PLAN output, or
result correctness -- never wall-clock. All fixtures synthetic (no PII).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from taxprep import duplicates as D
from taxprep import ingest
from taxprep.ingest import RC_EXTRACT_FAILED, _SkipFile, ingest_dir
from taxprep.models import Document
from taxprep.mstore import MedallionStore

# Synthetic payer identities (not real EINs).
EIN_A = "12-3456789"
EIN_B = "98-7654321"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class CountingConn:
    """sqlite3 connection proxy counting execute() calls (and COMMITs)."""

    def __init__(self, conn):
        self._conn = conn
        self.executes = 0
        self.commits = 0

    def execute(self, sql, *args, **kwargs):
        self.executes += 1
        if isinstance(sql, str) and sql.strip().upper().startswith("COMMIT"):
            self.commits += 1
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture()
def store(tmp_path):
    return MedallionStore(tmp_path / "data")


@pytest.fixture()
def counting_store(store):
    counter = CountingConn(store._conn)
    store._conn = counter
    store._counter = counter  # noqa: SLF001 - test instrumentation
    return store


def _w2_fields(ein, name, wages, withheld="1500"):
    return {
        "employer_ein": {"value": ein},
        "employer_name": {"value": name},
        "1": {"value": wages},
        "2": {"value": withheld},
    }


def _upsert_w2(store, doc_id, sha, ein, name, wages, tax_year=2024,
               status="needs_review"):
    doc = Document(
        doc_id=doc_id,
        tax_year=tax_year,
        form_type="W-2",
        source_path=f"/in/{doc_id}.txt",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=_w2_fields(ein, name, wages),
        status=status,
        source_sha256=sha,
    )
    store.upsert(doc)
    return doc


def _payer_cols(store, doc_id):
    row = store._conn.execute(  # noqa: SLF001 - white-box column check
        "SELECT payer_ein, payer_name_norm FROM silver_doc WHERE doc_id = ?",
        (doc_id,)).fetchone()
    return (row["payer_ein"], row["payer_name_norm"])


def _write_corpus(root: Path, n: int, payers: int = 10) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        p = i % payers
        (root / f"w2-{i:04d}.txt").write_text(
            "Form W-2 Wage and Tax Statement\n"
            "Tax Year 2024\n"
            f"Employer: ACME-{p:04d} CORP 12-34567{p:02d}\n"
            f"Box 1 Wages ${10000 + i * 137}.00\n"
            f"Box 2 Withheld ${1500 + i}.00\n",
            encoding="utf-8")


@pytest.fixture()
def no_hooks(monkeypatch):
    monkeypatch.setattr(ingest, "_hook_assess_new_bronze",
                        lambda store, sha: "disabled")
    monkeypatch.setattr(ingest, "_hook_assess_silver_doc",
                        lambda store, doc_id: "disabled")


# ---------------------------------------------------------------------------
# 1. stored payer identity + indexed L4 lookup
# ---------------------------------------------------------------------------

def test_upsert_populates_payer_columns(store):
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    ein, name = _payer_cols(store, "doc-a")
    assert ein == "123456789"
    assert name == "acme corp"
    # unknown identity stores '' (populated, not NULL -> no re-backfill)
    _upsert_w2(store, "doc-b", "b" * 64, "", "", "10000")
    assert _payer_cols(store, "doc-b") == ("", "")


def test_l4_candidate_query_uses_payer_index(store):
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    plan = store._conn.execute(  # noqa: SLF001
        "EXPLAIN QUERY PLAN "
        "SELECT doc_id, fields_json FROM silver_doc "
        "WHERE form_type = ? AND tax_year = ? AND payer_ein = ? "
        "AND payer_name_norm = ? AND doc_id <> ? ORDER BY doc_id",
        ("W-2", 2024, "123456789", "acme corp", "doc-a")).fetchall()
    detail = " ".join(r["detail"] for r in plan)
    assert "idx_silver_doc_payer" in detail
    assert "SCAN silver_doc" not in detail


def test_l4_same_payer_priors_only_same_payer(store):
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    _upsert_w2(store, "doc-b", "b" * 64, EIN_A, "Acme Corp", "20000")
    _upsert_w2(store, "doc-c", "c" * 64, EIN_B, "Beta LLC", "30000")
    _upsert_w2(store, "doc-d", "d" * 64, EIN_A, "Acme Corp", "40000",
               tax_year=2023)  # same payer, other year
    with store.txn() as conn:
        priors = D._l4_same_payer_priors(
            conn, "W-2", 2024, ("123456789", "acme corp"), "doc-b")
    assert [p[0] for p in priors] == ["doc-a"]


def test_l4_supersedes_group_only_for_same_payer(store):
    # doc-a and doc-b: same payer, differing Box 1 -> supersedes pair.
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    _upsert_w2(store, "doc-b", "b" * 64, EIN_A, "Acme Corp", "20000")
    # doc-c: different payer, same year -> must not pair with doc-a/doc-b.
    _upsert_w2(store, "doc-c", "c" * 64, EIN_B, "Beta LLC", "10000")
    created = D.assess_new_bronze(store, "b" * 64)
    assert len(created) == 1
    with store.txn() as conn:
        members = dict(conn.execute(
            "SELECT member_key, role FROM dup_member WHERE group_id = ?",
            (created[0],)).fetchall())
    assert members == {"doc-b": "candidate", "doc-a": "reference"}
    # doc-c's assessment finds no same-payer prior with differing values.
    assert D.assess_new_bronze(store, "c" * 64) == []
    # identical values -> no supersedes group either.
    _upsert_w2(store, "doc-e", "e" * 64, EIN_B, "Beta LLC", "10000")
    assert D.assess_new_bronze(store, "e" * 64) == []


def test_l4_backfill_runs_once_per_legacy_doc(store):
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    # Simulate a legacy row written before the B1 columns existed.
    store._conn.execute(  # noqa: SLF001
        "UPDATE silver_doc SET payer_ein = NULL, payer_name_norm = NULL "
        "WHERE doc_id = 'doc-a'")
    assert _payer_cols(store, "doc-a") == (None, None)
    _upsert_w2(store, "doc-b", "b" * 64, EIN_A, "Acme Corp", "20000")
    D.assess_new_bronze(store, "b" * 64)
    assert _payer_cols(store, "doc-a") == ("123456789", "acme corp")

    class BackfillCounter(CountingConn):
        def __init__(self, conn):
            super().__init__(conn)
            self.backfill_updates = 0

        def execute(self, sql, *args, **kwargs):
            if (isinstance(sql, str) and sql.strip().upper().startswith(
                    "UPDATE silver_doc SET payer_ein")):
                self.backfill_updates += 1
            return super().execute(sql, *args, **kwargs)

    # Second assessment performs zero backfill UPDATEs (backfill-once).
    counter = BackfillCounter(store._conn)  # noqa: SLF001
    store._conn = counter  # noqa: SLF001
    try:
        D.assess_new_bronze(store, "b" * 64)
    finally:
        store._conn = counter._conn  # noqa: SLF001 - restore
    assert counter.backfill_updates == 0
    assert _payer_cols(store, "doc-a") == ("123456789", "acme corp")


def test_legacy_schema_migrates_payer_columns_and_index(tmp_path):
    from taxprep.mstore import _load_schema_sql  # noqa: SLF001
    old_sql = _load_schema_sql()
    # Reconstruct the pre-B1 schema by stripping the B1 additions.
    strips = [
        ("    updated_at TEXT NOT NULL,\n"
         "    -- B1: stored payer identity for the L4 same-payer indexed lookup.\n"
         "    -- NULL = never populated (legacy row, backfilled once on read);\n"
         "    -- '' = populated, unknown.\n"
         "    payer_ein TEXT,\n"
         "    payer_name_norm TEXT\n"
         ");",
         "    updated_at TEXT NOT NULL\n);"),
        ("-- B1: L4 candidate lookup (form, year, payer identity).\n"
         "CREATE INDEX idx_silver_doc_payer ON silver_doc\n"
         "    (form_type, tax_year, payer_ein, payer_name_norm);\n", ""),
        ("-- B1: per-file _docs_for_bronze lookup (ingest hot path).\n"
         "CREATE INDEX idx_silver_doc_bronze ON silver_doc (bronze_hash);\n",
         ""),
    ]
    for snippet, replacement in strips:
        assert snippet in old_sql, snippet  # B1 additions present to strip
        old_sql = old_sql.replace(snippet, replacement)
    data_dir = tmp_path / "legacy-data"
    data_dir.mkdir()
    conn = sqlite3.connect(str(data_dir / "medallion.sqlite"))
    conn.executescript(old_sql)
    conn.close()
    store = MedallionStore(data_dir)  # migration runs on open
    cols = {r["name"] for r in store._conn.execute(  # noqa: SLF001
        "PRAGMA table_info(silver_doc)")}
    assert {"payer_ein", "payer_name_norm"} <= cols
    idx = {r["name"] for r in store._conn.execute(  # noqa: SLF001
        "PRAGMA index_list(silver_doc)")}
    assert {"idx_silver_doc_payer", "idx_silver_doc_bronze"} <= idx
    # Fresh writes populate the migrated columns.
    _upsert_w2(store, "doc-a", "a" * 64, EIN_A, "Acme Corp", "10000")
    assert _payer_cols(store, "doc-a") == ("123456789", "acme corp")


# ---------------------------------------------------------------------------
# 2. ingest_dir: one outer commit, flat per-doc executes, error isolation
# ---------------------------------------------------------------------------

def test_ingest_dir_single_outer_commit(counting_store, tmp_path, no_hooks):
    src = tmp_path / "incoming"
    _write_corpus(src, 20)
    report = ingest_dir(src, counting_store)
    assert report.ingested == 20
    assert counting_store._counter.commits == 1  # noqa: SLF001
    assert len(counting_store.list()) == 20


def test_ingest_dir_per_doc_executes_flat(tmp_path, no_hooks):
    per_doc = []
    for n in (30, 60):
        data = tmp_path / f"data-{n}"
        store = MedallionStore(data)
        counter = CountingConn(store._conn)
        store._conn = counter
        src = tmp_path / f"incoming-{n}"
        _write_corpus(src, n)
        report = ingest_dir(src, store)
        assert report.ingested == n
        per_doc.append(counter.executes / n)
    # Flat: doubling the corpus must not multiply per-doc executes.
    # (Pre-B1 this ratio was ~2.4 on the same fixture.)
    assert per_doc[1] <= 1.5 * per_doc[0], per_doc


def test_ingest_dir_error_doc_still_recorded(counting_store, tmp_path,
                                             monkeypatch, no_hooks):
    src = tmp_path / "incoming"
    _write_corpus(src, 5)
    real_bundle = ingest._page_bundle_for

    def boom(path, source_bytes, suffix, store, source_root=None):
        if path.name == "w2-0002.txt":
            raise RuntimeError("synthetic extraction failure")
        return real_bundle(path, source_bytes, suffix, store,
                           source_root=source_root)

    monkeypatch.setattr(ingest, "_page_bundle_for", boom)
    report = ingest_dir(src, counting_store)
    assert len(report.errored) == 1
    assert report.errored[0]["reason_code"] == RC_EXTRACT_FAILED
    assert report.errored[0]["file"].endswith("w2-0002.txt")
    # The failure is recorded as a document (nothing silent) ...
    assert len(report.docs) == 5
    # ... the rest of the batch ingested, and the batch committed once.
    assert report.ingested == 5
    assert counting_store._counter.commits == 1  # noqa: SLF001
    assert len(counting_store.list()) == 5


def test_ingest_dir_skip_file_isolation(counting_store, tmp_path,
                                        monkeypatch, no_hooks):
    src = tmp_path / "incoming"
    _write_corpus(src, 5)
    real_medallion = ingest._ingest_file_medallion

    def skip_one(path, source_bytes, suffix, store, **kwargs):
        if path.name == "w2-0003.txt":
            raise _SkipFile("test-skip")
        return real_medallion(path, source_bytes, suffix, store, **kwargs)

    monkeypatch.setattr(ingest, "_ingest_file_medallion", skip_one)
    report = ingest_dir(src, counting_store)
    assert len(report.skipped) == 1
    assert report.skipped[0]["reason_code"] == "test-skip"
    # Files around the skip still ingested; batch committed once.
    assert report.ingested == 4
    assert counting_store._counter.commits == 1  # noqa: SLF001
    assert len(counting_store.list()) == 4


# ---------------------------------------------------------------------------
# 3. indexed list-all/filter hot paths
# ---------------------------------------------------------------------------

def test_counts_single_group_by_query(counting_store):
    _upsert_w2(counting_store, "doc-a", "a" * 64, EIN_A, "Acme", "10000")
    _upsert_w2(counting_store, "doc-b", "b" * 64, EIN_B, "Beta", "20000")
    _upsert_w2(counting_store, "doc-c", "c" * 64, EIN_A, "Acme", "30000",
               tax_year=2023)
    counting_store._counter.executes = 0  # noqa: SLF001
    counts = counting_store.counts()
    assert counting_store._counter.executes == 1  # noqa: SLF001
    assert counts == {(2024, "W-2"): 2, (2023, "W-2"): 1}


def test_needs_review_filtered_in_sql(counting_store):
    _upsert_w2(counting_store, "doc-a", "a" * 64, EIN_A, "Acme", "10000",
               status="needs_review")
    _upsert_w2(counting_store, "doc-b", "b" * 64, EIN_B, "Beta", "20000",
               status="validated")
    _upsert_w2(counting_store, "doc-c", "c" * 64, EIN_A, "Acme", "30000",
               status="needs_review")
    counting_store._counter.executes = 0  # noqa: SLF001
    got = counting_store.needs_review()
    assert {d.doc_id for d in got} == {"doc-a", "doc-c"}
    # 1 filtered SELECT + 1 alias lookup per returned row (no full decode).
    assert counting_store._counter.executes == 1 + len(got)  # noqa: SLF001


def test_docs_for_bronze_indexed_lookup(counting_store):
    _upsert_w2(counting_store, "doc-a", "a" * 64, EIN_A, "Acme", "10000")
    _upsert_w2(counting_store, "doc-b", "b" * 64, EIN_B, "Beta", "20000")
    counting_store._counter.executes = 0  # noqa: SLF001
    got = counting_store.docs_for_bronze("a" * 64)
    assert [d.doc_id for d in got] == ["doc-a"]
    # 1 indexed SELECT + 1 alias lookup (was: full list() decode per file).
    assert counting_store._counter.executes == 2  # noqa: SLF001


# ---------------------------------------------------------------------------
# 4. regression guards
# ---------------------------------------------------------------------------

def test_mstore_duplicates_import_is_lazy():
    """duplicates must not be imported at mstore module top level.

    Observed: a top-level ``from . import duplicates`` in mstore (i.e.
    importing taxprep.duplicates before taxprep.mstore finishes
    importing) makes forked child processes crash under concurrency
    (test_concurrent_process_writers_no_lost_records); a function-local
    import inside upsert_silver_doc is safe. Static guard so the import
    never creeps back to the top.
    """
    import ast
    src = (Path(__file__).resolve().parent.parent
           / "taxprep" / "mstore.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
        else:
            continue
        assert not any("duplicates" in n for n in names), (
            "taxprep.duplicates must stay a lazy import in mstore "
            "(fork safety)")


def test_reingest_executes_linear(tmp_path, no_hooks):
    per_doc = []
    for n in (20, 40):
        data = tmp_path / f"data-{n}"
        store = MedallionStore(data)
        src = tmp_path / f"incoming-{n}"
        _write_corpus(src, n)
        ingest_dir(src, store)  # first ingest
        counter = CountingConn(store._conn)
        store._conn = counter
        report = ingest_dir(src, store)  # idempotent re-ingest
        assert report.ingested == n
        per_doc.append(counter.executes / n)
    assert per_doc[0] <= 20 and per_doc[1] <= 20
    assert per_doc[1] <= 1.3 * per_doc[0], per_doc
