"""MCP server tests -- all fixtures synthetic, stdio transport only."""

import asyncio
import json
from decimal import Decimal

import pytest

from taxprep import mcp_server
from taxprep.mcp_server import mcp
from taxprep.models import Document
from taxprep.store import DocumentStore

D = Decimal
EXPECTED_TOOLS = {
    "ingest_directory",
    "list_documents",
    "show_document",
    "validation_queue",
    "compute_carryforward",
    "validate_document",
}


def _field(value, confidence="high", raw=""):
    return {"value": value, "confidence": confidence, "raw_text": raw}


def _doc(doc_id, year, form, fields, status="transcribed"):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form,
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields,
        status=status,
    )


def _b1099(doc_id, year, proceeds, basis, term, status="validated"):
    return _doc(
        doc_id, year, "1099-B",
        {
            "1d_proceeds": _field(proceeds),
            "1e_basis": _field(basis),
            "term": _field(term),
            "broker": _field("Synthetic Broker"),
        },
        status=status,
    )


def _store_with(tmp_path, docs):
    store = DocumentStore(tmp_path / "data")
    for d in docs:
        store.upsert(d)
    return store


def test_all_six_tools_registered():
    async def names():
        return {t.name for t in await mcp.list_tools()}

    assert asyncio.run(names()) == EXPECTED_TOOLS


def test_list_documents_shape_and_json(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2", {"box1_wages": _field("85000")}, "validated"),
        _doc("b1-a", 2024, "1099-B", {"term": _field("short")}, "transcribed"),
    ])
    rows = mcp_server.list_documents(tax_year=2024,
                                     data_dir=str(store.data_dir))
    assert len(rows) == 2
    assert rows[0]["doc_id"] == "b1-a"  # sorted by form then id
    for r in rows:
        assert set(r) == {"doc_id", "tax_year", "form_type", "status",
                          "n_fields"}
    json.dumps(rows)  # Decimal-free
    only_w2 = mcp_server.list_documents(form_type="W-2",
                                        data_dir=str(store.data_dir))
    assert [r["doc_id"] for r in only_w2] == ["w2-a"]


def test_show_document_shape_and_json(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2", {"box1_wages": _field("85000", "high",
                                                        "Box 1 $85,000")},
             "validated"),
    ])
    rec = mcp_server.show_document("w2-a", data_dir=str(store.data_dir))
    assert rec["doc_id"] == "w2-a"
    assert rec["fields"]["box1_wages"]["confidence"] == "high"
    assert rec["fields"]["box1_wages"]["raw_text"] == "Box 1 $85,000"
    json.dumps(rec)
    with pytest.raises(KeyError):
        mcp_server.show_document("nope", data_dir=str(store.data_dir))


def test_ingest_directory_shape_and_json(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "w2_synth_2024.txt").write_text(
        "Form W-2 Wage and Tax Statement\nTax Year 2024\n"
        "Box 1 Wages $85,000.00\nEmployer: Synthetic Corp\nEIN 12-3456789\n")
    out = mcp_server.ingest_directory(str(incoming),
                                      data_dir=str(tmp_path / "data"))
    assert out["n_docs"] == 1
    assert out["counts"] == [
        {"tax_year": 2024, "form_type": "W-2", "count": 1}]
    assert len(out["needs_review_ids"]) == 1
    json.dumps(out)


def test_validation_queue_progress(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2", {}, "validated"),
        _doc("w2-b", 2024, "W-2", {"box1_wages": _field("1", "low")},
             "transcribed"),
        _doc("b1-a", 2024, "1099-B", {}, "needs_review"),
        _doc("w2-c", 2023, "W-2", {}, "validated"),
    ])
    q = mcp_server.validation_queue(data_dir=str(store.data_dir))
    assert {d["doc_id"] for d in q["queue"]} == {"w2-b", "b1-a"}
    assert q["progress"] == {"2024": {"validated": 1, "total": 3},
                             "2023": {"validated": 1, "total": 1}}
    assert q["queue"][0]["low_confidence_fields"] >= 0
    json.dumps(q)
    q24 = mcp_server.validation_queue(tax_year=2024,
                                      data_dir=str(store.data_dir))
    assert {d["doc_id"] for d in q24["queue"]} == {"w2-b", "b1-a"}


def test_compute_carryforward_happy_path_and_json(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1-24", 2024, "1000.00", "1500.00", "short", "validated"),
    ])
    out = mcp_server.compute_carryforward({"2024": "single"},
                                          data_dir=str(store.data_dir))
    assert "2024" in out["table"]
    assert out["years"]["2024"]["deductible_loss"] == "500.00"
    assert out["carryforward_into_2026"] == {"st": "0.00", "lt": "0"}
    json.dumps(out)  # no raw Decimals anywhere
    # every money figure in the per-year breakdown is a string
    assert isinstance(out["years"]["2024"]["st_carry_out"], str)


def test_compute_carryforward_refuses_unvalidated(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1-23", 2023, "1000.00", "1500.00", "short",
               status="transcribed"),
    ])
    with pytest.raises(ValueError, match="not yet validated"):
        mcp_server.compute_carryforward({"2023": "single"},
                                        data_dir=str(store.data_dir))


def test_compute_carryforward_needs_status(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1-24", 2024, "1000.00", "1500.00", "short", "validated"),
    ])
    with pytest.raises(ValueError, match="no filing_status"):
        mcp_server.compute_carryforward({}, data_dir=str(store.data_dir))


def test_validate_document_flips_and_corrects(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2", {"box1_wages": _field("85000", "low")},
             "transcribed"),
    ])
    out = mcp_server.validate_document(
        "w2-a",
        corrections={"box1_wages": "86,000.00"},
        confirmed=["box1_wages"],
        data_dir=str(store.data_dir),
    )
    assert out["status"] == "validated"
    assert out["validated_at"] is not None
    json.dumps(out)
    # persisted through the same store path the review UI uses
    doc = DocumentStore(str(store.data_dir)).get("w2-a")
    assert doc.status == "validated"
    assert doc.fields["box1_wages"]["value"] == 86000
    # and it leaves the validation queue
    q = mcp_server.validation_queue(data_dir=str(store.data_dir))
    assert q["queue"] == []
    assert q["progress"] == {"2024": {"validated": 1, "total": 1}}


def test_validate_document_unknown_doc(tmp_path):
    store = _store_with(tmp_path, [])
    with pytest.raises(KeyError):
        mcp_server.validate_document("ghost", {}, [],
                                     data_dir=str(store.data_dir))


def test_validate_document_docstring_states_human_gate():
    doc = mcp_server.validate_document.__doc__
    assert "HUMAN-GATED" in doc
    assert "explicit user approval" in doc
    assert "review UI" in doc
