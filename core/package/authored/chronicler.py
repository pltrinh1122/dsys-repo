"""chronicler — may-act decision-record registrar (DR-CMD-107;
renamed from dr_registrar, DR-CMD-100).

The dog-food clerk: the agent that governs Decision Records themselves —
the D1-D7 architecture's own governance memory. Peter rendered "proceed
with `decision-record registrar` agent" (~18:29 PDT 2026-09-27) on the
suggestion that the exemplar clerk should be needed for our designing,
authoring, and building work. Ninety-nine DRs in, the next-free
identifier chain is still hand-maintained in every record; the failure
modes are real, frequent, and mechanical — duplicate identifiers,
skipped numbers, malformed records, dangling premise links, addenda
applied to nonexistent records.

Role: on the operator's schedule (standing disposition; arrivals never
trigger it — CL4), sweep the staged DR drafts; vet each draft against
the commissioned mechanical criteria (DR-CMD-099's five checks,
adopted-as-set); register the well-formed records append-only; defer
the malformed ones for operator disposition (proposer != disposer
preserved for the ambiguous middle). The standing disposition
pre-authorizes the vetting-and-registration classes, not per-event
outcomes.

What it reads (office): staged DR drafts (presented markdown) plus the
existing doc/decision-records/ directory as presented material to
compute the registry tip — next expected number, registered
identifiers, registered content-hashes, reservations. It never
investigates the world; a DR's *truth* is the operator's disposition,
not an external fact.

Why this agent and not the alternatives: profile-conformance is already
gated mechanically inside every set run (no judgment left for an
agent); spec/glossary linting is script territory (no agency). The DR
registrar exercises bounded judgment — sequence integrity, reference
resolution — that is genuinely office work, at the highest frequency of
anything the architecture's authoring loop does, and its failure mode
(a broken decision chain) damages governance directly.

Archetype: clerk (may-act x office). D6 {OPERATOR} only: no WORLD,
AGENT, or SELF triggers. D2 principal_wins_ties: the commissioned
vetting criteria bind; presented bytes never win ties.

AS-BUILT DEVIATION (DR-CMD-100, still open at DR-CMD-107):
write_scope=["decision-record-registry"] names the true effect channel,
but the factory compiler's closed contracted-tool registry (J1,
DR-CMD-055/057) resolves write channels only against AGENT_TOOL_IDS /
CHANNEL_ALIASES — no contracted tool backs decision-record
registration today (tranche 2, DR-CMD-102, conditional). Compile
therefore refuses at the routing stage until a contracted tool exists
for this channel or the channel question is disposed (Peter).
Separately, the DR registry now exists as an adopted design
(doc/dr-registry-structure-design.md, DR-CMD-106: held, not built);
reading it as presented material needs no new infrastructure. The
profile is authored, validates, and passes the clerk gate; factory
registration (PROFILE_SET_002) is deferred pending the Operator's
disposition on the channel. No channel was silently substituted, no
tool was added to the pinned registry, the closed-registry discipline
was not amended, and no registry was built in this task.
"""

from __future__ import annotations

import hashlib
import re

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

ARCHETYPES = ("clerk",)


def chronicler_profile() -> AgentBehaviorProfile:
    """design/authoring-assist / chronicler: may-act DR registrar.

    Vets staged decision-record drafts against the commissioned
    mechanical criteria on the operator's schedule; registers the
    well-formed records append-only; defers the malformed for operator
    disposition. Reads staged drafts and the existing
    doc/decision-records/ directory as presented material only (office).
    """
    return AgentBehaviorProfile(
        agent="chronicler",
        d1_authority=D1Authority(
            position=0.5, per_event_disposition=False,
            standing_dispositions=["vet-and-register-dr-drafts-standing"],
            self_correction=False, self_planning=False),
        d2_fidelity=D2Fidelity(
            principal_precedence=["operator"],
            conflict_rule="principal_wins_ties"),
        d3_reproducibility=D3Reproducibility(
            position=0.0, deterministic_execution=True,
            replay_supported=True),
        d4_observability=D4Observability(
            position=1.0, records_events=True, records_intents=True,
            records_verifications=True,
            inspectors=["operator", "auditor"], retention="forever"),
        d5_scope=D5Scope(
            position=0.15,
            read_scope=["staging-area", "decision-records",
                        "disposition-records", "vetting-criteria"],
            # AS-BUILT DEVIATION: the true effect channel, but it
            # resolves against no contracted tool (see module docstring).
            # Bounded (one declared channel), never wildcard — CL3's
            # boundedness holds; J1 resolution does not.
            write_scope=["decision-record-registry"]),
        d6_initiative=D6Initiative(
            sources={TriggerSource.OPERATOR},
            gating={TriggerSource.OPERATOR: "authenticated-session"},
            authorization={TriggerSource.OPERATOR:
                           "may-act: vet staged DR drafts and register "
                           "well-formed records append-only on standing "
                           "disposition; pre-authorized-standing"}),
        d7_verification=D7Verification(
            position=0.75, intent_target=True, event_target=True,
            world_target=False, trigger_target=True,
            on_failure="fail_closed"),
    )


