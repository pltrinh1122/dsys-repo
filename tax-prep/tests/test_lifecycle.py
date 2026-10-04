"""R13 document-lifecycle state machine tests (Arc C, W1).

Synthetic fixtures only. Covers:
- the declared table: every legal (from, event, actor) triple fires;
  every illegal triple is refused with a reason code, state unchanged
- typed deterministic guards, including the R2/R3/R4 probes from
  msg_edb71a29b39e (any->validated with zero fields; validated ->
  needs_review on re-ingest; carryforward gate keyed on lifecycle)
- actor enforcement: operator-only events unreachable from MCP tools
- no direct `.status =` writes outside taxprep/lifecycle.py
- append-only lifecycle event log (decision_log kind="lifecycle");
  replay reproduces current state
- mermaid view generated from the table; docs/lifecycle.mmd matches
- gold.gate_check lifecycle wiring (validated|excluded pass)
- ingest / review / sync migration through the transition function
"""

import ast
import re
from pathlib import Path

import pytest

import taxprep
from taxprep import gold, ingest, lifecycle, review
from taxprep.ingest import ingest_dir, ingest_file
from taxprep.models import Document
from taxprep.store import DocumentStore

W2_TEXT = (
    "Form W-2 Wage and Tax Statement\n"
    "Tax Year 2024\n"
    "Box 1 Wages, tips, other compensation $10,000.00\n"
    "Box 2 Federal income tax withheld $1,500.00\n"
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _doc_at(state: str | None, **kw) -> Document:
    """A synthetic doc at lifecycle state ``state`` (None = pre-scan)."""
    if state is None:
        return lifecycle.new_document(
            doc_id=kw.get("doc_id", "doc-x"), tax_year=2024,
            form_type="W-2", source_path="", ocr_text_ref="",
            fields={"box1": {"value": "1", "confidence": "high",
                             "raw_text": ""}})
    return Document(doc_id=kw.get("doc_id", "doc-x"), tax_year=2024,
                    form_type="W-2", source_path="", ocr_text_ref="",
                    fields={"box1": {"value": "1", "confidence": "high",
                                     "raw_text": ""}},
                    status=state)


_GOOD_VALIDATE = lifecycle.ValidateInput(
    n_fields=1, form_known=True, year_known=True,
    form_confirmed_or_corrected=True, year_confirmed_or_corrected=True,
    field_confirmed_or_edited=True)

# Canonical inputs per event for the table sweep (chosen so every
# DECLARED row succeeds; illegal triples refuse before guards run).
_CANONICAL = {
    lifecycle.SCAN: lambda: lifecycle.ScanInput(),
    lifecycle.SELECT: lambda: lifecycle.SelectInput(auto=True),
    lifecycle.UNSELECT: lambda: None,
    lifecycle.INGEST: lambda: lifecycle.IngestInput(route="ok", clean=True),
    lifecycle.RE_EXTRACT: lambda: lifecycle.ReextractInput(
        values_differ=False),
    lifecycle.FIX_FORM_YEAR: lambda: lifecycle.FixInput("W-2", 2024),
    lifecycle.VALIDATE: lambda: _GOOD_VALIDATE,
    lifecycle.EXCLUDE: lambda: lifecycle.ExcludeInput("test-reason"),
    lifecycle.SOURCE_MISSING: lambda: None,
}

# Declared rows that need non-canonical inputs to succeed, keyed by
# (from, event, actor) -> (input, expected_target).
_SPECIAL = {
    (lifecycle.DISCOVERED, lifecycle.SELECT, lifecycle.OPERATOR):
        (lifecycle.SelectInput(), lifecycle.SELECTED),
    (lifecycle.SELECTED, lifecycle.INGEST, lifecycle.SYSTEM):
        (lifecycle.IngestInput(route="ok", clean=False),
         lifecycle.NEEDS_REVIEW),
    (lifecycle.MULTI_FORM, lifecycle.INGEST, lifecycle.SYSTEM):
        (lifecycle.IngestInput(route="multiform"), lifecycle.MULTI_FORM),
    (lifecycle.VALIDATED, lifecycle.RE_EXTRACT, lifecycle.SYSTEM):
        (lifecycle.ReextractInput(values_differ=True),
         lifecycle.REREVIEW),
    (lifecycle.REREVIEW, lifecycle.RE_EXTRACT, lifecycle.SYSTEM):
        (lifecycle.ReextractInput(values_differ=False),
         lifecycle.VALIDATED),
}


def _table_index():
    return {(r.from_state, r.event, r.actor): r
            for r in lifecycle.TRANSITION_TABLE}


def test_table_every_declared_row_fires():
    index = _table_index()
    for (from_state, event, actor), row in sorted(
            index.items(), key=lambda kv: str(kv[0])):
        doc = _doc_at(from_state)
        if (from_state, event, actor) in _SPECIAL:
            inp, expected = _SPECIAL[(from_state, event, actor)]
        else:
            inp, expected = _CANONICAL[event](), row.targets[0]
        res = lifecycle.transition(doc, event, actor=actor,
                                   event_input=inp)
        assert res.ok, (from_state, event, actor, res.reason_code)
        assert res.to_state == expected, (from_state, event, actor)
        assert doc.status == expected


def test_table_every_illegal_triple_refused():
    index = _table_index()
    froms = [None, *lifecycle.STATES]
    n_illegal = 0
    for from_state in froms:
        for event in lifecycle.EVENTS:
            for actor in lifecycle.ACTORS:
                if (from_state, event, actor) in index:
                    continue
                n_illegal += 1
                doc = _doc_at(from_state)
                before = doc.status
                res = lifecycle.transition(
                    doc, event, actor=actor,
                    event_input=_CANONICAL[event]())
                assert not res.ok, (from_state, event, actor)
                assert res.reason_code == "illegal_transition"
                assert res.to_state is None
                assert doc.status == before  # unchanged
    assert n_illegal > 100  # the table is sparse; most triples illegal


def test_table_covers_all_states_and_events():
    index = _table_index()
    froms = {r.from_state for r in lifecycle.TRANSITION_TABLE}
    assert froms == {None, *lifecycle.STATES}
    assert {r.event for r in lifecycle.TRANSITION_TABLE} == set(
        lifecycle.EVENTS)
    # every non-terminal state has an exclude row; every state has a
    # source_missing row
    for s in lifecycle.STATES:
        assert (s, lifecycle.SOURCE_MISSING,
                lifecycle.SYSTEM) in index
        if s not in lifecycle.TERMINAL_STATES:
            assert (s, lifecycle.EXCLUDE, lifecycle.OPERATOR) in index
        else:
            assert (s, lifecycle.EXCLUDE,
                    lifecycle.OPERATOR) not in index


# -- guards ---------------------------------------------------------------

@pytest.mark.parametrize("kwargs,code", [
    (dict(n_fields=0), "empty_fields"),
    (dict(form_known=False), "unknown_form"),
    (dict(year_known=False), "missing_year"),
    (dict(form_confirmed_or_corrected=False), "unconfirmed_form"),
    (dict(year_confirmed_or_corrected=False), "unconfirmed_year"),
    (dict(field_confirmed_or_edited=False), "nothing_confirmed"),
])
def test_validate_guard_refusals(kwargs, code):
    base = dict(n_fields=1, form_known=True, year_known=True,
                form_confirmed_or_corrected=True,
                year_confirmed_or_corrected=True,
                field_confirmed_or_edited=True)
    base.update(kwargs)
    doc = _doc_at(lifecycle.NEEDS_REVIEW)
    res = lifecycle.transition(doc, lifecycle.VALIDATE,
                               actor=lifecycle.OPERATOR,
                               event_input=lifecycle.ValidateInput(**base))
    assert not res.ok and res.reason_code == code
    assert doc.status == lifecycle.NEEDS_REVIEW  # unchanged


def test_fix_form_year_guards():
    doc = _doc_at(lifecycle.BLOCKED)
    res = lifecycle.transition(
        doc, lifecycle.FIX_FORM_YEAR, actor=lifecycle.OPERATOR,
        event_input=lifecycle.FixInput("UNKNOWN", 2024))
    assert not res.ok and res.reason_code == "identity_still_unknown_form"
    res = lifecycle.transition(
        doc, lifecycle.FIX_FORM_YEAR, actor=lifecycle.OPERATOR,
        event_input=lifecycle.FixInput("W-2", None))
    assert not res.ok and res.reason_code == "identity_still_missing_year"
    assert doc.status == lifecycle.BLOCKED
    # success applies the identity and clears the block
    doc.status_reason = "no-year"
    res = lifecycle.transition(
        doc, lifecycle.FIX_FORM_YEAR, actor=lifecycle.OPERATOR,
        event_input=lifecycle.FixInput("W-2", 2024))
    assert res.ok and res.to_state == lifecycle.NEEDS_REVIEW
    assert doc.form_type == "W-2" and doc.tax_year == 2024
    assert doc.status_reason is None


def test_exclude_requires_reason():
    doc = _doc_at(lifecycle.NEEDS_REVIEW)
    res = lifecycle.transition(doc, lifecycle.EXCLUDE,
                               actor=lifecycle.OPERATOR,
                               event_input=lifecycle.ExcludeInput("  "))
    assert not res.ok and res.reason_code == "exclude_reason_required"
    assert doc.status == lifecycle.NEEDS_REVIEW


def test_ingest_blocked_requires_reason():
    doc = _doc_at(lifecycle.SELECTED)
    res = lifecycle.transition(
        doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
        event_input=lifecycle.IngestInput(route="blocked"))
    assert not res.ok and res.reason_code == "route_missing_reason"
    assert doc.status == lifecycle.SELECTED


def test_system_select_requires_auto_policy():
    doc = _doc_at(lifecycle.DISCOVERED)
    res = lifecycle.transition(doc, lifecycle.SELECT, actor=lifecycle.SYSTEM,
                               event_input=lifecycle.SelectInput(auto=False))
    assert not res.ok and res.reason_code == "auto_select_disabled"
    assert doc.status == lifecycle.DISCOVERED


def test_operator_events_refused_for_system_actor():
    # There is no (from, event, "system") row for operator-only events
    # (except the guarded auto-select policy row).
    for event, inp in [
        (lifecycle.VALIDATE, _GOOD_VALIDATE),
        (lifecycle.EXCLUDE, lifecycle.ExcludeInput("r")),
        (lifecycle.FIX_FORM_YEAR, lifecycle.FixInput("W-2", 2024)),
        (lifecycle.UNSELECT, None),
    ]:
        doc = _doc_at(lifecycle.NEEDS_REVIEW)
        res = lifecycle.transition(doc, event, actor=lifecycle.SYSTEM,
                                   event_input=inp)
        assert not res.ok and res.reason_code == "illegal_transition", \
            event


def test_unknown_event_and_actor_raise():
    doc = _doc_at(lifecycle.NEEDS_REVIEW)
    with pytest.raises(ValueError):
        lifecycle.transition(doc, "teleport", actor=lifecycle.SYSTEM)
    with pytest.raises(ValueError):
        lifecycle.transition(doc, lifecycle.INGEST, actor="ghost")


# -- R2 / R4 probes ---------------------------------------------------------

def test_r2_zero_fields_cannot_validate():
    # any -> validated with zero fields is refused by construction
    for state in (lifecycle.NEEDS_REVIEW, lifecycle.TRANSCRIBED,
                  lifecycle.REREVIEW):
        doc = _doc_at(state)
        res = lifecycle.transition(
            doc, lifecycle.VALIDATE, actor=lifecycle.OPERATOR,
            event_input=lifecycle.ValidateInput(
                n_fields=0, form_known=True, year_known=True,
                form_confirmed_or_corrected=True,
                year_confirmed_or_corrected=True,
                field_confirmed_or_edited=True))
        assert not res.ok and res.reason_code == "empty_fields"
        assert doc.status == state


def test_r4_reingest_cannot_demote_validated():
    # There is no (validated, ingest) row: re-ingest is re_extract.
    doc = _doc_at(lifecycle.VALIDATED)
    res = lifecycle.transition(doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
                               event_input=lifecycle.IngestInput(route="ok"))
    assert not res.ok and res.reason_code == "illegal_transition"
    assert doc.status == lifecycle.VALIDATED


def test_r4_disagreeing_reextract_keeps_values_goes_rereview():
    fields = {"box1": {"value": "100.00", "confidence": "high",
                       "raw_text": ""}}
    doc = _doc_at(lifecycle.VALIDATED)
    doc.fields = dict(fields)
    res = lifecycle.transition(
        doc, lifecycle.RE_EXTRACT, actor=lifecycle.SYSTEM,
        event_input=lifecycle.ReextractInput(values_differ=True))
    assert res.ok and res.to_state == lifecycle.REREVIEW
    assert doc.status == lifecycle.REREVIEW
    assert doc.fields == fields  # validated values kept
    assert doc.re_review is True
    assert doc.status_reason == "extraction-disagrees"
    # agreeing re-extract from rereview returns to validated
    res = lifecycle.transition(
        doc, lifecycle.RE_EXTRACT, actor=lifecycle.SYSTEM,
        event_input=lifecycle.ReextractInput(values_differ=False))
    assert res.ok and res.to_state == lifecycle.VALIDATED
    assert doc.validated_at is not None and doc.re_review is False


def test_validate_sets_validated_at_deterministically():
    doc = _doc_at(lifecycle.NEEDS_REVIEW)
    res = lifecycle.transition(doc, lifecycle.VALIDATE,
                               actor=lifecycle.OPERATOR,
                               event_input=_GOOD_VALIDATE,
                               now="2026-10-04T00:00:00+00:00")
    assert res.ok and doc.validated_at == "2026-10-04T00:00:00+00:00"


def test_same_state_refire_is_quiet_noop():
    doc = _doc_at(lifecycle.TRANSCRIBED)
    res = lifecycle.transition(
        doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
        event_input=lifecycle.IngestInput(route="ok", clean=True),
        store=None)
    assert res.ok and res.noop and res.to_state == lifecycle.TRANSCRIBED


def test_blocked_reason_change_is_logged_not_noop(tmp_path):
    store = DocumentStore(tmp_path / "data")
    doc = _doc_at(lifecycle.BLOCKED)
    doc.status_reason = "needs-ocr"
    store.upsert(doc)
    res = lifecycle.transition(
        doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
        event_input=lifecycle.IngestInput(route="blocked",
                                         route_reason="encrypted"),
        store=store)
    assert res.ok and not res.noop
    assert doc.status_reason == "encrypted"
    evs = lifecycle.events_for(store, doc_id=doc.doc_id)
    assert len(evs) == 1 and evs[0]["to"] == lifecycle.BLOCKED


# -- structural: single transition function --------------------------------

def test_no_direct_status_writes_outside_lifecycle():
    """Every Document status write goes through lifecycle.transition().

    AST-based: finds real ``x.status = ...`` attribute assignments
    (SQL strings mentioning "status =" do not count). Scoped to the
    shipped package (taxprep/): test fixtures may build docs at
    arbitrary states via the constructor.
    """
    pkg = Path(taxprep.__file__).parent
    offenders = []
    for path in sorted(pkg.glob("*.py")):
        if path.name == "lifecycle.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "status":
                    offenders.append(
                        f"{path.name}:{t.lineno}: "
                        f"{ast.unparse(node).splitlines()[0]}")
    assert not offenders, "\n".join(offenders)


def test_mcp_surface_cannot_fire_operator_events():
    """Operator-only events are unreachable from MCP/agent tools.

    mcp_server.py must not call the transition function at all (it may
    read lifecycle constants), no MCP tool may reference the operator
    actor, and no validate / exclude / select / fix tool may exist.
    """
    from taxprep import mcp_server
    src = Path(mcp_server.__file__).read_text(encoding="utf-8")
    assert "lifecycle.transition" not in src
    tree = ast.parse(src)
    tool_fns = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if "tool" in ast.unparse(dec):
                tool_fns.append(node)
    assert tool_fns, "expected @mcp.tool() functions"
    tool_names = {t.name for t in tool_fns}
    banned = {"validate", "validate_document", "exclude", "select",
              "unselect", "fix_form_year", "fix_identity"}
    assert not (tool_names & banned), tool_names & banned
    for fn in tool_fns:
        fsrc = ast.unparse(fn)
        assert "transition(" not in fsrc, fn.name
    # the shared ingest path (used by the ingest_directory tool) only
    # ever fires system-actor events: no operator event is reachable
    # indirectly through it either.
    from taxprep import ingest as _ingest_mod
    assert "lifecycle.OPERATOR" not in Path(
        _ingest_mod.__file__).read_text(encoding="utf-8")
    # the tools that exist are the blind read-only / ingest set
    assert "ingest_directory" in tool_names
    assert "relevance_override" in tool_names  # not a lifecycle event


def test_operator_surfaces_exist_for_operator_events():
    """Sanity: the operator-only events ARE reachable from the review
    UI and CLI (the surfaces the table names)."""
    review_src = Path(review.__file__).read_text(encoding="utf-8")
    assert "lifecycle.transition" in review_src
    assert "actor=lifecycle.OPERATOR" in review_src
    from taxprep import cli
    cli_src = Path(cli.__file__).read_text(encoding="utf-8")
    assert "lifecycle.EXCLUDE" in cli_src


# -- event log + replay -----------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "data")


def _persist_like_review(store, doc):
    """Persist a transitioned doc the way review.py does."""
    from taxprep import silver
    bronze_hash = silver.bronze_hash_for_doc(store, doc)
    with store.txn():
        if bronze_hash is None:
            store.upsert(doc)
        else:
            silver.persist_silver_doc(
                store, doc, silver.derivation_for_doc(store, doc.doc_id),
                bronze_hash)


def test_event_log_chain_and_replay(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "w2.txt", W2_TEXT)
    (doc,) = ingest_file(src / "w2.txt", store)
    # W2_TEXT extracts with unparsed lines -> needs_review (the exact
    # target is the extractor's call; the table maps it).
    assert doc.status in ("transcribed", "needs_review")
    evs = lifecycle.events_for(store, doc_id=doc.doc_id)
    assert [e["event"] for e in evs] == ["scan", "select", "ingest"]
    assert [e["actor"] for e in evs] == ["system", "system", "system"]
    assert evs[0]["from"] is None and evs[0]["to"] == "discovered"
    assert evs[1]["from"] == "discovered" and evs[1]["to"] == "selected"
    assert evs[2]["from"] == "selected" and evs[2]["to"] == doc.status
    # blind contract: metadata only -- exact key shape, no values
    for e in evs:
        assert set(e) == {"ts", "doc_id", "event", "actor", "from", "to",
                          "reason_code"}
        assert e["doc_id"] == doc.doc_id

    rep = lifecycle.replay_lifecycle(store, doc.doc_id)
    assert rep.ok and rep.n_events == 3
    assert rep.final_state == store.get(doc.doc_id).status == doc.status

    # operator validate through the transition function, then replay
    doc = store.get(doc.doc_id)
    res = lifecycle.transition(
        doc, lifecycle.VALIDATE, actor=lifecycle.OPERATOR,
        event_input=lifecycle.ValidateInput(
            n_fields=2, form_known=True, year_known=True,
            form_confirmed_or_corrected=True,
            year_confirmed_or_corrected=True,
            field_confirmed_or_edited=True),
        store=store)
    assert res.ok
    _persist_like_review(store, doc)
    rep = lifecycle.replay_lifecycle(store, doc.doc_id)
    assert rep.ok and rep.final_state == "validated"
    assert lifecycle.state_of(store, doc.doc_id) == "validated"


def test_replay_detects_chain_breaks(store):
    lifecycle.record_event(store, doc_id="d9", event="ingest",
                           actor="system", from_state="selected",
                           to_state="transcribed", reason_code=None)
    lifecycle.record_event(store, doc_id="d9", event="validate",
                           actor="operator", from_state="needs_review",
                           to_state="validated", reason_code=None)
    rep = lifecycle.replay_lifecycle(store, "d9")
    assert not rep.ok and rep.breaks == [1]
    assert rep.final_state == "validated"


def test_decision_log_is_append_only(store):
    doc = _doc_at(None)
    lifecycle.transition(doc, lifecycle.SCAN, actor=lifecycle.SYSTEM,
                         event_input=lifecycle.ScanInput(), store=store)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE decision_log SET payload_json = '{}' "
            "WHERE kind = 'lifecycle'")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "DELETE FROM decision_log WHERE kind = 'lifecycle'")
    assert len(lifecycle.events_for(store,
                                    doc_id=doc.doc_id)) == 1


