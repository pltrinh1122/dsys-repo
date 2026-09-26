"""Author-agent loop golden run (DR-CMD-083).

Deterministic replay of the loop's mechanical chain on pinned bytes
(commission -> stage -> drive -> diagnose), plus refusal cases. The
inferential step (authoring) happened once, live; its bytes are pinned
in core/package/authored/ and replayed here without inference.

Cases:
  L1  loop replay, wright: pinned bytes -> verified, diagnostics green
  L2  loop replay, registrar: pinned bytes -> verified, 6/6 diagnostics
  L3  tamper refusal: byte changed after pinning -> driver refuses
  L4  archetype-gate refusal: staff profile with write_scope -> refused
  L5  diagnostics failure: failing case -> verdict diagnostics-failed
  L6  byte-identity: two replays -> identical outcomes and hashes
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from . import author_agent as aa

LIVE = Path(__file__).parent / "authored"

VIOLATOR_SRC = '''"""Fixture: staff profile with a write_scope (must refuse at S2)."""
from __future__ import annotations
from core.package.agent_behavior import AgentBehaviorProfile, derive_d5_position
from core.package.authored.wright import wright_profile

ARCHETYPES = ("staff", "office")

def violator_profile() -> AgentBehaviorProfile:
    p = wright_profile()
    d = p.model_dump()
    d["d5_scope"]["write_scope"] = ["tool-x"]
    d["d5_scope"]["position"] = derive_d5_position(["tool-x"])
    return AgentBehaviorProfile.model_validate(d)

def diagnostic_cases():
    return []
'''

DOOMED_SRC = '''"""Fixture: valid profile, failing diagnostic (must fail the loop)."""
from __future__ import annotations
from core.package.authored.wright import wright_profile, ARCHETYPES

def doomed_profile():
    return wright_profile()

def diagnostic_cases():
    return [("X-DOOM", lambda ctx: (False, "always fails"))]
'''


def _fresh_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="authorloop-gr-"))
    return root


def _commission(root: Path) -> None:
    aa.stage_commission(
        root, "commission-fixture",
        role_brief="golden-run fixture commission",
        acceptance_criteria=["loop green"],
        disposition_ref="fixture-not-a-disposition",
        principal_id="test-principal")


def _replay(root: Path, agent: str) -> dict:
    _commission(root)
    aa.record_authoring_session(root, "commission-fixture", agent,
                                {k: True for k in aa.CHECKLIST},
                                note="replay")
    src = (LIVE / f"{agent}.py").read_text()
    st = aa.stage_authored_profile(root, agent, src, rationale="replay",
                                   commission_id="commission-fixture")
    aa.stage_build_request(root, agent, "commission-fixture")
    out = aa.run_factory_driver_once(root)
    log = aa.read_log(root)
    verdict = next(r for r in log
                   if r["kind"] == "verdict" and r["agent"] == agent)
    return {"outcome": out["outcomes"][agent], "verdict": verdict,
            "pinned": st["sha256"]}


def run() -> dict:
    results: list[dict] = []

    def case(cid: str, passed: bool, detail: str = ""):
        results.append({"case": cid, "passed": passed, "detail": detail})

    # L1 / L2 — replay, both loop-authored profiles
    r1 = _replay(_fresh_root(), "wright")
    case("L1", r1["outcome"] == "verified"
         and r1["verdict"]["diagnostics"]["all_green"],
         f"outcome={r1['outcome']}")
    r2 = _replay(_fresh_root(), "registrar")
    dg = r2["verdict"]["diagnostics"]
    case("L2", r2["outcome"] == "verified" and dg["all_green"]
         and len(dg["cases"]) == 6,
         f"outcome={r2['outcome']} cases={len(dg['cases'])}")

    # L3 — tamper after pinning refuses
    root3 = _fresh_root()
    _commission(root3)
    aa.record_authoring_session(root3, "commission-fixture", "wright",
                                {k: True for k in aa.CHECKLIST})
    src = (LIVE / "wright.py").read_text()
    aa.stage_authored_profile(root3, "wright", src, rationale="t", 
                              commission_id="commission-fixture")
    (root3 / "wright.py").write_text(src + "\n# tampered\n")
    aa.stage_build_request(root3, "wright", "commission-fixture")
    try:
        aa.run_factory_driver_once(root3)
        case("L3", False, "tamper not refused")
    except aa.Refusal as e:
        case("L3", "pinned" in str(e) or "changed under the driver" in str(e),
             str(e)[:80])

    # L4 — archetype-gate refusal (staff S2)
    root4 = _fresh_root()
    _commission(root4)
    aa.record_authoring_session(root4, "commission-fixture", "violator",
                                {k: True for k in aa.CHECKLIST})
    aa.stage_authored_profile(root4, "violator", VIOLATOR_SRC,
                              rationale="t", commission_id="commission-fixture")
    aa.stage_build_request(root4, "violator", "commission-fixture")
    out4 = aa.run_factory_driver_once(root4)
    v4 = next(r for r in aa.read_log(root4) if r["kind"] == "verdict")
    case("L4", out4["outcomes"]["violator"] == "refused"
         and v4.get("stage") == "archetype-gate",
         f"outcome={out4['outcomes']['violator']} stage={v4.get('stage')}")

    # L5 — failing diagnostic fails the loop
    root5 = _fresh_root()
    _commission(root5)
    aa.record_authoring_session(root5, "commission-fixture", "doomed",
                                {k: True for k in aa.CHECKLIST})
    aa.stage_authored_profile(root5, "doomed", DOOMED_SRC,
                              rationale="t", commission_id="commission-fixture")
    aa.stage_build_request(root5, "doomed", "commission-fixture")
    out5 = aa.run_factory_driver_once(root5)
    case("L5", out5["outcomes"]["doomed"] == "diagnostics-failed",
         f"outcome={out5['outcomes']['doomed']}")

    # L6 — byte-identity across two replays
    a = _replay(_fresh_root(), "registrar")["verdict"]
    b = _replay(_fresh_root(), "registrar")["verdict"]
    key = lambda v: (v["outcome"], v["artifact_hash"], v["profile_hash"],
                     [(c["case_id"], c["passed"]) for c in
                      v["diagnostics"]["cases"]])
    case("L6", key(a) == key(b), "two registrar replays identical")

    failed = [r["case"] for r in results if not r["passed"]]
    return {"ok": not failed, "failed": failed, "results": results}


if __name__ == "__main__":
    rep = run()
    for r in rep["results"]:
        print(("PASS " if r["passed"] else "FAIL "), r["case"],
              "-", r["detail"][:70])
    print(json.dumps({"ok": rep["ok"], "failed": rep["failed"]}))
    raise SystemExit(0 if rep["ok"] else 1)
