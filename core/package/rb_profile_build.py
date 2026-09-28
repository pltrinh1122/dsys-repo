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
                 (charter disagreement -> refuse). O1a (DR-CMD-111): the
                 module exec + builder call run in a supervised child
                 process; this process never execs authored bytes.
  2. VALIDATE — revalidate the child-returned profile JSON (data only);
                 build-time personalization binding (DR-CMD-070); zero
                 warnings; revalidation. A builder-phase failure in the
                 child is raised here (refuses at s2, verbatim reason).
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
  - O1a containment (DR-CMD-111): the arbitrary-code surface (module exec +
    builder call) runs in a supervised child process
    (`sys.executable -m core.package.rb_profile_build --build-child`;
    interpreter pinned to the running one; stdin/stdout JSON protocol).
    The parent hash-pins (pure hashlib), spawns, enforces a 120s timeout,
    applies POSIX best-effort resource limits (RLIMIT_AS 2 GiB, RLIMIT_CPU
    via preexec_fn; skipped off-POSIX), and relays the result. Child
    timeout / crash / malformed output -> deterministic RECEIVE refusal;
    the child's stderr goes to the parent's stderr, never into the
    transcript (byte-equal replay preserved). GATE/COMPILE/VERIFY/STAGE
    run ambient-side on revalidated data only. O1b (whole drive in the
    child) was refused: the placement experiment demonstrated a co-located
    builder corrupting the vetting it shares a process with.
  - A builder returning a non-AgentBehaviorProfile is now a staged
    VALIDATE refusal (fail-closed); pre-O1a it propagated out of
    drive_build uncaught. Deliberate hardening, recorded here.
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

import base64
import hashlib
import json
import os
import subprocess
import sys
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
# O1a containment (DR-CMD-111): the arbitrary-code surface — module exec +
# builder call — runs in a supervised child process. The parent keeps
# integrity (hash-pin, pure hashlib) + supervision (spawn, timeout,
# resource limits, transcript relay) and never execs authored bytes.
# GATE/COMPILE/VERIFY/STAGE stay ambient-side and witnessed, operating
# only on revalidated data.
#
# Why O1a and not O1b (whole drive_build in the child): the placement
# experiment (2026-09-27) falsified the O1b relocation claim. A builder
# that mutates imported factory module state in-process (two lines
# patching the compiler's channel-alias map) staged a must-refuse profile
# through all six steps with a well-formed transcript when vetting shared
# the builder's process; the split placement refused it with the
# byte-identical honest reason. O1b fails open with a well-formed
# transcript — the worst failure shape in this architecture.
#
# Child protocol (stdin -> stdout, exactly one JSON object on stdout):
#   in:  {"module_b64": base64(authored bytes), "profile_name": str}
#   out: {"ok": true, "builder_name": str, "archetypes": [...],
#         "profile_json": <model_dump(mode="json")>}
#     or {"ok": false, "step_id": "receive"|"validate"|"child",
#         "reason": str, "builder_name": str|None, "archetypes": [...]}
# The child's stderr is echoed to the parent's stderr for debugging and
# NEVER enters the transcript (byte-equal replay). Timeouts, crashes, and
# malformed child output become deterministic RECEIVE refusals.
# ---------------------------------------------------------------------------

BUILD_SUBPROCESS_TIMEOUT_S = 120  # as-built; tunable. Builds are infrequent.
_CHILD_ARGV_FLAG = "--build-child"