def test_state_of_falls_back_to_stored_status_for_legacy_docs(store):
    doc = Document(doc_id="legacy-1", tax_year=2024, form_type="W-2",
                   source_path="", ocr_text_ref="", status="validated")
    store.upsert(doc)
    assert lifecycle.replay_lifecycle(store, "legacy-1").n_events == 0
    assert lifecycle.state_of(store, "legacy-1") == "validated"
    assert lifecycle.state_of(store, "no-such-doc") is None


def test_sibling_entry_points():
    # sources.py (R11/R12) getattr-guards these; they must exist and
    # round-trip the contract shape.
    assert callable(lifecycle.record_event)
    assert callable(lifecycle.events_for)
    assert callable(lifecycle.state_of)


# -- mermaid -----------------------------------------------------------------

def test_mermaid_generated_from_table():
    mm = lifecycle.mermaid()
    assert mm.startswith("stateDiagram-v2\n")
    assert "[*] --> discovered : scan (system)" in mm
    assert "needs_review --> validated : validate (operator)" in mm
    assert "validated --> rereview : re_extract (system)" in mm
    # checked-in rendering matches the generator verbatim
    rendered = Path(taxprep.__file__).parent.parent / "docs" / \
        "lifecycle.mmd"
    assert rendered.read_text(encoding="utf-8") == mm


