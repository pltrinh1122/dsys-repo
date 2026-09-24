#!/usr/bin/env python3
"""tool-record-promotion (rb-release-verify-installed, step 2): the
promotion bridge's first recording (the World function, exactly) — if
ctx["doctor_ok"], record the promotion; else record nothing.

The record is written to <home>/var/promotions/<version>.json with
deterministic content ({version, feed_sha256}, sorted-keys compact
JSON — the K1 canonical discipline, extended). The version is the
drive's candidate (ctx remote_version, falling back to the manifest's
dist_version — the installer's converged version); feed_sha256 is the
poll result, which is recorded data and is never re-derived (R1).
Re-invocation overwrites byte-identical content — the record for a
version is a pure function of (version, feed_sha256), so no duplicate
promotion can exist.

As-built (spec §11): the version string is restricted to
[A-Za-z0-9._-]+ — a feed-supplied version must not become a path.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-record-promotion"

_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def run(ctx: dict) -> dict:
    if not ctx.get("doctor_ok"):
        return {
            "ok": True,
            "result": {"promotion_recorded": False,
                       "reason": "doctor_ok is not true"},
            "ctx_delta": {"promotion_recorded": False},
        }
    home = C.resolve_home()
    version = ctx.get("remote_version")
    if not version:
        manifest = C.read_manifest(home)
        version = (manifest or {}).get("dist_version")
    feed_sha256 = ctx.get("feed_sha256")
    if not version or not feed_sha256:
        raise C.ToolAborted(
            "promotion needs the candidate version and the poll's "
            "feed_sha256 in ctx (recorded data — never re-derived)")
    if not _SAFE_VERSION.fullmatch(str(version)):
        raise C.ToolAborted(
            f"refusing to promote unsafe version string: {version!r}")
    outdir = home / "var" / "promotions"
    outdir.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"version": version, "feed_sha256": feed_sha256},
                         sort_keys=True, separators=(",", ":"))
    (outdir / f"{version}.json").write_text(
        content + "\n", encoding="utf-8")
    return {
        "ok": True,
        "result": {"promotion_recorded": True},
        "ctx_delta": {"promotion_recorded": True},
    }