def _exec_authored_module(module_bytes: bytes, profile_name: str):
    """Exec the authored bytes in a fresh namespace; locate the builder.

    Runs in the child. Raises BuildRefused("receive", ...) with the exact
    reasons the pre-O1a RECEIVE step produced.
    """
    namespace: dict[str, Any] = {
        "__name__": f"rb_build_{profile_name}",
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
    return builder_name, module_archetypes, builder


def _call_builder(builder) -> AgentBehaviorProfile:
    """Call the builder. Runs in the child. Raises BuildRefused("validate",
    ...) with the exact reasons the pre-O1a VALIDATE step produced for the
    builder-call phase.
    """
    try:
        profile = builder()
    except ValidationError as e:
        raise BuildRefused(
            "validate", f"profile construction failed validation: {e}")
    except Exception as e:  # noqa: BLE001 — any builder failure refuses
        raise BuildRefused("validate", f"builder raised {type(e).__name__}: {e}")
    if not isinstance(profile, AgentBehaviorProfile):
        # AS-BUILT hardening: pre-O1a this propagated out of drive_build
        # uncaught; now it is a staged validate refusal (fail-closed).
        raise BuildRefused(
            "validate",
            f"builder returned {type(profile).__name__}, not an "
            f"AgentBehaviorProfile")
    return profile


def _build_child_main() -> None:
    """Child entry point (`python -m core.package.rb_profile_build
    --build-child`). Reads the request JSON on stdin, execs the module,
    calls the builder, writes exactly one JSON object on stdout."""
    payload = json.load(sys.stdin)
    module_bytes = base64.b64decode(payload["module_b64"])
    profile_name = payload["profile_name"]
    try:
        builder_name, module_archetypes, builder = _exec_authored_module(
            module_bytes, profile_name)
    except BuildRefused as e:
        sys.stdout.write(json.dumps({
            "ok": False, "step_id": e.step_id, "reason": e.reason,
            "builder_name": None, "archetypes": [],
        }))
        return
    try:
        profile = _call_builder(builder)
    except BuildRefused as e:
        # Builder-phase failure: still report builder identity so the
        # parent's RECEIVE detail stays faithful; VALIDATE raises it.
        sys.stdout.write(json.dumps({
            "ok": False, "step_id": e.step_id, "reason": e.reason,
            "builder_name": builder_name,
            "archetypes": list(module_archetypes),
        }))
        return
    try:
        profile_json = profile.model_dump(mode="json")
    except Exception as e:  # noqa: BLE001 — fail-closed, never propagate
        sys.stdout.write(json.dumps({
            "ok": False, "step_id": "validate",
            "reason": f"builder product not serializable: "
                      f"{type(e).__name__}: {e}",
            "builder_name": builder_name,
            "archetypes": list(module_archetypes),
        }))
        return
    sys.stdout.write(json.dumps({
        "ok": True,
        "builder_name": builder_name,
        "archetypes": list(module_archetypes),
        "profile_json": profile_json,
    }))


def _limit_child_resources() -> None:
    """POSIX best-effort resource limits for the build child (preexec_fn).

    The timeout in _run_build_child is the hard wall; these are defense in
    depth. Any failure here is swallowed — the child still runs.
    """
    try:
        import resource
        mem = 2 * 1024 ** 3  # 2 GiB address space
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        cpu = BUILD_SUBPROCESS_TIMEOUT_S + 60
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    except Exception:
        pass


def _run_build_child(module_bytes: bytes, profile_name: str) -> dict:
    """Spawn the supervised build child; return its result dict.

    Child timeout / non-zero exit / malformed output become deterministic
    RECEIVE refusals (fail-closed). The child's stderr is echoed to our
    stderr for debugging and never enters the transcript.
    """
    payload = json.dumps({
        "module_b64": base64.b64encode(bytes(module_bytes)).decode("ascii"),
        "profile_name": profile_name,
    })
    argv = [sys.executable, "-m", "core.package.rb_profile_build",
            _CHILD_ARGV_FLAG]
    # The child inherits our cwd and environment, so `core.package` resolves
    # exactly as it did for this process; the interpreter is pinned to the
    # running one (sys.executable).
    preexec = _limit_child_resources if os.name == "posix" else None
    try:
        proc = subprocess.run(argv, input=payload, capture_output=True,
                              text=True, timeout=BUILD_SUBPROCESS_TIMEOUT_S,
                              preexec_fn=preexec)
    except subprocess.TimeoutExpired:
        raise BuildRefused(
            "receive",
            "build subprocess timed out after "
            f"{BUILD_SUBPROCESS_TIMEOUT_S}s")
    if proc.stderr.strip():
        print(f"[rb-profile-build] build child stderr:\n{proc.stderr}",
              file=sys.stderr)
    if proc.returncode != 0:
        raise BuildRefused(
            "receive",
            f"build subprocess exited {proc.returncode}")
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise BuildRefused(
            "receive", "build subprocess returned malformed result")
    if not isinstance(result, dict) or "ok" not in result:
        raise BuildRefused(
            "receive", "build subprocess returned malformed result")
    return result


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
    # O1a (DR-CMD-111): the module exec + builder call run in the supervised
    # child process. This process (the parent) never execs authored bytes:
    # it hash-pinned them above (pure hashlib) and now supervises.
    child = _run_build_child(bytes(module_bytes), profile_name)
    if not child["ok"] and child.get("step_id") != "validate":
        # Exec-phase failure (or child malfunction): RECEIVE owns it, with
        # the child's verbatim reason.
        raise BuildRefused("receive", child["reason"])
    module_archetypes = tuple(child.get("archetypes") or ())
    builder_name = child.get("builder_name") or f"{profile_name}_profile"
    if module_archetypes != declared_archetypes:
        raise BuildRefused(
            "receive",
            f"charter disagreement: build-request declares "
            f"{list(declared_archetypes)} but the authored module declares "
            f"{list(module_archetypes)} — fail-closed")
    if not child["ok"]:
        # Builder-phase failure: VALIDATE owns the refusal (step fidelity —
        # a broken builder refuses at s2, never at s1). Stash and defer.
        ctx["child_build_error"] = child
    else:
        # The profile crosses the boundary as data only; the parent
        # revalidates it below before any vetting step touches it.
        ctx["profile_json"] = child["profile_json"]
    ctx["commission_ref"] = req["commission_ref"]
    ctx["profile_name"] = profile_name
    ctx["content_hash"] = computed
    ctx["declared_archetypes"] = declared_archetypes
    return {"builder": builder_name, "archetypes_match": True}


def _tool_validate_profile(ctx: dict) -> dict:
    child_error = ctx.get("child_build_error")
    if child_error is not None:
        # Builder-phase failure relayed from the child: raised here so the
        # refusal lands at VALIDATE (s2) with the verbatim reason.
        raise BuildRefused("validate", child_error["reason"])
    try:
        generic = AgentBehaviorProfile.model_validate(ctx["profile_json"])
    except ValidationError as e:
        raise BuildRefused(
            "validate", f"profile data failed revalidation: {e}")
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


if __name__ == "__main__" and _CHILD_ARGV_FLAG in sys.argv:
    _build_child_main()
