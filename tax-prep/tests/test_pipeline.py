"""Workstream G tests: pipeline stage registry, corrected order, the
validated=>relevant falsification fix, the override path, queue
filtering (CLI + MCP), and the PII-free sweep on the new/changed tools.

All fixtures synthetic. `pipeline run` executes only against the real
functions (ingest_dir, assess_relevance, verify_all, compute_chain);
REVIEW is human and is never executed.
"""

import json
import re

import pytest

from taxprep import mcp_server
from taxprep.cli import main as cli_main
from taxprep.models import Document
from taxprep.pipeline import (
    GAP_ANALYSIS,
    RUN_SEQUENCE,
    STAGES,
    check_registry,
    registry,
    run_pipeline,
    slice_sequence,
)
from taxprep.relevance import (
    _load_overrides,
    assess_relevance,
    relevance_override,
    summarize,
)
from taxprep.review import queue_html
from taxprep.store import DocumentStore


# -- fixtures ----------------------------------------------------------

def _doc(doc_id, year, form, status="transcribed", relevance="unassessed",
         fields=None):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form,
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields=fields or {},
        status=status,
        relevance=relevance,
    )


def _store_with(tmp_path, docs, name="data"):
    store = DocumentStore(tmp_path / name)
    for d in docs:
        store.upsert(d)
    return store


def _passing_store(tmp_path):
    """Fixtures VERIFICATION passes on: validated 1040s (no 1099-B lots,
    so lot integrity and transcript reconciliation pass vacuously)."""
    return _store_with(tmp_path, [
        _doc("r1040-24", 2024, "1040", status="validated"),
        _doc("r1040-25", 2025, "1040", status="validated"),
    ])


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


# -- registry ----------------------------------------------------------

def test_registry_order_kinds_and_content():
    check_registry()  # structural sanity
    names = [s["name"] for s in STAGES]
    assert names == ["INGESTION", "CLASSIFICATION", "EXTRACTION",
                     "RELEVANCE", "REVIEW", "VALIDATION",
                     "VERIFICATION", "CARRYFORWARD"]
    kinds = {s["name"]: s["kind"] for s in STAGES}
    assert kinds["REVIEW"] == "human"
    for n in names:
        if n != "REVIEW":
            assert kinds[n] == "mechanical", n
    for s in registry():
        assert s["title"] and s["description"] and s["kind"]
        assert s["kind"] in ("mechanical", "human", "analysis")
    # GAP_ANALYSIS rides alongside, after the eight, not in the run sequence
    full = registry()
    assert full[-1]["name"] == "GAP_ANALYSIS"
    assert GAP_ANALYSIS["kind"] == "analysis"
    assert "GAP_ANALYSIS" not in RUN_SEQUENCE
    assert len(RUN_SEQUENCE) == 8


def test_slice_sequence():
    sub = slice_sequence("classification", "relevance")
    assert [s["name"] for s in sub] == ["CLASSIFICATION", "EXTRACTION",
                                        "RELEVANCE"]
    assert [s["name"] for s in slice_sequence()] == RUN_SEQUENCE
    assert [s["name"] for s in slice_sequence(to_stage="ingestion")] == \
        ["INGESTION"]
    with pytest.raises(ValueError, match="unknown stage"):
        slice_sequence("nope")
    with pytest.raises(ValueError, match="comes after"):
        slice_sequence("verification", "ingestion")


# -- pipeline run --------------------------------------------------------

def test_pipeline_run_executes_mechanical_stages_with_banners(tmp_path):
    store = _passing_store(tmp_path)
    src = tmp_path / "src"
    src.mkdir()  # empty: INGESTION sees 0 files, idempotent
    lines: list[str] = []
    result = run_pipeline(store, input_dir=str(src), scope_years=[2024, 2025],
                          out=lines.append)
    assert result["ok"] is True
    assert result["failed_stage"] is None
    text = "\n".join(lines)
    # banners in the corrected order, numbered against the full sequence
    banners = re.findall(r"── STAGE (\d)/8: (\w+) ──", text)
    assert [b[1] for b in banners] == RUN_SEQUENCE
    assert [int(b[0]) for b in banners] == list(range(1, 9))
    # RELEVANCE runs before REVIEW (the corrected order)
    assert text.index("STAGE 4/8: RELEVANCE") < text.index("STAGE 5/8: REVIEW")
    # the human stage is skipped with an OPERATOR STEP marker, never executed
    assert "STAGE 5/8: REVIEW" in text
    review_entry = result["stages"][4]
    assert review_entry == {"name": "REVIEW", "status": "skipped",
                            "marker": "operator-step"}
    assert "OPERATOR STEP" in text
    # RELEVANCE persisted labels on every doc (no_silent_drops will pass)
    assert all(store.get(d.doc_id).relevance != "unassessed"
               for d in store.list())
    # VERIFICATION really ran and passed
    ver = result["stages"][6]
    assert ver["name"] == "VERIFICATION" and ver["status"] == "ok"
    assert ver["summary"]["passed"] is True
    # CARRYFORWARD chained the scope years
    cf = result["stages"][7]
    assert cf["summary"]["years"] == [2024, 2025]
    assert cf["summary"]["status"] == "ok"


