"""Harness-side author-agent loop (DR-CMD-083).

The author-agent is HARNESS-SIDE: ambient inference governed by the
ratified wright profile (core/package/authored/wright.py). This module is
the deterministic harness machinery that governed ambient uses — zero
inference inside:

  commission -> author (ambient, governed) -> stage -> drive -> diagnose

- Commissions, authoring sessions, staged bytes, build-requests, verdicts,
  and diagnostic reports are recorded in an append-only JSONL authoring
  log (seq-numbered, no timestamps — deterministic replay).
- Authored profile modules live in <root>/<agent>.py and use
  ABSOLUTE imports (from core.package.…), so the driver can load them
  from any root via importlib without package context. The live root is
  core/package/authored/ itself (log beside modules, one copy of the
  bytes); replay roots are temp dirs holding pinned copies.
- The factory driver runs the same pipeline as
  factory_profile_set_001.run_agent (archetype gate -> personalization
  binding -> validate -> compile -> verify), triggered by staged
  build-requests instead of a hardcoded list (J1-ii, DR-CMD-083).
- The driver then runs the profile's own diagnostic_cases() post-verify
  (J2). All-green = the agent's self-diagnostic passes.

Conventions for an authored module:
  <agent>_profile() -> AgentBehaviorProfile   (builder, set-001 style)
  ARCHETYPES: tuple[str, ...]                  (declared archetypes)
  diagnostic_cases() -> list[(case_id, predicate)]
      predicate(ctx) -> (passed: bool, detail: str)
      ctx = {"profile", "artifact", "verdict", "module"}
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Authoring log (append-only, seq-numbered, no timestamps)
# ---------------------------------------------------------------------------

def _log_path(root: Path) -> Path:
    return root / "authoring-log.jsonl"


def _append(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    lp = _log_path(root)
    seq = 0
    if lp.exists():
        for line in lp.read_text().splitlines():
            if line.strip():
                seq = max(seq, json.loads(line)["seq"])
    record = {"seq": seq + 1, **record}
    with lp.open("a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_log(root: Path) -> list[dict[str, Any]]:
    lp = _log_path(root)
    if not lp.exists():
        return []
    return [json.loads(line) for line in lp.read_text().splitlines()
            if line.strip()]


# ---------------------------------------------------------------------------
# Commission + authoring session (governance checklist, spec §6)
# ---------------------------------------------------------------------------

CHECKLIST = ("G1 commission exists and is operator-attributed",
             "G2 declared archetypes conform (mechanical gate)",
             "G3 profile validates with zero warnings (mechanical)",
             "G4 rationale staged (judgment calls as prose)",
             "G5 stage-only: no deployment, no commit, no push",
             "G6 diagnostics authored alongside (J2)")


def stage_commission(root: Path, commission_id: str, role_brief: str,
                     acceptance_criteria: list[str],
                     disposition_ref: str,
                     principal_id: str = "operator") -> dict[str, Any]:
    """Record an operator commission. Nothing is authored without one."""
    if not principal_id:
        raise ValueError("commission requires an attributed principal")
    return _append(root, {
        "kind": "commission",
        "commission_id": commission_id,
        "principal_id": principal_id,
        "role_brief": role_brief,
        "acceptance_criteria": acceptance_criteria,
        "disposition_ref": disposition_ref,
    })


def record_authoring_session(root: Path, commission_id: str, agent_name: str,
                             checklist: dict[str, bool],
                             note: str = "") -> dict[str, Any]:
    """Record the governance checklist. A missed item refuses the session."""
    missing = [k for k in CHECKLIST if not checklist.get(k, False)]
    if missing:
        raise Refusal(f"authoring session refused; checklist missed: {missing}")
    commissions = [r for r in read_log(root)
                   if r["kind"] == "commission"
                   and r["commission_id"] == commission_id]
    if not commissions:
        raise Refusal(f"no such commission {commission_id!r} (G1)")
    return _append(root, {
        "kind": "authoring-session",
        "commission_id": commission_id,
        "agent": agent_name,
        "checklist": {k: True for k in CHECKLIST},
        "note": note,
    })


class Refusal(Exception):
    """Governance refusal with explicit reasons (never silent)."""


# ---------------------------------------------------------------------------
# Staging authored bytes (hash-pinned; the bytes are proposed, not trusted)
# ---------------------------------------------------------------------------

def stage_authored_profile(root: Path, agent_name: str, source: str,
                           rationale: str, commission_id: str,
                           ) -> dict[str, Any]:
    """Stage an authored profile module. Returns the pinned manifest."""
    target = root / f"{agent_name}.py"
    digest = hashlib.sha256(source.encode()).hexdigest()
    target.write_text(source)
    return _append(root, {
        "kind": "staged-profile",
        "commission_id": commission_id,
        "agent": agent_name,
        "path": str(target),
        "sha256": digest,
        "rationale": rationale,
    })


def stage_build_request(root: Path, agent_name: str,
                        commission_id: str) -> dict[str, Any]:
    """Stage a build-request for the driver (J1-ii: stigmergic invocation)."""
    staged = [r for r in read_log(root)
              if r["kind"] == "staged-profile" and r["agent"] == agent_name]
    if not staged:
        raise Refusal(f"no staged profile for {agent_name!r}")
    return _append(root, {
        "kind": "build-request",
        "commission_id": commission_id,
        "agent": agent_name,
        "profile_sha256": staged[-1]["sha256"],
    })


# ---------------------------------------------------------------------------
# Diagnostics runner (J2)
# ---------------------------------------------------------------------------

DiagnosticCtx = dict[str, Any]
Predicate = Callable[[DiagnosticCtx], tuple[bool, str]]


def run_diagnostics(module: Any, profile: Any, artifact: Any,
                    verdict: Any) -> dict[str, Any]:
    """Run the profile's own diagnostic_cases(). All must pass."""
    cases = module.diagnostic_cases()
    if not cases:
        raise Refusal("diagnostic_cases() empty (G6: profile incomplete)")
    ctx: DiagnosticCtx = {"profile": profile, "artifact": artifact,
                          "verdict": verdict, "module": module}
    results = []
    for case_id, predicate in cases:
        try:
            passed, detail = predicate(ctx)
        except Exception as e:  # noqa: BLE001 — a crashing case fails
            passed, detail = False, f"predicate raised {type(e).__name__}: {e}"
        results.append({"case_id": case_id, "passed": bool(passed),
                        "detail": str(detail)})
    failed = [r["case_id"] for r in results if not r["passed"]]
    return {"cases": results, "failed": failed, "all_green": not failed}


