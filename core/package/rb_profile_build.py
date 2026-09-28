"""rb-profile-build — the profile-build run-book (DR-CMD-101).

Closes the bootstrap loop at the contract level with wiring, not a new
agent. The falsification it implements (rendered by Peter 2026-09-27):
no `builder` agent is needed — the role is filled by wright (authors) +
the factory driver (builds) + ambient labor; the real gap was the
unclosed loop commission -> wright authors -> factory driver builds ->
staging for disposition, previously closed by hand-driven ambient
subagents.

The seam (load-bearing): the wright's defined output is a staged
*build-request* for the factory driver. This run-book's input contract IS
that build-request::

    {commission_ref, profile_name, authored_module_bytes, content_hash,
     declared_archetypes}

The wright side stays ambient labor: no wright runtime exists, and this
run-book does NOT invoke one and does NOT invoke any LLM. The authored
bytes arrive as an injected discrete step-change (the v1 commitment:
inference reaches the machine only as discrete step-changes), labeled as
such in DR-CMD-101.

Six strictly-sequential steps, fail-closed at every gate; refusals are
staged with exact reasons, never worked around:

  1. RECEIVE  — accept the build-request; sha256 over the authored bytes
                 must equal content_hash (tamper -> refuse, fail-closed;
                 cf. the verified-build hash-pinning precedent). The
                 module's own ARCHETYPES must agree with declared_archetypes
                 (charter disagreement -> refuse).
  2. VALIDATE — construct the profile via the module's
                 <profile_name>_profile builder; build-time personalization
                 binding (DR-CMD-070); zero warnings; revalidation.
  3. GATE     — the archetype gate (check_profile) over declared_archetypes;
                 violations -> refuse with exact reasons.
  4. COMPILE  — compile_profile; CompileRefused -> refuse with the EXACT
                 reason string. This is where honesty is tested: the three
                 clerk profiles' routing refusals reproduce verbatim.
  5. VERIFY   — factory verifier; anything but verified+operable -> refuse.
  6. STAGE    — all green -> stage the content hashes + full build
                 transcript for Operator disposition (adopt / register /
                 publish). The run-book NEVER publishes, registers, or
                 disposes.

As-built boundaries (honest, not bridged):
  - Authored bytes execute in-process (exec in a fresh namespace). This is
    the recorded open gap "contain proposed authored code during
    stage-profile" — same trust posture as today's hand-driven builds,
    containment NOT claimed.
  - The build-time binding (principal_id="factory-build-time",
    disposition_ref="commission:<commission_ref>") is NOT a deployment
    personalization: it satisfies DR-CMD-070's compiler contract (the
    profile must have passed through bind_personalization()) while the
    archetype gate itself stays the run-book's own GATE step. The
    commission_ref is the Operator disposition authorizing the build.
  - Profile-level diagnostic_cases() (e.g. the triager's T-D1..T-D8) are
    authoring-time checks, run by whoever authors the module; the
    pipeline-time check is the factory verifier (step 5).

Zero inference: drive_build is a pure function of the build-request.
Deterministic replay: same build-request bytes -> byte-equal transcript
(canonical JSON; no timestamps, no temp paths, no randomness anywhere in
the transcript path).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from .agent_behavior import AgentBehaviorProfile, bind_personalization
from .factory_archetypes import check_profile
from .factory_compiler import CompileRefused, compile_profile
from .factory_verifier import verify
from .schema import RunBook, Step, Tool

RUNBOOK_ID = "rb-profile-build"
RELEASE_VERSION = "0.1.0"

BUILD_TIME_PRINCIPAL = "factory-build-time"


class BuildRefused(Exception):
    """A run-book step refused its work: fail-closed.

    Carries the step id and the EXACT reason; the drive halts and the
    refusal is staged in the transcript. A refusal is never downgraded.
    """

    def __init__(self, step_id: str, reason: str):
        super().__init__(f"{step_id} refused: {reason}")
        self.step_id = step_id
        self.reason = reason


# ---------------------------------------------------------------------------
# Run-book entities (the updater.py convention: RunBook/Step/Tool entities,
# steps strictly sequential, each step an (allowlisted expr, tool) pair)
# ---------------------------------------------------------------------------

_TOOL_IDS = (
    "tool-receive-build-request",
    "tool-validate-profile",
    "tool-gate-archetypes",
    "tool-compile-profile",
    "tool-verify-profile",
    "tool-stage-for-disposition",
)


def _runbook_entities() -> tuple[list[RunBook], list[Step], list[Tool]]:
    runbooks = [RunBook(id=RUNBOOK_ID, release_version=RELEASE_VERSION,
                        name=RUNBOOK_ID)]
    steps = [Step(id=f"{RUNBOOK_ID}-s{seq}", runbook_id=RUNBOOK_ID, seq=seq,
                  expr="True", tool_id=tool_id)
             for seq, tool_id in enumerate(_TOOL_IDS, start=1)]
    tools = [Tool(id=tool_id, name=tool_id) for tool_id in _TOOL_IDS]
    return runbooks, steps, tools


RUNBOOKS, STEPS, TOOLS_DECLARED = _runbook_entities()


# ---------------------------------------------------------------------------
# Tools — each a pure function of ctx (no world: the build-request is the
# injected step-change the run-book is closed over). Each returns its
# step-detail dict, or raises BuildRefused.
# ---------------------------------------------------------------------------

_REQUIRED_REQUEST_KEYS = ("commission_ref", "profile_name",
                          "authored_module_bytes", "content_hash",
                          "declared_archetypes")


def _tool_receive_build_request(ctx: dict) -> dict:
    req = ctx.get("build_request")
    if not isinstance(req, dict):
        raise BuildRefused("receive",
                           "malformed build-request: not a mapping")
    for key in _REQUIRED_REQUEST_KEYS:
        if key not in req:
            raise BuildRefused(
                "receive", f"malformed build-request: missing {key!r}")
    profile_name = req["profile_name"]
    module_bytes = req["authored_module_bytes"]
    declared_hash = req["content_hash"]
    declared_archetypes = tuple(req["declared_archetypes"])
    if not isinstance(module_bytes, (bytes, bytearray)):
        raise BuildRefused(
            "receive", "malformed build-request: authored_module_bytes "
                       "must be bytes")
    computed = hashlib.sha256(bytes(module_bytes)).hexdigest()
    if computed != declared_hash:
        raise BuildRefused(
            "receive",
            f"build-request hash mismatch: declared {declared_hash} != "
            f"computed {computed} (tamper or corruption — fail-closed)")
    # Execute the authored bytes in a fresh namespace (no sys.modules
    # pollution; deterministic: same bytes -> same namespace contents).
    # AS-BUILT: in-process execution — the containment gap is recorded
    # open work, not claimed (see module docstring).
    namespace: dict[str, Any] = {
        "__name__": f"rb_build_{profile_name}_{computed[:12]}",
    }
    try:
        code = compile(bytes(module_bytes),
                       f"<build-request:{profile_name}>", "exec")
    except (SyntaxError, ValueError) as e:
        raise BuildRefused(
            "receive",
            f"authored module does not compile: {type(e).__name__}: {e}")
    try:
        exec(code, namespace)
    except Exception as e:  # noqa: BLE001 — any exec failure refuses
        raise BuildRefused(
            "receive",
            f"authored module does not execute: {type(e).__name__}: {e}")
    builder_name = f"{profile_name}_profile"
    builder = namespace.get(builder_name)
    if not callable(builder):
        raise BuildRefused(
            "receive",
            f"authored module exposes no builder {builder_name!r} "
            f"(expected '<profile_name>_profile')")
    module_archetypes = tuple(namespace.get("ARCHETYPES") or ())
    if module_archetypes != declared_archetypes:
        raise BuildRefused(
            "receive",
            f"charter disagreement: build-request declares "
            f"{list(declared_archetypes)} but the authored module declares "
            f"{list(module_archetypes)} — fail-closed")
    ctx["commission_ref"] = req["commission_ref"]
    ctx["profile_name"] = profile_name
    ctx["content_hash"] = computed
    ctx["declared_archetypes"] = declared_archetypes
    ctx["builder"] = builder
    return {"builder": builder_name, "archetypes_match": True}


def _tool_validate_profile(ctx: dict) -> dict:
    builder: Callable[[], AgentBehaviorProfile] = ctx["builder"]
    try:
        generic = builder()
    except ValidationError as e:
        raise BuildRefused(
            "validate", f"profile construction failed validation: {e}")
    except Exception as e:  # noqa: BLE001 — any builder failure refuses
        raise BuildRefused(
            "validate", f"builder raised {type(e).__name__}: {e}")
    # Build-time binding (NOT a deployment personalization): satisfies
    # DR-CMD-070's compiler contract. The archetype gate itself is the
    # run-book's own GATE step, so gate=None here by design.
    try:
        profile = bind_personalization(
            generic,
            principal_id=BUILD_TIME_PRINCIPAL,
            bindings={},
            disposition_ref=f"commission:{ctx['commission_ref']}",
            gate=None,
        )
    except ValueError as e:
        raise BuildRefused("validate", f"personalization binding refused: {e}")
    try:
        AgentBehaviorProfile.model_validate(profile.model_dump(mode="json"))
    except ValidationError as e:
        raise BuildRefused("validate", f"profile revalidation failed: {e}")
    warnings = profile.warnings()
    if warnings:
        raise BuildRefused(
            "validate",
            "profile validates with warnings (must be zero): "
            + "; ".join(warnings))
    ctx["profile"] = profile
    return {"position_vector": profile.position_vector(), "warnings": []}


def _tool_gate_archetypes(ctx: dict) -> dict:
    violations = check_profile(ctx["profile"], ctx["declared_archetypes"])
    if violations:
        raise BuildRefused("gate", "; ".join(str(v) for v in violations))
    return {"violations": []}


def _tool_compile_profile(ctx: dict) -> dict:
    try:
        artifact = compile_profile(ctx["profile"])
    except CompileRefused as e:
        # The EXACT reason string is staged — honesty is tested here.
        raise BuildRefused("compile", str(e))
    ctx["artifact"] = artifact
    return {
        "profile_hash": artifact.manifest.profile_hash,
        "plan_hash": artifact.plan.plan_hash,
        "artifact_hash": artifact.manifest.artifact_hash,
    }


def _tool_verify_profile(ctx: dict) -> dict:
    # The staging path never enters the transcript (determinism).
    root = Path(tempfile.mkdtemp(
        prefix=f"rb-profile-build-{ctx['profile_name']}-"))
    verdict = verify(ctx["artifact"], ctx["profile"], root)
    if verdict.verdict != "verified" or not verdict.operable:
        raise BuildRefused(
            "verify",
            f"verdict={verdict.verdict} operable={verdict.operable} "
            f"failure_reason={verdict.failure_reason or 'none'}")
    ctx["verdict"] = verdict
    return {
        "verdict": verdict.verdict,
        "operable": verdict.operable,
        "n_static": len(verdict.static_results),
        "n_probes": len(verdict.probe_results),
    }


def _tool_stage_for_disposition(ctx: dict) -> dict:
    artifact = ctx["artifact"]
    staged = {
        "disposition": "staged-for-operator",
        "commission_ref": ctx["commission_ref"],
        "profile_name": ctx["profile_name"],
        "content_hash": ctx["content_hash"],
        "profile_hash": artifact.manifest.profile_hash,
        "plan_hash": artifact.plan.plan_hash,
        "artifact_hash": artifact.manifest.artifact_hash,
        "verdict": "verified",
        "note": ("NOT published; NOT registered; NOT disposed — Operator "
                 "disposition required (adopt / register / publish)."),
    }
    ctx["staged"] = staged
    return {"staged": True}


TOOLS: dict[str, Callable[[dict], dict]] = {
    "tool-receive-build-request": _tool_receive_build_request,
    "tool-validate-profile": _tool_validate_profile,
    "tool-gate-archetypes": _tool_gate_archetypes,
    "tool-compile-profile": _tool_compile_profile,
    "tool-verify-profile": _tool_verify_profile,
    "tool-stage-for-disposition": _tool_stage_for_disposition,
}


# ---------------------------------------------------------------------------
# Driver — strictly sequential; a refusal halts the run and is staged.
# ---------------------------------------------------------------------------

def drive_build(build_request: dict) -> dict:
    """Run the six steps strictly sequentially over one build-request.

    Pure function of the build-request: no LLM calls, no ambient
    discretion, no timestamps, no randomness in the transcript path.
    Returns the build transcript (deterministic: same bytes -> byte-equal
    transcript via transcript_bytes()).
    """
    ctx: dict[str, Any] = {"build_request": build_request}
    steps_out: list[dict[str, Any]] = []
    terminal: dict[str, Any] | None = None
    for step in sorted(STEPS, key=lambda s: s.seq):
        try:
            detail = TOOLS[step.tool_id](ctx) or {}
            steps_out.append({
                "seq": step.seq,
                "step_id": step.id,
                "tool_id": step.tool_id,
                "status": "ok",
                "detail": detail,
            })
        except BuildRefused as e:
            steps_out.append({
                "seq": step.seq,
                "step_id": step.id,
                "tool_id": step.tool_id,
                "status": "refused",
                "reason": e.reason,
            })
            terminal = {"outcome": "refused", "at_step": step.id,
                        "reason": e.reason}
            break
    if terminal is None:
        terminal = {"outcome": "staged", "at_step": None, "reason": ""}
    transcript: dict[str, Any] = {
        "runbook_id": RUNBOOK_ID,
        "release_version": RELEASE_VERSION,
        "commission_ref": ctx.get("commission_ref", ""),
        "profile_name": ctx.get("profile_name", ""),
        "content_hash": ctx.get("content_hash", ""),
        "declared_archetypes": list(ctx.get("declared_archetypes", [])),
        "steps": steps_out,
        "terminal": terminal,
    }
    if "staged" in ctx:
        transcript["staged"] = ctx["staged"]
    return transcript


def transcript_bytes(transcript: dict) -> bytes:
    """Canonical bytes of a transcript (the replay-identity)."""
    return json.dumps(transcript, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


__all__ = [
    "RUNBOOK_ID",
    "RELEASE_VERSION",
    "BuildRefused",
    "RUNBOOKS",
    "STEPS",
    "TOOLS_DECLARED",
    "TOOLS",
    "drive_build",
    "transcript_bytes",
]
