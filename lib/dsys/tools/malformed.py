#!/usr/bin/env python3
"""Fixture tool: violates the tool contract (non-boolean 'ok').

Exercises C1: the executor must normalize this deviation into a
malformed tool failure, never propagate it, never let it into ctx."""

TOOL_NAME = "malformed"


def run(ctx: dict) -> dict:
    return {"ok": "yes", "result": "not-a-boolean", "ctx_delta": {}}
