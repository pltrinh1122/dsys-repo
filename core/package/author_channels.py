"""Afferent/efferent channels for the author-agent (DR-CMD-085).

The channels are the containment boundary's I/O: the only paths in and
out of the author-agent loop. Sibling to author_agent.py — that module's
core is untouched; this module adds the boundary.

Topology (falsified alternative excluded, 2026-09-26): the CLI invokes
harness machinery; it does NOT relay chat to a separate endpoint. J0
stands — the author-agent is ambient inference governed by a profile.

Vocabulary is PROVISIONAL (J-CH2): channel kinds are enums; display
names live in CHANNEL_NAMES and nowhere else, so adopting, amending, or
renaming the vocabulary relabels one table.

Principal channels (bound for the wright):
  AP-A3 commission ......... admit_commission (staged queue, canonical)
  AP-A2 standing disposition  admit_commission(kind=AP_A2)
  AP-E1 staged proposal .... stage_authored_profile (author_agent.py)
  AP-E2 report .............. read_results
  AP-E3 disclosure .......... channel-admission / channel-refusal records
World channels: specified, UNBOUND for the wright (D7 0.75, D5 0.0).
  world_ingress / world_egress refuse with reasons; every refused
  attempt is logged (boundary probes are audit-visible).
"""

from __future__ import annotations

import argparse
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from . import author_agent as aa
from .agent_behavior import TriggerSource


# ---------------------------------------------------------------------------
# Vocabulary (PROVISIONAL — J-CH2). Kinds are enums; names live in the
# single table below. Behavior never branches on a display string.
# ---------------------------------------------------------------------------

class PrincipalAfferent(str, Enum):
    AP_A1 = "AP-A1"
    AP_A2 = "AP-A2"
    AP_A3 = "AP-A3"
    AP_A4 = "AP-A4"


class PrincipalEfferent(str, Enum):
    AP_E1 = "AP-E1"
    AP_E2 = "AP-E2"
    AP_E3 = "AP-E3"
    AP_E4 = "AP-E4"


class WorldAfferent(str, Enum):
    AW_A1 = "AW-A1"
    AW_A2 = "AW-A2"
    AW_A3 = "AW-A3"
    AW_A4 = "AW-A4"


class WorldEfferent(str, Enum):
    AW_E1 = "AW-E1"
    AW_E2 = "AW-E2"
    AW_E3 = "AW-E3"


CHANNEL_NAMES: dict[Enum, str] = {
    # PROVISIONAL (J-CH2) — rename = relabel this table only.
    PrincipalAfferent.AP_A1: "disposition",
    PrincipalAfferent.AP_A2: "standing disposition",
    PrincipalAfferent.AP_A3: "commission",
    PrincipalAfferent.AP_A4: "authorization",
    PrincipalEfferent.AP_E1: "staged proposal",
    PrincipalEfferent.AP_E2: "report",
    PrincipalEfferent.AP_E3: "disclosure",
    PrincipalEfferent.AP_E4: "clarification request",
    WorldAfferent.AW_A1: "trigger event",
    WorldAfferent.AW_A2: "read data",
    WorldAfferent.AW_A3: "world claim",
    WorldAfferent.AW_A4: "tool result",
    WorldEfferent.AW_E1: "tool invocation",
    WorldEfferent.AW_E2: "flow initiation",
    WorldEfferent.AW_E3: "effect attestation",  # proposed new
}

COMMISSION_KINDS = {PrincipalAfferent.AP_A2, PrincipalAfferent.AP_A3}

# principal_id -> D6 source. The wright binds OPERATOR only; the gate
# below enforces the *profile's* D6 mechanically.
_PRINCIPAL_SOURCES = {"operator": TriggerSource.OPERATOR}


def channel_name(code: Enum) -> str:
    """Display name for a channel code (single source of truth)."""
    return CHANNEL_NAMES[code]


