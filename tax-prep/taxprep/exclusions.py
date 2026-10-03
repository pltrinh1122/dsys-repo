"""Operator-recorded exclusions for the carryforward guard (R3).

Exclusion state lives here -- NOT in store.py (owned by another
workstream) -- as a small JSON sidecar under the data dir:

    <data_dir>/exclusions.json     {"<doc_id>": {"doc_id", "reason",
                                                "recorded_at"}}

An exclusion is the Operator's attested decision that a document which
trips the carryforward guard (UNKNOWN/MULTI_FORM/BLOCKED/ORPHANED form
or status, missing tax year, or a 1099-B with zero lots) may be skipped
by the guard. It suppresses the guard blocker for that doc_id only;
it never overrides the validation gate (unvalidated documents still
refuse) and it never carries document content -- reasons are the
Operator's own words, kept local to the data dir and never surfaced
over the MCP boundary.

The reason is required and non-empty: a reasonless exclusion is a
silent drop, which this system refuses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EXCLUSIONS_FILENAME = "exclusions.json"


def _path(data_dir) -> Path:
    return Path(data_dir) / EXCLUSIONS_FILENAME


def _load(data_dir) -> dict:
    """Read the exclusion records; {} when no file exists.

    Raises ValueError (loud, fail closed) on corrupt JSON -- a damaged
    exclusion file must never be mistaken for "no exclusions".
    """
    path = _path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{EXCLUSIONS_FILENAME} is unreadable: {e}")
    if not isinstance(raw, dict):
        raise ValueError(f"{EXCLUSIONS_FILENAME} is corrupt: not a JSON object")
    return raw


def _save(data_dir, entries: dict) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def record_exclusion(data_dir, doc_id: str, reason: str) -> dict:
    """Record (or replace) the Operator's exclusion for ``doc_id``.

    ``reason`` is required and non-empty -- refusals are ValueError.
    Returns the stored record {"doc_id", "reason", "recorded_at"}.
    """
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("doc_id is required: cannot record an exclusion without it")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(
            "reason is required: an exclusion without a reason is a "
            "silent drop -- record why the Operator is excluding this document"
        )
    entries = _load(data_dir)
    record = {
        "doc_id": doc_id,
        "reason": reason.strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entries[doc_id] = record
    _save(data_dir, entries)
    return record


def list_exclusions(data_dir) -> list[dict]:
    """All recorded exclusions, sorted by doc_id. PII-free shapes only
    as far as the guard is concerned -- reasons are Operator text kept
    local to the data dir."""
    entries = _load(data_dir)
    return [entries[k] for k in sorted(entries)]


def is_excluded(data_dir, doc_id: str) -> bool:
    """True when the Operator has recorded an exclusion for ``doc_id``."""
    return doc_id in _load(data_dir)
