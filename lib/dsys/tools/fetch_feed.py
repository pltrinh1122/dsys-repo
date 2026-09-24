#!/usr/bin/env python3
"""tool-fetch-feed (rb-release-check, step 1): the release-check poll.

The sole network touch in the registry (DR-CMD-055 F2(a), updater-spec
§5 P2): one HTTPS GET of the pinned feed URL from operator config. The
result enters the machine only as external trigger payload — data,
content-hashed into the event log, never resolved or executed.

Feed document (as-built, spec §11): a JSON object
{"version": "<release>", "feed_sha256": "sha256:<hex>"} where <hex> is
the publisher's sha256 over the canonical JSON (sorted keys, compact
separators) of the document with the feed_sha256 member removed. The
tool recomputes it the same way, so publisher and consumer agree
byte-for-byte; raw-byte hashing is unimplementable for a
self-describing checksum (spec §11).

run(ctx) -> {"ok", "result", "ctx_delta"}. Any GET failure (unreachable
host, non-2xx, timeout, unparseable feed) raises: the run-book's
retry:3 policy covers transience, then the run aborts.
"""

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-fetch-feed"

_GET_TIMEOUT_S = 30  # as-built: the timeout bound (spec §11)


def _canonical_hex(doc: dict) -> str:
    """sha256 over the canonical form of the feed document with the
    feed_sha256 member removed — the publisher computes it the same
    way (spec §11)."""
    bare = {k: v for k, v in doc.items() if k != "feed_sha256"}
    canonical = json.dumps(bare, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    cfg = C.read_updater_config(home)
    feed_url = cfg["feed_url"]
    if not feed_url:
        raise C.ToolAborted(
            "no pinned feed URL configured (updater.feed_url) — refusing "
            "to invent a pin")
    try:
        req = urllib.request.Request(
            feed_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_GET_TIMEOUT_S) as resp:
            body = resp.read()
    except Exception as e:
        raise C.ToolAborted(
            f"feed poll failed: {type(e).__name__}: {e}")
    try:
        doc = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise C.ToolAborted(f"feed poll failed: unparseable feed: {e}")
    if not isinstance(doc, dict):
        raise C.ToolAborted(
            "feed poll failed: feed is not a JSON object")
    version = doc.get("version")
    declared = doc.get("feed_sha256")
    if not isinstance(version, str) or not version:
        raise C.ToolAborted(
            "feed poll failed: feed declares no version string")
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        raise C.ToolAborted(
            "feed poll failed: feed declares no sha256 checksum")
    # The recorded feed_sha256 is the content hash of the received
    # document (spec §4.1); feed_checksum is the feed's declared
    # checksum — their mismatch is the tamper signal the next tool
    # checks (spec §4.3). The raw feed bytes are not stored: the
    # small-ctx discipline holds; the hash binds the bytes for replay.
    delta = {
        "feed_sha256": "sha256:" + _canonical_hex(doc),
        "remote_version": version,
        "feed_checksum": declared,
    }
    return {
        "ok": True,
        "result": {"fetched": True, "remote_version": version},
        "ctx_delta": delta,
    }