# ---------------------------------------------------------------------------
# Principal-afferent: commission admission (J-CH1 — staged queue canonical;
# CLI is a thin ingress adapter over this same gate).
# ---------------------------------------------------------------------------

def _refuse_admission(root: Path, commission_id: str, channel: str,
                      reasons: list[str]) -> None:
    # _append is the log's single writer; reused (not duplicated) so seq
    # stays gapless. Refused ingress is audit-visible (AP-E3).
    aa._append(root, {"kind": "channel-admission",
                      "commission_id": commission_id,
                      "channel": channel,
                      "admitted": False,
                      "reasons": reasons})
    raise aa.Refusal("; ".join(reasons))


def admit_commission(root: Path, profile: Any, *, commission_id: str,
                     kind: Any = PrincipalAfferent.AP_A3,
                     principal_id: str = "operator",
                     brief: str = "",
                     acceptance_criteria: list[str] | None = None,
                     disposition_ref: str = "") -> dict[str, Any]:
    """Admit one commission across the boundary. Refuse-with-reasons."""
    if isinstance(kind, str):
        try:
            kind = PrincipalAfferent(kind)
        except ValueError:
            kind = None
    channel = kind.value if isinstance(kind, PrincipalAfferent) else str(kind)
    log = aa.read_log(root)

    def refuse(reasons: list[str]) -> None:
        _refuse_admission(root, commission_id, channel, reasons)

    if kind not in COMMISSION_KINDS:
        refuse([f"not a commission channel: {channel} "
                f"(expected AP-A2/AP-A3)"])
    source = _PRINCIPAL_SOURCES.get(principal_id)
    if source is None:
        refuse([f"unknown principal {principal_id!r}: no D6 source mapping"])
    assert source is not None
    if source not in profile.d6_initiative.sources:
        refuse([f"principal {principal_id!r} maps to source "
                f"{source.value!r}, not bound by {profile.agent!r} "
                f"(D6 sources: "
                f"{sorted(s.value for s in profile.d6_initiative.sources)})"])
    if not brief or not brief.strip():
        refuse(["commission brief is empty"])
    criteria = acceptance_criteria or []
    if (not criteria or
            any(not c or not c.strip() for c in criteria)):
        refuse(["acceptance_criteria must be a non-empty list of "
                "non-empty strings"])
    if not disposition_ref or not disposition_ref.strip():
        refuse(["disposition_ref is empty (G1: commission must cite a "
                "disposition)"])
    if any(r.get("kind") == "commission"
           and r.get("commission_id") == commission_id for r in log):
        refuse([f"duplicate commission_id {commission_id!r}"])

    staged = aa.stage_commission(
        root, commission_id, brief, criteria, disposition_ref,
        principal_id=principal_id)
    checks = [f"kind={channel}", f"principal={principal_id}",
              f"source={source.value}", "brief,acceptance,disposition ok",
              "commission_id unique"]
    aa._append(root, {"kind": "channel-admission",
                      "commission_id": commission_id,
                      "channel": channel,
                      "admitted": True,
                      "checks": checks})
    return staged


def pending_commissions(root: Path) -> list[dict[str, Any]]:
    """Commissions with no authoring session — the queue's read side."""
    log = aa.read_log(root)
    sessioned = {r["commission_id"] for r in log
                 if r.get("kind") == "authoring-session"}
    return [r for r in log
            if r.get("kind") == "commission"
            and r.get("commission_id") not in sessioned]


def _next_commission_id(root: Path) -> str:
    seq = 0
    for r in aa.read_log(root):
        seq = max(seq, r.get("seq", 0))
    return f"commission-{seq + 1:04d}"


# ---------------------------------------------------------------------------
# Principal-efferent: result reports (AP-E2)
# ---------------------------------------------------------------------------