def test_pipeline_run_fails_fast_at_verification(tmp_path):
    store = _store_with(tmp_path, [
        _doc("r1040-24", 2024, "1040", status="validated"),
        _doc("w2-24", 2024, "W-2", status="transcribed"),  # blocks the gate
    ])
    src = tmp_path / "src"
    src.mkdir()
    lines: list[str] = []
    result = run_pipeline(store, input_dir=str(src), scope_years=[2024],
                          out=lines.append)
    assert result["ok"] is False
    assert result["failed_stage"] == "VERIFICATION"
    text = "\n".join(lines)
    assert "STAGE 7/8: VERIFICATION" in text
    assert "STAGE 8/8: CARRYFORWARD" not in text  # fail fast: never ran
    assert "checks_failed" in text


def test_pipeline_run_slice_and_validation_checkpoint(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-24", 2024, "W-2", status="transcribed"),
    ])
    src = tmp_path / "src"
    src.mkdir()
    lines: list[str] = []
    result = run_pipeline(store, input_dir=str(src), scope_years=[2024],
                          from_stage="classification", to_stage="validation",
                          out=lines.append)
    assert result["ok"] is True
    text = "\n".join(lines)
    assert "STAGE 2/8: CLASSIFICATION" in text
    assert "STAGE 6/8: VALIDATION" in text
    assert "STAGE 1/8" not in text and "STAGE 7/8" not in text
    # VALIDATION is a checkpoint: the queue is non-empty, so the human's
    # work is flagged with an OPERATOR STEP marker, not executed
    val = result["stages"][-1]
    assert val["status"] == "ok"
    assert val["summary"]["marker"] == "operator-step"
    assert "OPERATOR STEP" in text
    assert store.get("w2-24").status == "transcribed"  # untouched


def test_verify_no_silent_drops_passes_after_relevance(tmp_path):
    from taxprep.verify import verify_no_silent_drops

    store = _store_with(tmp_path, [_doc("w2-24", 2024, "W-2")])
    assert verify_no_silent_drops(store)["passed"] is False
    run_pipeline(store, input_dir=None, scope_years=[2024],
                 from_stage="RELEVANCE", to_stage="RELEVANCE",
                 out=lambda _l: None)
    assert verify_no_silent_drops(store)["passed"] is True


def test_pipeline_run_needs_input_dir_for_ingestion_slice(tmp_path):
    store = _passing_store(tmp_path)
    lines: list[str] = []
    result = run_pipeline(store, input_dir=None, scope_years=[2024, 2025],
                          to_stage="INGESTION", out=lines.append)
    assert result["ok"] is False
    assert result["failed_stage"] == "INGESTION"
    assert "no_input_dir" in result["stages"][0]["reason"]


# -- falsification fix: validated => relevant ---------------------------

def test_validated_doc_is_never_irrelevant(tmp_path):
    store = _store_with(tmp_path, [
        # out of scope AND a duplicate: every mechanical rule says drop it
        _doc("old-dup", 2019, "W-2", status="validated"),
    ])
    # make a second doc with byte-identical OCR so old-dup is a duplicate
    d2 = _doc("old-dup-2", 2019, "W-2", status="transcribed")
    store.upsert(d2)
    (store.ocr_dir / "old-dup.txt").write_text("identical text",
                                              encoding="utf-8")
    (store.ocr_dir / "old-dup-2.txt").write_text("identical text",
                                                 encoding="utf-8")
    verdicts = assess_relevance(store, [2023, 2024, 2025, 2026], persist=True)
    assert verdicts["old-dup"]["verdict"] == "relevant"
    assert verdicts["old-dup"]["reasons"] == ["validated_by_operator"]
    assert store.get("old-dup").relevance == "relevant"
    # the non-validated duplicate is still dropped by the mechanical rule
    assert verdicts["old-dup-2"]["verdict"] == "irrelevant"