# The commissioned mechanical vetting criteria (DR-CMD-099, adopted as
# the set; content ratifiable/amendable by Peter). Ambiguous -> defer.
REQUIRED_SECTIONS = ("status", "date", "matter", "premises", "next-free")
ID_PATTERN = re.compile(r"^DR-CMD-(\d{3})$")


def dr_record_decision(draft: dict, tip: dict) -> tuple[str, dict]:
    """Pure DR vetting rule (office criteria; no world investigation).

    draft: {"id": "DR-CMD-100", "sections": {name: present-bool},
            "premise_refs": ["DR-CMD-094", ...],
            "supersedes": [...], "addendum_to": "DR-CMD-093" | None,
            "content_hash": str}
    tip:   {"next_number": int, "reserved": [int, ...],
            "registered_ids": [...], "registered_hashes": [...]}
    Returns ("record", {"reasons": [...]}) or ("defer", {"reasons": [...]}).
    Total: every draft maps to exactly one outcome, never silent. The
    malformed or ambiguous defers to operator disposition.
    """
    reasons: list[str] = []
    draft_id = draft.get("id") or ""
    m = ID_PATTERN.match(draft_id)
    if not m:
        return "defer", {"reasons": [f"identifier {draft_id!r} not "
                                     "well-formed (expected DR-CMD-###)"]}
    n = int(m.group(1))
    registered_ids = list(tip.get("registered_ids") or [])
    registered_hashes = list(tip.get("registered_hashes") or [])
    reserved = list(tip.get("reserved") or [])

    if draft_id in registered_ids:
        reasons.append(f"identifier {draft_id} already registered "
                       "(duplicate)")
    if n in reserved:
        reasons.append(f"number {n:03d} is reserved; registering it is "
                       "operator business, not standing business")
    next_number = tip.get("next_number")
    if next_number is not None and n != next_number:
        reasons.append(f"identifier {draft_id} is not next-in-sequence "
                       f"(registry tip expects DR-CMD-{next_number:03d}; "
                       "no gaps, no gap-fills, no duplicates)")

    sections = draft.get("sections") or {}
    missing = [s for s in REQUIRED_SECTIONS if not sections.get(s)]
    if missing:
        reasons.append(f"required sections missing: {missing}")

    for ref in draft.get("premise_refs") or []:
        if ref not in registered_ids:
            reasons.append(f"dangling premise ref {ref}: not in the "
                           "registry")
    for target in draft.get("supersedes") or []:
        if target not in registered_ids:
            reasons.append(f"supersedes target {target} not in the "
                           "registry")
    addendum_to = draft.get("addendum_to")
    if addendum_to and addendum_to not in registered_ids:
        reasons.append(f"addendum target {addendum_to} not in the "
                       "registry")

    content_hash = draft.get("content_hash") or ""
    if content_hash and content_hash in registered_hashes:
        reasons.append("content-hash already registered (duplicate "
                       "record under a new identifier)")

    if reasons:
        return "defer", {"reasons": reasons}
    return "record", {"reasons": [f"{draft_id} is next-in-sequence, "
                                  "well-formed, all refs resolve, "
                                  "content-hash unseen"]}


def _tip_fixture() -> dict:
    return {"next_number": 100,
            "reserved": [59],
            "registered_ids": ["DR-CMD-096", "DR-CMD-097", "DR-CMD-098",
                               "DR-CMD-099"],
            "registered_hashes": ["deadbeef01"]}


def _draft_fixture(**over) -> dict:
    d = {"id": "DR-CMD-100",
         "sections": {s: True for s in REQUIRED_SECTIONS},
         "premise_refs": ["DR-CMD-096"],
         "supersedes": [],
         "addendum_to": None,
         "content_hash": "feedface02"}
    d.update(over)
    return d


