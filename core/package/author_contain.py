"""Execution containment launcher (DR-CMD-086; /pb-decide C ratified).

Containment = venv (dependency hermeticity) + subprocess discipline
(execution boundary):

  - A dedicated, hash-pinned venv (``~/.dsys/author-venv``, harness-managed)
    isolates *packages*: the contained run sees only declared dependencies.
  - The contained entry point
    (``core.package.author_contained_entry``, on the scratch copy) runs as
    a subprocess with: cwd pinned to a per-run scratch dir, environment
    scrubbed to an explicit allowlist, wall-clock timeout, the source tree
    copied in (hash-pinned), all stdio captured, and an interpreter audit
    hook (``sitecustomize.py`` in the scratch dir) that refuses filesystem
    writes outside scratch, subprocess spawning, and network use.

The venv isolates packages, NOT effects — the subprocess discipline is the
execution boundary, and even that is cooperative (interpreter-level): it
refuses accidental escapes by authored code, it does not sandbox an
adversary. See doc/author-agent-containment-spec.md.

Zero inference inside. The contained run proposes (verdict records in the
scratch log); the parent adopts into the live log — proposer != disposer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = Path(__file__).with_name("author_requirements.txt")
SHIM_SOURCE = Path(__file__).with_name("author_contain_sitecustomize.py")
ENTRY_MODULE = "core.package.author_contained_entry"

SPEC_VERSION = "contain/v1"
DEFAULT_VENV = Path.home() / ".dsys" / "author-venv"
DEFAULT_TIMEOUT_S = 120
RUNS_DIR = REPO_ROOT / "runs"  # gitignored; per-run scratch + run records


# ---------------------------------------------------------------------------
# venv (dependency hermeticity; J-C1: harness-managed)
# ---------------------------------------------------------------------------

def _parse_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", line)
        if m:
            pins[m.group(1).lower().replace("-", "_")] = m.group(2)
    return pins


def _freeze(python: Path) -> dict[str, str]:
    out = subprocess.run([str(python), "-m", "pip", "freeze"],
                         capture_output=True, text=True, check=True,
                         timeout=120)
    found: dict[str, str] = {}
    for line in out.stdout.splitlines():
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line.strip())
        if m:
            found[m.group(1).lower().replace("-", "_")] = m.group(2)
    return found


def ensure_venv(venv_dir: Path | None = None,
                timeout_s: int = 600) -> Path:
    """Create (harness-managed) or verify the contained venv.

    Returns the venv python. Reinstalls when installed pins drift from
    author_requirements.txt. Raises on failure — a contained run never
    falls back to the ambient interpreter.
    """
    venv_dir = Path(venv_dir) if venv_dir else DEFAULT_VENV
    python = venv_dir / "bin" / "python"
    if not python.exists():
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                       check=True, timeout=timeout_s,
                       capture_output=True, text=True)
        subprocess.run([str(python), "-m", "pip", "install",
                        "--require-hashes", "-r", str(REQUIREMENTS)],
                       check=True, timeout=timeout_s,
                       capture_output=True, text=True)
        return python
    pins = _parse_pins()
    installed = _freeze(python)
    drift = {name: (pins[name], installed.get(name))
             for name in pins if installed.get(name) != pins[name]}
    if drift:
        subprocess.run([str(python), "-m", "pip", "install",
                        "--require-hashes", "-r", str(REQUIREMENTS)],
                       check=True, timeout=timeout_s,
                       capture_output=True, text=True)
    return python


def venv_fingerprint(python: Path) -> dict[str, Any]:
    return {
        "path": str(python.parent.parent),
        "python": subprocess.run(
            [str(python), "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, check=True,
            timeout=60).stdout.strip(),
        "packages": {n: v for n, v in _freeze(python).items()
                     if n in _parse_pins()},
    }


# ---------------------------------------------------------------------------
# scratch preparation (J-C2: copy-in, hash-pinned)
# ---------------------------------------------------------------------------

def tree_sha256(root: Path) -> str:
    """sha256 over sorted (relative-posix-path, bytes) of a tree."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            h.update(rel.encode() + b"\x00")
            h.update(p.read_bytes())
            h.update(b"\x00")
    return h.hexdigest()


def _next_scratch() -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    taken = [int(d.name.split("-", 1)[1]) for d in RUNS_DIR.iterdir()
             if d.is_dir() and d.name.startswith("contain-")
             and d.name.split("-", 1)[1].isdigit()]
    return RUNS_DIR / f"contain-{(max(taken, default=0) + 1):04d}"