def test_validated_beats_recorded_override(tmp_path):
    store = _store_with(tmp_path, [
        _doc("v1", 2024, "W-2", status="validated"),
    ])
    out = relevance_override(store, "v1", "irrelevant", "operator test")
    assert out["applied_verdict"] == "relevant"
    assert out["suppressed"] is True
    assert store.get("v1").relevance == "relevant"
    verdicts = assess_relevance(store, [2024], persist=True)
    assert verdicts["v1"] == {"verdict": "relevant",
                              "reasons": ["validated_by_operator"]}
    # the record itself is still auditable
    assert _load_overrides(store)["v1"]["verdict"] == "irrelevant"


# -- explicit override path ----------------------------------------------

def test_relevance_override_records_and_flips(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w-old", 2019, "W-2"),  # year_out_of_scope mechanically
    ])
    out = relevance_override(store, "w-old", "relevant",
                             "operator: keep for the amendment file")
    rec = out["record"]
    assert rec == {"doc_id": "w-old", "verdict": "relevant",
                   "reason": "operator: keep for the amendment file",
                   "ts": rec["ts"]}
    assert out["applied_verdict"] == "relevant"
    assert out["suppressed"] is False
    assert store.get("w-old").relevance == "relevant"
    # honored on the next mechanical run
    verdicts = assess_relevance(store, [2023, 2024, 2025, 2026], persist=True)
    assert verdicts["w-old"]["verdict"] == "relevant"
    assert verdicts["w-old"]["reasons"] == ["operator_override"]
    # append-only sidecar, JSONL
    sidecar = store.data_dir / "relevance_overrides.jsonl"
    rows = [json.loads(l) for l in sidecar.read_text(
        encoding="utf-8").splitlines()]
    assert rows[-1]["doc_id"] == "w-old"


def test_relevance_override_validation(tmp_path):
    store = _store_with(tmp_path, [_doc("w1", 2024, "W-2")])
    with pytest.raises(ValueError, match="one of"):
        relevance_override(store, "w1", "maybe", "reason")
    with pytest.raises(ValueError, match="non-empty"):
        relevance_override(store, "w1", "relevant", "   ")
    with pytest.raises(KeyError):
        relevance_override(store, "nope", "relevant", "reason")


def test_override_to_irrelevant_restorable(tmp_path):
    store = _store_with(tmp_path, [_doc("w2-24", 2024, "W-2")])
    relevance_override(store, "w2-24", "irrelevant", "operator: dup scan")
    assert store.get("w2-24").relevance == "irrelevant"
    relevance_override(store, "w2-24", "relevant", "operator: restored")
    assert store.get("w2-24").relevance == "relevant"


# -- queue filtering -----------------------------------------------------

def test_review_ui_queue_excludes_irrelevants_by_default(tmp_path):
    store = _store_with(tmp_path, [
        _doc("keep-1", 2024, "W-2", relevance="relevant"),
        _doc("drop-1", 2024, "W-2", relevance="irrelevant"),
    ])
    html_default = queue_html(store, None, None)
    assert "keep-1" in html_default
    assert "drop-1" not in html_default
    assert "hidden" in html_default  # the exclusion is announced, not silent
    html_all = queue_html(store, None, None, include_irrelevant=True)
    assert "keep-1" in html_all and "drop-1" in html_all
    assert "irrelevant" in html_all  # reason-adjacent verdict column


def _cli(capsys, *argv):
    assert cli_main(list(argv)) == 0
    return capsys.readouterr().out


def test_cli_validation_queue_excludes_irrelevants(tmp_path, capsys):
    store = _store_with(tmp_path, [
        _doc("keep-1", 2024, "W-2"),
        _doc("drop-1", 2024, "W-2", relevance="irrelevant"),
    ])
    dd = str(store.data_dir)
    out = _cli(capsys, "--data-dir", dd, "validation-queue")
    assert "keep-1" in out and "drop-1" not in out
    assert "irrelevant document(s) hidden" in out
    out_all = _cli(capsys, "--data-dir", dd, "validation-queue",
                   "--include-irrelevant")
    assert "keep-1" in out_all and "drop-1" in out_all


