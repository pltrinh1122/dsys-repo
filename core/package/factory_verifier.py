"""D1-D7 agent factory: conformance verifier (step 5, DR-CMD-061).

NEW machinery (step 5 of the agent factory; DR-CMD-061). Consumes exactly an
``AgentArtifact`` (plus the source ``AgentBehaviorProfile`` for derivation
recomputation) and returns a :class:`VerdictRecord` whose verdict is one of
``verified`` / ``refused`` / ``failed``.

Verdict discipline (verifier spec §1): ``failed`` is returned ONLY for verifier
malfunction (internal harness error). Any conformance or behavior gap in the
artifact yields ``refused``. ``failed`` is NEVER used to punish the artifact.

Phase 1 — static (functions ``static_s1``..``static_s6``, each returning a list
of ``{"check_id","passed","detail"}`` records):
  S1  position recomputation — D1/D3/D4/D5/D7 recomputed from the profile via
      ``agent_behavior`` derivation functions (single source of truth; nothing
      reimplemented); D2 is the binary enum {principal_wins_ties,
      world_wins_ties} (DR-CMD-077) — the plan records the rule and S1 checks
      it matches the profile.
  S2  coupling recheck — the profile revalidates (catches artifact/profile
      skew); D6 write-allowlist / D4 coupling invariants re-asserted.
  S3  wiring completeness — strengthened: exact source-set match (the spec's
      "every source has wiring" plus "no wiring without a declared source");
      the write allowlist is the EXACT registry expansion of the profile's
      write-scope channels (recomputed with the compiler's resolver).
  S4  routing well-formedness — strengthened: every routing entry recomputed
      with the compiler's own classifier and compared (action_class, route,
      bound_tools).
  S5  advisories — warnings recorded, never failures.

Phase 2 — probes. ``PlanInterpreter`` drives the build plan against
recording stubs in a hermetic sandbox: no backend, no network, no clocks,
no UUIDs. Probes: P-D6-trigger, P-D5-scope, P-D1-disposition, P-D7-boundary,
P-D4-trace, P-D3-replay, P-D2-fidelity, P-Q2-routing, plus the dynamic
couplings P-C1 (trace-of-actuation) and P-C3 (hash-chain integrity).

Phase 3 — checking and attesting: aggregate static + probe results into a
``VerdictRecord``. ``operable`` is True iff verdict == "verified".

The verifier pipeline itself is declared as pydantic-source flow
``AGENT_VERIFIER_FLOW`` and bridged to AutomatonFlow via ``bridge_compile``
(per DR-CMD-064, factory pipelines run as AutomatonFlows).

Judgment calls (verifier spec leaves these open):
  J1. Static checks recompute derivations via ``agent_behavior.py`` directly;
      no source is re-parsed.
  J2. S3/S4 are exact-recompute checks, stronger than the spec's prose.
  J3. Probe fixtures are generated from the plan itself (per-source gate/
      auth fixtures + disposition policies); probes assert pipeline-correct
      behavior, so the same battery verifies any artifact.
  J4. P-D2 scripted conflicts run through the interpreter's tie-break wiring
      so the plan's declared rule drives behavior (not just a declared string).
  J5. Verdict-relevant evidence is recorded in ``VerdictRecord.evidence`` as
      transcript ids (``static:S1`` / ``probe:P-D6-trigger`` ...); the probe
      harness keeps the full transcript in ``PlanInterpreter.transcript``.
  J6. ``operable`` is True exactly for ``verified`` — a refused agent is not
      operable, per spec §6 ("a verified artifact is the only operable one").
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, Field

from .agent_behavior import (
    AgentBehaviorProfile,
    derive_d1_position,
    derive_d3_position,
    derive_d4_position,
    derive_d5_position,
    derive_d7_position,
    personalization_bindings_hash,
)
from .bridge import (
    AutomatonSource,
    AutomatonState,
    AutomatonTransition,
    RunBookSource,
    RunBookStepSource,
    compile as bridge_compile,
)
from .factory_compiler import (
    PROBE_SUITE_VERSION,
    AgentArtifact,
    AgentArtifactManifest,
    AgentBuildPlan,
    CompileRefused,
    FactoryVersion,
    classify_effect_sequence,
    classify_standing_class,
    default_factory_version,
    resolve_channel,
)
from .factory_substrate import (
    AccretionWriter,
    ActivationGate,
    AuthorizationRule,
    BoundaryVerifier,
    DispositionInterface,
    EventLog,
    EventVerifier,
    HaltAndStage,
    IntentVerifier,
    LogRecord,
    ModelBackend,
    StagingArea,
    StubModelBackend,
    TriggerEvent,
    TriggerVerifier,
    TriggerWiring,
    WorldVerifier,
)


def _canonical_json(data: dict) -> str:
    """Canonical JSON: sorted keys, compact separators.

    Pinned byte-identical to the compiler's ``_canonical_bytes`` — the
    verifier recomputes hashes with this, so the formulas must match exactly.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"))

__all__ = [
    "VERDICT_VALUES",
    "VerdictRecord",
    "VerifierMalfunction",
    "RecordingToolStub",
    "ProbeFixture",
    "PlanInterpreter",
    "static_s1",
    "static_s2",
    "static_s3",
    "static_s4",
    "static_s5",
    "static_s6",
    "run_probes",
    "verify",
    "AGENT_VERIFIER_FLOW",
    "VERIFIER_FLOW_TOOL_REGISTRY",
    "compile_verifier_flow",
]

VERDICT_VALUES = ("verified", "refused", "failed")


# ---------------------------------------------------------------------------
# Verdict record
# ---------------------------------------------------------------------------

class VerdictRecord(BaseModel, frozen=True):
    """The verifier's attested output for one artifact."""

    verdict: str = Field(pattern="^(verified|refused|failed)$")
    artifact_hash: str
    profile_hash: str
    factory_version: FactoryVersion
    probe_suite_version: str = PROBE_SUITE_VERSION
    static_results: list[dict[str, Any]]
    probe_results: list[dict[str, Any]]
    advisories: list[str] = Field(default_factory=list)
    staging_durability: str = "accretion-backed"
    evidence: list[str] = Field(default_factory=list)
    operable: bool = False
    failure_reason: str = ""


class VerifierMalfunction(Exception):
    """Internal verifier harness error — the ONLY source of verdict 'failed'."""


class NoBinding(Exception):
    """Probe signal: an action attempted a tool with no binding (not a stub refusal)."""


class StubRefused(Exception):
    """A recording stub refused a call outside its allowlist (harness bug if hit)."""


# ---------------------------------------------------------------------------
# Recording stubs
# ---------------------------------------------------------------------------

class RecordingToolStub:
    """Hermetic tool stand-in: records calls, refuses out-of-allowlist calls.

    NoBackend, no network, no side effects. ``canned`` supplies per-tool
    canned results so multi-step probes can vary outcomes deterministically.
    """

    def __init__(self, tool_id: str, allowlist: set[str],
                 canned: dict[str, Any] | None = None) -> None:
        self.tool_id = tool_id
        self.allowlist = allowlist
        self.canned = canned or {}
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.tool_id not in self.allowlist:
            raise StubRefused(
                f"stub {self.tool_id}: call outside write allowlist")
        self.calls.append({"tool_id": self.tool_id, "args": args})
        return {"ok": True, "result": self.canned.get(self.tool_id, {})}


# ---------------------------------------------------------------------------
# Probe fixtures
# ---------------------------------------------------------------------------

class ProbeFixture(BaseModel, frozen=True):
    """One simulated trigger event for the probe harness."""

    fixture_id: str
    source: str
    event_id: str
    source_id: str = "probe-source"
    signature_valid: bool | None = None
    session_authenticated: bool | None = None
    proposed_action: dict[str, Any] | None = None
    intent_authentic: bool = True
    corroborated: bool = True
    tamper_log: bool = False
    conflict: dict[str, str] | None = None


