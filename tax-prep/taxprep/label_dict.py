"""Operator-editable label dictionary (R23 requirement 3, stream C).

The single source of truth is ``taxprep/data/label_dictionary.json``:
printed (normalized) label -> canonical key -> 1040 / 1040-X line per
year -> citation. No label->canonical mapping is hardcoded here or
anywhere else in this stream; this module is a thin read layer over
the data file, so concurrent rule refinements by the workstation
session merge against data, not code.

Normalization: strip, collapse internal whitespace, UPPERCASE
(the same rule transcript.py uses for its label tables).

Deterministic: no time, no randomness, no set-ordered output.
Local-only; synthetic fixtures in tests; no PII.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

DICT_PATH = Path(__file__).resolve().parent / "data" / "label_dictionary.json"

_SCHEMA_VERSION = 1


def normalize_label(raw: str) -> str:
    """Normalize a printed label: strip, collapse whitespace, UPPERCASE."""
    return re.sub(r"\s+", " ", raw.strip()).upper()


def _validate_shape(doc: object) -> dict:
    """Fail closed on a malformed dictionary file (never guess)."""
    if not isinstance(doc, dict):
        raise ValueError("label dictionary: top level must be an object")
    if doc.get("version") != _SCHEMA_VERSION:
        raise ValueError(
            f"label dictionary: unsupported version {doc.get('version')!r} "
            f"(expected {_SCHEMA_VERSION})"
        )
    labels = doc.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("label dictionary: 'labels' must be an object")
    for label, entry in labels.items():
        if not isinstance(entry, dict):
            raise ValueError(f"label dictionary: entry {label!r} not an object")
        if set(entry) != {"canonical_key", "lines_1040", "lines_1040x",
                          "citation"}:
            raise ValueError(
                f"label dictionary: entry {label!r} has wrong fields: "
                f"{sorted(entry)}"
            )
        if not isinstance(entry["canonical_key"], str) or not entry["canonical_key"]:
            raise ValueError(f"label dictionary: entry {label!r} bad canonical_key")
        for field in ("lines_1040", "lines_1040x"):
            m = entry[field]
            if not isinstance(m, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in m.items()
            ):
                raise ValueError(
                    f"label dictionary: entry {label!r} bad {field}"
                )
        if not isinstance(entry["citation"], str):
            raise ValueError(f"label dictionary: entry {label!r} bad citation")
    return doc


@lru_cache(maxsize=1)
def _load_cached() -> dict:
    """Load + validate the dictionary file once per process."""
    with open(DICT_PATH, encoding="utf-8") as fh:
        return _validate_shape(json.load(fh))


def load() -> dict:
    """Return the label dictionary (deep copy; safe for callers to keep).

    Cached on first load; the copy means callers can never mutate the
    shared cache or each other's view.
    """
    return copy.deepcopy(_load_cached())


def lookup(label: str) -> dict | None:
    """Return the dictionary entry for a label, or None when unmapped.

    Accepts an already-normalized label; the normalization is applied
    idempotently so raw printed labels work too. Returned entry is a
    copy -- never the shared cache object.
    """
    entry = _load_cached()["labels"].get(normalize_label(label))
    return copy.deepcopy(entry) if entry is not None else None


def labels_for_canonical(canonical_key: str) -> list[str]:
    """All normalized labels that map to a canonical key (sorted).

    Sorted output keeps Operator tooling deterministic regardless of
    how the JSON file is edited.
    """
    labels = _load_cached()["labels"]
    return sorted(
        label for label, entry in labels.items()
        if entry["canonical_key"] == canonical_key
    )


def unmapped(labels: list[str]) -> list[str]:
    """Labels with no dictionary entry, in the caller's order.

    "Listed, never dropped" helper for the R23 capture pipeline: every
    printed label is either mapped to a canonical key or surfaced here
    for the Operator to review.
    """
    known = _load_cached()["labels"]
    return [label for label in labels if normalize_label(label) not in known]