def test_cli_relevance_override(tmp_path, capsys):
    store = _store_with(tmp_path, [_doc("w-old", 2019, "W-2")])
    dd = str(store.data_dir)
    out = _cli(capsys, "--data-dir", dd, "relevance-override", "w-old",
               "relevant", "--reason", "operator test")
    assert "override recorded" in out and "w-old" in out
    assert DocumentStore(store.data_dir).get("w-old").relevance == "relevant"


def test_cli_pipeline_stages_lists_corrected_order(tmp_path, capsys):
    out = _cli(capsys, "pipeline", "stages")
    order = [l.split()[0] for l in out.splitlines()
             if l and not l.startswith(" ")]
    assert order == RUN_SEQUENCE + ["GAP_ANALYSIS"]
    assert "[human     ]" in out  # REVIEW is the human stage


def test_cli_pipeline_run_slice(tmp_path, capsys):
    store = _passing_store(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    out = _cli(capsys, "--data-dir", str(store.data_dir), "pipeline",
               "run", str(src), "--from", "relevance", "--to", "validation")
    assert "STAGE 4/8: RELEVANCE" in out
    assert "STAGE 6/8: VALIDATION" in out
    assert "STAGE 7/8" not in out


def test_cli_pipeline_run_requires_data_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TAXPREP_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(SystemExit) as exc:
        cli_main(["pipeline", "run"])
    assert exc.value.code == 2  # N1 fail-closed with the setup hint


# -- MCP: queue filter + override tool -------------------------------------

def test_mcp_validation_queue_filter_and_override(tmp_path):
    store = _store_with(tmp_path, [
        _doc("keep-1", 2024, "W-2"),
        _doc("drop-1", 2024, "W-2"),
    ])
    dd = str(store.data_dir)
    mcp_server.relevance_override("drop-1", "irrelevant", "mcp test",
                                  data_dir=dd)
    q = mcp_server.validation_queue(data_dir=dd)
    assert {d["doc_id"] for d in q["queue"]} == {"keep-1"}
    assert q["irrelevant_excluded"] == 1
    json.dumps(q)
    _pii_free(q)
    q_all = mcp_server.validation_queue(data_dir=dd, include_irrelevant=True)
    assert {d["doc_id"] for d in q_all["queue"]} == {"keep-1", "drop-1"}
    assert q_all["irrelevant_excluded"] == 0
    assert all("relevance" in d for d in q_all["queue"])
    _pii_free(q_all)


def test_mcp_relevance_override_tool(tmp_path):
    store = _store_with(tmp_path, [_doc("w-old", 2019, "W-2")])
    dd = str(store.data_dir)
    out = mcp_server.relevance_override("w-old", "relevant",
                                        "operator direction", data_dir=dd)
    assert out["record"]["doc_id"] == "w-old"
    assert out["applied_verdict"] == "relevant"
    json.dumps(out)
    _pii_free(out)
    with pytest.raises(ValueError):
        mcp_server.relevance_override("w-old", "maybe", "x", data_dir=dd)
    with pytest.raises(KeyError):
        mcp_server.relevance_override("nope", "relevant", "x", data_dir=dd)


def test_pii_sweep_new_tools(tmp_path):
    store = _store_with(tmp_path, [
        _doc("w2-a", 2024, "W-2",
             fields={"box1": {"value": "$85,000.00", "confidence": "high",
                              "raw_text": "Box 1 $85,000.00"}}),
        _doc("w-old", 2019, "W-2", relevance="irrelevant"),
    ])
    dd = str(store.data_dir)
    outputs = [
        mcp_server.validation_queue(data_dir=dd),
        mcp_server.validation_queue(data_dir=dd, include_irrelevant=True),
        mcp_server.assess_relevance(data_dir=dd),
        mcp_server.relevance_override("w-old", "relevant",
                                      "operator sweep", data_dir=dd),
    ]
    for out in outputs:
        json.dumps(out)
        _pii_free(out)
    # the operator's free-text reason crosses the tool boundary; the
    # recursive sweep above asserts it carries no value/raw_text keys
    # and no money patterns


def test_summarize_counts_stable_with_new_reasons(tmp_path):
    store = _store_with(tmp_path, [
        _doc("v1", 2019, "W-2", status="validated"),
        _doc("w1", 2024, "W-2"),
        _doc("u1", 2024, "UNKNOWN"),
    ])
    verdicts = assess_relevance(store, [2024], persist=True)
    s = summarize(verdicts)
    assert s["counts"] == {"relevant": 2, "irrelevant": 0, "needs_human": 1}
    assert s["relevant_ids"] == ["v1", "w1"]
