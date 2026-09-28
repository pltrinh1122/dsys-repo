"""Factory profile set 002 — loop-authored agent profiles (DR-CMD-083).

Profiles authored through the author-agent loop (commission -> author ->
stage -> drive -> diagnose), not hand-placed: the builders live in
core/package/authored/ (hash-pinned in the authoring manifest); this
module only registers them for the standard validate -> compile ->
verify pipeline.

  wright     — agent-profile author (harness-side author-agent; J3 bootstrap)
  registrar  — verified-build registry (J4 demo: authored end-to-end
               through the loop)
  registrar_clerk — may-act x office clerk variant of the registrar
               (DR-CMD-096, adopted with deviation; registered DR-CMD-104
               after tool-register-artifact landed)

Invariants (as set 001): proposer != disposer; zero warnings; positions
derived, never hand-set; D2 binary enum; D6 structural.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .agent_behavior import bind_personalization
from .authored.registrar import registrar_profile
from .authored.registrar_clerk import registrar_clerk_profile
from .authored.wright import wright_profile
from .factory_archetypes import check_profile
from .factory_compiler import compile_profile
from .factory_verifier import verify

PROFILE_SET_002: dict[str, Any] = {
    "wright": wright_profile,
    "registrar": registrar_profile,
    "registrar_clerk": registrar_clerk_profile,
}

PROFILE_ARCHETYPES_002: dict[str, tuple[str, ...]] = {
    "wright": ("staff", "office"),
    "registrar": ("staff", "office"),
    "registrar_clerk": ("clerk",),
}


def run_agent(name: str) -> dict[str, Any]:
    """Validate, compile, and verify one set-002 profile. Returns its report."""
    builder = PROFILE_SET_002[name]
    generic = builder()
    try:
        profile = bind_personalization(
            generic,
            principal_id="test-principal",
            bindings={},
            disposition_ref="test-fixture",  # fixture, not a real disposition
            gate=lambda p: [str(v)
                            for v in check_profile(
                                p, PROFILE_ARCHETYPES_002[name])],
        )
    except ValueError as e:
        raise AssertionError(f"{name}: personalization binding refused:\n  - {e}")
    warnings = profile.warnings()
    if warnings:
        raise AssertionError(
            f"{name}: profile must validate with zero warnings, got: {warnings}")
    artifact = compile_profile(profile)
    root = Path(tempfile.mkdtemp(prefix=f"pset002-{name}-"))
    verdict = verify(artifact, profile, root)
    return {
        "agent": name,
        "position_vector": profile.position_vector(),
        "warnings": warnings,
        "compile": {
            "profile_hash": artifact.manifest.profile_hash,
            "plan_hash": artifact.plan.plan_hash,
            "artifact_hash": artifact.manifest.artifact_hash,
        },
        "verify": {
            "verdict": verdict.verdict,
            "operable": verdict.operable,
            "failure_reason": verdict.failure_reason,
            "n_static": len(verdict.static_results),
            "n_probes": len(verdict.probe_results),
        },
    }


def run() -> dict[str, Any]:
    """Run all set-002 profiles through validate -> compile -> verify."""
    reports = {name: run_agent(name) for name in PROFILE_SET_002}
    ok = all(r["verify"]["verdict"] == "verified" for r in reports.values())
    return {"ok": ok, "agents": reports}


if __name__ == "__main__":
    import json as _json
    _rep = run()
    for _name, _r in _rep["agents"].items():
        _v = _r["position_vector"]
        print(f"{_name}: D1={_v['D1']} D2={_v['D2']} D3={_v['D3']} "
              f"D4={_v['D4']} D5={_v['D5']} D6={_v['D6']} D7={_v['D7']} "
              f"-> {_r['verify']['verdict']}")
    print(_json.dumps({"ok": _rep["ok"]}, indent=2))
    raise SystemExit(0 if _rep["ok"] else 1)


__all__ = [
    "PROFILE_SET_002",
    "PROFILE_ARCHETYPES_002",
    "run",
    "run_agent",
    "registrar_profile",
    "wright_profile",
]
