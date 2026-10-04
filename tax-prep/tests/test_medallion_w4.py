"""W4 (Arc B) tests: gated gold, input digests, blind audit.

All fixtures synthetic. Every gold output asserted PII-free via the
recursive blind-orchestrator sweep (extended to gate_check,
gated_carryforward, and blind_audit).

dup_group / conflict rows are written with direct SQL: W3's
duplicates.py writers are not in the tree yet, so these fixtures own
the contract-§3 tables they need. When duplicates.py lands, its
writers must produce rows these tests' gate logic already assumes
(group status open/disposed, dup_member.role agree/disagree for
corroboration).
"""

import hashlib
import json
import re
from decimal import Decimal

import pytest

from taxprep import gold
from taxprep.models import Document
from taxprep.mstore import MedallionStore
from taxprep import cli as CLI

DERIV = {"derivation_version": "2",
         "config_hash": "c" * 64,
         "derivation_digest": "d" * 64}

NOW = "2026-10-03T00:00:00+00:00"


def _store(tmp_path):
    return MedallionStore(tmp_path / "data")


def _bronze(store, data: bytes, names):
    """One bronze object seen at len(names) paths (aliases)."""
    sha = hashlib.sha256(data).hexdigest()
    store.store_bronze_bytes(sha, data)
    for n in names:
        p = store.data_dir / n
        p.write_bytes(data)
        store.add_alias(sha, str(p))
    return sha


def _lot(proceeds="500.00", basis="1000.00", term="short"):
    return {
        "description": None,
        "date_acquired": "01/15/2024",
        "date_sold": "06/20/2024",
        "proceeds_1d": proceeds,
        "basis_1e": basis,
        "wash_1g": None,
        "accrued_market_discount_1f": None,
        "fed_withheld_4": None,
        "term": term,
        "covered": None,
    }


def _doc1099(store, sha, doc_id, year, lots, status="validated",
             summary_totals=None, status_reason=None):
    fields = {"lots": {"value": lots, "confidence": "high", "raw_text": ""}}
    if summary_totals is not None:
        fields["summary_totals"] = {"value": summary_totals,
                                    "confidence": "high", "raw_text": ""}
    doc = Document(
        doc_id=doc_id,
        tax_year=year,
        form_type="1099-B",
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields,
        status=status,
        validated_at=NOW if status == "validated" else None,
        source_sha256=sha,  # upsert_silver_doc keys bronze_hash off this
        status_reason=status_reason,
    )
    store.upsert_silver_doc(doc, **DERIV)
    return doc


def _dup_group(store, group_id, class_, members, status="open"):
    """members: list of (member_key, role). Direct SQL (W3 writers pending)."""
    with store.txn():
        store._conn.execute(
            "INSERT INTO dup_group (group_id, class, status, created_at) "
            "VALUES (?, ?, ?, ?)", (group_id, class_, status, NOW))
        for key, role in members:
            store._conn.execute(
                "INSERT INTO dup_member (group_id, member_key, role) "
                "VALUES (?, ?, ?)", (group_id, key, role))


