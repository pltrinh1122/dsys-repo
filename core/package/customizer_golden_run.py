"""Golden run: the Customizer agent and the customization sequence.

Covers: profile validation (zero warnings), archetype conformance,
envelope validation, prove-absence, the propose -> dispose -> register
channel sequence, and the negative controls (stowaway customization,
self-registration, post-release customization, double adoption,
non-operator disposition).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.package import author_channels as ch
from core.package import artifact_registry as reg
from core.package.customizer import (
    CustomizationProposal,
    RegistryEvidence,
    customizer_profile,
    validate_proposal_envelope,
    ProposalViolation,
    ARCHETYPES,
)

CASES: list[tuple[str, callable]] = []
FAILED: list[str] = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _proposal(**kw):
    base = dict(
        agent_name="email_ingest", artifact_kind="schema",
        artifact_name="matter-record", artifact_source='{"a": 1}',
        rationale="no matter schema exists",
        compatibility="downstream: disposition machinery; v1 additive",
        proposed_version=1, commission_id="commission-0001",
        registry_evidence=RegistryEvidence(
            kind="schema", query="matter", hits=[]))
    base.update(kw)
    return CustomizationProposal(**base)


@case("G-C1 profile validates with zero warnings")
def _():
    p = customizer_profile()
    assert p.agent == "customizer"
    assert p.model_dump()  # serializes clean


@case("G-C2 archetype gate: staff + office conform, zero violations")
def _():
    from core.package.factory_archetypes import check_profile
    vs = check_profile(customizer_profile(), list(ARCHETYPES))
    assert not vs, vs


@case("G-C3 envelope validates; sha pinned")
def _():
    s = validate_proposal_envelope(_proposal())
    assert s["envelope"] == "valid" and len(s["artifact_sha256"]) == 64


@case("G-C4 prove-absence is computed: empty registry -> empty hits")
def _():
    with tempfile.TemporaryDirectory() as t:
        ev = reg.absence_evidence(Path(t), "schema", "matter")
        assert ev["hits"] == [] and ev["query"] == "matter"


@case("G-C5 propose refuses forged evidence (registry now has hits)")
def _():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        reg.register(root, kind="schema", name="matter-record",
                     artifact_bytes=b'{"a": 1}', producer="customizer",
                     commission_id="commission-0001",
                     disposition_ref="op-adopt-001")
        # proposal claims absence; the channel re-runs the lookup
        import core.package.author_agent as aa
        aa.stage_commission(root, "commission-0001", "brief",
                            ["accept"], "op-1", principal_id="operator")
        pf = root / "prop.json"
        pf.write_text(_proposal().model_dump_json())
        try:
            ch.stage_customization_proposal(root, proposal_file=pf,
                                            commission_id="commission-0001")
        except aa.Refusal as e:
            assert "stale or forged" in str(e), e
            return
        raise AssertionError("forged evidence accepted")


@case("G-C6 end-to-end: propose -> adopt -> registered v1, pinned")
def _():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        import core.package.author_agent as aa
        aa.stage_commission(root, "commission-0001", "brief",
                            ["accept"], "op-1", principal_id="operator")
        pf = root / "prop.json"
        pf.write_text(_proposal().model_dump_json())
        staged = ch.stage_customization_proposal(
            root, proposal_file=pf, commission_id="commission-0001")
        assert staged["status"] == "pending-disposition"
        adopted = ch.adopt_customization_proposal(
            root, proposal_seq=staged["proposal_seq"],
            disposition_ref="op-adopt-001", by="operator")
        art = adopted["artifact"]
        assert art["version"] == 1 and art["disposition_ref"] == "op-adopt-001"
        assert len(art["sha256"]) == 64
        hits = reg.lookup(root, "schema", "matter")
        assert [h.name for h in hits] == ["matter-record"]


@case("G-C7 adopt refuses non-operator disposition")
def _():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        import core.package.author_agent as aa
        aa.stage_commission(root, "commission-0001", "brief",
                            ["accept"], "op-1", principal_id="operator")
        pf = root / "prop.json"
        pf.write_text(_proposal().model_dump_json())
        staged = ch.stage_customization_proposal(
            root, proposal_file=pf, commission_id="commission-0001")
        try:
            ch.adopt_customization_proposal(
                root, proposal_seq=staged["proposal_seq"],
                disposition_ref="x", by="ambient")
        except aa.Refusal as e:
            assert "operator-attributed" in str(e), e
            return
        raise AssertionError("non-operator adoption allowed")


@case("G-C8 adopt refuses double adoption")
def _():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        import core.package.author_agent as aa
        aa.stage_commission(root, "commission-0001", "brief",
                            ["accept"], "op-1", principal_id="operator")
        pf = root / "prop.json"
        pf.write_text(_proposal().model_dump_json())
        staged = ch.stage_customization_proposal(
            root, proposal_file=pf, commission_id="commission-0001")
        ch.adopt_customization_proposal(
            root, proposal_seq=staged["proposal_seq"],
            disposition_ref="op-adopt-001", by="operator")
        try:
            ch.adopt_customization_proposal(
                root, proposal_seq=staged["proposal_seq"],
                disposition_ref="op-adopt-002", by="operator")
        except aa.Refusal as e:
            assert "already adopted" in str(e), e
            return
        raise AssertionError("double adoption allowed")


@case("G-C9 post-release customization refused; new commission -> v2")
def _():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        import core.package.author_agent as aa
        aa.stage_commission(root, "commission-0001", "brief",
                            ["accept"], "op-1", principal_id="operator")
        pf = root / "prop.json"
        pf.write_text(_proposal().model_dump_json())
        s1 = ch.stage_customization_proposal(root, proposal_file=pf,
                                             commission_id="commission-0001")
        ch.adopt_customization_proposal(root, proposal_seq=s1["proposal_seq"],
                                        disposition_ref="op-adopt-001",
                                        by="operator")
        # same original commission, new bytes, honest supersede claim ->
        # refused at registration: post-release customization under the
        # original commission is the falsified claim, made mechanical.
        ev = reg.absence_evidence(root, "schema", "matter")
        pf2 = root / "prop2.json"
        pf2.write_text(_proposal(
            artifact_source='{"a": 9}', proposed_version=2,
            supersedes="matter-record",
            rationale="v1 insufficient: needs a source field",
            registry_evidence=RegistryEvidence(
                kind="schema", query="matter", hits=ev["hits"])
        ).model_dump_json())
        s2 = ch.stage_customization_proposal(root, proposal_file=pf2,
                                             commission_id="commission-0001")
        try:
            ch.adopt_customization_proposal(root, proposal_seq=s2["proposal_seq"],
                                            disposition_ref="op-adopt-002",
                                            by="operator")
        except aa.Refusal as e:
            assert "post-release customization refused" in str(e), e
        else:
            raise AssertionError("post-release customization allowed")
        # new commission (new authoring cycle), same supersede -> v2
        aa.stage_commission(root, "commission-0002", "brief2",
                            ["accept"], "op-2", principal_id="operator")
        pf3 = root / "prop3.json"
        pf3.write_text(_proposal(
            artifact_source='{"a": 9}', proposed_version=2,
            supersedes="matter-record",
            rationale="v1 insufficient: needs a source field",
            commission_id="commission-0002",
            registry_evidence=RegistryEvidence(
                kind="schema", query="matter", hits=ev["hits"])
        ).model_dump_json())
        s3 = ch.stage_customization_proposal(root, proposal_file=pf3,
                                             commission_id="commission-0002")
        adopted = ch.adopt_customization_proposal(
            root, proposal_seq=s3["proposal_seq"],
            disposition_ref="op-adopt-003", by="operator")
        assert adopted["artifact"]["version"] == 2


@case("G-C10 diagnostics E-C1..E-C11 all green")
def _():
    from core.package.customizer import diagnostic_cases
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        ctx = {"tmp_root": t}
        failed = []
        for name, fn in diagnostic_cases():
            ok, detail = fn(ctx)
            if not ok:
                failed.append(f"{name}: {detail}")
        assert not failed, failed


def main() -> int:
    passed = 0
    for name, fn in CASES:
        try:
            fn()
        except Exception as e:
            FAILED.append(f"{name}: {type(e).__name__}: {e}")
            print(f"FAIL {name}: {e}")
        else:
            passed += 1
            print(f"ok   {name}")
    print(f"\n{passed}/{len(CASES)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
