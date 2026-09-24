"""Golden run for the Countersign mapping (dyad-system d-work #156, PR-C).

Acceptances:
  1. The pinned schema copy (countersign-core.json) matches
     PINNED_SCHEMA_VERSION and PINNED_SCHEMA_SHA256; a tampered copy is
     detected (plan #156 P2: drift fails the run).
  2. The golden state maps to a document that passes the craft's
     validate() + check() with zero problems, and maps byte-identically
     twice (determinism).
  3. Derivation rules hold on the golden state: automaton/flow runs are
     automatic with the executor; the authorize disposition cited by a
     promotion has basis `release` and binds the artifact hash; the
     release carries that countersignature; the original DispositionMode
     survives only in the profile (F4).
  4. Implicit mode: a harness run targeted by a directive citing an
     in-force set_standing disposition is implicit, and the mandate exists.
  5. Triage: a disclosure maps to an escalation opening an explicit act,
     countersigned with the escalation as subject.
  6. counter -> amend.
Refusal cases (the check flags each):
  R1 a countersignature whose signer is an agent;
  R2 an automatic act whose processor is an agent;
  R3 a DispositionMode leaked into `basis` (F4 collision);
  R4 an escalation opening a non-explicit act.

Prints a JSON summary {"ok", "counts", "violations", "refusals",
"pinned_schema"}; exits 1 on any violation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys

from .countersign_map import (
    PINNED_SCHEMA_SHA256, PINNED_SCHEMA_VERSION, SCHEMA_PATH, check, counts,
    load_schema, pinned_problems, render, to_countersign,
)
from .golden_run import build_state
from .schema import (
    Directive, Disclosure, DisclosureKind, DisclosureStatus, Disposition,
    DispositionMode, DispositionResponse, DispositionStatus,
)


def _by(doc: dict, entity: str) -> dict:
    return {d["id"]: d for d in doc[entity]}


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            violations.append(msg)

    # 1. pinned schema
    pin = pinned_problems()
    violations += pin
    if pin:
        return {"ok": False, "violations": violations, "refusals": refusals, "counts": {}}
    tampered = SCHEMA_PATH.read_bytes().replace(b'"0.1.0"', b'"0.1.1"', 1)
    expect(hashlib.sha256(tampered).hexdigest() != PINNED_SCHEMA_SHA256,
           "a tampered schema copy must not match the pinned sha256")
    refusals.append("tampered schema copy detected: sha256 differs from pin")
    sch = load_schema()

    # 2. golden state maps and checks clean, deterministically
    doc = to_countersign(build_state())
    problems = check(doc, sch)
    violations += [f"golden: {p}" for p in problems]
    expect(render(doc) == render(to_countersign(build_state())), "mapping is not deterministic")

    # 3. derivation rules on the golden state
    acts, sigs, rels = _by(doc, "acts"), _by(doc, "countersignatures"), _by(doc, "releases")
    for aid in ("act-ar-ar1", "act-ar-ar2", "act-fr-fr1"):
        a = acts.get(aid, {})
        expect(a.get("mode") == "automatic" and a.get("processor") == "party-executor",
               f"{aid}: must be automatic, processed by the executor")
    expect(acts.get("act-hr-hr1", {}).get("mode") == "explicit", "act-hr-hr1 must be explicit (no standing)")
    cs = sigs.get("countersignature-disp1", {})
    expect(cs.get("basis") == "release" and cs.get("bound_hash") == "h-art1-001"
           and cs.get("answer") == "yes" and cs.get("signer") == "party-h-op",
           f"disp1 must countersign yes, basis release, bound to h-art1-001: {cs}")
    expect(cs.get("profile", {}).get("disposition_mode") == "authorize",
           "the original DispositionMode must survive in the profile only (F4)")
    expect(rels.get("release-rel1", {}).get("countersignature") == "countersignature-disp1",
           "release rel1 must carry disp1's countersignature")

    # 4. implicit mode via a standing disposition cited by a directive
    s4 = build_state()
    s4.dispositions["ds-std"] = Disposition(id="ds-std", dyad_id="d1",
        text="standing: promote on green gates", hat_id="hat-bo", proposer_id="a-leo",
        disposer_id="h-op", mode=DispositionMode.SET_STANDING, standing_domain="promotion",
        status=DispositionStatus.APPROVED, response=DispositionResponse.YES)
    s4.directives["dir-std"] = Directive(id="dir-std", source_run_id="cos1",
        target_run_id="hr1", action="pause", disposition_id="ds-std")
    d4 = to_countersign(s4)
    violations += [f"implicit: {p}" for p in check(d4, sch)]
    expect(_by(d4, "acts")["act-hr-hr1"]["mode"] == "implicit", "hr1 under a standing directive must be implicit")
    m4 = _by(d4, "mandates").get("mandate-ds-std", {})
    expect(m4.get("countersignature") == "countersignature-ds-std" and m4["scope"]["event_class"] == "promotion",
           f"set_standing must map to a mandate: {m4}")
    expect(_by(d4, "countersignatures")["countersignature-ds-std"]["basis"] == "mandate",
           "set_standing basis must be mandate")

    # 5. triage: disclosure -> escalation opening an explicit act
    s5 = build_state()
    s5.disclosures["dis2"] = Disclosure(id="dis2", dyad_id="d1", kind=DisclosureKind.UNCERTAINTY,
        text="stale precondition report", status=DisclosureStatus.ACKNOWLEDGED, seq=1)
    s5.dispositions["disp-t"] = Disposition(id="disp-t", dyad_id="d1", text="triage dis2",
        hat_id="hat-bo", proposer_id="a-leo", disposer_id="h-op", mode=DispositionMode.TRIAGE,
        disclosure_ref="dis2", status=DispositionStatus.APPROVED)
    d5 = to_countersign(s5)
    violations += [f"triage: {p}" for p in check(d5, sch)]
    x5 = _by(d5, "escalations").get("escalation-dis-dis2", {})
    expect(x5.get("opens") == "act-disp-disp-t", f"dis2 must open the triage act: {x5}")
    expect(_by(d5, "countersignatures")["countersignature-disp-t"]["subject"] == "escalation-dis-dis2",
           "a triage countersignature's subject is the escalation")

    # 6. counter -> amend (status stays proposed, E3)
    s6 = build_state()
    s6.dispositions["disp-c"] = Disposition(id="disp-c", dyad_id="d1", text="ratify the close plan",
        hat_id="hat-bo", proposer_id="a-leo", disposer_id="h-op", response=DispositionResponse.COUNTER,
        counter_text="only after the audit signs")
    d6 = to_countersign(s6)
    violations += [f"counter: {p}" for p in check(d6, sch)]
    expect(_by(d6, "countersignatures").get("countersignature-disp-c", {}).get("answer") == "amend",
           "a counter response must map to amend")

    # R1 signer is an agent
    sr1 = build_state()
    sr1.dispositions["disp1"] = sr1.dispositions["disp1"].model_copy(update={"disposer_id": "a-leo"})
    bad = check(to_countersign(sr1), sch)
    hit = [p for p in bad if "signer party-a-leo is not human" in p]
    expect(bool(hit), f"an agent signer must be flagged: {bad}")
    refusals += [f"agent signer flagged: {h}" for h in hit[:1]]

    # R2 automatic act processed by an agent
    dr2 = copy.deepcopy(doc)
    next(a for a in dr2["acts"] if a["id"] == "act-ar-ar1")["processor"] = "party-a-leo"
    bad = check(dr2, sch)
    hit = [p for p in bad if p.startswith("act-ar-ar1: processor")]
    expect(bool(hit), f"an agent processing an automatic act must be flagged: {bad}")
    refusals += [f"agent executor flagged: {h}" for h in hit[:1]]

    # R3 DispositionMode leaked into basis (F4)
    dr3 = copy.deepcopy(doc)
    dr3["countersignatures"][0]["basis"] = "authorize"
    bad = check(dr3, sch)
    hit = [p for p in bad if "not in ['per-act', 'mandate', 'release']" in p]
    expect(bool(hit), f"a DispositionMode as basis must be refused: {bad}")
    refusals += [f"mode-as-basis refused: {h}" for h in hit[:1]]

    # R4 escalation opening an automatic act
    dr4 = copy.deepcopy(d5)
    next(x for x in dr4["escalations"] if x["id"] == "escalation-dis-dis2")["opens"] = "act-ar-ar1"
    bad = check(dr4, sch)
    hit = [p for p in bad if "not an explicit act" in p]
    expect(bool(hit), f"an escalation opening an automatic act must be flagged: {bad}")
    refusals += [f"non-explicit escalation flagged: {h}" for h in hit[:1]]

    return {"ok": not violations, "violations": violations, "refusals": refusals,
            "counts": counts(doc),
            "pinned_schema": {"version": PINNED_SCHEMA_VERSION, "sha256": PINNED_SCHEMA_SHA256}}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