# -- gold gate wiring (R3 probe: keyed on lifecycle state) --------------------

_DERIV = {"derivation_version": "2", "config_hash": "c" * 64,
          "derivation_digest": "d" * 64}


def _bronze(store, data: bytes, name: str) -> str:
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    store.store_bronze_bytes(sha, data)
    return sha


def _doc1099(store, sha, doc_id, year, status="validated"):
    lot = {"description": None, "date_acquired": "01/15/2024",
           "date_sold": "06/20/2024", "proceeds_1d": "500.00",
           "basis_1e": "1000.00", "wash_1g": None,
           "accrued_market_discount_1f": None, "fed_withheld_4": None,
           "term": "short", "covered": None}
    doc = Document(
        doc_id=doc_id, tax_year=year, form_type="1099-B",
        source_path=f"{doc_id}.pdf", ocr_text_ref=f"ocr/{doc_id}.txt",
        fields={"lots": {"value": [lot], "confidence": "high",
                         "raw_text": ""}},
        status=status, source_sha256=sha)
    store.upsert_silver_doc(doc, **_DERIV)
    return doc


def test_gate_passes_when_all_validated_or_excluded(tmp_path):
    store = DocumentStore(tmp_path / "data")
    sha = _bronze(store, b"gold-a", "a.pdf")
    _doc1099(store, sha, "docA", 2024, status="validated")
    assert gold.gate_check(store, 2024) == []

    # an excluded doc is out of the gate's scope
    doc = store.get("docA")
    res = lifecycle.transition(doc, lifecycle.EXCLUDE,
                               actor=lifecycle.OPERATOR,
                               event_input=lifecycle.ExcludeInput("dup"),
                               store=store)
    assert res.ok
    _persist_like_review(store, doc)
    assert gold.gate_check(store, 2024) == []


