"""MCP server tests -- all fixtures synthetic, stdio transport only.

Blind-orchestrator contract: NO tool output may contain PII. The
_pii_free helper enforces this recursively on every tool under test:
no "value"/"raw_text" keys, no $<digit> money patterns in strings.
"""

import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path

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
    "verify_completeness",
    "verify_validation_gate",
    "verify_lot_integrity",
    "verify_transcript_reconciliation",
    "verify_all",
    "bus_publish",
    "bus_poll",
    "assess_relevance",
    "relevance_override",
    "analyze_gaps",
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


def _lot(proceeds=None, basis=None, term=None, wash_1g=None):
    return {
        "description": None,
        "date_acquired": "01/15/2024",
        "date_sold": "06/20/2024",
        "proceeds_1d": proceeds,
        "basis_1e": basis,
        "wash_1g": wash_1g,
        "fed_withheld_1f": None,
        "term": term,
        "covered": None,
    }


def _b1099(doc_id, year, proceeds, basis, term, status="validated", lots=None):
    if lots is None:
        lots = [_lot(proceeds, basis, term)]
    return _doc(
        doc_id, year, "1099-B",
        {
            "lots": _field(lots),
            "broker": _field("Synthetic Broker"),
        },
        status=status,
    )


def _store_with(tmp_path, docs):
    store = DocumentStore(tmp_path / "data")
    for d in docs:
        store.upsert(d)
    return store


