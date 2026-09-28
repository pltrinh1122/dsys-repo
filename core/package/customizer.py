"""customizer — the customization-sequence agent (ambient-side, inference).

Role: when authoring detects a required artifact (schema, criteria,
contract) with no suitable instance in the artifact registry, the
customizer drafts the artifact and stages a CustomizationProposal —
the bridge envelope between authoring inference and factory mechanics.

The customizer PROPOSES. It never registers, never builds, never
disposes: D5 0.0 (empty write_scope), every D6 authorization stage-only.
Registration is the factory registry's mechanical channel, gated on an
operator-attributed adoption disposition; building is the factory
driver. Proposer != disposer, end to end.

Sequence (pre-delivery — the falsified "after Factory release" claim is
refused mechanically by artifact_registry.register):
  1. detect    — authoring assessment finds a required artifact class
                 with no suitable instance (inference; the ambient's job).
  2. prove     — registry lookup, computed evidence (mechanical).
  3. propose   — stage CustomizationProposal (this agent, stage-only).
  4. dispose   — operator adopts/amends/refuses, via the harness
                 (propose -> dispose is a harness turn, not a factory mode).
  5. register  — versioned, content-pinned, on the adoption disposition
                 (mechanical; artifact_registry).
  6. build     — the customized artifact enters the factory pipeline;
                 dependent agents author against the registered version.

Archetypes: staff + office. D6 {OPERATOR, AGENT}: invoked by the
operator directly, or by the author agent through the staging medium
(DR-CMD-078 stigmergic trigger — the author stages a
"customization-needed" state the customizer observes). D7 0.75
fail_closed: a proposal whose evidence doesn't check out is refused,
never staged on a caveat.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

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


def customizer_profile() -> AgentBehaviorProfile:
    """cognitive-assist / customizer: draft missing artifacts, stage proposals.

    Stage-only drafter (J-A analog): proposals are staged for operator
    disposition; registration and build are factory mechanics the
    customizer can never invoke (empty write_scope, S2). Principal-wins-ties:
    drafted artifacts track the principal's intent.
    """
    return AgentBehaviorProfile(
        agent="customizer",
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
            read_scope=["staging-area", "artifact-registry",
                        "disposition-records", "spec-library"],
            write_scope=[]),  # S2: proposals are staged, never effected
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR, TriggerSource.AGENT},
            gating={TriggerSource.OPERATOR: "authenticated-session",
                    TriggerSource.AGENT:
                        "staged customization-needed state, observed "
                        "through the staging medium (DR-CMD-078)"},
            authorization={TriggerSource.OPERATOR: "stage-only",
                           TriggerSource.AGENT: "stage-only; never register, "
                           "never build, never dispose"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


# ---------------------------------------------------------------------------
# The proposal envelope — the bridge contract between the customizer
# (inference) and the factory (mechanics). Everything the factory needs
# to verify, register, and build without re-inferring.
# ---------------------------------------------------------------------------

class RegistryEvidence(BaseModel):
    kind: Literal["schema", "criteria", "contract"]
    query: str
    hits: list[str] = Field(default_factory=list)


class CustomizationProposal(BaseModel):
    agent_name: str  # requesting agent, e.g. "email_ingest"
    artifact_kind: Literal["schema", "criteria", "contract"]
    artifact_name: str
    artifact_source: str  # the proposed bytes (JSON / pydantic source)
    rationale: str
    registry_evidence: RegistryEvidence
    compatibility: str  # downstream-consumer analysis: who else touches
    # this contract, and why the customization interoperates
    proposed_version: int = Field(ge=1)
    commission_id: str
    supersedes: str | None = None  # artifact NAME this version supersedes,
    # e.g. "matter-record" — set only when the registry already holds a
    # version that is unsuitable; the rationale must state the insufficiency


class ProposalViolation(Exception):
    """Fail-closed: every envelope refusal carries reasons."""


def validate_proposal_envelope(p: CustomizationProposal) -> dict:
    """Mechanical envelope validation (no inference).

    Refuses: empty artifact/rationale/compatibility; evidence with an
    empty query (unproven absence); evidence carrying hits (a suitable
    artifact EXISTS — prove-absence failed, no proposal needed);
    evidence kind mismatching the artifact kind.
    """
    def bad(reason: str) -> ProposalViolation:
        return ProposalViolation(reason)

    if not p.agent_name.strip():
        raise bad("agent_name required: who requested this customization")
    if not p.artifact_name.strip():
        raise bad("artifact_name required")
    if not p.artifact_source.strip():
        raise bad("artifact_source empty: a proposal customizes bytes, "
                  "not wishes")
    if not p.rationale.strip():
        raise bad("rationale required (G4: every authored artifact states "
                  "its reason)")
    if not p.compatibility.strip():
        raise bad("compatibility analysis required: a customized contract "
                  "has downstream consumers; name them")
    ev = p.registry_evidence
    if not ev.query.strip():
        raise bad("registry evidence has no query: absence unproven")
    if ev.kind != p.artifact_kind:
        raise bad(f"evidence kind {ev.kind!r} != artifact kind "
                  f"{p.artifact_kind!r}")
    if ev.hits and p.supersedes is None:
        raise bad(f"prove-absence failed: registry already holds "
                  f"{ev.hits} for query {ev.query!r} — no customization "
                  f"needed; author against the registered artifact, or set "
                  f"supersedes to version it with a stated insufficiency")
    if p.supersedes is not None and p.supersedes not in ev.hits:
        raise bad(f"supersedes={p.supersedes!r} names an artifact absent "
                  f"from the evidence hits {ev.hits}: version what exists, "
                  f"not what doesn't")
    if not p.commission_id.strip():
        raise bad("commission_id required")
    sha = hashlib.sha256(p.artifact_source.encode("utf-8")).hexdigest()
    return {"envelope": "valid", "artifact_sha256": sha,
            "artifact_bytes": len(p.artifact_source.encode("utf-8"))}


def diagnostic_cases():
    """J2 self-diagnostics for the customizer agent and its envelope."""
    from core.package import artifact_registry as reg
    import tempfile

    def _proposal(**kw):
        base = dict(
            agent_name="email_ingest", artifact_kind="schema",
            artifact_name="matter-record", artifact_source='{"a": 1}',
            rationale="no matter schema exists", compatibility="downstream: "
            "disposition machinery; v1 is additive, no consumer breaks",
            proposed_version=1, commission_id="commission-0001",
            registry_evidence=RegistryEvidence(
                kind="schema", query="matter", hits=[]))
        base.update(kw)
        return CustomizationProposal(**base)

    def e_c1_profile_conforms(ctx):
        from core.package.factory_archetypes import check_profile
        vs = check_profile(customizer_profile(), list(ARCHETYPES))
        return not vs, f"violations={vs}"

    def e_c2_stage_only(ctx):
        p = customizer_profile()
        ok = (p.d5_scope.write_scope == []
              and all("stage-only" in a
                      for a in p.d6_initiative.authorization.values()))
        return ok, f"write_scope={p.d5_scope.write_scope}"

    def e_c3_envelope_valid(ctx):
        try:
            s = validate_proposal_envelope(_proposal())
        except ProposalViolation as e:
            return False, str(e)
        return True, f"sha={s['artifact_sha256'][:12]}"

    def e_c4_refuse_empty_evidence_query(ctx):
        pr = _proposal(registry_evidence=RegistryEvidence(
            kind="schema", query="  ", hits=[]))
        try:
            validate_proposal_envelope(pr)
        except ProposalViolation as e:
            return True, f"refused: {e}"
        return False, "accepted an unproven absence"

    def e_c5_refuse_when_artifact_exists(ctx):
        pr = _proposal(registry_evidence=RegistryEvidence(
            kind="schema", query="matter", hits=["matter-record"]))
        try:
            validate_proposal_envelope(pr)
        except ProposalViolation as e:
            return True, f"refused: {e}"
        return False, "proposed despite a registered artifact"

    def e_c6_refuse_empty_rationale(ctx):
        pr = _proposal(rationale="  ")
        try:
            validate_proposal_envelope(pr)
        except ProposalViolation as e:
            return True, f"refused: {e}"
        return False, "accepted a reasonless proposal"

    def e_c7_registry_roundtrip(ctx):
        import tempfile
        _td = tempfile.TemporaryDirectory()
        ctx["_td"] = _td  # keep alive for the case duration
        root = Path(_td.name)
        rec = reg.register(
            root, kind="schema", name="matter-record",
            artifact_bytes=b'{"a": 1}', producer="customizer",
            commission_id="commission-0001",
            disposition_ref="op-adopt-001")
        ev = reg.absence_evidence(root, "schema", "matter")
        ok = (rec.version == 1 and rec.sha256 ==
              hashlib.sha256(b'{"a": 1}').hexdigest()
              and ev["hits"] == ["matter-record"])
        return ok, f"v={rec.version} hits={ev['hits']}"

    def e_c8_refuse_duplicate_registration(ctx):
        import tempfile
        _td = tempfile.TemporaryDirectory()
        ctx["_td"] = _td  # keep alive for the case duration
        root = Path(_td.name)
        reg.register(root, kind="schema", name="dup",
                     artifact_bytes=b'{"a": 1}', producer="customizer",
                     commission_id="commission-0001",
                     disposition_ref="op-adopt-001")
        try:
            reg.register(root, kind="schema", name="dup",
                         artifact_bytes=b'{"a": 1}', producer="customizer",
                         commission_id="commission-0002",
                         disposition_ref="op-adopt-002")
        except reg.RegistryError as e:
            return True, f"refused: {e}"
        return False, "registered identical bytes twice"

    def e_c9_version_bump_not_overwrite(ctx):
        import tempfile
        _td = tempfile.TemporaryDirectory()
        ctx["_td"] = _td  # keep alive for the case duration
        root = Path(_td.name)
        reg.register(root, kind="schema", name="bump",
                     artifact_bytes=b'{"a": 1}', producer="customizer",
                     commission_id="commission-0001",
                     disposition_ref="op-adopt-001")
        rec = reg.register(root, kind="schema", name="bump",
                           artifact_bytes=b'{"a": 2}', producer="customizer",
                           commission_id="commission-0002",
                           disposition_ref="op-adopt-002")
        ok = rec.version == 2
        return ok, f"v={rec.version}"

    def e_c10_refuse_post_release_customization(ctx):
        # The falsified claim, made mechanical: customizing a delivered
        # artifact under its ORIGINAL commission is refused; a new
        # commission (new authoring cycle) is the only path to v2.
        import tempfile
        _td = tempfile.TemporaryDirectory()
        ctx["_td"] = _td  # keep alive for the case duration
        root = Path(_td.name)
        reg.register(root, kind="schema", name="postrel",
                     artifact_bytes=b'{"a": 1}', producer="customizer",
                     commission_id="commission-0001",
                     disposition_ref="op-adopt-001")
        try:
            reg.register(root, kind="schema", name="postrel",
                         artifact_bytes=b'{"a": 9}', producer="customizer",
                         commission_id="commission-0001",
                         disposition_ref="op-adopt-003")
        except reg.RegistryError as e:
            return True, f"refused: {e}"
        return False, "post-release customization under the original " \
                      "commission was allowed"

    def e_c11_supersede_path_versions_honestly(ctx):
        # A versioned customization names the registered artifact it
        # supersedes (with a stated insufficiency in rationale); the
        # envelope refuses a supersede of something not in evidence.
        pr = _proposal(
            registry_evidence=RegistryEvidence(
                kind="schema", query="matter", hits=["matter-record"]),
            supersedes="matter-record", proposed_version=2,
            rationale="v1 lacks the source field consumers need")
        try:
            validate_proposal_envelope(pr)
        except ProposalViolation as e:
            return False, f"honest supersede refused: {e}"
        bad = _proposal(
            registry_evidence=RegistryEvidence(
                kind="schema", query="matter", hits=["matter-record"]),
            supersedes="ghost-artifact", proposed_version=2)
        try:
            validate_proposal_envelope(bad)
        except ProposalViolation:
            return True, "honest supersede accepted; phantom refused"
        return False, "supersede of a non-evident artifact accepted"

    return [("E-C1", e_c1_profile_conforms),
            ("E-C2", e_c2_stage_only),
            ("E-C3", e_c3_envelope_valid),
            ("E-C4", e_c4_refuse_empty_evidence_query),
            ("E-C5", e_c5_refuse_when_artifact_exists),
            ("E-C6", e_c6_refuse_empty_rationale),
            ("E-C7", e_c7_registry_roundtrip),
            ("E-C8", e_c8_refuse_duplicate_registration),
            ("E-C9", e_c9_version_bump_not_overwrite),
            ("E-C10", e_c10_refuse_post_release_customization),
            ("E-C11", e_c11_supersede_path_versions_honestly)]
