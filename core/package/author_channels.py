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
import hashlib
import json
import shutil
import sys
import tempfile
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
# Authoring-package staging (AP-E1 staged-proposal; the MECHANICAL side of
# "authoring"). The ambient's inference delivers an AuthoringPackage; this
# command checks everything checkable and stages it. Zero inference here.
#
# Pipeline (fail-closed, reasons at every step):
#   G1 envelope -> commission exists + operator-attributed
#   -> stage bytes + hash-pinned manifest
#   -> G2 archetype gate, run early so the ambient gets immediate
#      feedback (drive_one re-runs it; the driver trusts nothing)
#   -> G4 rationale present, G6 diagnostic_cases present
#   -> record authoring session -> stage build-request (J1-ii)
# A refusal after bytes are staged leaves the bytes without a
# build-request: the driver builds only staged build-requests, so a
# refused package can never be built silently.
# ---------------------------------------------------------------------------

def stage_profile_package(root: Path, *, agent_name: str, profile_file: Path,
                          rationale_file: Path, archetypes: list[str],
                          commission_id: str, note: str = "") -> dict:
    from .author_package import (AuthoringPackage, CHECKLIST_ITEMS,
                                 PackageViolation, validate_envelope)
    from .factory_archetypes import check_profile

    if list(CHECKLIST_ITEMS) != list(aa.CHECKLIST):
        raise aa.Refusal("checklist drift: author_package.CHECKLIST_ITEMS "
                         "does not match author_agent.CHECKLIST")

    def refuse(reasons: list[str]):
        raise aa.Refusal("; ".join(reasons))

    try:
        source = profile_file.read_text()
    except OSError as e:
        refuse([f"cannot read profile file {profile_file}: {e}"])
    try:
        rationale = rationale_file.read_text()
    except OSError as e:
        refuse([f"cannot read rationale file {rationale_file}: {e}"])

    pkg = AuthoringPackage(
        agent_name=agent_name, profile_source=source, rationale=rationale,
        archetypes=tuple(archetypes), commission_id=commission_id,
        checklist={k: True for k in CHECKLIST_ITEMS}, note=note)
    try:
        summary = validate_envelope(pkg)
    except PackageViolation as e:
        refuse([f"package envelope invalid: {e}"])

    log = aa.read_log(root)
    commissions = [r for r in log
                   if r.get("kind") == "commission"
                   and r.get("commission_id") == commission_id]
    if not commissions:
        refuse([f"no such commission {commission_id!r} (G1)"])
    if commissions[-1].get("principal_id") != "operator":
        refuse([f"commission {commission_id!r} is not operator-attributed "
                f"(principal={commissions[-1].get('principal_id')!r}) (G1)"])

    staged = aa.stage_authored_profile(
        root, agent_name, source, rationale, commission_id)

    module = aa._load_authored(root, agent_name)
    builder = getattr(module, f"{agent_name}_profile", None)
    if builder is None:
        refuse([f"module lacks builder {agent_name}_profile() (G2)"])
    try:
        violations = check_profile(builder(), archetypes)
    except ValueError as e:
        refuse([f"G2 archetype-gate: {e}"])
    if violations:
        refuse([f"G2 archetype-gate: {v}" for v in violations])

    cases_fn = getattr(module, "diagnostic_cases", None)
    if cases_fn is None:
        refuse(["module lacks diagnostic_cases() (G6)"])
    if not cases_fn():
        refuse(["diagnostic_cases() empty (G6: profile incomplete)"])

    session = aa.record_authoring_session(
        root, commission_id, agent_name,
        {k: True for k in aa.CHECKLIST}, note=note)
    req = aa.stage_build_request(root, agent_name, commission_id)
    return {
        "agent": agent_name,
        "profile_sha256": staged["sha256"],
        "session_seq": session["seq"],
        "build_request_seq": req["seq"],
        "gates": {"G1 commission operator-attributed": "ok",
                  "G2 archetype-gate": "ok",
                  "G4 rationale staged": "ok",
                  "G5 stage-only": "ok (command stages; never deploys)",
                  "G6 diagnostics authored": "ok"},
        "envelope": summary,
    }