@pytest.mark.parametrize("status", [
    "needs_review", "transcribed", "BLOCKED", "errored", "rereview",
    "ORPHANED", "discovered", "selected", "MULTI_FORM",
])
def test_gate_refuses_unvalidated_lifecycle_states(tmp_path, status):
    store = DocumentStore(tmp_path / "data")
    sha = _bronze(store, b"gold-b", "b.pdf")
    _doc1099(store, sha, "docB", 2024, status=status)
    codes = [b["code"] for b in gold.gate_check(store, 2024)]
    assert gold.LIFECYCLE_NOT_READY in codes
    blk = [b for b in gold.gate_check(store, 2024)
           if b["code"] == gold.LIFECYCLE_NOT_READY
           and b["doc_id"] == "docB"]
    assert len(blk) == 1 and blk[0]["status"] == status


def test_gate_ignores_other_years_and_null_year_is_fail_closed(tmp_path):
    store = DocumentStore(tmp_path / "data")
    sha = _bronze(store, b"gold-c", "c.pdf")
    _doc1099(store, sha, "docC", 2023, status="needs_review")
    assert gold.gate_check(store, 2024) == []  # other year: out of scope
    _doc1099(store, sha, "docD", None, status="needs_review")
    codes = [b["code"] for b in gold.gate_check(store, 2024)]
    assert gold.LIFECYCLE_NOT_READY in codes  # NULL year: fail-closed


