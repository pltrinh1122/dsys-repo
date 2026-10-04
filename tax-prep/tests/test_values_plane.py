"""Values-plane boundary tests (R12).

Every AGENT surface -- MCP tools in taxprep/mcp_server.py and bus
payloads -- stays metadata-only. This file pins the boundary: no
paths, no filenames, no amounts, no page images may appear in MCP
tool output or bus messages.

The Operator console itself (loopback, R10-hardened) IS the values
plane and is allowed to show them -- but even there, the Bus view
renders payload KEY names only, never values (pinned below).
"""

from __future__ import annotations

import base64
import io
import json
import re

import pytest

from taxprep import bus as _bus
from taxprep import console as _console
from taxprep import mcp_server
from taxprep import persons as _persons
from taxprep.models import Document
from taxprep.store import DocumentStore

SECRET_PATH = "/home/op/secret-vault/w2-acme-corp.pdf"
SECRET_NAME = "w2-acme-corp.pdf"
SECRET_AMOUNT = "85000.00"
SECRET_SSN = "000-00-1234"
# R21a: owner names are PII -- they must never cross the agent boundary.
# Only opaque ids (person-1..n) plus counts may appear.
SECRET_OWNER_NAME = "Alex Rivera"


def _pii_doc():
    return Document(
        doc_id="w2-pii-2024",
        tax_year=2024,
        form_type="W-2",
        source_path=SECRET_PATH,
        ocr_text_ref="ocr/w2-pii-2024.txt",
        fields={
            "box1_wages": {"value": SECRET_AMOUNT, "confidence": "high",
                           "raw_text": f"Box 1 Wages {SECRET_AMOUNT}"},
            "employer_ein": {"value": "12-3456789", "confidence": "low",
                             "raw_text": "EIN 12-3456789"},
        },
        status="transcribed",
    )


@pytest.fixture()
def pii_store(tmp_path):
    store = DocumentStore(tmp_path / "data")
    store.upsert(_pii_doc())
    return store