def read_results(root: Path, commission_id: str) -> dict[str, Any]:
    """Gather staged verdicts + diagnostics for a commission.

    A refused verdict is a *complete* result (the loop concluded); only
    missing or malformed records refuse, with reasons.
    """
    log = aa.read_log(root)
    mine = [r for r in log if r.get("commission_id") == commission_id]
    if not any(r.get("kind") == "commission" for r in mine):
        raise aa.Refusal(f"no such commission {commission_id!r}")
    verdicts = [r for r in mine if r.get("kind") == "verdict"]
    if not verdicts:
        present = sorted({r.get("kind") for r in mine})
        raise aa.Refusal(
            f"no verdict staged for commission {commission_id!r}; "
            f"present records: {present}")
    out = []
    for v in verdicts:
        if "outcome" not in v:
            raise aa.Refusal(
                f"malformed verdict record seq={v.get('seq')}: "
                "missing outcome")
        entry: dict[str, Any] = {"agent": v.get("agent"),
                                 "outcome": v["outcome"]}
        for k in ("artifact_hash", "profile_hash", "stage",
                  "failure_reason", "reasons"):
            if k in v:
                entry[k] = v[k]
        if v["outcome"] == "verified":
            d = v.get("diagnostics")
            if not isinstance(d, dict) or "all_green" not in d:
                raise aa.Refusal(
                    f"malformed result for {v.get('agent')!r}: verified "
                    "verdict without diagnostics")
            entry["diagnostics"] = {
                "all_green": d["all_green"],
                "failed": d.get("failed", []),
                "n_cases": len(d.get("cases", [])),
            }
        out.append(entry)
    return {
        "commission_id": commission_id,
        "verdicts": out,
        "all_green": all(v.get("outcome") == "verified" and
                         v.get("diagnostics", {}).get("all_green", False)
                         for v in out),
    }


# ---------------------------------------------------------------------------
# World channels: specified, UNBOUND for the wright (D7 0.75, D5 0.0).
# Profile-driven gates; every refused attempt is logged. A profile that
# *would* admit still refuses: handling is a future field-agent matter.
# ---------------------------------------------------------------------------

def _as_world_code(code: Any, enum: type[Enum], direction: str) -> Enum:
    if isinstance(code, enum):
        return code
    try:
        return enum(code)
    except ValueError:
        raise aa.Refusal(
            f"unknown world {direction} code {code!r}; "
            f"expected one of {[e.value for e in enum]}")


def world_ingress(root: Path, profile: Any, code: Any,
                  payload: Any = None) -> None:
    """World → agent. Always refuses for the wright (D7: no world_target)."""
    wc = _as_world_code(code, WorldAfferent, "ingress")
    agent = profile.agent
    if not profile.d7_verification.world_target:
        reasons = [
            f"world ingress refused for {agent!r}: D7 world_target=false "
            "(harness-internal-reader); fail_closed"]
        decision = "refused-profile"
    else:
        reasons = [f"world ingress {wc.value} admitted by profile but "
                   "handling unimplemented: future field-agent matter"]
        decision = "refused-unimplemented"
    aa._append(root, {"kind": "channel-refusal", "direction": "ingress",
                      "code": wc.value, "agent": agent,
                      "decision": decision, "reasons": reasons})
    raise aa.Refusal("; ".join(reasons))


def world_egress(root: Path, profile: Any, code: Any,
                 payload: Any = None) -> None:
    """Agent → world. Always refuses for the wright (D5: no tools)."""
    wc = _as_world_code(code, WorldEfferent, "egress")
    agent = profile.agent
    if not profile.d5_scope.write_scope:
        reasons = [
            f"world egress refused for {agent!r}: D5 write_scope empty "
            "(no contracted tools); staff stage-only"]
        decision = "refused-profile"
    else:
        reasons = [f"world egress {wc.value} admitted by profile but "
                   "handling unimplemented: future field-agent matter"]
        decision = "refused-unimplemented"
    aa._append(root, {"kind": "channel-refusal", "direction": "egress",
                      "code": wc.value, "agent": agent,
                      "decision": decision, "reasons": reasons})
    raise aa.Refusal("; ".join(reasons))