def test_gate_vocabulary_extended():
    assert "lifecycle_not_ready" in gold.GOLD_REASON_CODES


# -- ingest / review / sync migration ------------------------------------------

def test_ingest_drives_scan_select_ingest(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "w2.txt", W2_TEXT)
    (doc,) = ingest_file(src / "w2.txt", store)
    # W2_TEXT extracts with unparsed lines -> needs_review (the exact
    # target is the extractor's call; the table maps it).
    assert doc.status in ("transcribed", "needs_review")
    evs = lifecycle.events_for(store, doc_id=doc.doc_id)
    assert [e["event"] for e in evs] == ["scan", "select", "ingest"]
    assert evs[-1]["to"] == doc.status
    # re-ingest is an I2 no-op: no new lifecycle events
    ingest_file(src / "w2.txt", store)
    assert len(lifecycle.events_for(store, doc_id=doc.doc_id)) == 3


def test_ingest_error_route_yields_errored(tmp_path, store, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "w2.txt", W2_TEXT)

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(ingest, "_build_documents", _boom)
    rep = ingest_dir(src, store)
    assert rep.errored and rep.docs
    err_doc = rep.docs[0]
    assert err_doc.status == "errored"
    assert err_doc.status_reason == "extract-failed"
    evs = lifecycle.events_for(store, doc_id=err_doc.doc_id)
    assert evs[-1]["to"] == "errored"


