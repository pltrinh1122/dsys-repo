"""W2 medallion tests (Arc B): silver derivation + ingest flow + review wiring.

All fixtures synthetic. Covers the coordinator's W2 acceptance items:

- stable artifact ids across runs (contract section 6);
- derivation cache hit -> no new rows (db_digest identical);
- ingest-twice -> identical db_digest;
- version bump -> silver rebuilt, validated values preserved,
  re_review set, orphaned decisions flagged (I6);
- E2 double-count probe: same bytes at two paths -> one bronze / two
  aliases / single gold count (-500.00);
- D2 e2e still passes (ingest -> validate unchanged -> carryforward);
- blind-orchestrator PII sweep extended to the W2 outputs.
"""

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from taxprep import extractors, ingest, silver
from taxprep.ingest import ingest_dir, ingest_file, source_doc_id, sync
from taxprep.review import apply_validation
from taxprep.store import DocumentStore

W2_TEXT = (
    "Form W-2 Wage and Tax Statement\n"
    "Tax Year 2024\n"
    "Box 1 Wages, tips, other compensation $10,000.00\n"
    "Box 2 Federal income tax withheld $1,500.00\n"
)

B1099_TEXT = (
    "Form 1099-B Proceeds From Broker Transactions Tax Year 2024\n"
    "Broker: EXAMPLE BROKERAGE\n"
    "Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 "
    "1g Wash sale loss disallowed $0.00 short term\n"
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def iso(tmp_path):
    src = tmp_path / "incoming"
    src.mkdir()
    return {"src": src, "store": DocumentStore(tmp_path / "data")}


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


# -- contract section 6: stable ids --------------------------------------------

def test_artifact_id_formula(iso):
    bronze = "ab" * 32
    doc = "doc1"
    aid = silver.artifact_id_for(doc, bronze, 3, "field", "box1")
    expect = hashlib.sha256(
        f"{doc}:{bronze}:3:field:box1".encode("utf-8")).hexdigest()[:32]
    assert aid == expect
    # ids differ across every axis
    assert silver.artifact_id_for(doc, bronze, 3, "field", "box1") != \
        silver.artifact_id_for(doc, bronze, 4, "field", "box1")
    assert silver.artifact_id_for(doc, bronze, 3, "field", "box1") != \
        silver.artifact_id_for(doc, bronze, 3, "lot", "box1")
    # ... and across docs sharing one bronze (R1 children, CSV rows)
    assert silver.artifact_id_for("doc1", bronze, 3, "field", "box1") != \
        silver.artifact_id_for("doc2", bronze, 3, "field", "box1")


def test_derive_artifacts_stable_and_complete(iso):
    src = _write(iso["src"] / "b1099.txt", B1099_TEXT)
    store = iso["store"]
    doc = ingest_file(src, store)[0]
    sha = hashlib.sha256(B1099_TEXT.encode()).hexdigest()
    ctx = silver.DerivationContext.current()

    arts1 = silver.derive_artifacts(
        doc, None, bronze_hash=sha,
        derivation_version=ctx.derivation_version,
        config_hash=ctx.config_hash)
    arts2 = silver.derive_artifacts(
        doc, None, bronze_hash=sha,
        derivation_version=ctx.derivation_version,
        config_hash=ctx.config_hash)
    assert arts1 == arts2  # byte-identical re-derivation (I5)

    by_key = {(a["artifact_type"], a["anchor"]): a for a in arts1}
    # field artifacts mirror every fields-dict key ...
    for key in ("broker", "lots", "summary_totals"):
        assert ("field", key) in by_key
    # ... one lot artifact per lot ...
    assert ("lot", "lot:0") in by_key
    # ... every id follows the contract formula ...
    for a in arts1:
        expect = hashlib.sha256(
            f"{a['doc_id']}:{a['bronze_hash']}:{a['page']}:"
            f"{a['artifact_type']}:"
            f"{a['anchor']}".encode("utf-8")).hexdigest()[:32]
        assert a["artifact_id"] == expect
    # ... and the stored rows match the pure derivation.
    stored = {(a["artifact_type"], a["anchor"]): a
              for a in store.get_artifacts(doc.doc_id)}
    assert set(stored) == set(by_key)
    for key in by_key:
        assert stored[key]["artifact_id"] == by_key[key]["artifact_id"]
        assert stored[key]["value_json"] == by_key[key]["value_json"]


def test_derive_artifacts_payer_and_section(iso):
    from taxprep.models import Document
    # payer blocks -> one payer artifact per payerN.* group, plus the
    # individual field artifacts.
    doc = Document(
        doc_id="d1", tax_year=2024, form_type="WAGE_INCOME_TRANSCRIPT",
        source_path="x.txt", ocr_text_ref="",
        fields={
            "payer1.name": {"value": "ACME", "confidence": "high",
                            "raw_text": ""},
            "payer1.box1": {"value": "100.00", "confidence": "high",
                            "raw_text": ""},
            "payer2.box1": {"value": "200.00", "confidence": "high",
                            "raw_text": ""},
        })
    arts = silver.derive_artifacts(
        doc, None, bronze_hash="bb" * 32, derivation_version="2",
        config_hash="cc" * 64)
    anchors = {(a["artifact_type"], a["anchor"]) for a in arts}
    assert ("payer", "payer1") in anchors
    assert ("payer", "payer2") in anchors
    assert ("field", "payer1.box1") in anchors
    payer1 = next(a for a in arts
                  if (a["artifact_type"], a["anchor"]) == ("payer", "payer1"))
    assert json.loads(payer1["value_json"])["box1"]["value"] == "100.00"
    # split children -> one section artifact.
    child = Document(
        doc_id="abc-p1-2-deadbeef", tax_year=2024, form_type="1099-INT",
        source_path="x.txt", ocr_text_ref="", fields={},
        page_range="1-2", parent_doc_id="abc")
    sarts = silver.derive_artifacts(
        child, None, bronze_hash="bb" * 32, derivation_version="2",
        config_hash="cc" * 64)
    sections = [a for a in sarts if a["artifact_type"] == "section"]
    assert len(sections) == 1
    assert sections[0]["anchor"] == "p1-2-deadbeef"
    assert sections[0]["page"] == 1  # best-known page
    # bookkeeping keys are never artifacts.
    doc.fields["__form_type__"] = {"value": "W-2", "history": []}
    barts = silver.derive_artifacts(
        doc, None, bronze_hash="bb" * 32, derivation_version="2",
        config_hash="cc" * 64)
    assert all(a["anchor"] != "__form_type__" for a in barts)


# -- I6 reconcile: Semantics B ---------------------------------------------------

def test_reconcile_semantics_b():
    old = {
        "keep": {"value": "10.00", "confidence": "high", "raw_text": ""},
        "chg": {"value": "20.00", "confidence": "high", "raw_text": ""},
        "gone": {"value": "30.00", "confidence": "high", "raw_text": ""},
        "unval": {"value": "40.00", "confidence": "low", "raw_text": ""},
        "__form_type__": {"value": "W-2", "history": []},
    }
    new = {
        "keep": {"value": "10.00", "confidence": "high", "raw_text": ""},
        "chg": {"value": "99.99", "confidence": "high", "raw_text": ""},
        "unval": {"value": "41.00", "confidence": "low", "raw_text": ""},
        "fresh": {"value": "50.00", "confidence": "high", "raw_text": ""},
    }
    r = silver.reconcile_rederivation(
        old_fields=old, new_fields=new,
        validated_keys={"keep", "chg", "gone"})
    # validated + agreeing -> old value kept, no flag
    assert r.fields["keep"]["value"] == "10.00"
    # validated + changed -> validated wins + re_review
    assert r.fields["chg"]["value"] == "20.00"
    assert r.re_review is True
    # validated + vanished -> dropped (Semantics B)
    assert "gone" not in r.fields
    # unvalidated -> new values win
    assert r.fields["unval"]["value"] == "41.00"
    assert r.fields["fresh"]["value"] == "50.00"
    # bookkeeping carried over untouched
    assert r.fields["__form_type__"]["value"] == "W-2"

    # all agreeing -> no re_review
    r2 = silver.reconcile_rederivation(
        old_fields={"a": {"value": "1.00"}}, new_fields={"a": {"value": "1"}},
        validated_keys={"a"})
    assert r2.re_review is False
    assert r2.fields["a"]["value"] == "1.00"  # old representation kept


# -- I2/I5: cache hit and ingest-twice -------------------------------------------

def test_derivation_cache_hit_writes_nothing(iso):
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    store = iso["store"]
    ingest_file(src, store)
    d1 = store.db_digest()
    c1 = store.table_counts()

    # re-ingest the same bytes: I2 no-op -- no new rows anywhere.
    docs = ingest_file(src, store)
    assert len(docs) == 1
    assert store.db_digest() == d1
    assert store.table_counts() == c1


def test_ingest_twice_identical_db(iso):
    _write(iso["src"] / "w2.txt", W2_TEXT)
    _write(iso["src"] / "b1099.txt", B1099_TEXT)
    store = iso["store"]
    ingest_dir(iso["src"], store)
    d1 = store.db_digest()
    ingest_dir(iso["src"], store)
    assert store.db_digest() == d1
    # same bytes under a new name: still one bronze, two aliases.
    _write(iso["src"] / "w2-copy.txt", W2_TEXT)
    ingest_dir(iso["src"], store)
    counts = store.table_counts()
    assert counts["bronze"] == 2
    sha = hashlib.sha256(W2_TEXT.encode()).hexdigest()
    assert sorted(store.get_bronze(sha)["aliases"]) == [
        str(iso["src"] / "w2-copy.txt"), str(iso["src"] / "w2.txt")]
    assert len(store) == 2  # one silver doc per bronze


# -- I6: version bump -------------------------------------------------------------

def test_version_bump_rebuilds_silver_preserves_decisions(
        iso, monkeypatch):
    src = _write(iso["src"] / "w2.txt", W2_TEXT)
    store = iso["store"]
    doc = ingest_file(src, store)[0]
    # operator validates: edits box "1", confirms box "2" unchanged.
    apply_validation(store, doc.doc_id, {"1": "12345.67"}, confirmed=["2"],
                     confirm_form_type=True, confirm_tax_year=True)
    assert store.get(doc.doc_id).status == "validated"

    # extractor bump: box "1" re-derives differently, box "2" vanishes.
    # (The bumped version is computed, not hardcoded: the tree's real
    # EXTRACTOR_VERSION moves with R15 and friends.)
    _bumped = str(int(extractors.EXTRACTOR_VERSION) + 1)

    def _v3(form_type, text, year, text_source=None, pdf_path=None):
        return ({"1": {"value": "99999.99", "confidence": "high",
                       "raw_text": ""}}, "transcribed")

    monkeypatch.setattr(ingest, "_extract_for_type", _v3)
    monkeypatch.setattr(extractors, "EXTRACTOR_VERSION", _bumped)
    again = ingest_file(src, store)[0]

    # validated values win; vanished validated fields drop; re_review set.
    # R13: the disagreeing re-derivation moves validated -> rereview.
    assert again.status == "rereview"
    assert again.fields["1"]["value"] == "12345.67"
    assert "2" not in again.fields
    assert again.re_review is True
    assert again.status_reason == "extraction-disagrees"
    # silver rebuilt at the new derivation (for the doc's current fields;
    # rows for vanished anchors may linger until W1 implements full
    # replace in replace_artifacts -- flagged).
    arts = store.get_artifacts(doc.doc_id)
    assert arts
    current = silver.field_artifact_anchors(again.fields)
    cur_versions = {a["derivation_version"] for a in arts
                    if (a["artifact_type"], a["anchor"]) in current}
    assert cur_versions == {_bumped}
    # ...and the vanished field's validate decision is flagged orphaned
    # (append-only: the original row is untouched).
    validates = store.decisions_for(doc_id=doc.doc_id, kind="validate")
    assert len(validates) == 2  # the operator's + the orphan flag
    orphans = [d for d in validates if d["payload"].get("orphaned")]
    assert len(orphans) == 1
    assert orphans[0]["actor"] == "system"
    assert orphans[0]["payload"]["validated_fields"] == ["2"]
    # the surviving field's decisions are NOT orphaned.
    edits = store.decisions_for(doc_id=doc.doc_id, kind="edit")
    assert edits and not any(
        d["payload"].get("orphaned") for d in edits)
    # a further ingest converges: cache hit, no new rows, no duplicate
    # orphan flags.
    d_before = store.db_digest()
    n_flags = lambda: len(
        [d for d in store.decisions_for(doc_id=doc.doc_id)
         if d["payload"].get("orphaned")])
    assert n_flags() == 1
    ingest_file(src, store)
    assert store.db_digest() == d_before
    assert n_flags() == 1


# -- E2: same bytes, two paths -> single count -------------------------------------

def test_e2_two_paths_same_bytes_single_gold_count(iso):
    from taxprep.carryforward import from_store

    (iso["src"] / "feb").mkdir()
    (iso["src"] / "mar").mkdir()
    _write(iso["src"] / "feb" / "stmt.txt", B1099_TEXT)
    _write(iso["src"] / "mar" / "stmt.txt", B1099_TEXT)  # identical bytes
    store = iso["store"]
    rep = ingest_dir(iso["src"], store)

    sha = hashlib.sha256(B1099_TEXT.encode()).hexdigest()
    assert store.table_counts()["bronze"] == 1
    assert len(store.get_bronze(sha)["aliases"]) == 2
    assert len(store) == 1  # one silver doc: review shows it once

    doc = store.list()[0]
    boxes = [c for c in doc.fields if not c.startswith("__")]
    apply_validation(store, doc.doc_id, {}, confirmed=boxes,
                     confirm_form_type=True, confirm_tax_year=True)
    assert store.get(doc.doc_id).status == "validated"
    assert rep.files_seen == 2 and rep.ingested == 2

    r = from_store(store, 2024)
    assert r["st_current"] == Decimal("-500.00")  # not -1000.00
    assert r["lots_included"] == 1


# -- D2 e2e still passes ------------------------------------------------------------

def test_d2_e2e_ingest_validate_carryforward_no_retyping(iso):
    """D2: ingest -> validate UNCHANGED -> carryforward (no retyping)."""
    from taxprep.carryforward import from_store

    src = _write(iso["src"] / "b1099.txt", B1099_TEXT)
    store = iso["store"]
    doc = ingest_file(src, store)[0]
    assert doc.form_type == "1099-B" and doc.tax_year == 2024
    boxes = [c for c in doc.fields if not c.startswith("__")]
    apply_validation(store, doc.doc_id, {}, confirmed=boxes,
                     confirm_form_type=True, confirm_tax_year=True)
    assert store.get(doc.doc_id).status == "validated"
    r = from_store(store, 2024)
    assert r["st_current"] == Decimal("-500.00")
    assert r["lots_included"] == 1


# -- review wiring: decision log + artifact mirror ----------------------------------

def test_validate_logs_decision_and_syncs_artifacts(iso):
    src = _write(iso["src"] / "b1099.txt", B1099_TEXT)
    store = iso["store"]
    doc = ingest_file(src, store)[0]
    before = {(a["artifact_type"], a["anchor"]): a["value_json"]
              for a in store.get_artifacts(doc.doc_id)}

    apply_validation(store, doc.doc_id, {"broker": "EDITED BROKER"},
                     confirmed=["lots"],
                     confirm_form_type=True, confirm_tax_year=True)

    # kind=validate logged with the contract payload shape ...
    validates = store.decisions_for(doc_id=doc.doc_id, kind="validate")
    assert len(validates) == 1
    assert validates[0]["actor"] == "operator"
    assert validates[0]["payload"]["validated_fields"] == ["broker", "lots"]
    # ... kind=edit logged per correction ...
    edits = store.decisions_for(doc_id=doc.doc_id, kind="edit")
    assert len(edits) == 1
    assert edits[0]["payload"]["field"] == "broker"
    assert edits[0]["payload"]["old"] != "EDITED BROKER"
    assert edits[0]["payload"]["new"] == "EDITED BROKER"
    assert edits[0]["artifact_id"] is not None
    # ... and the field artifact mirrors the edited fields_json.
    after = {(a["artifact_type"], a["anchor"]): a
             for a in store.get_artifacts(doc.doc_id)}
    assert set(after) == set(before)  # no artifacts added/dropped
    new_vj = after[("field", "broker")]["value_json"]
    assert new_vj != before[("field", "broker")]
    assert json.loads(new_vj)["value"] == "EDITED BROKER"
    assert json.loads(new_vj)["history"][0]["new"] == "EDITED BROKER"
    # lot artifacts untouched by a broker edit.
    assert after[("lot", "lot:0")]["value_json"] == before[("lot", "lot:0")]
    # derivation stamp preserved (not reset to the facade "1").
    assert {a["derivation_version"] for a in
            store.get_artifacts(doc.doc_id)} == \
        {extractors.EXTRACTOR_VERSION}


# -- blind contract: PII sweep over the W2 outputs ------------------------------------

def test_pii_sweep_w2_outputs(iso):
    _write(iso["src"] / "b1099.txt", B1099_TEXT)
    store = iso["store"]
    rep = ingest_dir(iso["src"], store)
    doc = store.list()[0]
    boxes = [c for c in doc.fields if not c.startswith("__")]
    apply_validation(store, doc.doc_id, {}, confirmed=boxes,
                     confirm_form_type=True, confirm_tax_year=True)
    sha = hashlib.sha256(B1099_TEXT.encode()).hexdigest()

    _pii_free(store.db_digest())
    _pii_free(store.table_counts())
    _pii_free(store.get_bronze(sha))
    _pii_free(store.decisions_for())
    _pii_free(rep.summary())
    _pii_free(sync(iso["src"], store))
    _pii_free(silver.derivation_config())
    # digests/counts carry no values at all: artifact values (local-only)
    # must not leak into the digest/count blobs.
    blob = json.dumps(store.db_digest()) + json.dumps(store.table_counts())
    assert "EXAMPLE BROKERAGE" not in blob
    assert "1000.00" not in blob