def diagnostic_cases():
    """The chronicler's self-diagnostic playbook (J2)."""

    def d_dr1_may_act_shape(ctx):
        p = ctx["profile"]
        a = p.d1_authority
        ok = (not a.per_event_disposition and a.position == 0.5
              and bool(a.standing_dispositions)
              and not a.self_correction and not a.self_planning)
        return ok, (f"per_event={a.per_event_disposition} "
                    f"position={a.position} "
                    f"standing={a.standing_dispositions}")

    def d_dr2_operator_only(ctx):
        p = ctx["profile"]
        d6 = p.d6_initiative
        want = {TriggerSource.OPERATOR}
        missing = [s for s in d6.sources
                   if s not in d6.gating or s not in d6.authorization]
        ok = set(d6.sources) == want and not missing
        return ok, (f"sources={sorted(s.name for s in d6.sources)} "
                    f"missing={missing}")

    def d_dr3_office_reading(ctx):
        p = ctx["profile"]
        v = p.d7_verification
        ok = (v.position == 0.75 and not v.world_target
              and v.intent_target and v.event_target and v.trigger_target
              and v.on_failure == "fail_closed")
        return ok, (f"D7={v.position} world_target={v.world_target} "
                    f"on_failure={v.on_failure}")

    def d_dr4_bounded_write_scope(ctx):
        p = ctx["profile"]
        s = p.d5_scope
        ok = (s.write_scope == ["decision-record-registry"]
              and s.position == 0.15
              and not any(w in {"unbounded", "open-ended", "*"}
                          for w in s.write_scope))
        return ok, f"write_scope={s.write_scope} position={s.position}"

    def d_dr5_principal_wins(ctx):
        p = ctx["profile"]
        ok = p.d2_fidelity.conflict_rule == "principal_wins_ties"
        return ok, f"conflict_rule={p.d2_fidelity.conflict_rule}"

    def _dec(name, draft, tip, want):
        outcome, detail = dr_record_decision(draft, tip)
        ok = outcome == want and bool(detail.get("reasons"))
        return ok, f"{name}: outcome={outcome} reasons={detail['reasons']}"

    def d_dr6_clean_next_in_sequence(ctx):
        mod = ctx["module"]
        return _dec("clean", mod._draft_fixture(), mod._tip_fixture(),
                    "record")

    def d_dr7_duplicate_identifier(ctx):
        mod = ctx["module"]
        return _dec("duplicate-id",
                    mod._draft_fixture(id="DR-CMD-098"),
                    mod._tip_fixture(), "defer")

    def d_dr8_skipped_number(ctx):
        mod = ctx["module"]
        return _dec("skipped",
                    mod._draft_fixture(id="DR-CMD-102"),
                    mod._tip_fixture(), "defer")

    def d_dr9_reserved_number_misuse(ctx):
        mod = ctx["module"]
        tip = mod._tip_fixture()
        tip["next_number"] = 59
        return _dec("reserved",
                    mod._draft_fixture(id="DR-CMD-059"), tip, "defer")

    def d_dr10_missing_sections(ctx):
        mod = ctx["module"]
        d = mod._draft_fixture()
        d["sections"] = {"status": True, "date": False, "matter": True,
                         "premises": False, "next-free": True}
        return _dec("missing-sections", d, mod._tip_fixture(), "defer")

    def d_dr11_dangling_premise_ref(ctx):
        mod = ctx["module"]
        return _dec("dangling-premise",
                    mod._draft_fixture(premise_refs=["DR-CMD-900"]),
                    mod._tip_fixture(), "defer")

    def d_dr12_addendum_to_nonexistent(ctx):
        mod = ctx["module"]
        return _dec("addendum-missing",
                    mod._draft_fixture(addendum_to="DR-CMD-900"),
                    mod._tip_fixture(), "defer")

    def d_dr13_duplicate_content_hash(ctx):
        mod = ctx["module"]
        return _dec("dup-hash",
                    mod._draft_fixture(content_hash="deadbeef01"),
                    mod._tip_fixture(), "defer")

    def d_dr14_malformed_identifier(ctx):
        mod = ctx["module"]
        return _dec("malformed-id",
                    mod._draft_fixture(id="DR100"),
                    mod._tip_fixture(), "defer")

    def d_dr15_artifact_fidelity(ctx):
        p, a = ctx["profile"], ctx["artifact"]
        expect = hashlib.sha256(p.canonical()).hexdigest()
        ok = a.manifest.profile_hash == expect
        return ok, f"profile_hash_match={ok}"

    return [("D-DR-1", d_dr1_may_act_shape),
            ("D-DR-2", d_dr2_operator_only),
            ("D-DR-3", d_dr3_office_reading),
            ("D-DR-4", d_dr4_bounded_write_scope),
            ("D-DR-5", d_dr5_principal_wins),
            ("D-DR-6", d_dr6_clean_next_in_sequence),
            ("D-DR-7", d_dr7_duplicate_identifier),
            ("D-DR-8", d_dr8_skipped_number),
            ("D-DR-9", d_dr9_reserved_number_misuse),
            ("D-DR-10", d_dr10_missing_sections),
            ("D-DR-11", d_dr11_dangling_premise_ref),
            ("D-DR-12", d_dr12_addendum_to_nonexistent),
            ("D-DR-13", d_dr13_duplicate_content_hash),
            ("D-DR-14", d_dr14_malformed_identifier),
            ("D-DR-15", d_dr15_artifact_fidelity)]
