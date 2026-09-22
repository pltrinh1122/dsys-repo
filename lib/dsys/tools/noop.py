#!/usr/bin/env python3
"""Reference tool: does nothing, succeeds. run(ctx) -> {"ok","result","ctx_delta"}."""

TOOL_NAME = "noop"


def run(ctx: dict) -> dict:
    return {"ok": True, "result": "noop", "ctx_delta": {}}
