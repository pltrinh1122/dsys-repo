"""R21: per-person scoping + 1040-X column-A builder.

All fixtures synthetic. Person names are obviously fake ("Alex Rivera"
etc.); the agent-facing surfaces must carry opaque ids (person-1..n)
only -- the name-leak sweep lives here and in test_values_plane.py.
"""

from __future__ import annotations

import json

import pytest

from taxprep import bus as _bus
from taxprep import column_a, duplicates, lifecycle
from taxprep import persons as _persons
from taxprep.cli import main as _cli_main
from taxprep import mcp_server
from taxprep.models import Document
from taxprep.store import DocumentStore

# Obviously-synthetic names for the registry.
NAME_A = "Alex Rivera"
NAME_B = "Jordan Lee"
NAME_C = "Sam Out"


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


@pytest.fixture()
def r21(tmp_path):
    store = DocumentStore(tmp_path / "data")
    p1 = _persons.register_person(store.data_dir, NAME_A)
    p2 = _persons.register_person(store.data_dir, NAME_B)
    p3 = _persons.register_person(store.data_dir, NAME_C)
    assert (p1, p2, p3) == ("person-1", "person-2", "person-3")
    return {"store": store, "data": tmp_path / "data",
            "p1": p1, "p2": p2, "p3": p3}


# -- person registry ----------------------------------------------------

def test_person_ids_deterministic_first_seen_order(r21, tmp_path):
    store = r21["store"]
    # Re-registering is idempotent.
    assert _persons.register_person(store.data_dir, NAME_A) == "person-1"
    # Stable across runs (new store handle, same data dir).
    store2 = DocumentStore(r21["data"])
    assert _persons.person_ids(store2.data_dir) == \
        ["person-1", "person-2", "person-3"]
    assert _persons.person_name(store2.data_dir, "person-2") == NAME_B
    # A fourth person continues the sequence.
    assert _persons.register_person(store2.data_dir, "Casey New") == "person-4"


def test_register_person_refuses_blank(r21):
    with pytest.raises(ValueError):
        _persons.register_person(r21["store"].data_dir, "   ")


