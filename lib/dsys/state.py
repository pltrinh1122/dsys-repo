"""Base-profile state commands: seed new states, read collections.

`init` writes a fresh state file (golden seed for the verified reference
state, empty seed for a blank SystemState). `get` reads collections or a
single record out of a state file. Both are local and hermetic; `get`
never writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


class StateError(Exception):
    """Raised for state-command misuse: unknown seed, unknown collection,
    unknown record id, unreadable state file."""


def _load_core(home: Path):
    """Import the vendored core the install-home way."""
    sys.path.insert(0, str(Path(home) / "lib" / "core"))
    from package.schema import SystemState  # noqa: E402
    from package.golden_run import build_state  # noqa: E402
    return SystemState, build_state


_SEEDS = ("golden", "empty")


def cmd_init(home: str | Path, seed: str, out: str | None = None) -> Path:
    """Write a fresh state file and return its path.

    seed "golden": build_state() — the verified reference state.
    seed "empty":  SystemState() — a blank state, no records.
    Default output is <home>/var/state/state.json; parent dirs are created.
    The file is written as pretty JSON (indent=2).
    """
    if seed not in _SEEDS:
        raise StateError(f"unknown seed: {seed!r} (expected one of {_SEEDS})")
    home = Path(home)
    SystemState, build_state = _load_core(home)
    state = build_state() if seed == "golden" else SystemState()
    out_path = Path(out) if out is not None else home / "var" / "state" / "state.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def cmd_get(state_file: str | Path, collection: str, id: str | None = None):
    """Read from a state file. Read-only.

    With id=None returns list[dict] of the whole collection; with an id
    returns the single record dict. Unknown collection or unknown id
    raises StateError.
    """
    path = Path(state_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StateError(f"state file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise StateError(f"state file is not valid JSON: {path} ({e})") from None
    if collection not in data:
        raise StateError(f"unknown collection: {collection!r}")
    coll = data[collection]
    if id is None:
        return list(coll.values())
    try:
        return coll[id]
    except KeyError:
        raise StateError(f"no {collection} record with id {id!r}") from None
