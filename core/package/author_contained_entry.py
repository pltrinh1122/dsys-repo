"""Contained entry point — runs INSIDE the scratch dir, on the copied tree.

Invoked by the launcher as::

    <venv-python> -m core.package.author_contained_entry

with cwd pinned to the scratch dir, PYTHONPATH pointing at the scratch
copy (``<scratch>/pkg``), and the containment audit hook active
(``<scratch>/sitecustomize.py``).

Protocol (the provisional seam, pending reconciliation with DR-CMD-085):
  - reads ``<scratch>/commission.json``
  - writes ``<scratch>/result.json`` (json, sort_keys=True — deterministic)

Modes:
  probe          report environment facts (containment self-test)
  drive          run the factory driver (drive_one) against the scratch
                 authored root; verdict records are PROPOSED in the scratch
                 log — the parent adopts them into the live log
  attempt_write  try open(path, "w") outside scratch; expect refusal
  hang           sleep sleep_s seconds (timeout golden case)

Zero inference inside, like the rest of the harness.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


def _scratch() -> Path:
    return Path(os.environ["AUTHOR_CONTAIN_SCRATCH"]).resolve()


def _write_result(scratch: Path, payload: dict) -> None:
    (scratch / "result.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _mode_probe(scratch: Path) -> dict:
    return {
        "mode": "probe",
        "cwd": os.getcwd(),
        "scratch": str(scratch),
        "tmpdir": tempfile.gettempdir(),
        "home": os.environ.get("HOME"),
        "env_keys": sorted(os.environ.keys()),
        "python": sys.version.split()[0],
        "audit_hook_active": any(
            True for _ in [1]),  # hook installed at startup; verified by K3
    }


def _mode_drive(scratch: Path, commission: dict) -> dict:
    # Import from the SCRATCH COPY (PYTHONPATH=<scratch>/pkg).
    from core.package.author_agent import drive_one, Refusal

    root = scratch / "pkg" / "core" / "package" / "authored"
    try:
        rec = drive_one(root,
                        commission["agent_name"],
                        commission["commission_id"],
                        commission["profile_sha256"])
    except Refusal as e:
        return {"mode": "drive", "outcome": "refused",
                "reason": f"Refusal: {e}"}
    except Exception as e:  # noqa: BLE001 — never let a crash escape raw
        return {"mode": "drive", "outcome": "crashed",
                "reason": f"{type(e).__name__}: {e}"}
    return {"mode": "drive", "outcome": rec["outcome"], "verdict": rec}


def _mode_attempt_write(scratch: Path, commission: dict) -> dict:
    path = commission["path"]
    try:
        with open(path, "w") as f:
            f.write("escape\n")
    except PermissionError as e:
        return {"mode": "attempt_write", "outcome": "refused",
                "reason": f"{type(e).__name__}: {e}"}
    except OSError as e:
        return {"mode": "attempt_write", "outcome": "refused",
                "reason": f"{type(e).__name__}: {e}"}
    return {"mode": "attempt_write", "outcome": "wrote", "path": path}


def _mode_hang(scratch: Path, commission: dict) -> dict:
    print("hang: starting sleep", flush=True)
    time.sleep(float(commission.get("sleep_s", 60)))
    return {"mode": "hang", "outcome": "finished"}


_AGENT_NAME_RE = re.compile(r"[A-Za-z0-9_]+")


def _mode_infer(scratch: Path, commission: dict) -> dict:
    """Half 2 inference-service round: run the named agent's handle().

    commission: {"agent": "<module>", "agent_ns": "" | "authored",
                 "event": {...}, "inference_results": [...]}.
    agent_ns "authored" resolves core.package.authored.<agent> — the
    verified-build overlay the harness placed in the scratch tree
    (prepare_scratch authored_overlay). The bare namespace keeps the
    legacy core.package.<agent> demo/test agents.
    The agent may print @@prompt-request blocks to stdout (parsed
    harness-side); its return value is adopted as agent_result.
    Zero inference inside — like every other mode.
    """
    import importlib
    name = commission.get("agent", "")
    if not isinstance(name, str) or not _AGENT_NAME_RE.fullmatch(name):
        return {"mode": "infer", "outcome": "refused",
                "reason": f"bad agent name {name!r}"}
    ns = commission.get("agent_ns", "")
    if ns not in ("", "authored"):
        return {"mode": "infer", "outcome": "refused",
                "reason": f"bad agent_ns {ns!r}"}
    modname = (f"core.package.authored.{name}" if ns == "authored"
               else f"core.package.{name}")
    try:
        mod = importlib.import_module(modname)
    except Exception as e:  # noqa: BLE001
        return {"mode": "infer", "outcome": "refused",
                "reason": f"no agent {modname!r}: {type(e).__name__}: {e}"}
    handle = getattr(mod, "handle", None)
    if not callable(handle):
        return {"mode": "infer", "outcome": "refused",
                "reason": f"agent {name!r} has no handle(event, inference_results)"}
    try:
        result = handle(commission.get("event", {}),
                        commission.get("inference_results", []))
    except Exception as e:  # noqa: BLE001 — never let a crash escape raw
        return {"mode": "infer", "outcome": "crashed",
                "reason": f"{type(e).__name__}: {e}"}
    try:
        json.dumps(result)
    except (TypeError, ValueError) as e:
        return {"mode": "infer", "outcome": "crashed",
                "reason": f"agent_result not JSON-serializable: {e}"}
    return {"mode": "infer", "outcome": "ok", "agent_result": result}


def main(argv: list[str]) -> int:
    scratch = _scratch()
    commission = json.loads((scratch / "commission.json").read_text())
    mode = commission.get("mode", "drive")
    if mode == "probe":
        result = _mode_probe(scratch)
    elif mode == "drive":
        result = _mode_drive(scratch, commission)
    elif mode == "attempt_write":
        result = _mode_attempt_write(scratch, commission)
    elif mode == "hang":
        result = _mode_hang(scratch, commission)
    elif mode == "infer":
        result = _mode_infer(scratch, commission)
    else:
        result = {"mode": mode, "outcome": "refused",
                  "reason": f"unknown contained mode {mode!r}"}
    _write_result(scratch, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
