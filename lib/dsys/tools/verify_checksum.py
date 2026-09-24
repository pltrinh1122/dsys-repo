#!/usr/bin/env python3
"""tool-verify-checksum (rb-release-verify, step 1): the feed-integrity
gate. Pure function of ctx: if ctx["feed_checksum"] !=
ctx["feed_sha256"], the feed's self-declared checksum does not match
the hash of the bytes actually received — a tampered feed aborts here:
no candidacy, run_aborted -> failed. The candidate release artifact's
integrity is the installer's discipline, not this tool's.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-verify-checksum"


def run(ctx: dict) -> dict:
    if ctx.get("feed_checksum") != ctx.get("feed_sha256"):
        raise C.ToolAborted("checksum mismatch: no candidacy")
    return {
        "ok": True,
        "result": {"checksum_ok": True},
        "ctx_delta": {},
    }