# ---------------------------------------------------------------------------
# Customization sequence channels (the bridge: customizer proposes,
# operator disposes, factory registers — pre-delivery, never after).
# ---------------------------------------------------------------------------

def stage_customization_proposal(root: Path, *, proposal_file: Path,
                                 commission_id: str,
                                 note: str = "") -> dict:
    """Mechanical side of 'propose': validate the envelope, require an
    operator-attributed commission, RE-RUN the registry lookup to verify
    the carried absence evidence, then stage the proposal (bytes pinned).
    Refuses with reasons on any failure. Never registers, never builds."""
    from .customizer import (CustomizationProposal, ProposalViolation,
                             validate_proposal_envelope)
    from . import artifact_registry as reg

    def refuse(reasons: list[str]):
        raise aa.Refusal("; ".join(reasons))

    try:
        raw = json.loads(proposal_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        refuse([f"cannot read proposal file {proposal_file}: {e}"])
    try:
        proposal = CustomizationProposal(**raw)
    except Exception as e:
        refuse([f"proposal envelope malformed: {e}"])
    try:
        summary = validate_proposal_envelope(proposal)
    except ProposalViolation as e:
        refuse([f"proposal envelope invalid: {e}"])

    log = aa.read_log(root)
    commissions = [r for r in log
                   if r.get("kind") == "commission"
                   and r.get("commission_id") == commission_id]
    if not commissions:
        refuse([f"no such commission {commission_id!r}"])
    if commissions[-1].get("principal_id") != "operator":
        refuse([f"commission {commission_id!r} is not operator-attributed "
                f"(principal={commissions[-1].get('principal_id')!r})"])
    if proposal.commission_id != commission_id:
        refuse([f"proposal cites {proposal.commission_id!r}, staged under "
                f"{commission_id!r}: commission mismatch"])

    # Verify the evidence: re-run the lookup NOW and compare.
    fresh = reg.absence_evidence(root, proposal.artifact_kind,
                                 proposal.registry_evidence.query)
    if sorted(fresh["hits"]) != sorted(proposal.registry_evidence.hits):
        refuse([f"registry evidence stale or forged: proposal claims hits "
                f"{proposal.registry_evidence.hits}, registry now returns "
                f"{fresh['hits']}"])

    # Supersede chain: a versioned customization must name a registered
    # artifact and propose exactly latest.version + 1.
    if proposal.supersedes is not None:
        latest = reg.latest_version(root, proposal.artifact_kind,
                                    proposal.supersedes)
        if latest is None:
            refuse([f"supersedes={proposal.supersedes!r}: not registered"])
        if proposal.proposed_version != latest.version + 1:
            refuse([f"supersedes {proposal.artifact_kind}/"
                    f"{proposal.supersedes} v{latest.version}: "
                    f"proposed_version must be {latest.version + 1}, got "
                    f"{proposal.proposed_version}"])
        if proposal.artifact_name != latest.name:
            refuse([f"supersede must version the same artifact: proposal "
                    f"names {proposal.artifact_name!r}, supersedes "
                    f"{latest.name!r}"])

    rec = aa._append(root, {
        "kind": "staged-proposal",
        "proposal": proposal.model_dump(),
        "proposal_sha256": summary["artifact_sha256"],
        "commission_id": commission_id,
        "status": "pending-disposition",
        "note": note,
    })
    return {"proposal_seq": rec["seq"],
            "proposal_sha256": summary["artifact_sha256"],
            "status": "pending-disposition",
            "evidence_verified": fresh}


def adopt_customization_proposal(root: Path, *, proposal_seq: int,
                                 disposition_ref: str,
                                 by: str = "operator") -> dict:
    """Mechanical side of 'dispose -> register': adopt a pending proposal.

    Requires the disposition to be operator-attributed (by == "operator"
    with a non-empty disposition_ref). Registers the artifact versioned
    and content-pinned; marks the proposal adopted. A proposal is adopted
    once; adoption is the only path to registration — the customizer can
    never self-register (its D5 write_scope is empty).
    """
    from . import artifact_registry as reg

    def refuse(reasons: list[str]):
        raise aa.Refusal("; ".join(reasons))

    if by != "operator":
        refuse([f"adoption refused: disposition must be operator-attributed "
                f"(by={by!r})"])
    if not disposition_ref or not disposition_ref.strip():
        refuse(["adoption refused: disposition_ref required — registration "
                "rests on disposition, never on drafting"])

    log = aa.read_log(root)
    proposals = [r for r in log
                 if r.get("kind") == "staged-proposal"
                 and r.get("seq") == proposal_seq]
    if not proposals:
        refuse([f"no staged proposal seq={proposal_seq}"])
    prec = proposals[-1]
    if any(r.get("kind") == "proposal-adopted"
           and r.get("proposal_seq") == proposal_seq for r in log):
        refuse([f"proposal seq={proposal_seq} already adopted: adopted "
                f"once, never twice"])
    p = prec["proposal"]
    try:
        rec = reg.register(
            root, kind=p["artifact_kind"], name=p["artifact_name"],
            artifact_bytes=p["artifact_source"].encode("utf-8"),
            producer="customizer", commission_id=p["commission_id"],
            disposition_ref=disposition_ref)
    except reg.RegistryError as e:
        refuse([f"registration refused: {e}"])

    aa._append(root, {"kind": "proposal-adopted",
                      "proposal_seq": proposal_seq,
                      "artifact": rec.model_dump(),
                      "disposition_ref": disposition_ref,
                      "by": by})
    # mark the staged proposal adopted (append-only: a superseding record)
    return {"proposal_seq": proposal_seq,
            "status": "adopted",
            "artifact": rec.model_dump()}


# ---------------------------------------------------------------------------
# Verified-build runtime: the runtime executes only VERIFIED builds.
# resolve_verified_agent pins the staged bytes (sha256 vs the staged
# manifest), requires a staged build-request for those bytes, and
# requires a "verified" verdict for the agent. Anything else refuses
# with reasons — an unverified or tampered-with agent never executes.
# ---------------------------------------------------------------------------

def resolve_verified_agent(root: Path, agent_name: str
                           ) -> tuple[Path, str]:
    """Return (module_path, sha256) for a verified built agent.

    Raises aa.Refusal unless the staged bytes are hash-pinned, covered
    by a build-request, and the agent has a "verified" verdict.
    """
    log = aa.read_log(root)
    staged = [r for r in log
              if r.get("kind") == "staged-profile"
              and r.get("agent") == agent_name]
    if not staged:
        raise aa.Refusal(f"no staged profile for {agent_name!r}")
    pin = staged[-1]["sha256"]
    path = root / f"{agent_name}.py"
    if not path.exists():
        raise aa.Refusal(f"staged module missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != pin:
        raise aa.Refusal(
            f"staged bytes changed under the runtime: pinned "
            f"{pin[:12]} vs actual {actual[:12]}")
    if not any(r.get("kind") == "build-request"
               and r.get("agent") == agent_name
               and r.get("profile_sha256") == pin for r in log):
        raise aa.Refusal(
            f"no build-request covers pinned bytes {pin[:12]} "
            f"for {agent_name!r}")
    if not any(r.get("kind") == "verdict"
               and r.get("agent") == agent_name
               and r.get("outcome") == "verified" for r in log):
        raise aa.Refusal(f"no verified verdict for {agent_name!r}; "
                         "the runtime executes verified builds only")
    return path, pin


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
    s = sub.add_parser("stage-profile",
                       help="stage an authored profile package "
                            "(mechanical side of authoring)")
    s.add_argument("--commission", required=True)
    s.add_argument("--agent", required=True,
                   help="agent name; module must define "
                        "{agent}_profile(), ARCHETYPES, diagnostic_cases()")
    s.add_argument("--profile-file", required=True,
                   help="path to the authored profile module source")
    s.add_argument("--rationale-file", required=True,
                   help="path to the staged rationale prose (G4)")
    s.add_argument("--archetypes", required=True,
                   help="comma-separated declared archetypes")
    s.add_argument("--note", default="",
                   help="ambient note recorded with the session")
    r = sub.add_parser("report", help="read staged results")
    r.add_argument("--commission", required=True)
    sub.add_parser("pending", help="list commissions with no session")
    i = sub.add_parser("infer", help="run the Half 2 inference-service loop")
    i.add_argument("--agent", required=True,
                   help="agent module in core.package (must define handle(event, inference_results))")
    i.add_argument("--root", default=None,
                   help="authoring root: resolve --agent as a VERIFIED "
                        "build (hash-pinned, verdict-gated) and execute "
                        "the staged module instead of core.package")
    i.add_argument("--event", required=True, help="JSON event for the agent")
    i.add_argument("--max-rounds", type=int, default=3)
    i.add_argument("--claude-timeout-s", type=int, default=120)
    p = sub.add_parser("propose-customization",
                       help="stage a customization proposal (mechanical "
                            "side of 'propose'; never registers)")
    p.add_argument("--commission", required=True)
    p.add_argument("--proposal-file", required=True,
                   help="JSON CustomizationProposal envelope")
    p.add_argument("--note", default="")
    a = sub.add_parser("adopt-proposal",
                       help="adopt a pending proposal on operator "
                            "disposition (registers the artifact)")
    a.add_argument("--proposal-seq", type=int, required=True)
    a.add_argument("--disposition-ref", required=True)
    a.add_argument("--by", default="operator")

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
        elif args.cmd == "stage-profile":
            rec = stage_profile_package(
                root, agent_name=args.agent,
                profile_file=Path(args.profile_file),
                rationale_file=Path(args.rationale_file),
                archetypes=[a.strip() for a in args.archetypes.split(",")
                            if a.strip()],
                commission_id=args.commission, note=args.note)
            print(json.dumps(rec, indent=2))
        elif args.cmd == "report":
            print(json.dumps(read_results(root, args.commission), indent=2))
        elif args.cmd == "pending":
            pending = pending_commissions(root)
            print(json.dumps([{"commission_id": r["commission_id"],
                               "seq": r["seq"]} for r in pending]))
        elif args.cmd == "propose-customization":
            rec = stage_customization_proposal(
                root, proposal_file=Path(args.proposal_file),
                commission_id=args.commission, note=args.note)
            print(json.dumps(rec, indent=2))
        elif args.cmd == "adopt-proposal":
            rec = adopt_customization_proposal(
                root, proposal_seq=args.proposal_seq,
                disposition_ref=args.disposition_ref, by=args.by)
            print(json.dumps(rec, indent=2))
        elif args.cmd == "infer":
            from . import author_infer
            ns, overlay, sha = "", None, None
            if args.root is not None:
                vroot = Path(args.root)
                mod_path, sha = resolve_verified_agent(vroot, args.agent)
                tmp = Path(tempfile.mkdtemp(prefix="verified-agent-"))
                shutil.copyfile(mod_path, tmp / f"{args.agent}.py")
                overlay, ns = tmp, "authored"
            try:
                t = author_infer.infer_loop(
                    agent=args.agent, event=json.loads(args.event),
                    max_rounds=args.max_rounds,
                    claude_timeout_s=args.claude_timeout_s,
                    authored_overlay=overlay, agent_ns=ns,
                    agent_sha256=sha)
            finally:
                if overlay is not None:
                    shutil.rmtree(overlay, ignore_errors=True)
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
    "stage_customization_proposal",
    "adopt_customization_proposal",
    "stage_profile_package",
    "world_egress",
    "world_ingress",
]