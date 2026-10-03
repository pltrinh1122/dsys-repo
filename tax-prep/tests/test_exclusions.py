"""Exclusion-record tests -- synthetic ids only, no PII."""

import pytest

from taxprep import exclusions


def test_record_and_lookup_roundtrip(tmp_path):
    dd = tmp_path / "data"
    rec = exclusions.record_exclusion(dd, "doc-1", "operator: test duplicate")
    assert rec["doc_id"] == "doc-1"
    assert rec["reason"] == "operator: test duplicate"
    assert "recorded_at" in rec
    assert exclusions.is_excluded(dd, "doc-1") is True
    assert exclusions.is_excluded(dd, "doc-9") is False


def test_reason_required(tmp_path):
    dd = tmp_path / "data"
    with pytest.raises(ValueError, match="reason is required"):
        exclusions.record_exclusion(dd, "x", "")
    with pytest.raises(ValueError, match="reason is required"):
        exclusions.record_exclusion(dd, "x", "   ")
    with pytest.raises(ValueError, match="reason is required"):
        exclusions.record_exclusion(dd, "x", None)


def test_doc_id_required(tmp_path):
    with pytest.raises(ValueError, match="doc_id is required"):
        exclusions.record_exclusion(tmp_path / "data", "", "reason")
    with pytest.raises(ValueError, match="doc_id is required"):
        exclusions.record_exclusion(tmp_path / "data", "  ", "reason")


def test_list_sorted_and_persisted(tmp_path):
    dd = tmp_path / "data"
    exclusions.record_exclusion(dd, "b-doc", "r2")
    exclusions.record_exclusion(dd, "a-doc", "r1")
    rows = exclusions.list_exclusions(dd)
    assert [r["doc_id"] for r in rows] == ["a-doc", "b-doc"]
    # file-backed: the record survives a fresh read
    assert (dd / "exclusions.json").is_file()
    again = exclusions.list_exclusions(dd)
    assert [(r["doc_id"], r["reason"]) for r in again] == [
        ("a-doc", "r1"), ("b-doc", "r2")]


def test_creates_parent_dirs(tmp_path):
    dd = tmp_path / "deep" / "nested" / "data"  # does not exist yet
    exclusions.record_exclusion(dd, "x", "why")
    assert (dd / "exclusions.json").is_file()
    assert exclusions.is_excluded(dd, "x") is True


def test_overwrite_replaces_reason(tmp_path):
    dd = tmp_path / "data"
    exclusions.record_exclusion(dd, "x", "first")
    exclusions.record_exclusion(dd, "x", "second")
    rows = exclusions.list_exclusions(dd)
    assert len(rows) == 1
    assert rows[0]["reason"] == "second"


def test_corrupt_file_refuses_loudly(tmp_path):
    dd = tmp_path / "data"
    dd.mkdir(parents=True)
    (dd / "exclusions.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable|corrupt"):
        exclusions.list_exclusions(dd)
    with pytest.raises(ValueError, match="unreadable|corrupt"):
        exclusions.is_excluded(dd, "x")
    with pytest.raises(ValueError, match="unreadable|corrupt"):
        exclusions.record_exclusion(dd, "x", "reason")


def test_missing_file_means_no_exclusions(tmp_path):
    dd = tmp_path / "does-not-exist"
    assert exclusions.is_excluded(dd, "x") is False
    assert exclusions.list_exclusions(dd) == []