def test_sync_orphan_fires_source_missing(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    p = _write(src / "w2.txt", W2_TEXT)
    (doc,) = ingest_file(p, store)
    assert doc.status in ("transcribed", "needs_review")
    p.unlink()
    out = ingest.sync(src, store)
    assert out["orphaned"] == [doc.doc_id]
    assert store.get(doc.doc_id).status == "ORPHANED"
    evs = lifecycle.events_for(store, doc_id=doc.doc_id)
    assert evs[-1]["event"] == "source_missing"
    assert evs[-1]["from"] == doc.status
    assert evs[-1]["to"] == "ORPHANED"
    rep = lifecycle.replay_lifecycle(store, doc.doc_id)
    assert rep.ok and rep.final_state == "ORPHANED"


def test_review_validates_blocked_doc_via_fix_then_validate(tmp_path,
                                                            monkeypatch):
    store = DocumentStore(tmp_path / "data")
    doc = Document(
        doc_id="blocked-1", tax_year=None, form_type="UNKNOWN",
        source_path="/tmp/b.pdf", ocr_text_ref="",
        fields={"box1": {"value": "10", "confidence": "high",
                         "raw_text": "Box 1 10"}},
        status="BLOCKED", status_reason="no-year")
    doc.ocr_text_ref = store.save_ocr(doc.doc_id, "text")
    store.upsert(doc)
    monkeypatch.setattr(review, "evidence_status",
                        lambda s, d: {"mode": "text"})
    out = review.apply_validation(
        store, "blocked-1", {}, ["box1"],
        form_type="W-2", tax_year=2024)
    assert out.status == "validated"
    assert out.form_type == "W-2" and out.tax_year == 2024
    evs = lifecycle.events_for(store, doc_id="blocked-1")
    assert [(e["event"], e["from"], e["to"]) for e in evs] == [
        ("fix_form_year", "BLOCKED", "needs_review"),
        ("validate", "needs_review", "validated"),
    ]


def test_review_validate_still_refuses_empty_fields(tmp_path, monkeypatch):
    store = DocumentStore(tmp_path / "data")
    doc = Document(doc_id="empty-1", tax_year=2024, form_type="W-2",
                   source_path="", ocr_text_ref="", fields={},
                   status="needs_review")
    store.upsert(doc)
    monkeypatch.setattr(review, "evidence_status",
                        lambda s, d: {"mode": "text"})
    with pytest.raises(review.ValidationRefused) as ei:
        review.apply_validation(store, "empty-1", {}, [],
                                confirm_form_type=True,
                                confirm_tax_year=True)
    assert "empty_fields" in ei.value.reasons
    assert store.get("empty-1").status == "needs_review"


def test_cli_exclude_moves_doc_to_excluded(tmp_path, monkeypatch):
    from taxprep import cli
    data = tmp_path / "data"
    store = DocumentStore(data)
    doc = Document(doc_id="ex-1", tax_year=2024, form_type="W-2",
                   source_path="", ocr_text_ref="",
                   fields={"box1": {"value": "1", "confidence": "high",
                                    "raw_text": ""}},
                   status="transcribed")
    store.upsert(doc)
    monkeypatch.setattr(cli.taxprep_config, "resolve",
                        lambda *a, **k: str(data))
    args = type("A", (), {"data_dir": None, "doc_id": "ex-1",
                          "reason": "duplicate of ex-2"})()
    assert cli.cmd_exclude(args) == 0
    assert store.get("ex-1").status == "excluded"
    evs = lifecycle.events_for(store, doc_id="ex-1")
    assert evs[-1]["event"] == "exclude"
    assert evs[-1]["actor"] == "operator"
    assert evs[-1]["to"] == "excluded"
    # gold gate passes for the excluded doc
    assert gold.gate_check(store, 2024) == []
