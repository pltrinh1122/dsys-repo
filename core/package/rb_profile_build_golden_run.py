"""Golden run for rb-profile-build (the closed bootstrap loop, DR-CMD-101).

Acceptances:
  B-1. registrar_clerk build-request -> RECEIVE -> VALIDATE -> GATE ->
       COMPILE -> VERIFY -> STAGE, all ok (DR-CMD-102 tranche 1:
       tool-register-artifact landed, so the 'artifact-registry'
       channel resolves at the routing stage; the DR-CMD-096 refusal
       is gone). The staged bundle carries the not-published /
       not-registered disclaimer — registration is the Operator's
       disposition, never the loop's. Two runs yield byte-equal
       transcripts (deterministic replay).
  B-2. triager build-request -> refuses at COMPILE with the exact reason
       (DR-CMD-097 record).
  B-3. dr_registrar build-request -> refuses at COMPILE with the exact
       reason (DR-CMD-100 record). Together B-2..B-3 prove the loop
       still handles the deviation class honestly — the refusal is
       staged verbatim, never routed around (tranche 2 not authorized).
  B-4. wright build-request (clean) -> RECEIVE -> VALIDATE -> GATE ->
       COMPILE -> VERIFY -> STAGE, all ok; the staged bundle carries the
       content hashes and the not-published/not-registered disclaimer;
       two runs on the same bytes yield byte-equal transcripts
       (deterministic replay).
  B-5. Tampered authored bytes (hash mismatch) -> refuses at RECEIVE,
       fail-closed, before any code executes.
  B-6. Builder yielding a validation-breaking profile (the DR-CMD-093 D2
       correction: 'commission_wins_ties' is not an enum value) ->
       refuses at VALIDATE.
  B-7. Staff-declared module with a may-act profile shape -> validates
       (well-formed) but refuses at GATE with the exact oracle violation
       strings.

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agent_behavior import AgentBehaviorProfile, bind_personalization
from .factory_archetypes import check_profile
from .factory_compiler import CompileRefused, compile_profile
from .rb_profile_build import drive_build, transcript_bytes

_HERE = Path(__file__).resolve().parent
_AUTHORED = _HERE / "authored"


def make_request(profile_name: str, module_bytes: bytes,
                 declared_archetypes: tuple[str, ...],
                 commission_ref: str) -> dict:
    return {
        "commission_ref": commission_ref,
        "profile_name": profile_name,
        "authored_module_bytes": bytes(module_bytes),
        "content_hash": hashlib.sha256(bytes(module_bytes)).hexdigest(),
        "declared_archetypes": tuple(declared_archetypes),
    }


def _read_fixture(name: str) -> bytes:
    return (_AUTHORED / f"{name}.py").read_bytes()


def _oracle_compile_reason(profile_name: str, builder_fn) -> str:
    """The refusal string from compiling the profile directly (no run-book)."""
    profile = bind_personalization(
        builder_fn(), principal_id="factory-build-time", bindings={},
        disposition_ref="commission:oracle")
    try:
        compile_profile(profile)
    except CompileRefused as e:
        return str(e)
    raise AssertionError(f"{profile_name}: oracle compiled?! (expected refusal)")


# Synthetic fixtures (source strings — deterministic by construction).

_BROKEN_SRC = '''"""Synthetic fixture B-6: builder yields a validation-breaking profile."""
from core.package.agent_behavior import AgentBehaviorProfile
from core.package.authored.wright import wright_profile

ARCHETYPES = ("staff", "office")

def broken_profile():
    good = wright_profile()
    data = good.model_dump(mode="json")
    # DR-CMD-093 D2 correction: 'commission_wins_ties' is not an enum value.
    data["d2_fidelity"]["conflict_rule"] = "commission_wins_ties"
    return AgentBehaviorProfile.model_validate(data)
'''

_GATE_VIOLATOR_SRC = '''"""Synthetic fixture B-7: staff-declared module, may-act profile shape."""
from core.package.authored.triager import triager_profile

ARCHETYPES = ("staff",)

def gate_violator_profile():
    # Triager-shaped (may-act x office) wearing a staff declaration:
    # well-formed (validate passes), but the staff gate refuses.
    return triager_profile()
'''

# The two remaining clerk routing refusals, verbatim per DR-CMD-097/100.
# (registrar_clerk's DR-CMD-096 refusal is gone: DR-CMD-102 tranche 1
# landed tool-register-artifact, so 'artifact-registry' resolves.)
_EXPECTED_CLERK_REFUSALS = {
    "triager":
        "compile refused at routing: write-scope channel 'quarantine' "
        "names no registered contracted tool or alias (B-3 analog)",
    "dr_registrar":
        "compile refused at routing: write-scope channel "
        "'decision-record-registry' names no registered contracted tool "
        "or alias (B-3 analog)",
}


def _terminal_step(transcript: dict) -> dict:
    return transcript["steps"][-1]


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # B-1: registrar_clerk now stages — the tranche-1 unblock, detected
    # mechanically. The 'artifact-registry' channel resolves at the
    # routing stage, so COMPILE passes; VERIFY and STAGE follow.
    from .authored.registrar_clerk import registrar_clerk_profile
    req1 = make_request("registrar_clerk", _read_fixture("registrar_clerk"),
                        ("clerk",), "commission:registrar-clerk-fixture")
    t1a = drive_build(req1)
    t1b = drive_build(req1)
    assert t1a["terminal"]["outcome"] == "staged", \
        f"registrar_clerk: expected staged, got {t1a['terminal']}"
    assert [s["status"] for s in t1a["steps"]] == ["ok"] * 6, \
        f"registrar_clerk: all six steps must pass: {t1a['steps']}"
    v1 = t1a["steps"][4]["detail"]
    assert v1["verdict"] == "verified" and v1["operable"], \
        f"registrar_clerk: verify must be verified+operable: {v1}"
    st1 = t1a["staged"]
    assert st1["disposition"] == "staged-for-operator", st1
    assert "NOT published; NOT registered; NOT disposed" in st1["note"], st1
    assert transcript_bytes(t1a) == transcript_bytes(t1b), \
        "registrar_clerk: two runs must yield byte-equal transcripts"
    violations.append("registrar_clerk staged through all six steps "
                      "(tranche-1 unblock); replay byte-equal; "
                      "NOT registered — registration is the Operator's "
                      "disposition")

    # B-2..B-3: triager and dr_registrar still refuse at COMPILE with the
    # exact routing-refusal reasons (tranche 2 not authorized).
    from .authored.triager import triager_profile
    from .authored.dr_registrar import dr_registrar_profile
    for name, builder in (("triager", triager_profile),
                          ("dr_registrar", dr_registrar_profile)):
        req = make_request(name, _read_fixture(name), ("clerk",),
                           f"commission:{name}-fixture")
        t = drive_build(req)
        last = _terminal_step(t)
        assert t["terminal"]["outcome"] == "refused", \
            f"{name}: expected refusal, got {t['terminal']}"
        assert last["step_id"] == "rb-profile-build-s4", \
            f"{name}: must refuse at COMPILE (s4), got {last['step_id']}"
        reason = last["reason"]
        # Exact against the direct-compile oracle ...
        assert reason == _oracle_compile_reason(name, builder), \
            f"{name}: run-book reason != oracle reason:\n{reason}"
        # ... and against the DR record literal.
        assert reason == _EXPECTED_CLERK_REFUSALS[name], \
            f"{name}: reason != DR record literal:\n{reason}"
        # The earlier steps all passed (the profile is well-formed).
        assert [s["status"] for s in t["steps"][:3]] == ["ok"] * 3, \
            f"{name}: receive/validate/gate must pass: {t['steps'][:3]}"
        refusals.append(f"{name} refused at COMPILE with the exact "
                        f"routing-refusal reason (verbatim)")

    # B-4: clean profile runs RECEIVE -> STAGE.
    wright_bytes = _read_fixture("wright")
    req4 = make_request("wright", wright_bytes, ("staff", "office"),
                        "commission:wright-clean")
    t4a = drive_build(req4)
    t4b = drive_build(req4)
    assert t4a["terminal"]["outcome"] == "staged", \
        f"wright: expected staged, got {t4a['terminal']}"
    assert [s["status"] for s in t4a["steps"]] == ["ok"] * 6, \
        f"wright: all six steps must pass: {t4a['steps']}"
    verify_detail = t4a["steps"][4]["detail"]
    assert verify_detail["verdict"] == "verified" and verify_detail["operable"], \
        f"wright: verify must be verified+operable: {verify_detail}"
    staged = t4a["staged"]
    assert staged["disposition"] == "staged-for-operator", staged
    assert "NOT published; NOT registered; NOT disposed" in staged["note"], \
        staged
    assert staged["content_hash"] == req4["content_hash"], staged
    # Deterministic replay: byte-equal transcripts.
    assert transcript_bytes(t4a) == transcript_bytes(t4b), \
        "wright: two runs must yield byte-equal transcripts"
    violations.append("wright staged through all six steps; replay byte-equal")

    # B-5: tampered bytes refuse at RECEIVE, before any code executes.
    tampered = bytearray(wright_bytes)
    tampered[len(tampered) // 2] ^= 0x01
    req5 = make_request("wright", bytes(tampered), ("staff", "office"),
                        "commission:wright-tampered")
    # Keep the ORIGINAL hash: the request claims bytes it does not carry.
    req5["content_hash"] = hashlib.sha256(wright_bytes).hexdigest()
    t5 = drive_build(req5)
    last5 = _terminal_step(t5)
    assert t5["terminal"]["outcome"] == "refused"
    assert last5["step_id"] == "rb-profile-build-s1", \
        f"tamper: must refuse at RECEIVE (s1), got {last5['step_id']}"
    assert "hash mismatch" in last5["reason"], last5["reason"]
    assert len(t5["steps"]) == 1, "tamper: no step after RECEIVE may run"
    refusals.append("tampered bytes refused at RECEIVE (hash mismatch, "
                    "fail-closed, no code executed)")

    # B-6: validation-breaking builder refuses at VALIDATE.
    broken_bytes = _BROKEN_SRC.encode()
    req6 = make_request("broken", broken_bytes, ("staff", "office"),
                        "commission:broken-fixture")
    t6 = drive_build(req6)
    last6 = _terminal_step(t6)
    assert t6["terminal"]["outcome"] == "refused"
    assert last6["step_id"] == "rb-profile-build-s2", \
        f"broken: must refuse at VALIDATE (s2), got {last6['step_id']}"
    assert "commission_wins_ties" in last6["reason"], last6["reason"]
    refusals.append("invalid-D2 builder refused at VALIDATE with the "
                    "pydantic reason")

    # B-7: staff-declared may-act shape refuses at GATE with oracle reasons.
    gv_bytes = _GATE_VIOLATOR_SRC.encode()
    req7 = make_request("gate_violator", gv_bytes, ("staff",),
                        "commission:gate-violator-fixture")
    t7 = drive_build(req7)
    last7 = _terminal_step(t7)
    assert t7["terminal"]["outcome"] == "refused"
    assert last7["step_id"] == "rb-profile-build-s3", \
        f"gate-violator: must refuse at GATE (s3), got {last7['step_id']}"
    oracle_violations = [str(v) for v in check_profile(
        triager_profile(), ("staff",))]
    assert oracle_violations, "oracle must produce staff violations"
    assert last7["reason"] == "; ".join(oracle_violations), \
        f"gate-violator: reason != oracle:\n{last7['reason']}"
    assert [s["status"] for s in t7["steps"][:2]] == ["ok"] * 2, \
        "gate-violator: receive+validate must pass (well-formed profile)"
    refusals.append("staff-declared may-act shape refused at GATE with the "
                    "exact oracle violation strings")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
