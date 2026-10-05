"""B2: batched writes -- replace_artifacts executemany + bronze_text batch.

No wall-clock assertions anywhere: every performance claim is stated as
SQL execute counts via a counting connection wrapper. All fixtures are
synthetic. Byte-identical artifact rows are asserted as JSON/content
equality, not counts alone.

Load-bearing: blind-orchestrator contract, deterministic, local-only.
No extraction-semantics, gate, or schema changes here -- executemany only.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from taxprep import ingest, silver
from taxprep.models import Document
from taxprep.store import DocumentStore


# -- counting connection ----------------------------------------------------


class _CountingConn:
    """Proxy over a sqlite3.Connection counting execute calls.

    ``execute`` and ``executemany`` each count as one call; ``kinds``
    records per-statement-kind counts (INSERT via execute vs via
    executemany are distinguished by the ``executemany`` counter).
    """

    _OWN = frozenset({"execute_calls", "executemany_calls", "kinds"})

    def __init__(self, real):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "execute_calls", 0)
        object.__setattr__(self, "executemany_calls", 0)
        object.__setattr__(self, "kinds", {})

    def _bump(self, sql):
        kinds = object.__getattribute__(self, "kinds")
        head = sql.split("(")[0].strip().upper().split()
        key = head[0] if head else "?"
        kinds[key] = kinds.get(key, 0) + 1

    def execute(self, sql, *args, **kw):
        self.execute_calls += 1
        self._bump(sql)
        return self._real.execute(sql, *args, **kw)

    def executemany(self, sql, seq, *args, **kw):
        self.executemany_calls += 1
        self._bump(sql)
        return self._real.executemany(sql, seq, *args, **kw)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        if name in self._OWN or name == "_real":
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_real"), name, value)

    def reset(self):
        object.__setattr__(self, "execute_calls", 0)
        object.__setattr__(self, "executemany_calls", 0)
        object.__getattribute__(self, "kinds").clear()


@pytest.fixture()
def counted(tmp_path):
    """DocumentStore whose connection counts every SQL call."""
    store = DocumentStore(tmp_path / "data")
    counting = _CountingConn(store._conn)
    store._conn = counting
    try:
        yield store, counting
    finally:
        store._conn = counting._real


# -- helpers -----------------------------------------------------------------


def _tfield(value, confidence="high", raw_text="", span=None):
    f = {"value": value, "confidence": confidence, "raw_text": raw_text}
    if span is not None:
        f["char_span"] = span
    return f


def _doc(doc_id, year, form, fields=None, status="transcribed"):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form,
        source_path=f"/tmp/{doc_id}.txt",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields or {},
        status=status,
    )


def _artifacts(n, doc_id="d-2025", prefix="field"):
    """N synthetic artifact dicts in replace_artifacts input shape."""
    return [
        {
            "artifact_id": f"{doc_id}#{prefix}:{i}",
            "page": (i % 7) + 1,
            "artifact_type": "field",
            "anchor": f"{prefix}:{i}",
            "value_json": json.dumps({"value": f"v{i}",
                                      "note": "ünïcode ✓"}) ,
            "offsets_json": json.dumps({"page": (i % 7) + 1}) if i % 3 else None,
            "derivation_version": "dv-test",
            "config_hash": "cfg-test",
        }
        for i in range(n)
    ]


def _row_by_id(store, doc_id):
    return {a["artifact_id"]: a for a in store.get_artifacts(doc_id)}


def _bronze_hash_of(store, doc_id):
    return store._conn.execute(
        "SELECT bronze_hash FROM silver_doc WHERE doc_id = ?",
        (doc_id,)).fetchone()["bronze_hash"]


def _register_bronze(store, sha):
    store.register_bronze(sha, 0)


# -- replace_artifacts batching ----------------------------------------------


def test_replace_artifacts_n_artifacts_is_o1_executes(counted):
    # O(1) executes for N artifacts: 1 SELECT (bronze hash) + 1 SELECT
    # (carried owners) + 1 DELETE + 1 executemany, inside one txn.
    store, counting = counted
    store.upsert(_doc("d-2025", 2025, "W-2",
                      {"box1": _tfield("10.00")}))
    arts = _artifacts(200)
    counting.reset()
    store.replace_artifacts("d-2025", arts)
    assert counting.kinds.get("SELECT") == 2
    assert counting.kinds.get("DELETE") == 1
    assert counting.executemany_calls == 1
    assert counting.kinds.get("INSERT") == 1  # the single executemany
    assert counting.kinds.get("BEGIN") == 1
    assert counting.kinds.get("COMMIT") == 1
    rows = store.get_artifacts("d-2025")
    assert len(rows) == 200


def test_replace_artifacts_rows_byte_identical(counted):
    # Same rows the old per-row loop wrote: every column mirrors the
    # input dict exactly; created_at == updated_at == one timestamp.
    store, _ = counted
    store.upsert(_doc("d-2025", 2025, "W-2",
                      {"box1": _tfield("10.00")}))
    arts = _artifacts(50)
    store.replace_artifacts("d-2025", arts)
    bronze_hash = _bronze_hash_of(store, "d-2025")
    got = _row_by_id(store, "d-2025")
    assert set(got) == {a["artifact_id"] for a in arts}
    stamps = set()
    for a in arts:
        row = got[a["artifact_id"]]
        assert row["doc_id"] == "d-2025"
        assert row["bronze_hash"] == bronze_hash
        assert row["page"] == a["page"]
        assert row["artifact_type"] == a["artifact_type"]
        assert row["anchor"] == a["anchor"]
        assert row["value_json"] == a["value_json"]
        assert row["offsets_json"] == a["offsets_json"]
        assert row["derivation_version"] == a["derivation_version"]
        assert row["config_hash"] == a["config_hash"]
        assert row["owner_person_id"] is None
        assert row["owner_suggestion"] is None
        assert row["created_at"] == row["updated_at"]
        stamps.add(row["created_at"])
    assert len(stamps) == 1  # one `now` for the whole batch


def test_replace_artifacts_empty_is_delete_only(counted):
    # Empty artifact list: DELETE runs, executemany runs with zero rows
    # (no per-row INSERT), no error.
    store, counting = counted
    store.upsert(_doc("d-2025", 2025, "W-2",
                      {"box1": _tfield("10.00")}))
    store.replace_artifacts("d-2025", _artifacts(5))
    assert len(store.get_artifacts("d-2025")) == 5
    counting.reset()
    store.replace_artifacts("d-2025", [])
    assert counting.kinds.get("DELETE") == 1
    assert counting.executemany_calls == 1
    assert len(store.get_artifacts("d-2025")) == 0


def test_replace_artifacts_r21a_owner_carry_preserved(counted):
    # Carried dict lookup per artifact_id + explicit wins -- the R21a
    # semantics the old loop implemented, now under executemany.
    store, _ = counted
    store.upsert(_doc("d-2025", 2025, "W-2",
                      {"box1": _tfield("10.00"),
                       "box2": _tfield("20.00")}))
    arts = _artifacts(3)
    store.replace_artifacts("d-2025", arts)
    aid0 = arts[0]["artifact_id"]
    aid1 = arts[1]["artifact_id"]
    store.set_artifact_owner(aid0, owner_person_id="person-7",
                             owner_suggestion="sys")
    # Re-derive: surviving ids keep the carried owner ...
    store.replace_artifacts("d-2025", _artifacts(3))
    got = _row_by_id(store, "d-2025")
    assert got[aid0]["owner_person_id"] == "person-7"
    assert got[aid0]["owner_suggestion"] == "sys"
    assert got[aid1]["owner_person_id"] is None
    # ... unless the incoming dict carries one explicitly (explicit wins).
    explicit = _artifacts(3)
    explicit[1]["owner_person_id"] = "person-9"
    explicit[1]["owner_suggestion"] = "op"
    store.replace_artifacts("d-2025", explicit)
    got = _row_by_id(store, "d-2025")
    assert got[aid1]["owner_person_id"] == "person-9"
    assert got[aid1]["owner_suggestion"] == "op"
    # Vanished ids leave no stale rows.
    store.replace_artifacts("d-2025", [explicit[0]])
    got = _row_by_id(store, "d-2025")
    assert set(got) == {explicit[0]["artifact_id"]}
    assert got[explicit[0]["artifact_id"]]["owner_person_id"] == "person-7"


def test_replace_artifacts_unknown_doc_raises(counted):
    store, _ = counted
    with pytest.raises(KeyError):
        store.replace_artifacts("no-such-doc", _artifacts(2))


# -- write_bronze_texts batching ----------------------------------------------


def _pages(n):
    return [f"page {i} text" for i in range(1, n + 1)]


def test_write_bronze_texts_batch_is_o1_executes(counted):
    # 105 pages: 1 txn + 1 executemany, not 105 txns + 105 INSERTs.
    store, counting = counted
    sha = "ab" * 32
    _register_bronze(store, sha)
    counting.reset()
    store.write_bronze_texts(sha, [
        {"page": i, "text_source": "native", "engine": None,
         "engine_version": None, "ocr_mode": None,
         "derivation_version": "dv", "config_hash": "cfg",
         "text": t}
        for i, t in enumerate(_pages(105), start=1)
    ])
    assert counting.kinds.get("BEGIN") == 1
    assert counting.executemany_calls == 1
    assert counting.kinds.get("INSERT") == 1  # the single executemany
    assert counting.kinds.get("COMMIT") == 1
    rows = store.read_bronze_text(sha, derivation_version="dv",
                                  config_hash="cfg")
    assert len(rows) == 105
    assert [r["page"] for r in rows] == list(range(1, 106))
    assert rows[0]["text"] == "page 1 text"
    assert rows[-1]["text"] == "page 105 text"
    assert all(r["text_source"] == "native" for r in rows)


def test_write_bronze_text_single_matches_batch(counted):
    # The single-row wrapper is byte-identical to the batch call.
    store, _ = counted
    _register_bronze(store, "aa" * 32)
    _register_bronze(store, "bb" * 32)
    store.write_bronze_text("aa" * 32, 3, text_source="ocr",
                            engine="tess", engine_version="5",
                            ocr_mode="force", derivation_version="dv",
                            config_hash="cfg", text="hello")
    store.write_bronze_texts("bb" * 32, [
        {"page": 3, "text_source": "ocr", "engine": "tess",
         "engine_version": "5", "ocr_mode": "force",
         "derivation_version": "dv", "config_hash": "cfg",
         "text": "hello"}
    ])
    a = store.read_bronze_text("aa" * 32, derivation_version="dv",
                               config_hash="cfg")
    b = store.read_bronze_text("bb" * 32, derivation_version="dv",
                               config_hash="cfg")
    assert len(a) == len(b) == 1
    assert a[0] == b[0]


def test_write_bronze_texts_upsert_on_conflict(counted):
    # Same derivation re-written is an update, not a duplicate; a
    # version bump adds rows (I5 cache-key semantics unchanged).
    store, _ = counted
    sha = "cc" * 32
    _register_bronze(store, sha)
    rows = [{"page": i, "text_source": "native", "engine": None,
             "engine_version": None, "ocr_mode": None,
             "derivation_version": "dv", "config_hash": "cfg",
             "text": f"v1 page {i}"} for i in (1, 2)]
    store.write_bronze_texts(sha, rows)
    rows[0]["text"] = "v2 page 1"
    store.write_bronze_texts(sha, rows)
    got = store.read_bronze_text(sha, derivation_version="dv",
                                 config_hash="cfg")
    assert len(got) == 2
    assert got[0]["text"] == "v2 page 1"
    store.write_bronze_texts(
        sha, [{**rows[0], "derivation_version": "dv2"}])
    assert len(store.read_bronze_text(sha, derivation_version="dv",
                                      config_hash="cfg")) == 2
    assert len(store.read_bronze_text(sha, derivation_version="dv2",
                                      config_hash="cfg")) == 1


def test_write_bronze_texts_empty_is_noop(counted):
    store, counting = counted
    _register_bronze(store, "dd" * 32)
    counting.reset()
    store.write_bronze_texts("dd" * 32, [])
    assert counting.executemany_calls == 1
    assert counting.kinds.get("INSERT") == 1  # zero-row executemany


# -- end-to-end: 105-page synthetic W&I transcript -----------------------------


_BOILERPLATE = (
    "IRS TRANSCRIPT SERVICE\n"
    "Taxpayer Identification Number: XXX-XX-1234\n"
)


def _filler_page(n):
    return (f"Page {n} continuation\n"
            f"Account activity detail line {n}.\n"
            "Form 1099-B\n"
            "Proceeds: $1.00\n"
            "Schedule D\n"
            f"Detail row {n}.\n")


def _long_wi_pages(pages_total=105):
    pages = []
    for i in range(pages_total):
        if i == 0:
            pages.append(_BOILERPLATE +
                         "Wage and Income Transcript For TY2025\n"
                         "Tax Year: 2025\nAdjusted Gross Income: $85,420.00\n")
        else:
            pages.append(_filler_page(i + 1))
    return pages


def _ingest_pages(store, pages, name="long.txt"):
    bundle = ingest.PageBundle(pages=pages, route="native",
                               text_source="native")
    text = "\n".join(pages)
    source_bytes = text.encode("utf-8")
    sha = hashlib.sha256(source_bytes).hexdigest()
    ingest._register_bronze(store, sha, source_bytes, name, encryption=None)
    return ingest._build_documents(name, ingest.source_doc_id(source_bytes),
                                   bundle, sha, store)


def test_105_page_wi_ingest_execute_budget_and_artifact_equality(counted):
    # Acceptance: the 105-page synthetic W&I ingest performs O(docs),
    # not O(pages * fields), SQL calls -- budget well under the
    # pre-B2 ~556 calls -- and the artifact rows exactly mirror what
    # silver.derive_artifacts produces (byte-identical JSON).
    store, counting = counted
    counting.reset()
    docs = _ingest_pages(store, _long_wi_pages())
    total = counting.execute_calls + counting.executemany_calls
    assert len(docs) == 1
    doc = docs[0]
    assert doc.form_type == "WAGE_INCOME_TRANSCRIPT"
    # Pre-B2 this ingest cost 556 execute calls; the batched writes are
    # O(1) per homogeneous set, so the whole doc lands in a small
    # constant budget (generous bound, not a timing claim).
    assert total < 60, f"ingest cost {total} SQL calls"
    # Per-page bronze rows: all 105 present from the single batch.
    ctx = silver.DerivationContext.current()
    rows = store.read_bronze_text(
        doc.source_sha256, derivation_version=ctx.derivation_version,
        config_hash=ctx.config_hash)
    assert len(rows) == 105
    # Artifact equality vs the derivation output itself.
    bundle = ingest.PageBundle(pages=_long_wi_pages(), route="native",
                               text_source="native")
    expected = silver.derive_artifacts(
        doc, bundle, bronze_hash=doc.source_sha256,
        derivation_version=ctx.derivation_version,
        config_hash=ctx.config_hash)
    got = {a["artifact_id"]: a for a in store.get_artifacts(doc.doc_id)}
    assert len(got) >= len(expected) > 0
    for e in expected:
        row = got.get(e["artifact_id"])
        assert row is not None, e["artifact_id"]
        assert row["value_json"] == e["value_json"]
        assert row["offsets_json"] == e["offsets_json"]
        assert row["anchor"] == e["anchor"]
        assert row["page"] == e["page"]


def test_105_page_wi_artifacts_stable_across_reingest(counted):
    # Deterministic replay: re-deriving the same transcript yields
    # byte-identical artifact rows (value/offsets JSON equal).
    store, _ = counted
    docs = _ingest_pages(store, _long_wi_pages())
    before = {a["artifact_id"]: (a["value_json"], a["offsets_json"])
              for a in store.get_artifacts(docs[0].doc_id)}
    docs = _ingest_pages(store, _long_wi_pages())
    after = {a["artifact_id"]: (a["value_json"], a["offsets_json"])
             for a in store.get_artifacts(docs[0].doc_id)}
    assert before == after
