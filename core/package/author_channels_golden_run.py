"""Author-agent channels golden run (DR-CMD-085).

Boundary cases for the containment I/O:
  H1  commission admitted via the staged queue (canonical ingress)
  H2  CLI commission ingress stages through the SAME admission
  H3  malformed commissions refused with reasons (API + CLI)
  H4  results staged retrievable after a full loop (AP-E2)
  H5  report with no verdict staged refuses with reasons
  H6  world-afferent addressed to the wright REFUSES (D7 0.75)
  H7  efferent-to-world attempt REFUSES (D5 0.0)
  H8  byte-identity: two full loops identical
  H9  name-independence: vocabulary rename cannot change behavior
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from . import author_agent as aa
from . import author_channels as ac
from .authored.wright import wright_profile

LIVE = Path(__file__).parent / "authored"


def _fresh_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="authorchan-gr-"))


def _cli(argv: list[str]) -> tuple[int | None, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ac.main(argv)
        except SystemExit as e:  # noqa: BLE001 — argparse usage errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


def _valid_kwargs(**over):
    kw = dict(commission_id="commission-h", principal_id="operator",
              brief="channels fixture brief",
              acceptance_criteria=["loop green"],
              disposition_ref="fixture-not-a-disposition")
    kw.update(over)
    return kw


def _full_loop(root: Path) -> tuple[dict, dict]:
    prof = wright_profile()
    ac.admit_commission(root, prof, **_valid_kwargs(
        commission_id="commission-h4"))
    aa.record_authoring_session(root, "commission-h4", "wright",
                                {k: True for k in aa.CHECKLIST},
                                note="channels")
    src = (LIVE / "wright.py").read_text()
    aa.stage_authored_profile(root, "wright", src, rationale="channels",
                              commission_id="commission-h4")
    aa.stage_build_request(root, "wright", "commission-h4")
    out = aa.run_factory_driver_once(root)
    return out, ac.read_results(root, "commission-h4")


def run() -> dict:
    results: list[dict] = []

    def case(cid: str, passed: bool, detail: str = ""):
        results.append({"case": cid, "passed": passed, "detail": detail})

    prof = wright_profile()

    # H1 — staged queue admission (canonical ingress)
    r1 = _fresh_root()
    rec = ac.admit_commission(r1, prof, **_valid_kwargs(
        commission_id="commission-h1"))
    log1 = aa.read_log(r1)
    adm1 = [x for x in log1 if x.get("kind") == "channel-admission"]
    pend1 = ac.pending_commissions(r1)
    case("H1", rec["commission_id"] == "commission-h1"
         and len(adm1) == 1 and adm1[0]["admitted"] is True
         and adm1[0]["channel"] == "AP-A3"
         and [p["commission_id"] for p in pend1] == ["commission-h1"],
         f"admitted={adm1[0]['admitted'] if adm1 else None}")

    # H2 — CLI ingress stages through the SAME admission
    r2 = _fresh_root()
    code2, out2, _ = _cli(["--root", str(r2), "commission",
                           "--brief", "cli fixture",
                           "--acceptance", "a1;a2",
                           "--disposition-ref", "fixture"])
    body2 = json.loads(out2) if out2.strip() else {}
    log2 = aa.read_log(r2)
    adm2 = [x for x in log2 if x.get("kind") == "channel-admission"]
    case("H2", code2 == 0 and body2.get("channel") == "AP-A3"
         and len(adm2) == 1 and adm2[0]["admitted"] is True,
         f"exit={code2} channel={body2.get('channel')}")

    # H3 — malformed commissions refused with reasons (API + CLI)
    r3 = _fresh_root()
    bad = []
    for label, kw in [
        ("empty-principal", _valid_kwargs(principal_id="")),
        ("unknown-principal", _valid_kwargs(principal_id="analyst")),
        ("empty-brief", _valid_kwargs(brief="  ")),
        ("empty-criteria", _valid_kwargs(acceptance_criteria=[])),
        ("empty-disposition", _valid_kwargs(disposition_ref="")),
    ]:
        try:
            ac.admit_commission(r3, prof, **kw)
            bad.append(f"{label}: admitted")
        except aa.Refusal as e:
            if not str(e).strip():
                bad.append(f"{label}: silent refusal")
    # duplicate id
    ac.admit_commission(r3, prof, **_valid_kwargs(commission_id="dup"))
    try:
        ac.admit_commission(r3, prof, **_valid_kwargs(commission_id="dup"))
        bad.append("duplicate: admitted")
    except aa.Refusal as e:
        if not str(e).strip():
            bad.append("duplicate: silent refusal")
    # refused admissions are audit-visible
    refused_recs = [x for x in aa.read_log(r3)
                    if x.get("kind") == "channel-admission"
                    and x.get("admitted") is False]
    # CLI-level refusal -> exit 4 with reasons on stderr
    code3, _, err3 = _cli(["--root", str(r3), "commission",
                           "--brief", "x", "--acceptance", "y",
                           "--disposition-ref", "z",
                           "--principal", "analyst"])
    case("H3", not bad and len(refused_recs) == 6
         and code3 == 4 and "refused" in err3,
         f"bad={bad} refused_recs={len(refused_recs)} cli_exit={code3}")

    # H4 — full loop, results retrievable (AP-E2)
    r4 = _fresh_root()
    out4, res4 = _full_loop(r4)
    v4 = res4["verdicts"][0] if res4["verdicts"] else {}
    case("H4", out4["outcomes"].get("wright") == "verified"
         and res4["all_green"] is True
         and v4.get("diagnostics", {}).get("n_cases") == 3,
         f"outcome={out4['outcomes'].get('wright')} "
         f"all_green={res4['all_green']}")

    # H5 — report with no verdict refuses with reasons
    r5 = _fresh_root()
    ac.admit_commission(r5, prof, **_valid_kwargs(
        commission_id="commission-h5"))
    try:
        ac.read_results(r5, "commission-h5")
        case("H5", False, "verdict-less report admitted")
    except aa.Refusal as e:
        case("H5", "no verdict" in str(e) and "commission-h5" in str(e),
             str(e)[:80])
    try:
        ac.read_results(r5, "commission-nope")
        case("H5b", False, "unknown commission admitted")
    except aa.Refusal as e:
        case("H5b", "no such commission" in str(e), str(e)[:60])

    # H6 — world-afferent to the wright refuses (D7 0.75)
    r6 = _fresh_root()
    try:
        ac.world_ingress(r6, prof, ac.WorldAfferent.AW_A1)
        case("H6", False, "world ingress admitted")
    except aa.Refusal as e:
        case("H6", "D7" in str(e) and "world_target=false" in str(e),
             str(e)[:80])
    refused6 = [x for x in aa.read_log(r6)
                if x.get("kind") == "channel-refusal"]
    case("H6b", len(refused6) == 1
         and refused6[0]["direction"] == "ingress"
         and refused6[0]["code"] == "AW-A1",
         f"logged={len(refused6)}")

    # H7 — efferent-to-world refuses (D5 0.0)
    r7 = _fresh_root()
    try:
        ac.world_egress(r7, prof, ac.WorldEfferent.AW_E1)
        case("H7", False, "world egress admitted")
    except aa.Refusal as e:
        case("H7", "D5" in str(e) and "write_scope empty" in str(e),
             str(e)[:80])

    # H8 — byte-identity across two full loops
    _, res_a = _full_loop(_fresh_root())
    _, res_b = _full_loop(_fresh_root())
    key = lambda res: json.dumps(res["verdicts"], sort_keys=True)
    case("H8", key(res_a) == key(res_b), "two loops identical")

    # H9 — vocabulary rename cannot change behavior (J-CH2)
    members = (list(ac.PrincipalAfferent) + list(ac.PrincipalEfferent)
               + list(ac.WorldAfferent) + list(ac.WorldEfferent))
    table_ok = (set(ac.CHANNEL_NAMES.keys()) == set(members)
                and all(isinstance(v, str) and v for v in
                        ac.CHANNEL_NAMES.values()))
    old = ac.CHANNEL_NAMES[ac.PrincipalAfferent.AP_A3]
    r9 = _fresh_root()
    try:
        ac.CHANNEL_NAMES[ac.PrincipalAfferent.AP_A3] = "renamed-label"
        rec9 = ac.admit_commission(r9, prof, **_valid_kwargs(
            commission_id="commission-h9"))
        adm9 = [x for x in aa.read_log(r9)
                if x.get("kind") == "channel-admission"]
        rename_ok = (rec9["commission_id"] == "commission-h9"
                     and adm9[0]["channel"] == "AP-A3"
                     and ac.channel_name(
                         ac.PrincipalAfferent.AP_A3) == "renamed-label")
    finally:
        ac.CHANNEL_NAMES[ac.PrincipalAfferent.AP_A3] = old
    case("H9", table_ok and rename_ok,
         f"table_complete={table_ok} behavior_stable={rename_ok}")

    failed = [r["case"] for r in results if not r["passed"]]
    return {"ok": not failed, "failed": failed, "results": results}


if __name__ == "__main__":
    rep = run()
    for r in rep["results"]:
        print(("PASS " if r["passed"] else "FAIL "), r["case"],
              "-", r["detail"][:70])
    print(json.dumps({"ok": rep["ok"], "failed": rep["failed"]}))
    raise SystemExit(0 if rep["ok"] else 1)