# ---------------------------------------------------------------------------
# Factory driver (deterministic; zero inference)
# ---------------------------------------------------------------------------

def _load_authored(root: Path, agent_name: str) -> Any:
    path = root / f"{agent_name}.py"
    if not path.exists():
        raise Refusal(f"authored module missing: {path}")
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(
        f"author_agent_staged_{agent_name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drive_one(root: Path, agent_name: str, commission_id: str,
              profile_sha256: str) -> dict[str, Any]:
    """Build one staged profile: gate -> bind -> compile -> verify -> diagnose."""
    from .agent_behavior import bind_personalization
    from .factory_archetypes import check_profile
    from .factory_compiler import compile_profile
    from .factory_verifier import verify

    module = _load_authored(root, agent_name)
    actual = hashlib.sha256(
        (root / f"{agent_name}.py").read_bytes()).hexdigest()
    if actual != profile_sha256:
        raise Refusal(
            f"staged bytes changed under the driver: pinned {profile_sha256[:12]} "
            f"vs actual {actual[:12]}")

    builder = getattr(module, f"{agent_name}_profile", None)
    if builder is None:
        raise Refusal(f"module lacks builder {agent_name}_profile()")
    archetypes = getattr(module, "ARCHETYPES", None)
    if not archetypes:
        raise Refusal("module lacks ARCHETYPES declaration (DR-CMD-069)")

    log = read_log(root)
    commission = next(
        r for r in log
        if r["kind"] == "commission" and r["commission_id"] == commission_id)

    generic = builder()
    violations = check_profile(generic, archetypes)
    if violations:
        return _verdict(root, agent_name, commission_id, "refused",
                        {"stage": "archetype-gate",
                         "reasons": [str(v) for v in violations]})
    try:
        profile = bind_personalization(
            generic,
            principal_id=commission["principal_id"],
            bindings={},
            disposition_ref=commission["disposition_ref"],
            gate=lambda p: [str(v) for v in check_profile(p, archetypes)],
        )
    except ValueError as e:
        return _verdict(root, agent_name, commission_id, "refused",
                        {"stage": "personalization", "reasons": [str(e)]})
    warnings = profile.warnings()
    if warnings:
        return _verdict(root, agent_name, commission_id, "refused",
                        {"stage": "validate", "reasons": warnings})

    artifact = compile_profile(profile)
    staging = Path(tempfile.mkdtemp(prefix=f"authorloop-{agent_name}-"))
    verdict = verify(artifact, profile, staging)
    if verdict.verdict != "verified":
        return _verdict(root, agent_name, commission_id, verdict.verdict,
                        {"stage": "verify",
                         "failure_reason": verdict.failure_reason,
                         "artifact_hash": artifact.manifest.artifact_hash,
                         "profile_hash": artifact.manifest.profile_hash})

    diagnostics = run_diagnostics(module, profile, artifact, verdict)
    ok = diagnostics["all_green"]
    return _verdict(root, agent_name, commission_id,
                    "verified" if ok else "diagnostics-failed",
                    {"artifact_hash": artifact.manifest.artifact_hash,
                     "profile_hash": artifact.manifest.profile_hash,
                     "position_vector": profile.position_vector(),
                     "diagnostics": diagnostics})


def _verdict(root: Path, agent_name: str, commission_id: str,
             outcome: str, detail: dict[str, Any]) -> dict[str, Any]:
    return _append(root, {"kind": "verdict", "commission_id": commission_id,
                          "agent": agent_name, "outcome": outcome,
                          **detail})


def run_factory_driver_once(root: Path) -> dict[str, Any]:
    """One driver pass: every build-request without a verdict gets built."""
    log = read_log(root)
    done = {r["agent"] for r in log if r["kind"] == "verdict"}
    results = []
    for req in log:
        if req["kind"] == "build-request" and req["agent"] not in done:
            results.append(drive_one(root, req["agent"],
                                     req["commission_id"],
                                     req["profile_sha256"]))
            done.add(req["agent"])
    return {"built": [r["agent"] for r in results],
            "outcomes": {r["agent"]: r["outcome"] for r in results}}


__all__ = [
    "CHECKLIST",
    "Refusal",
    "diagnostic_cases_protocol",
    "drive_one",
    "read_log",
    "record_authoring_session",
    "run_diagnostics",
    "run_factory_driver_once",
    "stage_authored_profile",
    "stage_build_request",
    "stage_commission",
]


def diagnostic_cases_protocol() -> str:
    """Human-readable statement of the diagnostic_cases() convention (J2)."""
    return ("diagnostic_cases() -> list of (case_id, predicate); "
            "predicate(ctx) -> (passed: bool, detail: str); "
            'ctx keys: profile, artifact, verdict, module.')