def test_persons_json_corrupt_fails_closed(r21):
    (r21["data"] / "persons.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        _persons.person_ids(r21["data"])


# -- suggestion: shown, never auto-applied --------------------------------

def test_suggest_owner_shown_not_applied(r21):
    store = r21["store"]
    doc = _doc("w2-a-2023", 2023, "W-2", {
        "recipient_name": _tfield(NAME_A, raw_text=f"Employee: {NAME_A}"),
        "box1_wages": _tfield("1000.00")})
    store.upsert(doc)
    res = _persons.suggest_owner_for_doc(store, "w2-a-2023")
    assert res == {"doc_id": "w2-a-2023", "owner_suggestion": "person-1",
                   "basis": "field_value_match:recipient_name",
                   "disposed": False}
    got = store.get("w2-a-2023")
    assert got.owner_suggestion == "person-1"
    # Un-disposed: the owner is still unassigned -- nothing was applied.
    assert got.owner_person_id is None


def test_suggest_ignores_payer_side_fields(r21):
    store = r21["store"]
    # employer_name is PAYER identity: suggesting from it would attribute
    # the document to the wrong person.
    store.upsert(_doc("w2-b-2023", 2023, "W-2", {
        "employer_name": _tfield(NAME_A)}))
    assert _persons.suggest_owner_for_doc(store, "w2-b-2023") is None
    assert store.get("w2-b-2023").owner_suggestion is None


def test_suggest_no_match_writes_nothing(r21):
    store = r21["store"]
    store.upsert(_doc("w2-c-2023", 2023, "W-2",
                      {"box1_wages": _tfield("1000.00")}))
    assert _persons.suggest_owner_for_doc(store, "w2-c-2023") is None
    assert store.get("w2-c-2023").owner_suggestion is None


def test_assign_owner_disposes_suggestion(r21):
    store = r21["store"]
    store.upsert(_doc("w2-d-2023", 2023, "W-2", {
        "recipient_name": _tfield(NAME_B)}))
    _persons.suggest_owner_for_doc(store, "w2-d-2023")
    # Operator overrides the suggestion with a different person.
    res = _persons.assign_owner(store, "w2-d-2023", "person-1")
    assert res["owner_person_id"] == "person-1"
    assert res["accepted_suggestion"] is False
    got = store.get("w2-d-2023")
    assert got.owner_person_id == "person-1"
    assert got.owner_suggestion is None  # consumed
    logged = store.decisions_for(doc_id="w2-d-2023", kind="owner_assignment")
    assert len(logged) == 1
    assert logged[0]["payload"]["person_id"] == "person-1"
    assert logged[0]["actor"] == "operator"


def test_assign_owner_accepts_suggestion(r21):
    store = r21["store"]
    store.upsert(_doc("w2-e-2023", 2023, "W-2", {
        "recipient_name": _tfield(NAME_A)}))
    _persons.suggest_owner_for_doc(store, "w2-e-2023")
    res = _persons.assign_owner(store, "w2-e-2023", "person-1")
    assert res["accepted_suggestion"] is True


def test_suggest_refused_when_owner_assigned(r21):
    store = r21["store"]
    store.upsert(_doc("w2-f-2023", 2023, "W-2", {
        "recipient_name": _tfield(NAME_A)}))
    _persons.assign_owner(store, "w2-f-2023", "person-2")
    with pytest.raises(ValueError):
        _persons.suggest_owner_for_doc(store, "w2-f-2023")


def test_assign_owner_unknown_person_refused(r21):
    store = r21["store"]
    store.upsert(_doc("w2-g-2023", 2023, "W-2"))
    with pytest.raises(ValueError):
        _persons.assign_owner(store, "w2-g-2023", "person-99")
    with pytest.raises(KeyError):
        _persons.assign_owner(store, "nope", "person-1")


# -- scope filter ---------------------------------------------------------

def test_out_of_scope_excluded_with_reason_not_deleted(r21):
    store = r21["store"]
    store.upsert(_doc("rt-2023", 2023, "RETURN_TRANSCRIPT",
                      {"agi": _tfield("100.00")}))
    store.upsert(_doc("w2-in-2023", 2023, "W-2",
                      {"box1_wages": _tfield("50.00")}))
    store.upsert(_doc("w2-un-2023", 2023, "W-2",
                      {"box1_wages": _tfield("60.00")}))
    _persons.assign_owner(store, "rt-2023", "person-3")   # out of scope
    _persons.assign_owner(store, "w2-in-2023", "person-1")  # in scope
    # w2-un-2023: unassigned -- the filter never touches it.

    applied = _persons.apply_scope_filter(store, {"person-1", "person-2"})
    assert applied == [{"doc_id": "rt-2023", "owner_person_id": "person-3"}]

    out = store.get("rt-2023")
    assert out.status == "excluded"
    assert out.status_reason == "out-of-scope-person"  # existing taxonomy
    # Never deleted: the record (and its fields) survive.
    assert out.fields["agi"]["value"] == "100.00"

    assert store.get("w2-in-2023").status == "transcribed"
    assert store.get("w2-un-2023").status == "transcribed"
    # Idempotent: a second run changes nothing.
    assert _persons.apply_scope_filter(store, {"person-1", "person-2"}) == []


def test_out_of_scope_reason_is_machine_taxonomy(r21):
    assert "out-of-scope-person" in lifecycle.MACHINE_EXCLUDE_REASONS
    # Free-text operator exclusions keep the standing code.
    doc = _doc("x-2023", 2023, "W-2")
    res = lifecycle.transition(
        doc, lifecycle.EXCLUDE, actor=lifecycle.OPERATOR,
        event_input=lifecycle.ExcludeInput(reason="operator no longer wants"))
    assert res.ok and doc.status_reason == "operator-excluded"


# -- joint / multi-owner: raised, never split ------------------------------

def test_joint_document_raised_for_allocation_not_split(r21):
    store = r21["store"]
    store.upsert(_doc("joint-2023", 2023, "1099-INT",
                      {"box1_interest": _tfield("12.34")}))
    cid = _persons.raise_allocation_conflict(
        store, "joint-2023", ["person-1", "person-2"])
    assert duplicates.open_conflicts(store) == {"allocation": 1}
    # The doc itself is untouched: no owner, no split.
    assert store.get("joint-2023").owner_person_id is None
    # Options are the opaque candidate ids.
    opts = [r["option_key"] for r in
            store._conn.execute(
                "SELECT option_key FROM conflict_option WHERE conflict_id = ? "
                "ORDER BY option_key", (cid,))]
    assert opts == ["person-1", "person-2"]
    # The Operator disposes explicitly via the R16a pattern.
    seq = duplicates.choose_conflict(store, cid, choice="person-1",
                                     actor="operator")
    assert seq >= 1
    assert duplicates.open_conflicts(store) == {}


def test_allocation_conflict_unknown_person_refused(r21):
    store = r21["store"]
    store.upsert(_doc("joint2-2023", 2023, "1099-INT"))
    with pytest.raises(ValueError):
        _persons.raise_allocation_conflict(
            store, "joint2-2023", ["person-1", "person-99"])


def test_artifact_owner_allocation_survives_rederive(r21):
    store = r21["store"]
    store.upsert(_doc("j3-2023", 2023, "1099-INT",
                      {"box1_interest": _tfield("12.34")}))
    arts = store.get_artifacts("j3-2023")
    assert arts, "field artifacts expected"
    aid = arts[0]["artifact_id"]
    res = _persons.assign_artifact_owner(store, aid, "person-2")
    assert res["owner_person_id"] == "person-2"
    # A re-derivation (replace_artifacts) preserves the Operator's
    # per-artifact allocation for surviving artifact ids.
    store.replace_artifacts("j3-2023", store.get_artifacts("j3-2023"))
    again = [a for a in store.get_artifacts("j3-2023")
             if a["artifact_id"] == aid][0]
    assert again["owner_person_id"] == "person-2"
    logged = store.decisions_for(kind="owner_assignment")
    assert any(d["artifact_id"] == aid for d in logged)


# -- return assignment (Operator decision) ----------------------------------

def test_return_assignment_recorded_as_decision(r21):
    store = r21["store"]
    store.upsert(_doc("w2-h-2023", 2023, "W-2"))
    _persons.assign_owner(store, "w2-h-2023", "person-3")
    res = _persons.record_return_assignment(
        store, "w2-h-2023", "person-3", "own")
    assert res["assignment"] == "own"
    rows = _persons.return_assignments(store, "w2-h-2023")
    assert len(rows) == 1
    assert rows[0]["payload"] == {
        "person_id": "person-3", "assignment": "own",
        "ts": rows[0]["payload"]["ts"]}
    assert rows[0]["actor"] == "operator"
    with pytest.raises(ValueError):
        _persons.record_return_assignment(
            store, "w2-h-2023", "person-3", "maybe")
    with pytest.raises(ValueError):
        _persons.record_return_assignment(
            store, "w2-h-2023", "person-99", "joint")


# -- opaque-id discipline -----------------------------------------------------

def _blob(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _assert_owner_ids_only(obj, label):
    blob = _blob(obj)
    for name in (NAME_A, NAME_B, NAME_C):
        assert name not in blob, f"{label}: owner name leaked"
        assert name.split()[0] not in blob, f"{label}: name fragment leaked"


def test_opaque_ids_on_agent_surfaces(r21):
    store, data = r21["store"], r21["data"]
    store.upsert(_doc("w2-i-2023", 2023, "W-2",
                      {"box1_wages": _tfield("999.99")}))
    _persons.assign_owner(store, "w2-i-2023", "person-1")

    # MCP tool outputs: opaque ids, never names.
    out = mcp_server.show_document("w2-i-2023", data_dir=str(data))
    _assert_owner_ids_only(out, "show_document")
    assert out["owner_person_id"] == "person-1"
    listed = mcp_server.list_documents(data_dir=str(data))
    _assert_owner_ids_only(listed, "list_documents")
    assert listed[0]["owner_person_id"] == "person-1"
    q = mcp_server.validation_queue(data_dir=str(data))
    _assert_owner_ids_only(q, "validation_queue")
    assert q["queue"][0]["owner_person_id"] == "person-1"

    # CLI --meta: opaque ids, never names.
    rc = _cli_main(["--data-dir", str(data), "show", "w2-i-2023", "--meta"])
    assert rc == 0

    # Bus payload builder: opaque ids + counts, never names.
    payload = _persons.scope_payload(store, {"person-1", "person-2"})
    _assert_owner_ids_only(payload, "scope_payload")
    assert payload["doc_counts"] == {"person-1": 1}
    _bus.publish("tax-prep.ops", "scope", payload,
                 bus_dir=str(r21["data"].parent / "bus"), from_id="op-1")
    msgs = _bus.list_messages("tax-prep.ops",
                              bus_dir=str(r21["data"].parent / "bus"))
    _assert_owner_ids_only(msgs, "bus scope message")


def test_cli_meta_output_has_ids_not_names(r21, capsys):
    store, data = r21["store"], r21["data"]
    store.upsert(_doc("w2-j-2023", 2023, "W-2"))
    _persons.assign_owner(store, "w2-j-2023", "person-2")
    assert _cli_main(["--data-dir", str(data), "show", "w2-j-2023",
                      "--meta"]) == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta["owner_person_id"] == "person-2"
    _assert_owner_ids_only(meta, "cli --meta")


def test_owner_ids_never_in_db_digest(r21):
    # The blind sweep hashes the digest: names must not be in it.
    blob = json.dumps(r21["store"].db_digest(), sort_keys=True)
    _assert_owner_ids_only({"digest": blob}, "db_digest")


# -- column-A builder ----------------------------------------------------------

def _validated_rt(store, doc_id, year, lines):
    fields = {k: _tfield(v, raw_text=f"{k} {v}") for k, v in lines.items()}
    store.upsert(_doc(doc_id, year, "RETURN_TRANSCRIPT", fields,
                      status="validated"))


def test_column_a_present_and_missing(r21):
    store = r21["store"]
    _validated_rt(store, "rt23", 2023,
                  {"agi": "12345.67", "withholding": "2000.00"})
    result = column_a.build_column_a(store, 2023)
    by_line = {e["line"]: e for e in result["lines"]}

    l1 = by_line["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "12345.67"          # Decimal-safe string
    assert l1["source"] == "return_transcript"
    assert l1["source_doc_id"] == "rt23"
    # Source + provenance carried (R15/R19 shapes).
    assert l1["provenance"]["confidence"] == "high"
    assert l1["provenance"]["raw_text"] == "agi 12345.67"
    assert l1["provenance"]["evidence_ref"] == \
        {"doc_id": "rt23", "field": "agi"}

    l12 = by_line["L12"]
    assert l12["status"] == "present" and l12["value"] == "2000.00"

    # Unmapped lines are MISSING: not zero, not an error.
    for code in ("L2", "L6", "L7", "L10", "L13", "L14", "L15", "L16"):
        e = by_line[code]
        assert e["status"] == "MISSING", code
        assert e["value"] is None and e["source"] is None
        assert e["provenance"] is None
    cov = result["coverage"]
    assert cov["n_present"] == 2
    assert cov["n_missing"] == cov["n_lines"] - 2
    assert cov["n_conflict"] == 0


def test_column_a_record_of_account_source(r21):
    store = r21["store"]
    store.upsert(_doc("roa24", 2024, "RECORD_OF_ACCOUNT",
                      {"agi": _tfield("7777.77")}, status="validated"))
    result = column_a.build_column_a(store, 2024)
    l1 = {e["line"]: e for e in result["lines"]}["L1"]
    assert l1["status"] == "present"
    assert l1["source"] == "record_of_account"
    assert l1["value"] == "7777.77"


def test_column_a_transcript_is_source_of_record(r21):
    # 2023/2024: the return transcript wins over the ROA; a disagreeing
    # ROA line is surfaced in also_seen, never silently resolved.
    store = r21["store"]
    _validated_rt(store, "rt23b", 2023, {"agi": "100.00"})
    store.upsert(_doc("roa23b", 2023, "RECORD_OF_ACCOUNT",
                      {"agi": _tfield("101.00")}, status="validated"))
    result = column_a.build_column_a(store, 2023)
    l1 = {e["line"]: e for e in result["lines"]}["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "100.00"
    assert l1["source"] == "return_transcript"
    assert l1["also_seen"] == [{
        "source": "record_of_account", "source_doc_id": "roa23b",
        "value": "101.00", "agrees": False}]


def test_column_a_ignores_unvalidated(r21):
    store = r21["store"]
    store.upsert(_doc("rt23u", 2023, "RETURN_TRANSCRIPT",
                      {"agi": _tfield("100.00")}, status="transcribed"))
    result = column_a.build_column_a(store, 2023)
    assert {e["line"]: e for e in result["lines"]}["L1"]["status"] == "MISSING"


def test_column_a_excludes_out_of_scope(r21):
    store = r21["store"]
    _validated_rt(store, "rt23c", 2023, {"agi": "100.00"})
    _persons.assign_owner(store, "rt23c", "person-3")
    _persons.apply_scope_filter(store, {"person-1", "person-2"})
    result = column_a.build_column_a(store, 2023)
    assert {e["line"]: e for e in result["lines"]}["L1"]["status"] == "MISSING"


def test_column_a_is_read_only(r21):
    store = r21["store"]
    _validated_rt(store, "rt23d", 2023,
                  {"agi": "100.00", "total_tax": "10.00"})
    before = (store.db_digest(), store.table_counts())
    column_a.build_column_a(store, 2023)
    after = (store.db_digest(), store.table_counts())
    assert before == after


def test_column_a_2025_corroboration_conflict(r21):
    store = r21["store"]
    _validated_rt(store, "rt25", 2025, {"agi": "51000.00"})
    store.upsert(_doc("o1040-25", 2025, "1040",
                      {"agi": _tfield("50000.00")}, status="validated"))
    result = column_a.build_column_a(store, 2025)
    l1 = {e["line"]: e for e in result["lines"]}["L1"]
    assert l1["status"] == "CONFLICT"
    assert l1["value"] is None  # no value is picked
    assert l1["conflict_id"]
    assert result["conflicts_raised"] == [{
        "line": "L1", "conflict_id": l1["conflict_id"],
        "transcript_doc": "rt25", "original_doc": "o1040-25"}]
    assert duplicates.open_conflicts(store) == {"corroboration": 1}
    assert l1["also_seen"][0]["value"] == "51000.00"


def test_column_a_2025_agreeing_sources_no_conflict(tmp_path):
    store = DocumentStore(tmp_path / "data")
    _validated_rt(store, "rt25b", 2025, {"agi": "50000.00"})
    store.upsert(_doc("o1040-25b", 2025, "1040",
                      {"agi": _tfield("50000.00")}, status="validated"))
    result = column_a.build_column_a(store, 2025)
    l1 = {e["line"]: e for e in result["lines"]}["L1"]
    assert l1["status"] == "present"
    assert l1["value"] == "50000.00"
    assert l1["source"] == "return_transcript"
    assert result["conflicts_raised"] == []
    assert duplicates.open_conflicts(store) == {}


def test_column_a_2025_original_only(r21):
    # R20 box/line extraction may not exist yet: the original alone
    # still sources the line (designed for the transcript's absence).
    store = r21["store"]
    store.upsert(_doc("o1040-25c", 2025, "1040",
                      {"agi": _tfield("42000.00")}, status="validated"))
    result = column_a.build_column_a(store, 2025)
    l1 = {e["line"]: e for e in result["lines"]}["L1"]
    assert l1["status"] == "present"
    assert l1["source"] == "original_return"
    assert l1["value"] == "42000.00"


def test_column_a_line_universe_is_stable():
    codes = [c for c, _, _ in column_a.COLUMN_A_LINES]
    assert codes == ["L1", "L2", "L4a", "L4b", "L5", "L6", "L7", "L10",
                     "L11", "L12", "L13", "L14", "L15", "L16", "L17",
                     "L18", "L20", "L22", "L23"]
    # Computed / reserved lines are never entries (never derived).
    assert "L8" not in codes and "L9" not in codes and "L19" not in codes
