#!/usr/bin/env python3
"""Fixture tool: always fails. run(ctx) -> {"ok": False, ...}."""

TOOL_NAME = "fail_always"


def run(ctx: dict) -> dict:
    return {"ok": False, "result": "boom", "ctx_delta": {}}
