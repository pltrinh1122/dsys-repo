"""Containment golden cases (DR-CMD-086).

K1  env scrub: a planted ambient-only variable is invisible inside.
K2  probe: cwd == scratch, tmpdir/home inside scratch.
K3  write outside scratch is refused by the audit hook; no file appears.
K4  wall-clock timeout kills a hanging workload; partials quarantined.
K5  two contained drives of the wright -> result.json byte-identical.
K6  commission-in / result-out round trip on a synthetic agent; the parent
    adopts the contained verdict into a live log (proposer != disposer).

Exit 0 iff every case passes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.package.author_contain import (  # noqa: E402
    adopt_verdict_records,
    run_contained,
)

ALLOWLIST_KEYS = {
    "PATH", "PYTHONPATH", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE",
    "TMPDIR", "LANG", "LC_ALL", "TZ", "HOME", "AUTHOR_CONTAIN_SCRATCH",
}

PROBE_MODULE = '''"""Synthetic contained-drive agent (golden K6). staff+office."""

from __future__ import annotations

from core.package.agent_behavior import (
    AgentBehaviorProfile,
    D1Authority,
    D2Fidelity,
    D3Reproducibility,
    D4Observability,
    D5Scope,
    D6Initiative,
    D7Verification,
    TriggerSource,
)

ARCHETYPES = ("staff", "office")


def probe_profile() -> AgentBehaviorProfile:
    return AgentBehaviorProfile(
        agent="probe",
        d1_authority=D1Authority(
            position=0.0, per_event_disposition=True,
            standing_dispositions=[],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.5, deterministic_execution=False,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.0,
            read_scope=["staging-area"],
            write_scope=[]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR:
                    "authenticated-session; operator-attributed commission"},
            authorization={TriggerSource.OPERATOR: "stage-only"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


def diagnostic_cases():
    return [("P-OK", lambda ctx: (True, "synthetic agent green"))]
'''


def _case_k1():
    os.environ["DSYS_CONTAIN_TEST_CANARY"] = "present"
    try:
        rec = run_contained({"mode": "probe"}, timeout_s=60)
    finally:
        del os.environ["DSYS_CONTAIN_TEST_CANARY"]
    assert rec["outcome"] == "ok", rec
    keys = set(rec["result"]["env_keys"])
    assert "DSYS_CONTAIN_TEST_CANARY" not in keys, "canary leaked inside"
    assert keys == ALLOWLIST_KEYS, f"env drift: {sorted(keys ^ ALLOWLIST_KEYS)}"
    return "env scrubbed to allowlist; canary invisible"


def _case_k2():
    rec = run_contained({"mode": "probe"}, timeout_s=60)
    r = rec["result"]
    scratch = Path(r["scratch"])
    assert Path(r["cwd"]) == scratch, (r["cwd"], r["scratch"])
    assert str(scratch) in r["tmpdir"], r["tmpdir"]
    assert str(scratch) in (r["home"] or ""), r["home"]
    return f"cwd==scratch; tmpdir+home inside ({scratch.name})"


def _case_k3():
    escape = Path("/tmp/author-contain-escape-probe")
    if escape.exists():
        escape.unlink()
    rec = run_contained({"mode": "attempt_write",
                         "path": str(escape)}, timeout_s=60)
    r = rec["result"]
    assert r["outcome"] == "refused", r
    assert "scratch" in r["reason"].lower(), r["reason"]
    assert not escape.exists(), "escape file was created!"
    return f"write refused ({r['reason'][:60]}...); no file created"


def _case_k4():
    rec = run_contained({"mode": "hang", "sleep_s": 30}, timeout_s=3)
    assert rec["outcome"] == "timeout", rec
    q = rec["quarantine"]
    assert "hang: starting sleep" in q["stdout"], q
    assert "result" not in rec or rec.get("result") is None
    return "timeout killed hang; partial stdout quarantined, nothing adopted"


def _wright_drive_inputs():
    log = Path(__file__).resolve().parent / "authored" / "authoring-log.jsonl"
    records = [json.loads(l) for l in log.read_text().splitlines()
               if l.strip()]
    req = next(r for r in records
               if r["kind"] == "build-request" and r["agent"] == "wright")
    return {"mode": "drive", "agent_name": "wright",
            "commission_id": req["commission_id"],
            "profile_sha256": req["profile_sha256"]}


def _case_k5():
    commission = _wright_drive_inputs()
    rec1 = run_contained(commission, timeout_s=300)
    rec2 = run_contained(commission, timeout_s=300)
    assert rec1["outcome"] == "ok", rec1["stdio"]
    assert rec2["outcome"] == "ok", rec2["stdio"]
    assert rec1["result"]["verdict"]["outcome"] == "verified", rec1["result"]
    b1 = (Path(rec1["run_local"]["scratch"]) / "result.json").read_bytes()
    b2 = (Path(rec2["run_local"]["scratch"]) / "result.json").read_bytes()
    assert b1 == b2, "contained replay diverged"
    assert rec1["inputs"]["tree_sha256"] == rec2["inputs"]["tree_sha256"]
    return (f"wright drive verified + replay byte-identical "
            f"({len(b1)} bytes)")


def _synthetic_overlay():
    overlay = Path(tempfile.mkdtemp(prefix="probe-overlay-"))
    (overlay / "probe.py").write_text(PROBE_MODULE)
    digest = hashlib.sha256(PROBE_MODULE.encode()).hexdigest()
    log = [
        {"seq": 1, "kind": "commission", "commission_id": "probe-001",
         "principal_id": "operator", "role_brief": "synthetic",
         "acceptance_criteria": ["green"], "disposition_ref": "DR-CMD-086"},
        {"seq": 2, "kind": "staged-profile", "commission_id": "probe-001",
         "agent": "probe", "path": str(overlay / "probe.py"),
         "sha256": digest, "rationale": "golden K6"},
        {"seq": 3, "kind": "build-request", "commission_id": "probe-001",
         "agent": "probe", "profile_sha256": digest},
    ]
    (overlay / "authoring-log.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in log) + "\n")
    return overlay, digest


def _case_k6():
    overlay, digest = _synthetic_overlay()
    rec = run_contained(
        {"mode": "drive", "agent_name": "probe",
         "commission_id": "probe-001", "profile_sha256": digest},
        authored_overlay=overlay, timeout_s=300)
    assert rec["outcome"] == "ok", rec["stdio"]
    verdict = rec["result"]["verdict"]
    assert verdict["outcome"] == "verified", verdict
    live = Path(tempfile.mkdtemp(prefix="probe-live-"))
    adopted = adopt_verdict_records(live, verdict)
    want = {k: v for k, v in verdict.items() if k != "seq"}
    got = {k: v for k, v in adopted.items() if k != "seq"}
    assert got == want, "adopted verdict differs from contained proposal"
    assert adopted["seq"] == 1
    return "round trip ok; contained verdict adopted verbatim (fresh seq)"


CASES = [
    ("K1", _case_k1),
    ("K2", _case_k2),
    ("K3", _case_k3),
    ("K4", _case_k4),
    ("K5", _case_k5),
    ("K6", _case_k6),
]


def main() -> int:
    failed = 0
    for case_id, fn in CASES:
        try:
            detail = fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[{case_id}] FAIL {type(e).__name__}: {e}")
        else:
            print(f"[{case_id}] PASS {detail}")
    print(f"containment golden: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
