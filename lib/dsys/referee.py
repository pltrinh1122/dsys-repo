"""Base-profile referee: validate states and render verification views.

The referee judges; it never acts. It is hermetic: no network, no writes,
no inference. Validation and views come entirely from the vendored
machine-native core under <home>/lib/core/package/.

Exit-code contract:
  0  clean / view rendered
  5  state has violations (referee's refusal of the state, not of the call)
Referee misuse (unknown view, unreadable state) raises RefereeError.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


class RefereeError(Exception):
    """Raised for referee misuse: unknown view, unreadable state file."""


def _core_dir(home: Path) -> Path:
    return Path(home) / "lib" / "core"


def _load_core(home: Path):
    """Import the vendored core the install-home way.

    sys.path.insert(0, str(home/"lib"/"core")) then `from package...`.
    """
    sys.path.insert(0, str(_core_dir(home)))
    from package.schema import SystemState  # noqa: E402
    from package.validators import validate  # noqa: E402
    from package.views import verification_view  # noqa: E402
    return SystemState, validate, verification_view


def core_hashes(home: Path) -> dict[str, str]:
    """{relpath: 12-char sha256} for every lib/core/package/*.py.

    Relpaths are relative to the install home, e.g.
    "lib/core/package/schema.py". Used for attestation: the referee
    always reports which core it judged against.
    """
    pkg = _core_dir(Path(home)) / "package"
    hashes: dict[str, str] = {}
    for f in sorted(pkg.glob("*.py")):
        rel = f.relative_to(Path(home)).as_posix()
        hashes[rel] = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    return hashes


def _load_state(state_file: str | Path, SystemState):
    text = Path(state_file).read_text(encoding="utf-8")
    return SystemState.model_validate_json(text)


def validate_state(home: str | Path, state_file: str | Path) -> tuple[int, dict]:
    """Validate a state file against the vendored core.

    Returns (exit_code, payload) where payload is
    {"state_file", "clean", "violations", "core_hashes"}.
    exit_code is 0 when clean, 5 when the state has violations.
    """
    home = Path(home)
    SystemState, validate, _ = _load_core(home)
    state = _load_state(state_file, SystemState)
    violations = validate(state)
    clean = violations == []
    return (0 if clean else 5), {
        "state_file": str(state_file),
        "clean": clean,
        "violations": violations,
        "core_hashes": core_hashes(home),
    }


# Row keys of the disclosure verification view, kept verbatim from
# package/views.py DisclosureViewRow: id, kind, text, seq, triage_in_flight.
_OPEN_DISCLOSURES = "open-disclosures"


def view_state(home: str | Path, state_file: str | Path, view: str) -> tuple[int, dict]:
    """Render a read-only verification view of a state file.

    Currently supported: "open-disclosures" -> {"view", "rows"} where rows
    are the disclosure verification-view rows as plain dicts with the
    DisclosureViewRow keys verbatim (kind serialized as its value).
    Any other view name raises RefereeError.
    """
    if view != _OPEN_DISCLOSURES:
        raise RefereeError(f"unknown view: {view!r}")
    home = Path(home)
    SystemState, _, verification_view = _load_core(home)
    state = _load_state(state_file, SystemState)
    rows = [
        {
            "id": r.id,
            "kind": r.kind.value if hasattr(r.kind, "value") else r.kind,
            "text": r.text,
            "seq": r.seq,
            "triage_in_flight": r.triage_in_flight,
        }
        for r in verification_view(state)
    ]
    return 0, {"view": view, "rows": rows}