def prepare_scratch(commission: dict[str, Any],
                    authored_overlay: Path | None = None) -> Path:
    """Build the per-run scratch dir: commission + copied tree + shim."""
    scratch = _next_scratch()
    pkg = scratch / "pkg"
    shutil.copytree(REPO_ROOT / "core", pkg / "core",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if authored_overlay is not None:
        target = pkg / "core" / "package" / "authored"
        shutil.rmtree(target)
        shutil.copytree(authored_overlay, target,
                        ignore=shutil.ignore_patterns("__pycache__",
                                                      "*.pyc"))
    (scratch / "commission.json").write_text(
        json.dumps(commission, sort_keys=True, indent=2) + "\n")
    # The shim MUST live where PYTHONPATH points (<scratch>/pkg), not in
    # the scratch root: for `python -m`, cwd is prepended to sys.path only
    # AFTER site imports sitecustomize at startup, so a scratch-root shim
    # would lose to the stdlib's own sitecustomize. PYTHONPATH precedes
    # the stdlib on the startup path, so <scratch>/pkg/sitecustomize.py
    # wins and the audit hook is installed before any contained code runs.
    shutil.copyfile(SHIM_SOURCE, pkg / "sitecustomize.py")
    (scratch / "tmp").mkdir()
    (scratch / "home").mkdir()
    return scratch


def _contained_env(scratch: Path) -> dict[str, str]:
    """Scrubbed environment: explicit allowlist, nothing inherited."""
    return {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(scratch / "pkg"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(scratch / "tmp"),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "HOME": str(scratch / "home"),
        "AUTHOR_CONTAIN_SCRATCH": str(scratch),
    }


# ---------------------------------------------------------------------------
# contained run
# ---------------------------------------------------------------------------

def run_contained(commission: dict[str, Any],
                  authored_overlay: Path | None = None,
                  timeout_s: int = DEFAULT_TIMEOUT_S,
                  venv_dir: Path | None = None,
                  keep_scratch: bool = True) -> dict[str, Any]:
    """Run one contained workload. Returns the run record (no timestamps,
    no pids — everything except ``run_local`` is deterministic)."""
    python = ensure_venv(venv_dir)
    scratch = prepare_scratch(commission, authored_overlay)
    commission_sha = hashlib.sha256(
        (scratch / "commission.json").read_bytes()).hexdigest()
    inputs = {
        "spec_version": SPEC_VERSION,
        "commission_sha256": commission_sha,
        "tree_sha256": tree_sha256(scratch / "pkg"),
        "venv": venv_fingerprint(python),
        "timeout_s": timeout_s,
    }
    try:
        completed = subprocess.run(
            [str(python), "-m", ENTRY_MODULE],
            cwd=str(scratch),
            env=_contained_env(scratch),
            capture_output=True, text=True,
            timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        # Partial outputs are QUARANTINED: recorded, never adopted.
        # (TimeoutExpired carries raw bytes even with text=True — decode.)
        def _dec(b: Any) -> str:
            if isinstance(b, bytes):
                return b.decode("utf-8", "replace")
            return b or ""
        return {"outcome": "timeout",
                "reason": f"wall-clock timeout after {timeout_s}s; "
                          f"contained process killed",
                "inputs": inputs,
                "quarantine": {
                    "stdout": _dec(e.stdout),
                    "stderr": _dec(e.stderr),
                },
                "run_local": {"scratch": str(scratch)}}
    result = None
    result_path = scratch / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
    record = {
        "outcome": "ok",
        "inputs": inputs,
        "result": result,
        "stdio": {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
        "run_local": {"scratch": str(scratch)},
    }
    (scratch / "run-record.json").write_text(
        json.dumps({k: v for k, v in record.items()
                    if k != "run_local"}, sort_keys=True, indent=2) + "\n")
    if not keep_scratch:
        shutil.rmtree(scratch, ignore_errors=True)
    return record


def adopt_verdict_records(live_root: Path,
                          verdict: dict[str, Any]) -> dict[str, Any]:
    """Adopt a contained verdict into the live authoring log.

    The contained run PROPOSED (scratch log); the parent DISPOSES by
    re-appending content (fresh live seq) — proposer != disposer.
    """
    from .author_agent import _append
    content = {k: v for k, v in verdict.items() if k != "seq"}
    return _append(Path(live_root), content)


__all__ = [
    "SPEC_VERSION",
    "adopt_verdict_records",
    "ensure_venv",
    "prepare_scratch",
    "run_contained",
    "tree_sha256",
    "venv_fingerprint",
]
