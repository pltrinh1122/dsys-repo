#!/usr/bin/env python3
"""tool-run-doctor (rb-release-verify-installed, step 1): runs the
dist's doctor checks in-process (lib.dsys.doctor against <home>) — no
subprocess is needed; the §2 in-process invocation covers it.

doctor_ok is true iff no check reports "fail" (as-built, spec §11:
warns are advisory; the tool runs the non-strict posture, matching the
CLI default). Reads only — trivially idempotent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-run-doctor"


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    import doctor  # lib/dsys top-level module (on sys.path via _common)

    report = doctor.run_checks(home, strict=False)
    failed = [c["name"] for c in report.get("checks", [])
              if c.get("status") == "fail"]
    ok = not failed
    return {
        "ok": True,
        "result": {"doctor_ok": ok, "failed_checks": failed},
        "ctx_delta": {"doctor_ok": ok},
    }
