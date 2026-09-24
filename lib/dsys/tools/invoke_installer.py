#!/usr/bin/env python3
"""tool-invoke-installer (rb-release-drive, step 1): the composed
perform step. Spawns install.sh as a subprocess (the §2 subprocess
scope — §8 governs invocation, and a tool may spawn subprocesses):
argv = ["install.sh", "--release", version, "--accretion-path",
<explicit>, "--accretion-required"] — the K2 repair: the explicit
accretion path always, never --overwrite (D5), always fail-closed (D2).

The accretion path is the running installation's manifest
accretion.path when recorded; else the default rule
"/var/daccretion/" + basename(home). A nonzero exit aborts loudly: a
failed install converges nothing — the version does not advance. The
tool does not record installed_version: convergence is the installer's,
and the manifest is the installer's to write.

Idempotency: the installer is idempotent (the 2026-09-20 finding —
reinstall after operator mutations -> exit 0; config, state, and log
preserved and honored). A crash during the install followed by
at-least-once re-invocation re-runs install.sh for the same version,
which converges to the same state.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-invoke-installer"

_INSTALL_TIMEOUT_S = 600  # as-built: the spawn bound (spec §11)


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    version = ctx.get("remote_version")
    if not version:
        raise C.ToolAborted(
            "installer drive needs remote_version in ctx")
    manifest = C.read_manifest(home)
    acc_path = C.accretion_path(home, manifest)
    installer = home / "install.sh"
    if not (installer.is_file() and os.access(installer, os.X_OK)):
        raise C.ToolAborted(
            f"installer not found or not executable: {installer}")
    argv = ["install.sh", "--release", version,
            "--accretion-path", acc_path, "--accretion-required"]
    try:
        proc = subprocess.run(
            argv, executable=str(installer), cwd=str(home),
            capture_output=True, text=True, timeout=_INSTALL_TIMEOUT_S)
    except Exception as e:
        raise C.ToolAborted(
            f"installer could not be spawned: "
            f"{type(e).__name__}: {e}")
    if proc.returncode != 0:
        raise C.ToolAborted(
            f"installer exited {proc.returncode} for {version}")
    return {
        "ok": True,
        "result": {"exit_code": 0, "version": version},
        "ctx_delta": {"exit_code": 0},
    }