def _pii_free(obj):
    """Recursive blind-orchestrator assertion over any tool output."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key leaked: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        assert not re.search(r"\$\d", obj), f"money leaked: {obj[:60]!r}"


def test_all_fifteen_tools_registered():
    async def names():
        return {t.name for t in await mcp.list_tools()}

    assert asyncio.run(names()) == EXPECTED_TOOLS
    assert "validate_document" not in asyncio.run(names())


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
    _pii_free(rows)
    only_w2 = mcp_server.list_documents(form_type="W-2",
                                        data_dir=str(store.data_dir))
    assert [r["doc_id"] for r in only_w2] == ["w2-a"]


def test_show_document_scrubbed_shape(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2",
             {"box1_wages": _field("85000", "high", "Box 1 $85,000"),
              "employer_name": _field("ACME CORP", "high", "ACME CORP")},
             "validated"),
        # transcript field codes embed payer names -- must be redacted
        _doc("t1", 2024, "WAGE_INCOME_TRANSCRIPT",
             {"payer1.ACME CORP.1": _field(85000.0, "high", "W-2 ACME CORP box 1")},
             "transcribed"),
    ])
    rec = mcp_server.show_document("w2-a", data_dir=str(store.data_dir))
    assert rec["doc_id"] == "w2-a"
    f = rec["fields"]["box1_wages"]
    assert set(f) == {"confidence", "has_value"}
    assert f == {"confidence": "high", "has_value": True}
    # envelope carries no paths or values
    assert "source_path" not in rec and "ocr_text_ref" not in rec
    json.dumps(rec)
    _pii_free(rec)

    trec = mcp_server.show_document("t1", data_dir=str(store.data_dir))
    codes = list(trec["fields"])
    assert codes == ["payer1.[payer].1"], f"payer name leaked via key: {codes}"
    _pii_free(trec)


def test_show_document_provenance_and_positional_payer_keys(tmp_path):
    """R5: provenance keys are exposed as non-PII metadata. R8: positional
    payer keys (payer1.1) pass through; the payer name survives only as a
    redacted has_value on payer1.name."""
    doc = _doc("ocr-1", 2024, "W-2",
               {"1": _field("10000.00", "high", "Box 1"),
                "payer1.name": _field("ACME CORP", "high", ""),
                "payer1.1": _field(85000.0, "high", "")},
               "transcribed")
    doc.text_source = "ocr"
    doc.reason_code = None
    doc.ocr_engine = "tesseract"
    doc.engine_version = "5.3.4"
    doc.ocr_mode = "redo-ocr"
    doc.attempts = [
        {"mode": "skip-text", "engine": "tesseract",
         "engine_version": "5.3.4", "ok": False, "chars": 12,
         "mean_confidence": None, "reason_code": "ocr_failed"},
        {"mode": "redo-ocr", "engine": "tesseract",
         "engine_version": "5.3.4", "ok": True, "chars": 480,
         "mean_confidence": 91.2, "reason_code": None},
    ]
    doc.mean_confidence = 91.2
    store = _store_with(tmp_path, [doc])
    dd = str(store.data_dir)

    rec = mcp_server.show_document("ocr-1", data_dir=dd)
    # provenance keys present (operational metadata, not taxpayer data)
    assert set(mcp_server.PROVENANCE_KEYS) <= set(rec)
    assert rec["text_source"] == "ocr"
    assert rec["ocr_engine"] == "tesseract"
    assert rec["engine_version"] == "5.3.4"
    assert rec["ocr_mode"] == "redo-ocr"
    assert rec["mean_confidence"] == 91.2
    assert [a["mode"] for a in rec["attempts"]] == ["skip-text", "redo-ocr"]
    # positional payer keys pass through unredacted; names never leak
    assert set(rec["fields"]) == {"1", "payer1.name", "payer1.1"}
    assert rec["fields"]["payer1.name"] == {"confidence": "high",
                                           "has_value": True}
    blob = json.dumps(rec)
    assert "ACME" not in blob
    assert "source_path" not in rec and "ocr_text_ref" not in rec
    json.dumps(rec)
    _pii_free(rec)

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
    _pii_free(out)


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
    _pii_free(q)
    q24 = mcp_server.validation_queue(tax_year=2024,
                                      data_dir=str(store.data_dir))
    assert {d["doc_id"] for d in q24["queue"]} == {"w2-b", "b1-a"}


def test_compute_carryforward_writes_report_and_returns_slim(tmp_path):
    store = _store_with(tmp_path, [
        _b1099("b1-24", 2024, "1000.00", "1500.00", "short", "validated"),
    ])
    out = mcp_server.compute_carryforward({"2024": "single"},
                                          data_dir=str(store.data_dir))
    # tool output is slim and PII-free
    assert set(out) == {"report_path", "years_covered", "n_warnings",
                        "status"}
    assert out["status"] == "ok"
    assert out["years_covered"] == [2024]
    assert isinstance(out["n_warnings"], int)
    json.dumps(out)
    _pii_free(out)
    # the full PII-bearing report lives in the local file
    report = Path(out["report_path"])
    assert report.exists()
    assert report.parent.name == "reports"
    text = report.read_text()
    assert "2024" in text and "$" in text  # amounts live in the file
    assert "500.00" in text  # the deductible, file-only


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


def test_verify_tools_registered_and_pii_free(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2", {"1": _field(1)}, "validated"),
        _doc("u1", None, "UNKNOWN", {}, "needs_review"),
        _b1099("b1", 2024, "100.00", "50.00", "short", "validated"),
    ])
    dd = str(store.data_dir)
    c = mcp_server.verify_completeness(data_dir=dd)
    assert c["passed"] is False and c["unknown_form_ids"] == ["u1"]
    g = mcp_server.verify_validation_gate(data_dir=dd)
    assert g["unvalidated_ids"] == ["u1"]
    g24 = mcp_server.verify_validation_gate(tax_year=2024, data_dir=dd)
    assert g24["passed"] is True
    li = mcp_server.verify_lot_integrity(tax_year=2024, data_dir=dd)
    assert li["passed"] is True and li["n_checks"] == 6
    r = mcp_server.verify_transcript_reconciliation(tax_year=2024,
                                                    data_dir=dd)
    assert r["n_docs_only_payers"] == 2  # no transcript ingested
    cr_out = mcp_server.verify_all(tax_year=2024, data_dir=dd)
    assert "completeness" in cr_out["checks"]
    assert "validation_gate" in cr_out["checks"]
    for out in (c, g, g24, li, r, cr_out):
        json.dumps(out)
        _pii_free(out)


def test_pii_sweep_all_tools(tmp_path, monkeypatch):
    """Every tool's output, recursively: no value/raw_text keys, no $N."""
    # isolate bus side effects (tuning file, bus dir) from the real home
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(tmp_path / "bus"))
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2",
             {"1": _field("$85,000.00", "high", "Box 1 $85,000.00"),
              "employer_name": _field("ACME CORP", "high", "ACME CORP")},
             "validated"),
        _b1099("b1", 2024, "100.00", "50.00", "short", "validated"),
        # multi-lot doc: the nested lot-table shape must sweep clean too
        _b1099("b2", 2024, None, None, None, "validated", lots=[
            _lot("1000.00", "1500.00", "short", wash_1g="300.00"),
            _lot("2000.00", "1200.00", "long"),
        ]),
    ])
    # R5 provenance on one doc: the sweep below must cover the new keys
    prov = store.get("w2-a")
    prov.text_source = "ocr"
    prov.ocr_engine = "tesseract"
    prov.engine_version = "5.3.4"
    prov.ocr_mode = "skip-text"
    prov.attempts = [{"mode": "skip-text", "engine": "tesseract",
                      "engine_version": "5.3.4", "ok": True, "chars": 900,
                      "mean_confidence": 93.0, "reason_code": None}]
    prov.mean_confidence = 93.0
    store.upsert(prov)
    dd = str(store.data_dir)
    outputs = [
        mcp_server.list_documents(data_dir=dd),
        mcp_server.show_document("w2-a", data_dir=dd),
        mcp_server.validation_queue(data_dir=dd),
        mcp_server.validation_queue(data_dir=dd, include_irrelevant=True),
        mcp_server.relevance_override("w2-a", "relevant",
                                      "operator sweep note", data_dir=dd),
        mcp_server.compute_carryforward({"2024": "single"}, data_dir=dd),
        mcp_server.verify_completeness(data_dir=dd),
        mcp_server.verify_validation_gate(data_dir=dd),
        mcp_server.verify_lot_integrity(tax_year=2024, data_dir=dd),
        mcp_server.verify_transcript_reconciliation(tax_year=2024,
                                                    data_dir=dd),
        mcp_server.verify_all(tax_year=2024, data_dir=dd),
        mcp_server.bus_publish(topic="tax-prep.ops", type="run-done",
                               payload={"n_docs": 2, "status": "ok"}),
        mcp_server.bus_poll(topic="tax-prep.ops"),
        mcp_server.assess_relevance(data_dir=dd),
        mcp_server.analyze_gaps(tax_year=2024, data_dir=dd),
    ]
    for out in outputs:
        json.dumps(out)
        _pii_free(out)


