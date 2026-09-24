#!/usr/bin/env python3
"""tool-read-policy (rb-policy-gate, step 1): the policy gate.

Reads updater.policy (auto | notify | off, default notify) and
updater.auto_max_bump (patch | minor | major, default patch) from
operator config and decides drive vs defer — the World function,
exactly. The tool pins what it read into ctx_delta (spec §4.4, G6 Q5):
the determinism declaration covers the (config, versions) -> decision
function, and the inputs are pinned in the log.

Deferrals that surface (auto-over-bump, notify) mint an
updater-deferred disclosure ({version, reason}) into
<home>/var/disclosures/ under the DR-5 seq discipline. Idempotency:
the tool checks ctx for an existing surfaced_seq for the candidate
version and skips re-minting — at most one surfacing per candidate
under at-least-once recovery.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-read-policy"


def _surface(home: Path, ctx: dict, version: str, reason: str,
             delta: dict) -> None:
    # At-most-once surfacing per candidate version: a re-invocation
    # whose folded ctx already carries this version's surfaced_seq
    # reuses it instead of minting a second disclosure.
    if (ctx.get("surfaced_version") == version
            and ctx.get("surfaced_seq")):
        delta["surfaced_version"] = ctx["surfaced_version"]
        delta["surfaced_seq"] = ctx["surfaced_seq"]
        return
    rec = C.mint_disclosure(
        home, "updater-deferred",
        f"version: {version}\nreason: {reason}\n")
    delta["surfaced_version"] = version
    delta["surfaced_seq"] = rec["seq"]


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    cfg = C.read_updater_config(home)
    policy = cfg["policy"]
    max_bump = cfg["auto_max_bump"]
    installed = ctx.get("installed_version")
    remote = ctx.get("remote_version")
    if installed is None or remote is None:
        raise C.ToolAborted(
            "policy gate needs installed_version and remote_version in ctx")
    if max_bump not in C._BUMP_ORDER:
        raise C.ToolAborted(
            f"unknown updater auto_max_bump: {max_bump!r}")
    delta = {"policy": policy, "auto_max_bump": max_bump}
    if policy == "auto":
        bump = C.bump(installed, remote)
        if C._BUMP_ORDER[bump] <= C._BUMP_ORDER[max_bump]:
            delta["decision"] = "drive"
            delta["reason"] = (
                f"policy=auto, bump={bump} within {max_bump}")
        else:
            delta["decision"] = "defer"
            delta["reason"] = (
                f"policy=auto but bump={bump} exceeds {max_bump}")
            _surface(home, ctx, remote, delta["reason"], delta)
    elif policy == "notify":
        delta["decision"] = "defer"
        delta["reason"] = "policy=notify: surfaced, not driven"
        _surface(home, ctx, remote, delta["reason"], delta)
    elif policy == "off":
        delta["decision"] = "defer"
        delta["reason"] = "policy=off: recorded only"
    else:
        # Unknown policy is a config error: abort loudly. Silently
        # degrading to 'off' would hide a typo'd policy ('autoo').
        raise C.ToolAborted(f"unknown updater policy: {policy!r}")
    return {
        "ok": True,
        "result": {"decision": delta["decision"]},
        "ctx_delta": delta,
    }