# ---------------------------------------------------------------------------
# CLI: invocation, not conversation.
# Subcommands invoke harness functions and print records. The CLI cannot
# reach the authoring inference (ambient-side, J0) — it stages
# commissions, runs the driver, and prints staged results.
# Exit codes: 0 ok, 2 usage (argparse), 4 governance refusal.
# ---------------------------------------------------------------------------

def _load_profile(name: str) -> Any:
    if name == "wright":
        from .authored.wright import wright_profile
        return wright_profile()
    raise aa.Refusal(f"no profile bound for agent {name!r} in this matter")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="wright-channels",
        description="Author-agent channel CLI: invoke harness machinery "
                    "(stage commissions, run the driver, read results). "
                    "It does not converse.")
    ap.add_argument("--root", default=str(Path(__file__).parent / "authored"),
                    help="authoring root (default: live authored area)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("commission", help="admit + stage a commission")
    c.add_argument("--brief", required=True)
    c.add_argument("--acceptance", required=True,
                   help="';'-separated acceptance criteria")
    c.add_argument("--disposition-ref", required=True)
    c.add_argument("--principal", default="operator")
    c.add_argument("--kind", default="one-shot",
                   choices=["one-shot", "standing"])
    c.add_argument("--id", default=None)
    c.add_argument("--agent", default="wright", choices=["wright"])

    sub.add_parser("drive", help="run the factory driver once")
    r = sub.add_parser("report", help="read staged results")
    r.add_argument("--commission", required=True)
    sub.add_parser("pending", help="list commissions with no session")
    i = sub.add_parser("infer", help="run the Half 2 inference-service loop")
    i.add_argument("--agent", required=True,
                   help="agent module in core.package (must define handle(event, inference_results))")
    i.add_argument("--event", required=True, help="JSON event for the agent")
    i.add_argument("--max-rounds", type=int, default=3)
    i.add_argument("--claude-timeout-s", type=int, default=120)

    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        if args.cmd == "commission":
            profile = _load_profile(args.agent)
            cid = args.id or _next_commission_id(root)
            kind = (PrincipalAfferent.AP_A3 if args.kind == "one-shot"
                    else PrincipalAfferent.AP_A2)
            criteria = [a.strip() for a in args.acceptance.split(";")
                        if a.strip()]
            rec = admit_commission(
                root, profile, commission_id=cid, kind=kind,
                principal_id=args.principal, brief=args.brief,
                acceptance_criteria=criteria,
                disposition_ref=args.disposition_ref)
            print(json.dumps({"commission_id": cid,
                              "channel": kind.value,
                              "channel_name": channel_name(kind),
                              "seq": rec["seq"]}))
        elif args.cmd == "drive":
            print(json.dumps(aa.run_factory_driver_once(root)))
        elif args.cmd == "report":
            print(json.dumps(read_results(root, args.commission), indent=2))
        elif args.cmd == "pending":
            pending = pending_commissions(root)
            print(json.dumps([{"commission_id": r["commission_id"],
                               "seq": r["seq"]} for r in pending]))
        elif args.cmd == "infer":
            from . import author_infer
            t = author_infer.infer_loop(
                agent=args.agent, event=json.loads(args.event),
                max_rounds=args.max_rounds,
                claude_timeout_s=args.claude_timeout_s)
            print(json.dumps(t, indent=1, sort_keys=True))
            return 0 if t["outcome"] == "complete" else 4
        return 0
    except aa.Refusal as e:
        print(json.dumps({"refused": True, "reasons": [str(e)]}),
              file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHANNEL_NAMES",
    "PrincipalAfferent",
    "PrincipalEfferent",
    "WorldAfferent",
    "WorldEfferent",
    "admit_commission",
    "channel_name",
    "main",
    "pending_commissions",
    "read_results",
    "world_egress",
    "world_ingress",
]