def _conflict(store, conflict_id, class_, field, options, status="open"):
    """options: list of (option_key, value_json, evidence_ref)."""
    with store.txn():
        store._conn.execute(
            "INSERT INTO conflict (conflict_id, class, field, status, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (conflict_id, class_, field, status, NOW))
        for key, value_json, evidence_ref in options:
            store._conn.execute(
                "INSERT INTO conflict_option (conflict_id, option_key, "
                "value_json, evidence_ref) VALUES (?, ?, ?, ?)",
                (conflict_id, key, value_json, evidence_ref))


def _pii_free(obj):
    """Recursive blind-orchestrator sweep: no value/raw_text keys, no $N."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key leaked: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        assert not re.search(r"\$\d", obj), f"money pattern leaked: {obj[:60]!r}"


def _codes(blockers):
    return [b["code"] for b in blockers]


# -- gate: duplicates --------------------------------------------------

def test_gate_refuses_open_l2_then_ruling_disposes(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-copy-a", ["a.pdf"])
    sha_b = _bronze(store, b"synthetic-copy-b-same-text", ["b.pdf"])
    _doc1099(store, sha_a, "docA", 2024, [_lot()])
    _doc1099(store, sha_b, "docB", 2024, [_lot()])
    _dup_group(store, "g-l2", "L2", [(sha_a, "candidate"),
                                     (sha_b, "candidate")])

    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["unresolved_duplicate"]
    assert blockers[0]["group_id"] == "g-l2"
    assert blockers[0]["n_docs"] == 2
    _pii_free(blockers)

    with pytest.raises(gold.GoldRefused) as ei:
        gold.gated_carryforward(store, 2024)
    assert ei.value.reason_codes[0]["code"] == "unresolved_duplicate"
    assert all(set(r) >= {"code", "detail"} for r in ei.value.reason_codes)

    # The operator's duplicate_ruling disposes the group: gate passes.
    store.log_decision(actor="operator", kind="duplicate_ruling",
                       group_id="g-l2",
                       payload={"group_id": "g-l2", "ruling": "keep_one",
                                "primary": sha_a})
    with store.txn():
        store._conn.execute(
            "UPDATE dup_group SET status='disposed', disposed_at=? "
            "WHERE group_id='g-l2'", (NOW,))
    assert gold.gate_check(store, 2024) == []
    r = gold.gated_carryforward(store, 2024)
    # keep_one: only the primary counts -- the duplicate is ruled out of
    # gold's input (a "distinct" ruling would count both: -1000.00).
    assert r["st_current"] == Decimal("-500.00")
    assert r["lots_included"] == 1


def test_gate_distinct_ruling_counts_both(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-copy-a", ["a.pdf"])
    sha_b = _bronze(store, b"synthetic-copy-b-same-text", ["b.pdf"])
    _doc1099(store, sha_a, "docA", 2024, [_lot()])
    _doc1099(store, sha_b, "docB", 2024, [_lot()])
    _dup_group(store, "g-l2", "L2", [(sha_a, "candidate"),
                                     (sha_b, "candidate")])
    # The operator rules both copies real: gold counts both.
    store.log_decision(actor="operator", kind="duplicate_ruling",
                       group_id="g-l2",
                       payload={"group_id": "g-l2", "ruling": "distinct",
                                "primary": None})
    with store.txn():
        store._conn.execute(
            "UPDATE dup_group SET status='disposed', disposed_at=? "
            "WHERE group_id='g-l2'", (NOW,))
    assert gold.gate_check(store, 2024) == []
    r = gold.gated_carryforward(store, 2024)
    assert r["st_current"] == Decimal("-1000.00")
    assert r["lots_included"] == 2


def test_gate_refuses_open_supersedes(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-orig", ["orig.pdf"])
    sha_b = _bronze(store, b"synthetic-corrected", ["corr.pdf"])
    _doc1099(store, sha_a, "docA", 2024, [_lot()])
    _doc1099(store, sha_b, "docB", 2024, [_lot()])
    _dup_group(store, "g-sup", "supersedes", [(sha_a, "candidate"),
                                              (sha_b, "candidate")])
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["unresolved_supersedes"]
    _pii_free(blockers)


def test_open_group_for_other_year_does_not_block(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-y23-a", ["a23.pdf"])
    sha_b = _bronze(store, b"synthetic-y23-b", ["b23.pdf"])
    _doc1099(store, sha_a, "docA", 2023, [_lot()])
    _doc1099(store, sha_b, "docB", 2023, [_lot()])
    _dup_group(store, "g23", "L2", [(sha_a, "candidate"),
                                    (sha_b, "candidate")])
    sha_c = _bronze(store, b"synthetic-y24", ["c24.pdf"])
    _doc1099(store, sha_c, "docC", 2024, [_lot()])
    assert gold.gate_check(store, 2024) == []
    assert _codes(gold.gate_check(store, 2023)) == ["unresolved_duplicate"]


# -- gate: corroboration agreement ---------------------------------------

def test_open_corroboration_all_agree_does_not_block(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-cor-a", ["ca.pdf"])
    sha_b = _bronze(store, b"synthetic-cor-b", ["cb.pdf"])
    _doc1099(store, sha_a, "docA", 2024, [_lot()])
    _doc1099(store, sha_b, "docB", 2024, [_lot()])
    _dup_group(store, "g-cor", "corroboration",
               [(sha_a, "agree"), (sha_b, "agree")])
    assert gold.gate_check(store, 2024) == []


def test_open_corroboration_with_disagreement_blocks(tmp_path):
    store = _store(tmp_path)
    sha_a = _bronze(store, b"synthetic-cor2-a", ["c2a.pdf"])
    sha_b = _bronze(store, b"synthetic-cor2-b", ["c2b.pdf"])
    _doc1099(store, sha_a, "docA", 2024, [_lot()])
    _doc1099(store, sha_b, "docB", 2024, [_lot()])
    _dup_group(store, "g-cor2", "corroboration",
               [(sha_a, "agree"), (sha_b, "disagree")])
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["unresolved_conflict"]
    assert blockers[0]["group_id"] == "g-cor2"
    assert blockers[0]["n_disagreeing"] == 1
    _pii_free(blockers)


# -- gate: conflicts -----------------------------------------------------

def test_gate_refuses_open_conflict(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-conf", ["cf.pdf"])
    _doc1099(store, sha, "docA", 2024, [_lot()])
    _conflict(store, "c1", "duplicate", "lots",
              [("opt-a", '"a"', "docA"), ("opt-b", '"b"', "docA")])
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["unresolved_conflict"]
    assert blockers[0]["conflict_id"] == "c1"
    _pii_free(blockers)
    with pytest.raises(gold.GoldRefused):
        gold.gated_carryforward(store, 2024)


def test_conflict_with_unresolvable_scope_blocks_every_year(tmp_path):
    # Fail-closed: evidence that resolves to nothing blocks all years.
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-conf2", ["cf2.pdf"])
    _doc1099(store, sha, "docA", 2024, [_lot()])
    _conflict(store, "c9", "ocr", "proceeds_1d",
              [("opt-a", '"a"', "artifact-that-does-not-exist")])
    assert _codes(gold.gate_check(store, 2024)) == ["unresolved_conflict"]
    assert _codes(gold.gate_check(store, 2025)) == ["unresolved_conflict"]


# -- gate: blocked docs ----------------------------------------------------

def test_gate_refuses_blocked_doc_exactly_once(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-blocked", ["bl.pdf"])
    with store.txn():
        store._conn.execute(
            "UPDATE bronze SET blocked_reason='needs-ocr' WHERE hash=?",
            (sha,))
    _doc1099(store, sha, "docB", 2024, [], status="BLOCKED",
             status_reason="needs-ocr")
    blockers = gold.gate_check(store, 2024)
    blocked = [b for b in blockers if b["code"] == "blocked_document"]
    assert len(blocked) == 1  # direct check + G2 wire-through deduped
    assert blocked[0]["doc_id"] == "docB"
    _pii_free(blockers)


# -- gate: G2 wire-through ---------------------------------------------------

def test_g2_incomplete_lot_wired_through(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-inc", ["inc.pdf"])
    _doc1099(store, sha, "docI", 2024,
             [_lot(proceeds="500.00", basis=None)])  # missing basis
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["incomplete_lot"]
    assert blockers[0]["g2_reason"] == "lot_missing_amounts"
    assert blockers[0]["doc_id"] == "docI"
    _pii_free(blockers)
    with pytest.raises(gold.GoldRefused) as ei:
        gold.gated_carryforward(store, 2024)
    assert ei.value.reason_codes[0]["code"] == "incomplete_lot"


def test_g2_unknown_term_wired_through(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-term", ["tm.pdf"])
    _doc1099(store, sha, "docT", 2024, [_lot(term="mystery")])
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["incomplete_lot"]
    assert blockers[0]["g2_reason"] == "lot_term_unknown"


def test_g2_doc_level_decision_log_exclusion_honored(tmp_path):
    # A doc-level decision-log exclusion behaves like a file-based
    # Operator exclusion: the doc leaves gold's guard and sums (no
    # blocker, no permanent excluded_lot).
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-exc", ["ex.pdf"])
    _doc1099(store, sha, "docX", 2024, [_lot()])
    store.log_decision(actor="operator", kind="exclude", doc_id="docX",
                       payload={"doc_id": "docX",
                                "reason": "superseded by corrected filing"})
    assert gold.gate_check(store, 2024) == []
    r = gold.gated_carryforward(store, 2024)
    assert r["lots_included"] == 0
    _pii_free(r)


def test_g2_artifact_level_exclusion_still_fail_closed(tmp_path):
    # An ARTIFACT-level decision-log exclusion cannot be honored by the
    # sum path yet: the gate refuses loudly instead of mis-summing.
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-exc2", ["ex2.pdf"])
    _doc1099(store, sha, "docY", 2024, [_lot()])
    aid = "f" * 32
    with store.txn():
        store._conn.execute(
            "INSERT INTO silver_artifact (artifact_id, doc_id, bronze_hash,"
            " page, artifact_type, anchor, value_json, derivation_version,"
            " config_hash, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,"
            "?,?,?)",
            (aid, "docY", sha, 0, "lot", "lot:0", "{}", "2", "cfg",
             NOW, NOW))
    store.log_decision(actor="operator", kind="exclude", doc_id="docY",
                       artifact_id=aid,
                       payload={"doc_id": "docY", "artifact_id": aid,
                                "reason": "bad lot"})
    blockers = gold.gate_check(store, 2024)
    assert _codes(blockers) == ["excluded_lot"]
    assert blockers[0]["doc_id"] == "docY"
    _pii_free(blockers)


# -- input digest ------------------------------------------------------------

def _clean_store(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-clean", ["cl.pdf"])
    _doc1099(store, sha, "docC", 2024, [_lot()],
             summary_totals={"short": {"proceeds_1d": "500.00",
                                       "basis_1e": "1000.00"}})
    return store


def test_input_digest_stable_across_recompute(tmp_path):
    store = _clean_store(tmp_path)
    params = {"filing_status": "single", "prior_st": "0", "prior_lt": "0"}
    r1 = gold.gated_carryforward(store, 2024, params=params)
    r2 = gold.gated_carryforward(store, 2024, params=params)
    assert r1["gold"]["input_digest"] == r2["gold"]["input_digest"]
    assert r1["gold"]["output_digest"] == r2["gold"]["output_digest"]
    assert r1["gold"]["run_id"] != r2["gold"]["run_id"]  # distinct runs
    n = store._conn.execute(
        "SELECT COUNT(*) FROM gold_run").fetchone()[0]
    assert n == 2
    _pii_free(r1)
    _pii_free(r2)


def test_input_digest_differs_on_params(tmp_path):
    store = _clean_store(tmp_path)
    h1 = gold.input_digest_for(store, 2024, {"note": "a"})
    h2 = gold.input_digest_for(store, 2024, {"note": "b"})
    assert h1 != h2
    assert len(h1) == 64 and len(h2) == 64


def test_input_digest_covers_decisions(tmp_path):
    store = _clean_store(tmp_path)
    h1 = gold.input_digest_for(store, 2024, {})
    store.log_decision(actor="operator", kind="relevance_override",
                       doc_id="docC",
                       payload={"doc_id": "docC", "verdict": "relevant",
                                "reason": "test"})
    h2 = gold.input_digest_for(store, 2024, {})
    assert h1 != h2  # decisions are part of the gold input


def test_input_digest_dedupes_bronze_hash(tmp_path):
    # Two silver_docs on one bronze hash (L1-merged aliases) count once.
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-merge", ["m1.pdf", "m2.pdf"])
    _doc1099(store, sha, "docM1", 2024, [_lot()])
    _doc1099(store, sha, "docM2", 2024, [_lot()])
    h_both = gold.input_digest_for(store, 2024, {})
    with store.txn():
        store._conn.execute("DELETE FROM silver_doc WHERE doc_id='docM2'")
    h_one = gold.input_digest_for(store, 2024, {})
    assert h_both == h_one


# -- E2 probe ------------------------------------------------------------------

def test_e2_probe_two_copies_same_bytes_single_count(tmp_path):
    # R16 E2: identical bytes under two paths -> one bronze, two aliases,
    # one silver doc; gold counts the lots once: -500.00, lots_included=1.
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-e2-bytes", ["feb.pdf", "mar.pdf"])
    n_aliases = store._conn.execute(
        "SELECT COUNT(*) FROM bronze_alias WHERE hash=?", (sha,)).fetchone()[0]
    assert n_aliases == 2
    _doc1099(store, sha, "docE2", 2024, [_lot("500.00", "1000.00", "short")])
    assert gold.gate_check(store, 2024) == []
    r = gold.gated_carryforward(store, 2024)
    assert r["st_current"] == Decimal("-500.00")
    assert r["lt_current"] == Decimal("0")
    assert r["lots_included"] == 1
    assert r["gold"]["input_digest"] is not None
    assert len(r["gold"]["output_digest"]) == 64
    _pii_free(r)


# -- blind audit -----------------------------------------------------------------

def test_blind_audit_clean_store_passes_all(tmp_path):
    store = _clean_store(tmp_path)
    audit = gold.blind_audit(store, 2024)
    assert set(audit) == {"bronze_accounted", "files_accounted",
                          "lot_sums_reconciled", "gold_inputs_validated",
                          "zero_unresolved_before_gold"}
    for name, inv in audit.items():
        assert inv["status"] == "pass", f"{name} failed: {inv}"
    audit_all = gold.blind_audit(store)
    assert all(v["status"] == "pass" for v in audit_all.values())
    _pii_free(audit)
    _pii_free(audit_all)


def test_blind_audit_bronze_accounted(tmp_path):
    store = _store(tmp_path)
    sha_orphan = _bronze(store, b"synthetic-orphan", ["o.pdf"])
    sha_ok = _bronze(store, b"synthetic-ok", ["ok.pdf"])
    _doc1099(store, sha_ok, "docO", 2024, [_lot()])
    inv = gold.blind_audit(store, 2024)["bronze_accounted"]
    assert inv["status"] == "fail"
    assert inv["unaccounted_hashes"] == [sha_orphan]
    assert inv["n_unaccounted"] == 1
    _pii_free(inv)

    # A blocked bronze (no silver docs) is accounted.
    with store.txn():
        store._conn.execute(
            "UPDATE bronze SET blocked_reason='encrypted' WHERE hash=?",
            (sha_orphan,))
    inv2 = gold.blind_audit(store, 2024)["bronze_accounted"]
    assert inv2["status"] == "pass"
    assert inv2["n_blocked"] == 1


def test_blind_audit_files_accounted(tmp_path):
    store = _clean_store(tmp_path)
    inv = gold.blind_audit(store)["files_accounted"]
    assert inv["status"] == "pass"
    assert inv["n_aliases"] == 1 and inv["n_bytes_refs"] == 1
    _pii_free(inv)

    # Simulate a lost content-addressed copy: fail, naming the hash.
    sha = next(iter(
        r[0] for r in store._conn.execute("SELECT hash FROM bronze")))
    with store.txn():
        store._conn.execute("DELETE FROM bronze_bytes_ref WHERE hash=?",
                            (sha,))
    inv2 = gold.blind_audit(store)["files_accounted"]
    assert inv2["status"] == "fail"
    assert inv2["missing_bytes_ref"] == [sha]


def test_blind_audit_lot_sums(tmp_path):
    # Reconciled totals -> pass.
    store = _clean_store(tmp_path)
    inv = gold.blind_audit(store, 2024)["lot_sums_reconciled"]
    assert inv["status"] == "pass"
    assert inv["n_evaluated"] == 1

    # Mismatched totals -> fail with the doc id (metadata only).
    store2 = _store(tmp_path / "t2")
    sha = _bronze(store2, b"synthetic-mis", ["mm.pdf"])
    _doc1099(store2, sha, "docMM", 2024, [_lot("500.00", "1000.00", "short")],
             summary_totals={"short": {"proceeds_1d": "500.00",
                                       "basis_1e": "999.00"}})
    inv2 = gold.blind_audit(store2, 2024)["lot_sums_reconciled"]
    assert inv2["status"] == "fail"
    assert inv2["mismatched_ids"] == ["docMM"]

    # No statement totals -> not_evaluated, never a vacuous pass.
    store3 = _store(tmp_path / "t3")
    sha3 = _bronze(store3, b"synthetic-no-tot", ["nt.pdf"])
    _doc1099(store3, sha3, "docNT", 2024, [_lot()])
    inv3 = gold.blind_audit(store3, 2024)["lot_sums_reconciled"]
    assert inv3["status"] == "not_evaluated"
    assert inv3["not_evaluated_ids"] == ["docNT"]
    _pii_free(inv3)


def test_blind_audit_gold_inputs_validated(tmp_path):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-unval", ["uv.pdf"])
    _doc1099(store, sha, "docU", 2024, [_lot()], status="transcribed")
    inv = gold.blind_audit(store, 2024)["gold_inputs_validated"]
    assert inv["status"] == "fail"
    assert inv["unvalidated_ids"] == ["docU"]
    _pii_free(inv)


def test_blind_audit_zero_unresolved(tmp_path):
    store = _clean_store(tmp_path)
    assert gold.blind_audit(store, 2024)["zero_unresolved_before_gold"][
        "status"] == "pass"
    sha = _bronze(store, b"synthetic-z2", ["z2.pdf"])
    sha2 = _bronze(store, b"synthetic-z3", ["z3.pdf"])
    _doc1099(store, sha, "docZ", 2024, [_lot()])
    _doc1099(store, sha2, "docZ2", 2024, [_lot()])
    _dup_group(store, "gz", "L2", [(sha, "candidate"), (sha2, "reference")])
    inv = gold.blind_audit(store, 2024)["zero_unresolved_before_gold"]
    assert inv["status"] == "fail"
    assert inv["open_group_ids"] == ["gz"]
    _pii_free(inv)


# -- CLI hunk ----------------------------------------------------------------------

def _cli_args(**kw):
    import argparse
    ns = argparse.Namespace(year=2024, filing_status="single",
                            prior_st="0", prior_lt="0", data_dir=None)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_cli_carryforward_routes_through_gate(tmp_path, monkeypatch, capsys):
    store = _clean_store(tmp_path)
    monkeypatch.setattr(CLI, "_store", lambda dd: store)
    rc = CLI.cmd_carryforward(_cli_args())
    assert rc == 0
    out = capsys.readouterr().out
    assert "gold input_digest" in out  # the gate's digest is observable


def test_cli_carryforward_refusal_is_loud(tmp_path, monkeypatch, capsys):
    store = _store(tmp_path)
    sha = _bronze(store, b"synthetic-cli-block", ["cb.pdf"])
    _doc1099(store, sha, "docCB", 2024, [_lot(basis=None)])
    monkeypatch.setattr(CLI, "_store", lambda dd: store)
    rc = CLI.cmd_carryforward(_cli_args())
    assert rc != 0
    err = capsys.readouterr().err
    assert "gold refused" in err
    assert "[incomplete_lot]" in err


# -- reason-code vocabulary ----------------------------------------------------------

def test_gold_refused_vocabulary(tmp_path):
    assert set(gold.GOLD_REASON_CODES) == {
        "unresolved_duplicate", "unresolved_supersedes",
        "unresolved_conflict", "blocked_document",
        "excluded_lot", "incomplete_lot",
    }
    exc = gold.GoldRefused([{"code": "unresolved_duplicate",
                             "detail": "d"}])
    assert exc.reason_codes == [{"code": "unresolved_duplicate",
                                 "detail": "d"}]
    assert "unresolved_duplicate" in str(exc)