def test_new_mcp_tools_shapes(tmp_path, monkeypatch):
    """bus_publish / bus_poll / assess_relevance / analyze_gaps behavior."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(tmp_path / "bus"))
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2",
             {"1": _field("$85,000.00", "high", "Box 1 $85,000.00")},
             "validated"),
    ])
    dd = str(store.data_dir)

    pub = mcp_server.bus_publish(topic="tax-prep.ops", type="run-done",
                                 payload={"n_docs": 1},
                                 correlation_id="corr-1")
    assert set(pub) == {"message_id", "path", "topic", "from"}
    assert pub["message_id"].startswith("msg_")
    assert Path(pub["path"]).is_file()
    json.dumps(pub)
    _pii_free(pub)

    # the publishing session's own broadcast is tuned out of its poll
    polled = mcp_server.bus_poll(topic="tax-prep.ops")
    assert polled["messages"] == [] and polled["topics"] == ["tax-prep.ops"]
    # another session's message IS delivered
    from taxprep import bus as _bus
    _bus.publish("tax-prep.ops", "run-done", {"n_docs": 5},
                 from_id="workstation-abcdef")
    polled2 = mcp_server.bus_poll(topic="tax-prep.ops")
    assert len(polled2["messages"]) == 1
    assert polled2["messages"][0]["from"] == "workstation-abcdef"
    assert polled2["messages"][0]["payload"] == {"n_docs": 5}
    _pii_free(polled2)

    # payload PII guard is the enforcement point
    with pytest.raises(ValueError, match="refused"):
        mcp_server.bus_publish(topic="t", type="x",
                               payload={"note": "12-3456789"})
    with pytest.raises(TypeError):
        mcp_server.bus_publish(topic="t", type="x", payload=["nope"])

    rel = mcp_server.assess_relevance(tax_year=2024, data_dir=dd)
    assert rel["counts"] == {"relevant": 1, "irrelevant": 0, "needs_human": 0}
    assert rel["relevant_ids"] == ["w2-a"]
    # persisted as a label on the document
    assert DocumentStore(store.data_dir).get("w2-a").relevance == "relevant"
    json.dumps(rel)
    _pii_free(rel)

    gaps = mcp_server.analyze_gaps(tax_year=2024, data_dir=dd)
    assert gaps["2024"]["has_transcript"] is False
    assert gaps["2024"]["expected_forms"] == []
    assert Path(gaps["report_path"]).is_file()
    json.dumps(gaps)
    _pii_free(gaps)


def test_guard_refusal_surfaces_blockers_through_mcp(tmp_path):
    """R3: the guard's blocker list surfaces through the MCP boundary.

    compute_carryforward refuses (raised tool error) with doc_ids +
    reason codes in the message; verify_all's carryforward_ready reason
    carries the same. Both are swept for PII: doc_ids and reason codes
    only, no values, no exclusion reasons.
    """
    store = _store_with(tmp_path, [
        _b1099("b1", 2024, "100.00", "50.00", "short", "validated"),
        _doc("u1", 2024, "UNKNOWN", {}, "validated"),
        _doc("z1", 2024, "1099-B", {}, "validated"),
    ])
    dd = str(store.data_dir)

    with pytest.raises(ValueError) as ei:
        mcp_server.compute_carryforward({"2024": "single"}, data_dir=dd)
    msg = str(ei.value)
    assert "u1(unknown_form)" in msg
    assert "z1(zero_lots)" in msg
    _pii_free(msg)

    out = mcp_server.verify_all(tax_year=2024, data_dir=dd)
    cr = out["checks"]["carryforward_ready"]
    assert cr["passed"] is False
    assert "u1(unknown_form)" in cr["reason"]
    assert "z1(zero_lots)" in cr["reason"]
    json.dumps(out)
    _pii_free(out)

    # an Operator exclusion clears the guard through the same path
    from taxprep import exclusions as _x
    _x.record_exclusion(dd, "u1", "operator: duplicate of scanned W-2")
    _x.record_exclusion(dd, "z1", "operator: informational copy, no lots")
    out2 = mcp_server.verify_all(tax_year=2024, data_dir=dd)
    assert out2["checks"]["carryforward_ready"] == {
        "passed": True, "reason": "ready"}
    json.dumps(out2)
    _pii_free(out2)
