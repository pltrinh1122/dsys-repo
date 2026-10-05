"""Label dictionary tests (R23 requirement 3, stream C).

The dictionary is Operator-editable DATA at
``taxprep/data/label_dictionary.json``; ``taxprep/label_dict.py`` is the
read layer. These tests pin the mechanical seed contract: every entry
of the two transcript.py label tables has a dictionary entry with the
same canonical key, 1040-X lines invert COLUMN_A_LINES, 1040 lines
carry ONLY verified mappings (missing is fine, wrong is not), and the
file is stably formatted (sorted keys, 2-space indent, trailing
newline) so concurrent workstation edits merge cleanly.

Synthetic labels only; no PII.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from taxprep import label_dict
from taxprep.column_a import COLUMN_A_LINES
from taxprep.transcript import _ACCOUNT_LABEL_TABLE, _RETURN_LABEL_TABLE

JSON_PATH = label_dict.DICT_PATH


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip()).upper()


def _raw_doc() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. JSON schema validity
# ---------------------------------------------------------------------------

def test_json_top_level_schema():
    doc = _raw_doc()
    assert doc["version"] == 1
    assert isinstance(doc["labels"], dict)
    assert set(doc) == {"version", "labels"}


def test_json_entry_schema():
    doc = _raw_doc()
    for label, entry in doc["labels"].items():
        assert label == _norm(label), f"label not normalized: {label!r}"
        assert set(entry) == {
            "canonical_key", "lines_1040", "lines_1040x", "citation"
        }, f"wrong fields for {label!r}"
        assert isinstance(entry["canonical_key"], str)
        assert entry["canonical_key"]
        for field in ("lines_1040", "lines_1040x"):
            mapping = entry[field]
            assert isinstance(mapping, dict), f"{label!r} {field} not a dict"
            assert all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in mapping.items()
            ), f"{label!r} {field} not str->str"
        assert isinstance(entry["citation"], str) and entry["citation"]


# ---------------------------------------------------------------------------
# 2. Mechanical seed: the transcript.py tables, transcribed, no new judgments
# ---------------------------------------------------------------------------

def _table_labels() -> dict[str, str]:
    """Normalized label -> canonical key for both transcript.py tables."""
    merged: dict[str, str] = {}
    for table in (_RETURN_LABEL_TABLE, _ACCOUNT_LABEL_TABLE):
        for label, key in table:
            norm = _norm(label)
            assert norm not in merged, f"duplicate label across tables: {norm!r}"
            merged[norm] = key
    return merged


def test_every_table_entry_has_dictionary_entry_with_same_key():
    table = _table_labels()
    labels = _raw_doc()["labels"]
    for norm, key in table.items():
        assert norm in labels, f"table label missing from dictionary: {norm!r}"
        assert labels[norm]["canonical_key"] == key, (
            f"{norm!r}: dictionary key {labels[norm]['canonical_key']!r} "
            f"!= table key {key!r}"
        )


def test_dictionary_covers_tables_exactly():
    """No invented labels, none silently dropped: dictionary == table union."""
    assert set(_raw_doc()["labels"]) == set(_table_labels())


def test_family_citations():
    """Return-transcript labels cite IRM 2.3.52; account labels cite Doc 6209 8A."""
    table = _table_labels()
    labels = _raw_doc()["labels"]
    return_norms = {_norm(l) for l, _ in _RETURN_LABEL_TABLE}
    account_norms = {_norm(l) for l, _ in _ACCOUNT_LABEL_TABLE}
    for norm, entry in labels.items():
        assert norm in table
        if norm in return_norms:
            assert "IRM 2.3.52" in entry["citation"], norm
        else:
            assert norm in account_norms
            assert "6209" in entry["citation"] and "8A" in entry["citation"], norm


# ---------------------------------------------------------------------------
# 3. 1040-X lines invert COLUMN_A_LINES; 1040 lines only where verified
# ---------------------------------------------------------------------------

def test_lines_1040x_invert_column_a_lines():
    key_to_line: dict[str, str] = {}
    for code, _label, keys in COLUMN_A_LINES:
        for k in keys:
            key_to_line.setdefault(k, code)
    labels = _raw_doc()["labels"]
    for norm, entry in labels.items():
        key = entry["canonical_key"]
        expected = ({"2023": key_to_line[key], "2024": key_to_line[key],
                     "2025": key_to_line[key]} if key in key_to_line else {})
        assert entry["lines_1040x"] == expected, (
            f"{norm!r}: lines_1040x {entry['lines_1040x']!r} != {expected!r}"
        )


def test_lines_1040_only_verified_mappings():
    """AGI -> line 11 (R23 spec, certain) and taxable_income -> line 15
    (taxprep/carryforward.py) are the only 1040 line mappings seeded.
    Everything else is an empty map: missing is fine, wrong is not."""
    labels = _raw_doc()["labels"]
    expected_1040 = {
        "agi": {"2023": "11", "2024": "11", "2025": "11"},
        "taxable_income": {"2023": "15", "2024": "15", "2025": "15"},
    }
    for norm, entry in labels.items():
        expected = expected_1040.get(entry["canonical_key"], {})
        assert entry["lines_1040"] == expected, (
            f"{norm!r}: unexpected lines_1040 {entry['lines_1040']!r}"
        )


# ---------------------------------------------------------------------------
# 4. Loader API
# ---------------------------------------------------------------------------

def test_load_round_trips_and_is_isolated():
    first = label_dict.load()
    second = label_dict.load()
    assert first == second
    assert first is not second
    # Mutating a returned view must not affect later loads.
    first["labels"]["AGI"]["canonical_key"] = "MUTATED"
    assert label_dict.lookup("AGI")["canonical_key"] == "agi"


def test_lookup():
    entry = label_dict.lookup("ADJUSTED GROSS INCOME")
    assert entry is not None
    assert entry["canonical_key"] == "agi"
    assert entry["lines_1040x"] == {"2023": "L1", "2024": "L1", "2025": "L1"}
    # Normalization is idempotent: raw printed labels work too.
    assert label_dict.lookup("  adjusted   gross  income ") == entry
    # Unknown label -> None, never a guess.
    assert label_dict.lookup("MYSTERY LABEL NO ONE PRINTED") is None
    # Returned entry is a copy, not the cache.
    entry["canonical_key"] = "MUTATED"
    assert label_dict.lookup("ADJUSTED GROSS INCOME")["canonical_key"] == "agi"


def test_labels_for_canonical():
    assert label_dict.labels_for_canonical("agi") == [
        "ADJUSTED GROSS INCOME",
        "ADJUSTED GROSS INCOME PER COMPUTER",
        "AGI",
    ]
    result = label_dict.labels_for_canonical("agi")
    assert result == sorted(result)
    assert label_dict.labels_for_canonical("account_balance") == [
        "ACCOUNT BALANCE"
    ]
    assert label_dict.labels_for_canonical("no_such_key") == []


def test_unmapped_lists_never_drops():
    got = label_dict.unmapped(
        ["AGI", "some unknown printed label", "TAXABLE INCOME",
         " another   UNKNOWN one "]
    )
    assert got == ["some unknown printed label", " another   UNKNOWN one "]
    assert label_dict.unmapped(["AGI", "WAGES"]) == []
    assert label_dict.unmapped([]) == []


def test_load_rejects_malformed(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 999, "labels": {}}), encoding="utf-8")
    monkeypatch.setattr(label_dict, "DICT_PATH", bad)
    label_dict._load_cached.cache_clear()
    try:
        with pytest.raises(ValueError, match="unsupported version"):
            label_dict.load()
    finally:
        label_dict._load_cached.cache_clear()


# ---------------------------------------------------------------------------
# 5. Stable formatting: parse -> re-dump -> byte-identical
# ---------------------------------------------------------------------------

def test_stable_formatting():
    """Sorted keys, 2-space indent, trailing newline -- the documented rule
    the workstation session merges against."""
    raw = JSON_PATH.read_bytes()
    assert raw.endswith(b"\n"), "dictionary must end with a trailing newline"
    assert not raw.endswith(b"\n\n"), "no extra trailing blank line"
    doc = json.loads(raw.decode("utf-8"))
    redump = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert raw == redump, "dictionary is not in stable canonical form"
    # Deep copy through the loader sees the same content.
    assert label_dict.load() == copy.deepcopy(doc)
