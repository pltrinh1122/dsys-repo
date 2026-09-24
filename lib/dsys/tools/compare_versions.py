#!/usr/bin/env python3
"""tool-compare-versions (rb-release-check, step 2): read the installed
release version from the installation manifest (<home>/var/manifest.json
-> dist_version). Guards compare payload.remote_version !=
payload.installed_version; comparison only, no inference. A pure read
of a value stable within an installation — trivially idempotent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-compare-versions"


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    manifest = C.read_manifest(home)
    if manifest is None:
        raise C.ToolAborted(
            f"no installation manifest at {home}/var/manifest.json")
    version = manifest.get("dist_version")
    if not version:
        raise C.ToolAborted(
            "installation manifest records no dist_version")
    return {
        "ok": True,
        "result": {"installed_version": version},
        "ctx_delta": {"installed_version": version},
    }