def _blob(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _assert_no_values_plane_leak(obj, label: str):
    blob = _blob(obj)
    assert SECRET_NAME not in blob, f"{label}: filename leaked"
    assert "secret-vault" not in blob, f"{label}: path leaked"
    assert SECRET_AMOUNT not in blob, f"{label}: amount leaked"
    assert SECRET_SSN not in blob, f"{label}: SSN leaked"
    assert "source_path" not in blob, f"{label}: source_path key leaked"
    assert "ocr_text_ref" not in blob, f"{label}: ocr_text_ref key leaked"
    assert "page_image" not in blob.lower(), f"{label}: page image leaked"
    # No base64 image blobs (page images) anywhere in agent output.
    assert not re.search(r"data:image/[a-z]+;base64", blob), \
        f"{label}: data-URI image leaked"


def test_mcp_show_document_metadata_only(pii_store, tmp_path):
    out = mcp_server.show_document("w2-pii-2024",
                                   data_dir=str(pii_store.data_dir))
    _assert_no_values_plane_leak(out, "show_document")
    # Scrubbed shape is still useful: boxes present, confidence, has_value.
    assert out["doc_id"] == "w2-pii-2024"
    assert out["fields"]["box1_wages"]["has_value"] is True
    assert out["fields"]["box1_wages"]["confidence"] == "high"


def test_mcp_list_documents_metadata_only(pii_store):
    out = mcp_server.list_documents(data_dir=str(pii_store.data_dir))
    _assert_no_values_plane_leak(out, "list_documents")
    assert out[0]["doc_id"] == "w2-pii-2024"


def test_mcp_validation_queue_metadata_only(pii_store):
    out = mcp_server.validation_queue(data_dir=str(pii_store.data_dir))
    _assert_no_values_plane_leak(out, "validation_queue")
    assert out["queue"][0]["doc_id"] == "w2-pii-2024"


def test_mcp_verify_all_metadata_only(pii_store):
    out = mcp_server.verify_all(data_dir=str(pii_store.data_dir))
    _assert_no_values_plane_leak(out, "verify_all")
    assert "passed" in out and "checks" in out


def test_bus_publish_refuses_pii_shaped_payload(tmp_path):
    with pytest.raises(ValueError):
        _bus.publish("tax-prep.ops", "note",
                     {"ssn": SECRET_SSN}, bus_dir=str(tmp_path / "bus"))


def test_bus_poll_metadata_only(tmp_path):
    bus_dir = tmp_path / "bus"
    _bus.publish("tax-prep.ops", "ingest_done",
                 {"doc_count": 3, "status": "ok"},
                 bus_dir=str(bus_dir), from_id="op-1")
    msgs = _bus.list_messages("tax-prep.ops", bus_dir=str(bus_dir))
    assert len(msgs) == 1
    _assert_no_values_plane_leak(msgs, "bus_poll")
    assert msgs[0]["payload"] == {"doc_count": 3, "status": "ok"}


def _assert_no_owner_name_leak(obj, label: str):
    blob = _blob(obj)
    assert SECRET_OWNER_NAME not in blob, f"{label}: owner name leaked"
    assert "Alex" not in blob, f"{label}: owner name fragment leaked"


def test_owner_names_never_cross_agent_boundary(pii_store, tmp_path):
    """R21a blind sweep: the person registry holds names; every agent
    surface (MCP tools, CLI --meta, bus payloads) carries opaque ids
    and counts only."""
    from taxprep.cli import main as _cli_main
    store = pii_store
    pid = _persons.register_person(store.data_dir, SECRET_OWNER_NAME)
    assert pid == "person-1"
    _persons.assign_owner(store, "w2-pii-2024", "person-1")

    out = mcp_server.show_document("w2-pii-2024",
                                   data_dir=str(store.data_dir))
    _assert_no_values_plane_leak(out, "show_document")
    _assert_no_owner_name_leak(out, "show_document")
    assert out["owner_person_id"] == "person-1"  # id crosses, name doesn't

    listed = mcp_server.list_documents(data_dir=str(store.data_dir))
    _assert_no_owner_name_leak(listed, "list_documents")
    assert listed[0]["owner_person_id"] == "person-1"

    payload = _persons.scope_payload(store, {"person-1"})
    _assert_no_owner_name_leak(payload, "scope_payload")
    assert payload["doc_counts"] == {"person-1": 1}
    bus_dir = tmp_path / "bus"
    _bus.publish("tax-prep.ops", "scope", payload, bus_dir=str(bus_dir),
                 from_id="op-1")
    msgs = _bus.list_messages("tax-prep.ops", bus_dir=str(bus_dir))
    _assert_no_owner_name_leak(msgs, "bus scope message")

    # The registry itself stays local: digest + table counts are clean.
    blob = json.dumps(store.db_digest()) + json.dumps(store.table_counts())
    _assert_no_owner_name_leak({"blob": blob}, "db_digest")

    # CLI --meta output: ids, never names.
    assert _cli_main(["--data-dir", str(store.data_dir), "show",
                      "w2-pii-2024", "--meta"]) == 0


def test_console_bus_view_renders_keys_never_values(tmp_path):
    bus_dir = tmp_path / "bus"
    _bus.publish("tax-prep.ops", "note",
                 {"sneaky_amount": "99999.99",
                  "sneaky_path": "/home/op/taxes/secret.pdf"},
                 bus_dir=str(bus_dir), from_id="op-1")
    store = DocumentStore(tmp_path / "data")
    html_out = _console.bus_html(store, bus_dir=str(bus_dir))
    assert "99999.99" not in html_out
    assert "/home/op/taxes/secret.pdf" not in html_out
    # ...but the key names (metadata) are visible.
    assert "sneaky_amount" in html_out
    assert "sneaky_path" in html_out
