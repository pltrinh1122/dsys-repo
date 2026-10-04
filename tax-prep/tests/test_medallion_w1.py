"""W1 medallion storage tests -- all fixtures synthetic.

Covers: JSONL migration (row counts, fields round-trip, tombstones,
validate decisions), bronze register/alias idempotency, the append-only
decision log (no UPDATE/DELETE pathway; seq monotonic), txn atomicity,
db_digest stability across identical writes, and the blind-orchestrator
PII sweep extended to the new W1 outputs (digests/counts only, never
values).
"""

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from taxprep.models import Document
from taxprep.mstore import MedallionStore


def _field(value, confidence="high"):
    return {"value": value, "confidence": confidence, "raw_text": ""}


def _doc(doc_id, **kw):
    args = dict(
        doc_id=doc_id,
        tax_year=2024,
        form_type="1099-B",
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields={},
        status="transcribed",
    )
    args.update(kw)
    return Document(**args)


def _pii_free(obj):
    """Recursive blind-orchestrator assertion (mirrors test_mcp_server)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key leaked: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        assert not re.search(r"\$\d", obj), f"money leaked: {obj[:60]!r}"


# -- migration ----------------------------------------------------------------

def _write_jsonl(data_dir: Path, docs: list[Document]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "documents.jsonl").open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d.to_dict()) + "\n")


def _lot(i):
    return {
        "description": None,
        "date_acquired": "01/15/2024",
        "date_sold": "06/20/2024",
        "proceeds_1d": f"{1000 + i}",
        "basis_1e": f"{900 + i}",
        "term": "short",
    }


def test_migration_from_jsonl(tmp_path):
    data = tmp_path / "data"
    src_file = tmp_path / "doc-b.pdf"
    src_bytes = b"synthetic pdf bytes for doc-b"
    src_file.write_bytes(src_bytes)
    src_sha = hashlib.sha256(src_bytes).hexdigest()

    doc_a = _doc(
        "doc-a", status="validated", validated_at="2026-10-03T00:00:00+00:00",
        fields={
            "broker": _field("Synthetic Broker"),
            "lots": _field([_lot(1), _lot(2)]),
        },
        text_source="native",
        ocr_engine="synthetic-engine",
        engine_version="0.1",
        attempts=[{"mode": "native", "ok": True}],
    )
    doc_b = _doc("doc-b", source_path=str(src_file), source_sha256=src_sha)
    doc_c = _doc("doc-c", status="needs_review")
    _write_jsonl(data, [doc_a, doc_b, doc_c])

    store = MedallionStore(data)
    assert (data / "medallion.sqlite").exists()
    # JSONL left in place as a backup, never written again
    assert (data / "documents.jsonl").exists()

    counts = store.table_counts()
    assert counts["bronze"] == 3
    assert counts["bronze_alias"] == 3
    assert counts["bronze_bytes_ref"] == 1  # only doc-b's file existed
    assert counts["silver_doc"] == 3
    # doc-a: 2 field artifacts + 2 lot artifacts; doc-b/c: none
    assert counts["silver_artifact"] == 4
    # one synthesized validate decision (doc-a)
    assert counts["decision_log"] == 1
    # provenance rows for all three docs
    assert counts["doc_provenance"] == 3

    # bronze identity: doc-b keyed by source bytes; tombstones for a/c
    bronze_b = store.get_bronze(src_sha)
    assert bronze_b is not None
    assert bronze_b["aliases"] == [str(src_file)]
    bronze_a = store.get_bronze("legacy-doc-a")
    assert bronze_a["blocked_reason"] == "legacy-no-source"
    assert store.get_bronze("legacy-doc-c")["blocked_reason"] == \
        "legacy-no-source"

    # fields round-trip identically
    assert store.get("doc-a").fields == doc_a.fields
    assert store.get("doc-b").fields == {}
    assert store.get("doc-a").status == "validated"
    assert store.get("doc-a").validated_at == "2026-10-03T00:00:00+00:00"
    assert store.get("doc-c").status == "needs_review"

    # tombstone docs come back with source_sha256=None (as authored)
    assert store.get("doc-a").source_sha256 is None
    assert store.get("doc-b").source_sha256 == src_sha

    # R5 provenance round-trips through the facade
    got_a = store.get("doc-a")
    assert got_a.text_source == "native"
    assert got_a.ocr_engine == "synthetic-engine"
    assert got_a.engine_version == "0.1"
    assert got_a.attempts == [{"mode": "native", "ok": True}]

    # synthesized validate decision
    decisions = store.decisions_for(doc_id="doc-a", kind="validate")
    assert len(decisions) == 1
    assert decisions[0]["actor"] == "operator"
    assert decisions[0]["payload"]["validated_fields"] == ["broker", "lots"]

    # reopening does not re-migrate
    store2 = MedallionStore(data)
    assert store2.table_counts() == counts

    # lot artifacts mirror fields["lots"]
    lots = store.get_artifacts("doc-a", artifact_type="lot")
    assert sorted(a["anchor"] for a in lots) == ["lot:0", "lot:1"]
    assert json.loads(lots[0]["value_json"])["term"] == "short"
    fields = store.get_artifacts("doc-a", artifact_type="field")
    assert sorted(a["anchor"] for a in fields) == ["broker", "lots"]
    # artifact ids are stable per contract §6 (as amended: doc_id joins
    # the hash so one bronze's many docs never collide)
    for a in lots + fields:
        expect = hashlib.sha256(
            f"doc-a:{a['bronze_hash']}:{a['page']}:{a['artifact_type']}:"
            f"{a['anchor']}".encode()
        ).hexdigest()[:32]
        assert a["artifact_id"] == expect


def test_no_migration_without_jsonl(tmp_path):
    data = tmp_path / "data"
    store = MedallionStore(data)
    assert store.table_counts()["silver_doc"] == 0
    assert not (data / "documents.jsonl").exists()


# -- bronze idempotency ----------------------------------------------------------

def test_bronze_register_and_alias_idempotent(tmp_path):
    data = tmp_path / "data"
    store = MedallionStore(data)
    sha = "ab" * 32
    assert store.register_bronze(sha, 100, encryption="owner-only") is True
    assert store.register_bronze(sha, 100) is False  # I2: no-op for state
    bronze = store.get_bronze(sha)
    assert bronze["size"] == 100
    assert bronze["encryption"] == "owner-only"  # not clobbered by re-ingest

    store.add_alias(sha, "incoming/a.pdf")
    store.add_alias(sha, "incoming/a.pdf")  # same path: idempotent
    store.add_alias(sha, "archive/a.pdf")   # second path: second alias
    assert store.get_bronze(sha)["aliases"] == [
        "archive/a.pdf", "incoming/a.pdf"]
    assert store.table_counts()["bronze"] == 1
    assert store.table_counts()["bronze_alias"] == 2
    assert store.get_bronze("ff" * 32) is None


# -- decision log: append-only ----------------------------------------------------

def test_decision_log_append_only(tmp_path):
    data = tmp_path / "data"
    store = MedallionStore(data)
    s1 = store.log_decision(actor="operator", kind="validate", doc_id="d1",
                            payload={"doc_id": "d1",
                                     "validated_fields": ["box1"],
                                     "ts": "2026-10-03T00:00:00+00:00"})
    s2 = store.log_decision(actor="operator", kind="edit", doc_id="d1",
                            payload={"field": "box1", "old": "1",
                                     "new": "2",
                                     "ts": "2026-10-03T00:00:01+00:00"})
    s3 = store.log_decision(actor="system", kind="duplicate_ruling",
                            group_id="g1",
                            payload={"group_id": "g1", "ruling": "distinct"})
    assert (s1, s2, s3) == (1, 2, 3)  # seq monotonic

    # no UPDATE/DELETE pathway on the API
    for name in ("update_decision", "delete_decision", "remove_decision",
                 "amend_decision"):
        assert not hasattr(store, name), name

    # the database itself refuses UPDATE/DELETE (triggers; surfaces as
    # sqlite3.IntegrityError via RAISE(ABORT, ...))
    raw = sqlite3.connect(str(data / "medallion.sqlite"))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            raw.execute("UPDATE decision_log SET kind='edit' WHERE seq=1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            raw.execute("DELETE FROM decision_log WHERE seq=1")
    finally:
        raw.close()

    # closed vocabulary refused loudly
    with pytest.raises(ValueError, match="unknown decision kind"):
        store.log_decision(actor="operator", kind="bogus", payload={})

    # filters
    assert [d["seq"] for d in store.decisions_for(doc_id="d1")] == [1, 2]
    assert [d["seq"] for d in store.decisions_for(kind="validate")] == [1]
    assert [d["seq"] for d in store.decisions_for()] == [1, 2, 3]
    assert store.decisions_for(kind="nope") == []


# -- txn atomicity ------------------------------------------------------------------

def test_txn_exception_leaves_zero_rows(tmp_path):
    data = tmp_path / "data"
    store = MedallionStore(data)
    with pytest.raises(RuntimeError, match="boom"):
        with store.txn():
            store.register_bronze("cc" * 32, 5)
            store.add_alias("cc" * 32, "x.pdf")
            raise RuntimeError("boom")
    assert store.table_counts()["bronze"] == 0
    assert store.table_counts()["bronze_alias"] == 0


# -- digest stability ---------------------------------------------------------------

def _identical_ops(store: MedallionStore) -> None:
    sha = "11" * 32
    store.register_bronze(sha, 100)
    store.add_alias(sha, "a.pdf")
    store.add_alias(sha, "b.pdf")
    doc = _doc("d1", source_sha256=sha,
               fields={"broker": _field("Synthetic Broker")})
    store.upsert_silver_doc(doc, derivation_version="1",
                            config_hash="c" * 64,
                            derivation_digest="d" * 64)
    store.log_decision(actor="operator", kind="validate", doc_id="d1",
                       payload={"doc_id": "d1", "validated_fields": ["broker"],
                                "ts": "2026-10-03T00:00:00+00:00"})


def test_db_digest_stable_across_identical_writes(tmp_path):
    store1 = MedallionStore(tmp_path / "one")
    store2 = MedallionStore(tmp_path / "two")
    _identical_ops(store1)
    _identical_ops(store2)
    d1, d2 = store1.db_digest(), store2.db_digest()
    assert d1 == d2
    assert d1["counts"]["bronze"] == 1
    assert d1["counts"]["bronze_alias"] == 2

    # a further write changes the digest (same tables, new content)
    store1.log_decision(actor="operator", kind="edit", doc_id="d1",
                        payload={"field": "broker", "old": "x", "new": "y",
                                 "ts": "2026-10-03T00:00:01+00:00"})
    assert store1.db_digest() != d2
    # ...but the untouched tables keep identical digests
    assert store1.db_digest()["tables"]["bronze"] == \
        d2["tables"]["bronze"]


# -- blind contract: digests/counts only, never values -------------------------------

def test_pii_sweep_new_w1_outputs(tmp_path):
    data = tmp_path / "data"
    store = MedallionStore(data)
    _identical_ops(store)
    sha = "11" * 32

    _pii_free(store.db_digest())
    _pii_free(store.table_counts())
    _pii_free(store.get_bronze(sha))
    _pii_free(store.decisions_for())
    # digests/counts carry no values at all: the serialized digest must
    # not contain any field value (values live in silver artifacts,
    # which are local-only and are NOT part of digest/count outputs)
    blob = json.dumps(store.db_digest()) + json.dumps(store.table_counts())
    assert "Synthetic Broker" not in blob