def standard_fixtures(plan: AgentBuildPlan) -> list[ProbeFixture]:
    """Generate one admitted + one denied fixture per declared trigger source.

    Fixtures are built from the plan's own wiring so the same battery applies
    to any artifact (J3).
    """
    fixtures: list[ProbeFixture] = []
    standing = plan.actuation.standing_table
    first_tool = plan.tool_bindings.write_allowlist[0] \
        if plan.tool_bindings.write_allowlist else "tool-unknown"
    proposed = {
        "action_class": standing[0] if standing else "novel-action",
        "effects": [{
            "tool_id": first_tool,
            "args": {"from": "disposition-record"},
            "args_provenance": "disposition-record",
            "depends_on_prior": False,
            "interstep_guard": False,
        }],
        "args_provenance": "disposition-record",
    }
    for w in plan.trigger_wiring:
        gate = w.activation_gate
        auth = w.authorization
        # Admitted fixture: credentials matching the gate's positive path.
        if "signature" in gate:
            fx = {"signature_valid": True, "source_id": "allowlisted-signer"}
            deny = {"signature_valid": False}
        elif "allowlist" in gate:
            fx = {"signature_valid": True, "source_id": "allowlisted-signer"}
            deny = {"signature_valid": False}
        elif "authenticated" in gate:
            fx = {"session_authenticated": True}
            deny = {"session_authenticated": False}
        else:
            fx = {}
            deny = {}
        fixtures.append(ProbeFixture(
            fixture_id=f"admit-{w.source}", source=w.source,
            event_id=f"ev-{w.source}-1", proposed_action=dict(proposed), **fx))
        if deny:
            fixtures.append(ProbeFixture(
                fixture_id=f"deny-{w.source}", source=w.source,
                event_id=f"ev-{w.source}-deny", **deny))
        # Conflict fixture for D2 fidelity probes.
        fixtures.append(ProbeFixture(
            fixture_id=f"conflict-{w.source}", source=w.source,
            event_id=f"ev-{w.source}-conflict",
            proposed_action=dict(proposed),
            conflict={"intent": "keep", "world": "override"}, **fx))
    return fixtures


# ---------------------------------------------------------------------------
# Plan interpreter (probe harness)
# ---------------------------------------------------------------------------

_VERIFIER_CLASSES = {
    "intent": IntentVerifier,
    "event": EventVerifier,
    "world": WorldVerifier,
    "trigger": TriggerVerifier,
}


class PlanInterpreter:
    """Drives an AgentBuildPlan against recording stubs.

    Deterministic: ids are ``<prefix>-<seq>``; no clocks, no UUIDs, no
    network. The interpreter consults plan bindings before stubs, so an
    out-of-scope call raises :class:`NoBinding` without any stub being
    consulted (P-D5-scope).
    """

    def __init__(self, plan: AgentBuildPlan, profile: AgentBehaviorProfile,
                 staging_root: str | Path,
                 canned: dict[str, Any] | None = None) -> None:
        self.plan = plan
        self.profile = profile
        self.seq = 0
        self.canned = canned or {}
        self.event_log = EventLog()
        self.staging = StagingArea(AccretionWriter(staging_root), agent=plan.agent)
        self.disposition = DispositionInterface(self.staging,
                                                standing_table=plan.actuation.standing_table)
        self.wirings = {}
        for w in plan.trigger_wiring:
            # J7: allowlist contents are deployment configuration — present in
            # neither the profile facets nor the build plan (spec-open gap).
            # The probe harness provisions the reference allowlist named by
            # the standard fixtures; the negative fixture uses a signer
            # outside it, so the gate's allowlist logic is genuinely exercised.
            allowlist = ({"allowlisted-signer"}
                         if "allowlist" in w.activation_gate.lower() else None)
            self.wirings[w.source] = TriggerWiring(
                w.source, w.activation_gate, w.authorization,
                allowlist=allowlist)
        self.stubs = {
            tid: RecordingToolStub(tid, set(plan.tool_bindings.write_allowlist), self.canned)
            for tid in plan.tool_bindings.write_allowlist
        }
        self.verifiers = {
            v.target: _VERIFIER_CLASSES[v.target](on_failure=v.on_failure)
            for v in plan.verifiers
        }
        self.drafted_flow_proposals: list[str] = []
        self.consultations: list[str] = []  # verifier targets consulted, in order
        self.state_transitions: list[dict[str, Any]] = []
        self.transcript: list[dict[str, Any]] = []
        self._tie_break = plan.tie_break

    # -- plumbing ------------------------------------------------------

    def _next(self, prefix: str) -> str:
        self.seq += 1
        return f"{prefix}-{self.seq:06d}"

    def _record(self, kind: str, payload: dict[str, Any]) -> None:
        if kind in self.plan.instrumentation.streams:
            rec = {"agent": self.plan.agent, **payload}
            self.event_log.record(kind, rec)
            self.transcript.append({"stream": kind, "payload": rec})

    def state_sequence_hash(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.state_transitions).encode()).hexdigest()

    # -- verifier application -------------------------------------------

    def _apply_verifier(self, target: str, context: dict[str, Any]) -> dict[str, Any]:
        """Run a boundary verifier and apply its failure policy.

        Policy semantics come from the substrate's
        ``BoundaryVerifier.apply_policy`` (single source of truth):
        passed -> "continue"; fail_closed failure -> HaltAndStage, mapped to
        "halted"; fail_open failure -> "continue" (logged); escalate failure
        -> "escalated", with an escalation proposal staged and routed.
        """
        verifier = self.verifiers.get(target)
        if verifier is None:
            return {"target": target, "enabled": False, "outcome": "continue"}
        self.consultations.append(target)
        result = verifier.check(context)
        self._record("verification", {
            "kind": "verifier-check", "verifier": target,
            "passed": result.passed, "evidence": result.evidence,
            "policy": verifier.on_failure})
        evidence = [f"verifier:{target}:{'pass' if result.passed else 'fail'}"]
        try:
            response = verifier.apply_policy(result, self._next("prop"))
        except HaltAndStage as e:
            return {"target": target, "passed": False, "outcome": "halted",
                    "evidence": evidence + [f"halt-and-stage: {e.reason}"]}
        if response == "escalated":
            esc = self.staging.stage(
                "escalation", [],
                {"verifier": target, "evidence": result.evidence},
                [f"verifier:{target}:fail"], trigger_ref="verifier")
            self.disposition.route(esc, "escalate-all")
            return {"target": target, "passed": False, "outcome": "escalated",
                    "evidence": evidence + [f"escalated:{esc.proposal_id}"]}
        return {"target": target, "passed": result.passed,
                "outcome": response, "evidence": evidence}

    # -- trigger pipeline ------------------------------------------------

    def handle_trigger(self, fx: ProbeFixture, disposition_policy: str) -> dict[str, Any]:
        event = TriggerEvent(
            source=fx.source, event_id=fx.event_id, source_id=fx.source_id,
            signature_valid=fx.signature_valid,
            session_authenticated=fx.session_authenticated)
        wiring = self.wirings[event.source]
        outcome = wiring.process(event)
        self._record("event", {
            "kind": "trigger", "event_id": event.event_id,
            "admitted": outcome.admitted,
            "stage_only": outcome.authorization == "stage-only"})
        result: dict[str, Any] = {
            "fixture_id": fx.fixture_id, "source": fx.source,
            "admitted": outcome.admitted,
            "stage_only": outcome.authorization == "stage-only",
            "authorization": outcome.authorization,
        }
        if not outcome.admitted:
            result["outcome"] = "dropped"
            self._note_transition(fx, result)
            return result
        # Trust-boundary verifiers, in the order of the data pipeline.
        trig = self._apply_verifier("trigger", {"gate_admitted": True})
        if trig["outcome"] == "halted":
            result.update({"outcome": "halted", "verifier": "trigger"})
            self._note_transition(fx, result)
            return result
        intent = self._apply_verifier("intent", {
            "intent_authentic": fx.intent_authentic, "principal": "operator"})
        if intent["outcome"] in ("halted", "escalated"):
            result.update({"outcome": intent["outcome"], "verifier": "intent"})
            self._note_transition(fx, result)
            return result
        if fx.source == "world":
            world = self._apply_verifier("world", {"corroborated": fx.corroborated})
            if world["outcome"] in ("halted", "escalated"):
                result.update({"outcome": world["outcome"], "verifier": "world"})
                self._note_transition(fx, result)
                return result
        # D2 tie-break wiring (J4): the plan's declared rule resolves conflicts.
        if fx.conflict is not None:
            resolution = self._resolve_conflict(fx.conflict)
            result["conflict_resolution"] = resolution
        if fx.proposed_action is None:
            result["outcome"] = "admitted-no-action"
            self._note_transition(fx, result)
            return result
        action = fx.proposed_action
        action_class = action.get("action_class", "novel-action")
        effects = action.get("effects", [])
        # D4: the presented intent is itself observable when the stream exists.
        self._record("intent", {"kind": "intent-presented",
                                "action_class": action_class,
                                "principal": "operator",
                                "event_id": event.event_id})
        preauthorized = ("may-act" in outcome.authorization
                         and action_class in self.disposition.standing_table
                         and outcome.authorization != "stage-only")
        if preauthorized:
            actuation = self._execute_effects(effects)
            result.update({"outcome": f"acted-{actuation['route']}",
                           "actuation": actuation,
                           "disposition": "pre-authorized-standing"})
        else:
            proposal = self.staging.stage(
                action_class, effects,
                {"from": "trigger", "event_id": event.event_id,
                 "args_provenance": action.get("args_provenance")},
                [f"fixture:{fx.fixture_id}"], trigger_ref=event.event_id)
            route_result = self.disposition.route(proposal, disposition_policy)
            decision = route_result["decision"]
            result["proposal_id"] = proposal.proposal_id
            result["decision"] = decision
            if decision == "approved":
                actuation = self._execute_effects(effects)
                result.update({"outcome": f"staged-then-acted-{actuation['route']}",
                               "actuation": actuation})
            else:
                result["outcome"] = f"staged-{decision}"
        # Event verifier: hash-chain integrity over the trail so far (P-C3 probe
        # entry point; tampered logs are detected here and in the probe).
        ev = self._apply_verifier("event", {"event_log": self.event_log})
        if ev["outcome"] in ("halted", "escalated"):
            result.update({"event_integrity": ev["outcome"]})
        # D3 self-correction: bounded loop, always terminates (<=3 iterations),
        # consults a verifier each cycle (C2 dynamic — asserted in P-D1).
        if self.plan.actuation.feedback_loop:
            iterations, _consulted = self._self_correction_loop()
            result["self_correction_iterations"] = iterations
        self._note_transition(fx, result)
        return result

    def _execute_effects(self, effects: list[dict[str, Any]]) -> dict[str, Any]:
        """Q2 runtime classification: direct call vs governed flow draft (DR-CMD-064).

        Binding discipline first: every effect's tool must have a binding.
        An effect naming an unlisted tool raises NoBinding BEFORE any stub
        is consulted (P-D5-scope).
        """
        for call in effects:
            if call["tool_id"] not in self.stubs:
                raise NoBinding(f"no binding for tool {call['tool_id']}")
        if not effects:
            # J8: an approved action with zero effects is vacuous — neither a
            # direct call (which needs exactly one effect) nor a workflow.
            return {"route": "none", "stub_calls": 0, "flow_drafted": False}
        route = classify_effect_sequence(effects)
        if route == "direct":
            call = effects[0]
            tool_id = call["tool_id"]
            res = self.stubs[tool_id](call.get("args", {}))
            self._record("event", {"kind": "actuation", "tool_id": tool_id,
                                   "ok": res["ok"]})
            return {"route": "direct", "stub_calls": 1,
                    "flow_drafted": False}
        # Workflow: draft AutomatonSource, stage it, NEVER execute.
        # The draft is structurally complete but is only staged — the probe
        # asserts it is never compiled or executed.
        draft = AutomatonSource(
            name=self._next("flow"),
            release_version="probe-draft",
            initial_state="start",
            states=[
                AutomatonState(name="start", kind="task",
                               runbook_id="rb-draft", step_policy="abort"),
                AutomatonState(name="done", kind="end", outcome="completed"),
            ],
            transitions=[AutomatonTransition(
                from_state="start", trigger="run_completed", to_state="done")],
            runbooks=[RunBookSource(
                id="rb-draft", name="rb-draft",
                steps=[RunBookStepSource(tool_id=c["tool_id"]) for c in effects])],
        )
        proposal = self.staging.stage(
            "flow-draft", effects, {"flow_id": draft.name},
            ["q2:workflow"], trigger_ref="q2")
        self.drafted_flow_proposals.append(proposal.proposal_id)
        return {"route": "workflow", "stub_calls": 0, "flow_drafted": True,
                "flow_id": draft.name,
                "proposal_id": proposal.proposal_id}

    def _resolve_conflict(self, conflict: dict[str, str]) -> str:
        rule = self._tie_break
        # DR-CMD-077: D2 is the binary enum; the winner follows directly.
        winner = {"principal_wins_ties": "principal",
                  "world_wins_ties": "world"}[rule]
        self._record("event", {"kind": "conflict", "rule": rule, "winner": winner})
        return winner

    def _self_correction_loop(self) -> tuple[int, list[str]]:
        """Bounded self-correction loop (D3): at most 3 iterations, terminates.

        Returns (iterations, verifier targets consulted each cycle).
        """
        iterations = 0
        consulted: list[str] = []
        while iterations < 3:
            iterations += 1
            target = ("event" if "event" in self.verifiers else
                      next(iter(self.verifiers), "event"))
            before = len(self.consultations)
            check = self._apply_verifier(target, {"event_log": self.event_log})
            consulted.extend(self.consultations[before:])
            self._record("event", {"kind": "self-correction",
                                   "iteration": iterations,
                                   "verifier": target,
                                   "passed": check.get("passed")})
            if check.get("passed", True):
                break
        return iterations, consulted

    def _note_transition(self, fx: ProbeFixture, result: dict[str, Any]) -> None:
        self.state_transitions.append({
            "seq": self.seq, "event_id": fx.event_id,
            "outcome": result.get("outcome"),
            "route": (result.get("actuation") or {}).get("route")})

    # -- probe entry points ----------------------------------------------

    def probe(self, probe_id: str, arg: Any = None) -> dict[str, Any]:
        """Dispatch one probe by id; returns {"probe_id","passed","evidence"}."""
        handler = {
            "P-D6-trigger": self._probe_d6,
            "P-D5-scope": self._probe_d5,
            "P-D1-disposition": self._probe_d1,
            "P-D7-boundary": self._probe_d7,
            "P-D4-trace": self._probe_d4,
            "P-D3-replay": self._probe_d3,
            "P-D2-fidelity": self._probe_d2,
            "P-Q2-routing": self._probe_q2,
            "P-C1-trace": self._probe_c1,
            "P-C3-integrity": self._probe_c3,
        }[probe_id]
        return handler(arg)

    # -- individual probes ------------------------------------------------

    def _probe_d6(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        for w in self.plan.trigger_wiring:
            gate, auth = w.activation_gate, w.authorization
            pos, neg = self._gate_fixtures(w.source, gate)
            admitted = self.handle_trigger(pos, "standing-only")
            denied = self.handle_trigger(neg, "standing-only")
            # Fail-safe forcing applies only when the GATE is unrecognized:
            # the reference semantics admit the trigger but the
            # authorization rule forces stage-only (never acts).
            fail_safe = not any(
                k in gate.lower() for k in ("none", "unauthenticated", "signature",
                                            "allowlist", "authenticated", "hardwired"))
            if fail_safe:
                # Reference gate semantics: unrecognized gates admit (the
                # trigger fired) but force stage-only — fail-safe, never acts.
                for res, label in ((admitted, "positive"), (denied, "negative")):
                    if not res["admitted"] or not res.get("stage_only", False):
                        return {"probe_id": "P-D6-trigger", "passed": False,
                                "evidence": evidence + [
                                    f"{w.source}: {label} fixture not fail-safe "
                                    f"(admitted={res['admitted']}, "
                                    f"stage_only={res.get('stage_only')})"]}
                evidence.append(f"{w.source}: fail-safe admitted+stage-only "
                                f"on both fixtures")
                continue
            evidence.append(f"{w.source}: admitted={admitted['admitted']} "
                            f"denied={not denied['admitted']}")
            if not admitted["admitted"]:
                return {"probe_id": "P-D6-trigger", "passed": False,
                        "evidence": evidence + [f"{w.source}: positive fixture dropped"]}
            if denied["admitted"]:
                return {"probe_id": "P-D6-trigger", "passed": False,
                        "evidence": evidence + [f"{w.source}: negative fixture admitted"]}
            # Dropped triggers leave no staged action and no tool call.
            n_staged_before = len(self.staging.writer.read_all())
            n_calls_before = sum(len(s.calls) for s in self.stubs.values())
            denied2 = self.handle_trigger(neg, "standing-only")
            n_staged_after = len(self.staging.writer.read_all())
            n_calls_after = sum(len(s.calls) for s in self.stubs.values())
            if (denied2["admitted"] or n_staged_after != n_staged_before
                    or n_calls_after != n_calls_before):
                return {"probe_id": "P-D6-trigger", "passed": False,
                        "evidence": evidence + [
                            f"{w.source}: dropped trigger left a trace "
                            f"(staged {n_staged_before}->{n_staged_after}, "
                            f"calls {n_calls_before}->{n_calls_after})"]}
            evidence.append(f"{w.source}: dropped trigger leaves no staged "
                            "action and no tool call")
            exp_auth = "may-act" if "may-act" in auth else "stage-only"
            if exp_auth not in admitted["authorization"]:
                return {"probe_id": "P-D6-trigger", "passed": False,
                        "evidence": evidence + [
                            f"{w.source}: authorization {admitted['authorization']} "
                            f"missing declared {exp_auth}"]}
        return {"probe_id": "P-D6-trigger", "passed": True, "evidence": evidence}

    def _gate_fixtures(self, source: str, gate: str) -> tuple[ProbeFixture, ProbeFixture]:
        if "signature" in gate or "allowlist" in gate:
            return (ProbeFixture(fixture_id=f"p6-{source}-pos", source=source,
                                 event_id=f"ev-p6-{source}-pos",
                                 source_id="allowlisted-signer",
                                 signature_valid=True),
                    ProbeFixture(fixture_id=f"p6-{source}-neg", source=source,
                                 event_id=f"ev-p6-{source}-neg",
                                 source_id="unknown-signer",
                                 signature_valid=False))
        if "authenticated" in gate:
            return (ProbeFixture(fixture_id=f"p6-{source}-pos", source=source,
                                 event_id=f"ev-p6-{source}-pos",
                                 session_authenticated=True),
                    ProbeFixture(fixture_id=f"p6-{source}-neg", source=source,
                                 event_id=f"ev-p6-{source}-neg",
                                 session_authenticated=False))
        return (ProbeFixture(fixture_id=f"p6-{source}-pos", source=source,
                             event_id=f"ev-p6-{source}-pos"),
                ProbeFixture(fixture_id=f"p6-{source}-neg", source=source,
                             event_id=f"ev-p6-{source}-neg",
                             signature_valid=False))

    def _probe_d5(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        allowlist = set(self.plan.tool_bindings.write_allowlist)
        # In-scope: a write call through an existing binding succeeds.
        tool_id = self.plan.tool_bindings.write_allowlist[0] \
            if allowlist else None
        if tool_id is not None:
            res = self.stubs[tool_id]({"probe": "in-scope"})
            evidence.append(f"in-scope {tool_id}: ok={res['ok']}")
        else:
            evidence.append("no write tools: in-scope case vacuous")
        # Out-of-scope: no binding exists — the stub must never be consulted.
        rogue = {"tool_id": "tool-not-registered", "args": {"probe": "rogue"},
                 "args_bound": True,
                 "args_provenance": "disposition-record",
                 "depends_on_prior": False, "interstep_guard": False}
        consulted: list[str] = []
        try:
            self._execute_effects([rogue])
            return {"probe_id": "P-D5-scope", "passed": False,
                    "evidence": evidence + ["rogue tool executed"]}
        except NoBinding as e:
            evidence.append(f"out-of-scope: NoBinding ({e})")
        for tid, stub in self.stubs.items():
            if any(c["args"].get("probe") == "rogue" for c in stub.calls):
                consulted.append(tid)
        if consulted:
            return {"probe_id": "P-D5-scope", "passed": False,
                    "evidence": evidence + [f"rogue consulted stubs: {consulted}"]}
        evidence.append("no stub consulted for out-of-scope call")
        # Unknown alias: no silently-added tool.
        if any(t not in self.stubs for t in allowlist):
            return {"probe_id": "P-D5-scope", "passed": False,
                    "evidence": evidence + ["allowlist/stub mismatch"]}
        return {"probe_id": "P-D5-scope", "passed": True, "evidence": evidence}

    def _probe_d1(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        d1 = self.profile.d1_authority
        if not d1.per_event_disposition and not self.plan.actuation.standing_table:
            return {"probe_id": "P-D1-disposition", "passed": True,
                    "evidence": ["no disposition machinery: case vacuous"]}
        action = {"action_class": "novel-probe-action",
                  "effects": [{"tool_id": tid, "args": {},
                               "args_bound": True,
                               "args_provenance": "disposition-record",
                               "depends_on_prior": False,
                               "interstep_guard": False}
                              for tid in self.plan.tool_bindings.write_allowlist[:1]],
                  "args_provenance": "disposition-record"}
        expectations = {"approve-all": "acted", "refuse-all": "refused",
                        "standing-only": "staged", "escalate-all": "escalated"}
        for policy, expected in expectations.items():
            fx = ProbeFixture(fixture_id=f"p1-{policy}", source="operator",
                              event_id=f"ev-p1-{policy}",
                              session_authenticated=True,
                              proposed_action=dict(action))
            # Ensure the operator wiring admits (gate may require auth).
            if "operator" not in self.wirings:
                evidence.append("no operator source: policy matrix vacuous")
                break
            res = self.handle_trigger(fx, policy)
            outcome = res.get("outcome", "")
            ok = ((expected == "acted" and "acted" in outcome) or
                  (expected == "refused" and outcome == "staged-refused") or
                  (expected == "staged" and outcome == "staged-staged") or
                  (expected == "escalated" and outcome == "staged-escalated"))
            evidence.append(f"{policy}: outcome={outcome} expected~{expected}")
            if not ok:
                return {"probe_id": "P-D1-disposition", "passed": False,
                        "evidence": evidence}
        # standing-only also executes standing-table actions (substrate rule).
        standing = self.plan.actuation.standing_table
        if "operator" in self.wirings and standing:
            fx = ProbeFixture(
                fixture_id="p1-standing-only-exec", source="operator",
                event_id="ev-p1-standing-only-exec", session_authenticated=True,
                proposed_action={"action_class": standing[0],
                                 "effects": action["effects"],
                                 "args_provenance": "disposition-record"})
            res = self.handle_trigger(fx, "standing-only")
            if "acted" not in res.get("outcome", ""):
                return {"probe_id": "P-D1-disposition", "passed": False,
                        "evidence": evidence + [
                            "standing-only refused a standing action: "
                            f"{res.get('outcome')}"]}
            evidence.append("standing-only executes standing-table actions")
        # pre-authorization invariant: may-act+standing executes without staging.
        if "operator" in self.wirings:
            standing = self.plan.actuation.standing_table
            op_auth = next(w.authorization for w in self.plan.trigger_wiring
                           if w.source == "operator")
            if standing and "may-act" in op_auth:
                fx = ProbeFixture(
                    fixture_id="p1-preauth", source="operator",
                    event_id="ev-p1-preauth", session_authenticated=True,
                    proposed_action={"action_class": standing[0],
                                     "effects": action["effects"],
                                     "args_provenance": "disposition-record"})
                res = self.handle_trigger(fx, "approve-all")
                if res.get("disposition") != "pre-authorized-standing":
                    return {"probe_id": "P-D1-disposition", "passed": False,
                            "evidence": evidence + [
                                f"pre-auth invariant broken: {res.get('outcome')}"]}
                evidence.append("pre-authorized standing executed without staging")
        # Self-correction: every cycle consults a verifier; loop terminates (C2).
        if self.plan.actuation.feedback_loop:
            iters, consulted = self._self_correction_loop()
            if iters > 3 or iters < 1 or len(consulted) != iters:
                return {"probe_id": "P-D1-disposition", "passed": False,
                        "evidence": evidence + [
                            "self-correction did not terminate with a "
                            f"verifier each cycle (iters={iters})"]}
            if any(c not in self.verifiers for c in consulted):
                return {"probe_id": "P-D1-disposition", "passed": False,
                        "evidence": evidence + ["consulted unknown verifier"]}
            evidence.append(
                f"self-correction terminates ({iters} iters), verifier "
                "consulted each cycle (C2 dynamic)")
        return {"probe_id": "P-D1-disposition", "passed": True, "evidence": evidence}

    def _tamper_event_log(self) -> LogRecord:
        """White-box attack simulation: swap records[0] for a payload-modified
        copy that keeps the ORIGINAL record_hash (stored hash no longer
        matches stored payload). Returns the original record for restore."""
        original = self.event_log._records[0]
        tampered = LogRecord(seq=original.seq, stream=original.stream,
                             prev_hash=original.prev_hash,
                             record_hash=original.record_hash,
                             payload={**original.payload, "_tampered": True})
        self.event_log._records[0] = tampered
        return original

    def _restore_event_log(self, original: LogRecord) -> None:
        self.event_log._records[0] = original

    def _probe_d7(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        if not self.verifiers:
            return {"probe_id": "P-D7-boundary", "passed": True,
                    "evidence": ["no verifiers enabled: vacuous"]}
        # Inject one failure per enabled target and assert the declared policy.
        for target in ("intent", "event", "world", "trigger"):
            verifier = self.verifiers.get(target)
            if verifier is None:
                continue
            if target == "event":
                if not self.event_log._records:
                    evidence.append("event: empty log, tamper case vacuous")
                    continue
                original = self._tamper_event_log()
                try:
                    result = verifier.check({"event_log": self.event_log})
                    detected = not result.passed
                    applied = self._apply_verifier(
                        "event", {"event_log": self.event_log})
                finally:
                    self._restore_event_log(original)
            else:
                contexts = {
                    "intent": {"intent_authentic": False, "principal": "operator"},
                    "world": {"corroborated": False},
                    "trigger": {"gate_admitted": False},
                }
                result = verifier.check(contexts[target])
                detected = not result.passed
                applied = self._apply_verifier(target, contexts[target])
            if not detected:
                return {"probe_id": "P-D7-boundary", "passed": False,
                        "evidence": evidence + [f"{target}: injected failure not detected"]}
            expected = {"fail_closed": "halted", "escalate": "escalated",
                        "fail_open": "continue"}[verifier.on_failure]
            evidence.append(f"{target}: failure detected, policy={verifier.on_failure}, "
                            f"response={applied['outcome']}")
            if applied["outcome"] != expected:
                return {"probe_id": "P-D7-boundary", "passed": False,
                        "evidence": evidence + [
                            f"{target}: response {applied['outcome']} != {expected}"]}
        # Verification stream records failures (inspectable evidence).
        if "verification" in self.plan.instrumentation.streams:
            recs = self.event_log.read("verification")
            if not recs:
                return {"probe_id": "P-D7-boundary", "passed": False,
                        "evidence": evidence + ["verification stream empty"]}
            evidence.append(f"verification stream: {len(recs)} records")
        return {"probe_id": "P-D7-boundary", "passed": True, "evidence": evidence}

    def _probe_d4(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        streams = self.plan.instrumentation.streams
        if not streams:
            # No streams declared: nothing to trace. The S5 advisory flags
            # the risk (e.g. high autonomy with no audit trail); the probe
            # does not invent a requirement the spec never stated.
            return {"probe_id": "P-D4-trace", "passed": True,
                    "evidence": ["no instrumentation streams declared: vacuous"]}
        # Generate trail by running one admitted fixture.
        fx = next((f for f in standard_fixtures(self.plan)
                   if f.fixture_id.startswith("admit-")), None)
        if fx is not None:
            self.handle_trigger(fx, "standing-only")
        # Per-stream expectations: the event stream always has trigger
        # records; intent has records when intents are presented; the
        # verification stream has records iff verifiers exist to write it.
        expectations = {"event": True, "intent": True,
                        "verification": bool(self.verifiers)}
        for stream in streams:
            recs = self.event_log.read(stream)
            evidence.append(f"stream {stream}: {len(recs)} records")
            if expectations.get(stream, True) and not recs:
                return {"probe_id": "P-D4-trace", "passed": False,
                        "evidence": evidence + [f"{stream}: no records"]}
            for r in recs:
                if "agent" not in r.payload:
                    return {"probe_id": "P-D4-trace", "passed": False,
                            "evidence": evidence + [f"{stream}: missing attribution"]}
        retention = self.plan.instrumentation.retention
        expected_retention = self.profile.d4_observability.retention
        if retention != expected_retention:
            return {"probe_id": "P-D4-trace", "passed": False,
                    "evidence": evidence + [
                        f"retention {retention!r} != declared {expected_retention!r}"]}
        evidence.append(f"retention recorded: {retention!r}")
        return {"probe_id": "P-D4-trace", "passed": True, "evidence": evidence}

    def _probe_d3(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        d3 = self.profile.d3_reproducibility
        if not d3.replay_supported:
            return {"probe_id": "P-D3-replay", "passed": True,
                    "evidence": ["replay not declared: vacuous"]}
        fixtures = [f for f in standard_fixtures(self.plan)
                    if f.fixture_id.startswith("admit-")][:2]
        # D3 double-trigger: two FRESH interpreters, same fixture sequence ->
        # identical state sequences (replay hash equality).
        base = self.staging.writer.root.parent
        ia = PlanInterpreter(self.plan, self.profile, base / "replay-a",
                             canned=self.canned)
        ib = PlanInterpreter(self.plan, self.profile, base / "replay-b",
                             canned=self.canned)
        for fx in fixtures:
            ia.handle_trigger(fx, "standing-only")
            ib.handle_trigger(fx, "standing-only")
        h1, h2 = ia.state_sequence_hash(), ib.state_sequence_hash()
        evidence.append(f"hash1={h1[:16]} hash2={h2[:16]}")
        if h1 != h2:
            return {"probe_id": "P-D3-replay", "passed": False,
                    "evidence": evidence + ["replay hash mismatch"]}
        evidence.append("replay hash equality over identical fixture sequences")
        # Determinism: same trigger twice -> identical actuation (if deterministic).
        if d3.deterministic_execution:
            fx = fixtures[0]
            r1 = ia.handle_trigger(fx, "standing-only")
            r2 = ia.handle_trigger(fx, "standing-only")
            act1 = json.dumps((r1.get("actuation") or {}).get("stub_calls"),
                              sort_keys=True)
            act2 = json.dumps((r2.get("actuation") or {}).get("stub_calls"),
                              sort_keys=True)
            if act1 != act2:
                return {"probe_id": "P-D3-replay", "passed": False,
                        "evidence": evidence + ["double-trigger actuation differs"]}
            evidence.append("double-trigger identical actuation")
        # Self-correction terminates (bounded).
        if self.plan.actuation.feedback_loop:
            iters, _ = self._self_correction_loop()
            if iters > 3:
                return {"probe_id": "P-D3-replay", "passed": False,
                        "evidence": evidence + [f"self-correction unbounded: {iters}"]}
            evidence.append(f"self-correction terminates after {iters}")
        else:
            evidence.append("self-correction not declared: no loop asserted")
        return {"probe_id": "P-D3-replay", "passed": True, "evidence": evidence}

    def _probe_d2(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        fixtures = [f for f in standard_fixtures(self.plan)
                    if f.fixture_id.startswith("conflict-")][:3]
        rule = self._tie_break
        winners: list[str] = []
        for fx in fixtures:
            res = self.handle_trigger(fx, "standing-only")
            winner = res.get("conflict_resolution")
            winners.append(winner)
            expected = {"principal_wins_ties": "principal",
                        "world_wins_ties": "world"}[rule]
            evidence.append(f"{fx.fixture_id}: winner={winner} rule={rule}")
            if winner != expected:
                return {"probe_id": "P-D2-fidelity", "passed": False,
                        "evidence": evidence}
        # The dsys audit: principal and world never BOTH win when one rule governs.
        if rule == "principal_wins_ties" and "world" in winners:
            return {"probe_id": "P-D2-fidelity", "passed": False,
                    "evidence": evidence + ["world won under principal_wins_ties"]}
        if rule == "world_wins_ties" and "principal" in winners:
            return {"probe_id": "P-D2-fidelity", "passed": False,
                    "evidence": evidence + ["principal won under world_wins_ties"]}
        return {"probe_id": "P-D2-fidelity", "passed": True, "evidence": evidence}

    def _probe_q2(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        allowlist = self.plan.tool_bindings.write_allowlist
        if not allowlist:
            return {"probe_id": "P-Q2-routing", "passed": True,
                    "evidence": ["no write tools: vacuous"]}
        tid = allowlist[0]
        # Single bound effect -> direct call.
        direct_fx = {"tool_id": tid, "args": {"q2": "direct"},
                     "args_bound": True,
                     "args_provenance": "disposition-record",
                     "depends_on_prior": False, "interstep_guard": False}
        before = len(self.stubs[tid].calls)
        act = self._execute_effects([direct_fx])
        if act["route"] != "direct" or len(self.stubs[tid].calls) != before + 1:
            return {"probe_id": "P-Q2-routing", "passed": False,
                    "evidence": evidence + ["single bound effect not direct"]}
        evidence.append("single bound effect -> direct tool call")
        # Multi-step / guarded -> governed flow drafted, staged, never executed.
        before = len(self.stubs[tid].calls)
        multi = [dict(direct_fx, args={"q2": "step1"}),
                 {"tool_id": tid, "args": {"q2": "step2"},
                  "args_bound": True,
                  "args_provenance": "prior-tool-result",  # dependency -> workflow
                  "depends_on_prior": True, "interstep_guard": False}]
        act = self._execute_effects(multi)
        if act["route"] != "workflow" or not act["flow_drafted"]:
            return {"probe_id": "P-Q2-routing", "passed": False,
                    "evidence": evidence + ["multi-step not routed to workflow"]}
        if len(self.stubs[tid].calls) != before:
            return {"probe_id": "P-Q2-routing", "passed": False,
                    "evidence": evidence + ["workflow steps executed (forbidden)"]}
        staged = self.drafted_flow_proposals
        if not staged or self.staging.get(staged[-1]) is None:
            return {"probe_id": "P-Q2-routing", "passed": False,
                    "evidence": evidence + ["flow draft not staged"]}
        evidence.append("multi-step -> flow drafted+staged, never executed")
        # Standing action with undeclared tools -> runtime classification.
        novel = {"tool_id": tid, "args": {"q2": "novel"},
                 "args_bound": True,
                 "args_provenance": "disposition-record",
                 "depends_on_prior": False, "interstep_guard": False}
        act = self._execute_effects([novel])
        if act["route"] != "direct":
            return {"probe_id": "P-Q2-routing", "passed": False,
                    "evidence": evidence + ["novel-action runtime classification failed"]}
        evidence.append("novel action classified at runtime")
        # Standing-class multi-step via the real pipeline: unseen flow
        # structure is never pre-authorized (compiler spec §5) — it must
        # route to workflow (drafted+staged, never executed) even when the
        # class carries a standing disposition.
        standing = self.plan.actuation.standing_table
        if standing and "operator" in self.wirings:
            before = len(self.stubs[tid].calls)
            fx = ProbeFixture(fixture_id="pq2-standing-multi", source="operator",
                              event_id="ev-pq2-standing-multi",
                              session_authenticated=True,
                              proposed_action={
                                  "action_class": standing[0],
                                  "effects": multi,
                                  "args_provenance": "disposition-record"})
            res = self.handle_trigger(fx, "approve-all")
            act = res.get("actuation") or {}
            if (act.get("route") != "workflow" or not act.get("flow_drafted")
                    or len(self.stubs[tid].calls) != before):
                return {"probe_id": "P-Q2-routing", "passed": False,
                        "evidence": evidence + [
                            "standing-class multi-step not routed to "
                            f"workflow (route={act.get('route')})"]}
            evidence.append("standing-class multi-step -> workflow "
                            "(unseen flow never pre-authorized)")
        return {"probe_id": "P-Q2-routing", "passed": True, "evidence": evidence}

    def _probe_c1(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        if "event" not in self.plan.instrumentation.streams:
            # No event stream declared: there is no trace to be complete.
            # (Same standing as P-D4: probes test declared machinery.)
            return {"probe_id": "P-C1-trace", "passed": True,
                    "evidence": ["no event stream declared: vacuous"]}
        fx = ProbeFixture(
            fixture_id="pc1", source="operator", event_id="ev-pc1",
            session_authenticated=True,
            proposed_action={"action_class": "c1-probe",
                             "effects": [{"tool_id": tid, "args": {"c1": 1},
                                          "args_bound": True,
                                          "args_provenance": "disposition-record",
                                          "depends_on_prior": False,
                                          "interstep_guard": False}
                                         for tid in
                                         self.plan.tool_bindings.write_allowlist[:1]],
                             "args_provenance": "disposition-record"})
        if "operator" not in self.wirings:
            return {"probe_id": "P-C1-trace", "passed": True,
                    "evidence": ["no operator source: vacuous"]}
        res = self.handle_trigger(fx, "approve-all")
        records = [r for r in self.event_log.read("event")
                   if r.payload.get("event_id") == "ev-pc1"
                   or r.payload.get("kind") == "actuation"]
        if not records:
            return {"probe_id": "P-C1-trace", "passed": False,
                    "evidence": ["no event records for per-event actuation"]}
        evidence.append(f"C1: {len(records)} event records for per-event actuation")
        return {"probe_id": "P-C1-trace", "passed": True, "evidence": evidence}

    def _probe_c3(self, _arg: Any) -> dict[str, Any]:
        evidence: list[str] = []
        fx = ProbeFixture(fixture_id="pc3", source="operator", event_id="ev-pc3",
                          session_authenticated=True)
        if "operator" in self.wirings:
            self.handle_trigger(fx, "standing-only")
        verifier = self.verifiers.get("event")
        if verifier is None:
            return {"probe_id": "P-C3-integrity", "passed": True,
                    "evidence": ["no event verifier: vacuous"]}
        ok = verifier.check({"event_log": self.event_log})
        if not ok.passed:
            return {"probe_id": "P-C3-integrity", "passed": False,
                    "evidence": ["intact log failed verification"]}
        evidence.append("intact log verifies")
        # Tamper, then confirm detection.
        if self.event_log._records:
            original = self._tamper_event_log()
            try:
                tampered = verifier.check({"event_log": self.event_log})
            finally:
                self._restore_event_log(original)
            if tampered.passed:
                return {"probe_id": "P-C3-integrity", "passed": False,
                        "evidence": evidence + ["tampered log not detected"]}
            evidence.append("tampered log detected")
        else:
            evidence.append("empty log: tamper case vacuous")
        return {"probe_id": "P-C3-integrity", "passed": True, "evidence": evidence}


PROBE_IDS = ("P-D6-trigger", "P-D5-scope", "P-D1-disposition", "P-D7-boundary",
             "P-D4-trace", "P-D3-replay", "P-D2-fidelity", "P-Q2-routing",
             "P-C1-trace", "P-C3-integrity")


def run_probes(plan: AgentBuildPlan, profile: AgentBehaviorProfile,
               staging_root: str | Path,
               probe_ids: Iterable[str] = PROBE_IDS) -> tuple[list[dict[str, Any]],
                                                             PlanInterpreter]:
    """Run the probe battery; one interpreter per run (fresh state)."""
    interp = PlanInterpreter(plan, profile, staging_root)
    results: list[dict[str, Any]] = []
    for pid in probe_ids:
        try:
            results.append(interp.probe(pid))
        except VerifierMalfunction:
            raise
        except Exception as e:  # probe harness malfunction -> failed verdict
            raise VerifierMalfunction(f"probe {pid} malfunction: {e}") from e
    return results, interp


# ---------------------------------------------------------------------------
# Static checks S1-S5
# ---------------------------------------------------------------------------

def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check_id": check_id, "passed": passed, "detail": detail}


def static_s1(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S1: recompute D1/D3/D4/D5/D7 positions from the profile facets.

    Calls the ``agent_behavior`` derivation functions directly — the single
    source of truth (verifier spec §2: do not duplicate formulas).
    """
    plan = artifact.plan
    d1, d3, d4 = (profile.d1_authority, profile.d3_reproducibility,
                  profile.d4_observability)
    d5, d7 = profile.d5_scope, profile.d7_verification
    recomputed = {
        "D1": derive_d1_position(d1.per_event_disposition,
                                 d1.standing_dispositions,
                                 d1.self_correction, d1.self_planning),
        "D3": derive_d3_position(d3.deterministic_execution,
                                 d3.replay_supported),
        "D4": derive_d4_position(d4.records_events, d4.records_intents,
                                 d4.records_verifications),
        "D5": derive_d5_position(d5.write_scope),
        "D7": derive_d7_position(d7.intent_target, d7.event_target,
                                 d7.world_target, d7.trigger_target),
    }
    out: list[dict[str, Any]] = []
    for dim, value in recomputed.items():
        ok = plan.derived_positions.get(dim) == value
        out.append(_check(f"S1-{dim}", ok,
                          f"plan={plan.derived_positions.get(dim)} recomputed={value}"))
    # D2: the binary enum (DR-CMD-077) — the plan records the rule, and the
    # profile's rule must match; C6 retired with the scalar.
    out.append(_check("S1-D2", plan.derived_positions.get("D2")
                      == profile.d2_fidelity.conflict_rule
                      and profile.d2_fidelity.conflict_rule
                      in ("principal_wins_ties", "world_wins_ties"),
                      f"recorded D2={plan.derived_positions.get('D2')}"))
    return out


def static_s2(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S2: revalidate the profile (C1-C5, C7); catch skew."""
    out: list[dict[str, Any]] = []
    try:
        AgentBehaviorProfile.model_validate(profile.model_dump(mode="json"))
        out.append(_check("S2-revalidate", True, "profile revalidates (C1-C5, C7)"))
    except Exception as e:
        out.append(_check("S2-revalidate", False, f"profile fails revalidation: {e}"))
    plan = artifact.plan
    # D6/D4 coupling spot checks (validators already enforce; re-asserted).
    out.append(_check("S2-d6-backend", bool(plan.backend_binding.model_pin),
                      "empty model pin" if not plan.backend_binding.model_pin
                      else f"model_pin={plan.backend_binding.model_pin}"))
    # D5 write-scope channels all resolve (recomputed; the plan stores only
    # the expanded allowlist, per the closed-registry discipline).
    unresolved = []
    for c in profile.d5_scope.write_scope:
        try:
            resolve_channel(c)
        except CompileRefused:
            unresolved.append(c)
    out.append(_check("S2-d5-channels", not unresolved,
                      f"unresolvable channels: {unresolved}" if unresolved
                      else "all write-scope channels resolve"))
    return out


def static_s3(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S3: wiring completeness — exact source-set match + exact allowlist expansion."""
    plan = artifact.plan
    out: list[dict[str, Any]] = []
    declared = {s.value for s in profile.d6_initiative.sources}
    wired = {w.source for w in plan.trigger_wiring}
    out.append(_check("S3-sources", declared == wired,
                      f"declared={sorted(declared)} wired={sorted(wired)}"))
    for w in plan.trigger_wiring:
        out.append(_check(f"S3-gate-{w.source}", bool(w.activation_gate),
                          "empty activation gate" if not w.activation_gate else "ok"))
        out.append(_check(f"S3-auth-{w.source}", bool(w.authorization),
                          "empty authorization" if not w.authorization else "ok"))
    expected_allowlist: list[str] = []
    for channel in profile.d5_scope.write_scope:
        try:
            for tid in resolve_channel(channel):
                if tid not in expected_allowlist:
                    expected_allowlist.append(tid)
        except CompileRefused as e:
            out.append(_check("S3-allowlist", False, f"channel resolution refused: {e}"))
            return out
    actual = plan.tool_bindings.write_allowlist
    out.append(_check("S3-allowlist", actual == expected_allowlist,
                      f"actual={actual} expected={expected_allowlist}"))
    out.append(_check("S3-read-grants",
                      plan.tool_bindings.read_grants == profile.d5_scope.read_scope,
                      f"read_grants={plan.tool_bindings.read_grants}"))
    for name, flag in (("intent", profile.d7_verification.intent_target),
                       ("event", profile.d7_verification.event_target),
                       ("world", profile.d7_verification.world_target),
                       ("trigger", profile.d7_verification.trigger_target)):
        if not flag:
            continue
        v = next((x for x in plan.verifiers if x.target == name), None)
        out.append(_check(f"S3-verifier-{name}", v is not None,
                          "missing verifier plan" if v is None else
                          f"placement={v.placement} on_failure={v.on_failure}"))
    return out


def static_s4(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S4: routing well-formedness — every entry recomputed with the compiler."""
    plan = artifact.plan
    out: list[dict[str, Any]] = []
    by_class = {r.action_class: r for r in plan.actuation.routing}
    for cls in plan.actuation.standing_table:
        expected = classify_standing_class(cls)
        actual = by_class.get(cls)
        ok = (actual is not None and actual.route == expected.route
              and actual.bound_tools == expected.bound_tools)
        out.append(_check(f"S4-standing-{cls}", ok,
                          f"route={actual.route if actual else None} "
                          f"expected={expected.route}" if not ok else "ok"))
    for channel in profile.d5_scope.write_scope:
        entry = by_class.get(channel)
        try:
            tids = resolve_channel(channel)
        except CompileRefused:
            out.append(_check(f"S4-channel-{channel}", False, "refused"))
            continue
        expected_route = "workflow" if len(tids) > 1 else "direct"
        ok = (entry is not None and entry.route == expected_route
              and entry.bound_tools == tids)
        out.append(_check(f"S4-channel-{channel}", ok,
                          f"route={entry.route if entry else None} "
                          f"expected={expected_route}" if not ok else "ok"))
    for r in plan.actuation.routing:
        if r.route == "direct" and len(r.bound_tools) != 1:
            out.append(_check(f"S4-shape-{r.action_class}", False,
                              "direct route with != 1 bound tool"))
        if r.route == "workflow" and len(r.bound_tools) < 2 and not r.note:
            out.append(_check(f"S4-shape-{r.action_class}", False,
                              "workflow route without tools or note"))
    if not any(c["check_id"].startswith("S4-shape") and not c["passed"] for c in out):
        out.append(_check("S4-shape", True, "all routing entries well-formed"))
    return out


def static_s5(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S5: advisories — warnings recorded, never failures."""
    out = [_check("S5-advisories", True, "advisories are informational only")]
    for w in profile.warnings():
        out.append({"check_id": "S5-advisory", "passed": True, "detail": w})
    return out


def static_s6(artifact: AgentArtifact, profile: AgentBehaviorProfile) -> list[dict[str, Any]]:
    """S6: personalization integrity (DR-CMD-070).

    The manifest's personalization section is hash-covered, so an
    undisclosed mutation already fails ingest (artifact hash mismatch).
    S6 checks the section is *truthful*: present iff the profile is bound,
    principal ids agree, and bindings_hash recomputes from the profile's
    effective PERSONAL/BUILD field values (single source:
    personalization_bindings_hash). A disclosed re-binding is a new build,
    not a mutation — it re-mints and re-verifies.
    """
    out: list[dict[str, Any]] = []
    section = artifact.manifest.personalization
    bound = profile.personalization
    out.append(_check("S6-section", (section is None) == (bound is None),
                      "section/profile binding consistent"
                      if (section is None) == (bound is None)
                      else "manifest section and profile binding disagree"))
    if section is None or bound is None:
        return out
    out.append(_check("S6-principal", section.principal_id == bound.principal_id,
                      f"principal_id={section.principal_id}"))
    out.append(_check(
        "S6-bindings-hash",
        section.bindings_hash == personalization_bindings_hash(profile),
        "bindings_hash recomputes from profile PERSONAL/BUILD fields"
        if section.bindings_hash == personalization_bindings_hash(profile)
        else "bindings_hash does not match profile PERSONAL/BUILD fields"))
    out.append(_check("S6-disposition-ref", bool(section.disposition_ref),
                      "disposition_ref recorded"
                      if section.disposition_ref else
                      "disposition_ref empty: binding without a recorded "
                      "principal disposition"))
    return out


# ---------------------------------------------------------------------------
# verify()
# ---------------------------------------------------------------------------

def _plan_canonical_bytes(plan: AgentBuildPlan) -> bytes:
    """Byte-identical to the compiler's ``_plan_canonical``."""
    data = plan.model_dump(mode="json")
    data.pop("plan_hash", None)
    return _canonical_json(data).encode("utf-8")


def _artifact_hash(artifact: AgentArtifact) -> str:
    """Recompute the compiler's artifact_hash formula exactly.

    ``sha256(canonical(manifest minus artifact_hash) + plan_bytes)`` —
    mirrors ``tool_mint_manifest``. Any formula drift here fails ingest
    loudly rather than passing quietly.
    """
    core = artifact.manifest.model_dump(mode="json")
    core.pop("artifact_hash", None)
    return hashlib.sha256(
        _canonical_json(core).encode("utf-8")
        + _plan_canonical_bytes(artifact.plan)).hexdigest()


def verify(artifact: AgentArtifact, profile: AgentBehaviorProfile,
           staging_root: str | Path | None = None) -> VerdictRecord:
    """Verify one artifact against its source profile.

    Returns a VerdictRecord; raises nothing except VerifierMalfunction-derived
    ``failed`` records (never raised — returned as verdict="failed").
    """
    factory_version = artifact.manifest.factory_version
    profile_hash = hashlib.sha256(profile.canonical()).hexdigest()
    base = dict(
        artifact_hash=artifact.manifest.artifact_hash,
        profile_hash=profile_hash,
        factory_version=factory_version,
        probe_suite_version=PROBE_SUITE_VERSION,
        staging_durability="accretion-backed",
    )
    try:
        return _verify_inner(artifact, profile, profile_hash, base, staging_root)
    except VerifierMalfunction as e:
        return VerdictRecord(verdict="failed", static_results=[], probe_results=[],
                             evidence=[], operable=False,
                             failure_reason=f"verifier malfunction: {e}", **base)
    except Exception as e:  # any other internal error is also a malfunction
        return VerdictRecord(verdict="failed", static_results=[], probe_results=[],
                             evidence=[], operable=False,
                             failure_reason=f"verifier malfunction: {type(e).__name__}: {e}",
                             **base)


def _refused(reason: str, static_results: list, probe_results: list,
             advisories: list[str], evidence: list[str], base: dict) -> VerdictRecord:
    return VerdictRecord(verdict="refused", static_results=static_results,
                         probe_results=probe_results, advisories=advisories,
                         evidence=evidence + [f"refusal:{reason}"],
                         operable=False, **base)


def _verify_inner(artifact: AgentArtifact, profile: AgentBehaviorProfile,
                  profile_hash: str, base: dict,
                  staging_root: str | Path | None) -> VerdictRecord:
    static_results: list[dict[str, Any]] = []
    probe_results: list[dict[str, Any]] = []
    evidence: list[str] = []

    # -- ingesting: hash discipline (tamper on parseable input -> refused) --
    if artifact.manifest.profile_hash != profile_hash:
        return _refused("profile/artifact hash mismatch", static_results,
                        probe_results, [], evidence, base)
    recomputed_plan_hash = hashlib.sha256(
        _plan_canonical_bytes(artifact.plan)).hexdigest()
    if recomputed_plan_hash != artifact.plan.plan_hash:
        return _refused("plan canonical hash mismatch", static_results,
                        probe_results, [], evidence, base)
    if _artifact_hash(artifact) != artifact.manifest.artifact_hash:
        return _refused("artifact hash mismatch", static_results,
                        probe_results, [], evidence, base)
    evidence.append("ingest: hashes verified")

    # -- static --
    for check in (static_s1, static_s2, static_s3, static_s4, static_s5,
                  static_s6):
        try:
            static_results.extend(check(artifact, profile))
        except VerifierMalfunction:
            raise
        except Exception as e:
            raise VerifierMalfunction(f"{check.__name__}: {e}") from e
    evidence.extend(f"static:{r['check_id']}" for r in static_results)
    advisories = [r["detail"] for r in static_results
                  if r["check_id"] == "S5-advisory"]
    static_failures = [r for r in static_results if not r["passed"]]

    # -- probing (runs even when static failed, to collect full evidence) --
    root = Path(staging_root) if staging_root else Path(tempfile.mkdtemp(
        prefix="verifier-probes-"))
    probe_results, _interp = run_probes(artifact.plan, profile, root)
    evidence.extend(f"probe:{r['probe_id']}" for r in probe_results)
    probe_failures = [r for r in probe_results if not r["passed"]]

    # -- checking --
    if static_failures or probe_failures:
        reasons = ([r["check_id"] for r in static_failures]
                   + [r["probe_id"] for r in probe_failures])
        return _refused("static/probe failures: " + ",".join(reasons),
                        static_results, probe_results, advisories, evidence, base)

    # -- attesting --
    return VerdictRecord(verdict="verified", static_results=static_results,
                         probe_results=probe_results, advisories=advisories,
                         evidence=evidence, operable=True, **base)


# ---------------------------------------------------------------------------
# Verifier pipeline flow tools (thin delegating stage functions)
# ---------------------------------------------------------------------------

def tool_load_artifact(payload: dict) -> dict:
    """rb-verifier-ingest: verify hash discipline over the artifact."""
    artifact: AgentArtifact = payload["artifact"]
    profile: AgentBehaviorProfile = payload["profile"]
    profile_hash = hashlib.sha256(profile.canonical()).hexdigest()
    checks = {
        "profile_hash_match": artifact.manifest.profile_hash == profile_hash,
        "plan_hash_match": hashlib.sha256(
            _plan_canonical_bytes(artifact.plan)).hexdigest()
            == artifact.plan.plan_hash,
        "artifact_hash_match": _artifact_hash(artifact) == artifact.manifest.artifact_hash,
    }
    return {"hashes_match": all(checks.values()), "checks": checks}


def tool_recompute_positions(payload: dict) -> dict:
    return {"results": static_s1(payload["artifact"], payload["profile"])}


def tool_recheck_couplings(payload: dict) -> dict:
    return {"results": static_s2(payload["artifact"], payload["profile"])}


def tool_check_wiring(payload: dict) -> dict:
    return {"results": static_s3(payload["artifact"], payload["profile"])
            + static_s4(payload["artifact"], payload["profile"])
            + static_s5(payload["artifact"], payload["profile"])
            + static_s6(payload["artifact"], payload["profile"])}


def tool_run_probe(payload: dict) -> dict:
    plan: AgentBuildPlan = payload["plan"]
    profile: AgentBehaviorProfile = payload["profile"]
    root = Path(payload.get("staging_root") or tempfile.mkdtemp(prefix="verifier-probe-"))
    results, _ = run_probes(plan, profile, root, [payload["probe_id"]])
    return {"results": results}


def tool_aggregate_verdict(payload: dict) -> dict:
    static_results: list = payload["static_results"]
    probe_results: list = payload["probe_results"]
    failures = [r for r in static_results + probe_results if not r["passed"]]
    verdict = "refused" if failures else "verified"
    return {"verdict": verdict,
            "failures": [r.get("check_id") or r.get("probe_id") for r in failures]}


def tool_mint_verdict_record(payload: dict) -> dict:
    record: VerdictRecord = payload["record"]
    return {"verdict": record.verdict, "operable": record.operable,
            "artifact_hash": record.artifact_hash}


VERIFIER_FLOW_TOOL_REGISTRY: dict[str, Callable] = {
    "tool-load-artifact": tool_load_artifact,
    "tool-recompute-positions": tool_recompute_positions,
    "tool-recheck-couplings": tool_recheck_couplings,
    "tool-check-wiring": tool_check_wiring,
    "tool-run-probe": tool_run_probe,
    "tool-aggregate-verdict": tool_aggregate_verdict,
    "tool-mint-verdict-record": tool_mint_verdict_record,
}


# ---------------------------------------------------------------------------
# Pydantic-source verifier pipeline -> AutomatonFlow (DR-CMD-064)
# ---------------------------------------------------------------------------

def _v_task(name: str, runbook_id: str) -> AutomatonState:
    return AutomatonState(name=name, kind="task", runbook_id=runbook_id,
                          step_policy="abort")


def _v_edge(frm: str, to: str, trigger: str = "run_completed",
            guard: str | None = None) -> AutomatonTransition:
    return AutomatonTransition(from_state=frm, trigger=trigger, guard=guard,
                               to_state=to)


AGENT_VERIFIER_FLOW = AutomatonSource(
    name="agent-verifier-flow",
    release_version=default_factory_version().factory_release,
    initial_state="ingesting",
    states=[
        _v_task("ingesting", "rb-verifier-ingest"),
        _v_task("static_checking", "rb-verifier-static"),
        _v_task("probing", "rb-verifier-probe"),
        _v_task("checking", "rb-verifier-check"),
        _v_task("attesting", "rb-verifier-attest"),
        AutomatonState(name="verified", kind="end", outcome="completed"),
        AutomatonState(name="refused", kind="end", outcome="completed"),
        AutomatonState(name="failed", kind="end", outcome="aborted"),
    ],
    transitions=[
        _v_edge("ingesting", "static_checking", guard="payload.hashes_match == True"),
        _v_edge("ingesting", "failed", trigger="run_aborted"),
        _v_edge("static_checking", "probing"),
        _v_edge("static_checking", "failed", trigger="run_aborted"),
        _v_edge("probing", "checking"),
        _v_edge("probing", "failed", trigger="run_aborted"),
        _v_edge("checking", "attesting"),
        _v_edge("checking", "failed", trigger="run_aborted"),
        _v_edge("attesting", "verified", guard="payload.verdict == 'verified'"),
        _v_edge("attesting", "refused", guard="payload.verdict == 'refused'"),
        _v_edge("attesting", "failed", trigger="run_aborted"),
    ],
    runbooks=[
        RunBookSource(id="rb-verifier-ingest", name="rb-verifier-ingest",
                      steps=[RunBookStepSource(tool_id="tool-load-artifact")]),
        RunBookSource(id="rb-verifier-static", name="rb-verifier-static",
                      steps=[
                          RunBookStepSource(tool_id="tool-recompute-positions"),
                          RunBookStepSource(tool_id="tool-recheck-couplings"),
                          RunBookStepSource(tool_id="tool-check-wiring"),
                      ]),
        RunBookSource(id="rb-verifier-probe", name="rb-verifier-probe",
                      steps=[RunBookStepSource(tool_id="tool-run-probe")]),
        RunBookSource(id="rb-verifier-check", name="rb-verifier-check",
                      steps=[RunBookStepSource(tool_id="tool-aggregate-verdict")]),
        RunBookSource(id="rb-verifier-attest", name="rb-verifier-attest",
                      steps=[RunBookStepSource(tool_id="tool-mint-verdict-record")]),
    ],
)


def compile_verifier_flow():
    """Bridge the verifier pipeline source to AutomatonFlow entities."""
    return bridge_compile(AGENT_VERIFIER_FLOW, VERIFIER_FLOW_TOOL_REGISTRY)
