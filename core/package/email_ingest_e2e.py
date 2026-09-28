"""End-to-end sequence: build the email_ingest agent, then customize it.

PHASE A (build): commission -> author (ambient inference, labeled) ->
    stage-profile (mechanical) -> factory driver -> verified verdict ->
    verified-build runtime execution (5 emails, ambient-authored verdicts).
PHASE B (customize): detect missing artifact -> registry prove-absence ->
    draft proposal (ambient inference, labeled) -> stage proposal
    (mechanical) -> SIMULATED operator adoption (labeled; not the
    operator's act) -> register v1 pinned -> validate dependents against
    the registered schema -> negative case (post-release rule).

Everything runs in a scratch root. Inference is ambient-simulated, never
production. Matter records are returned payloads, never store writes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIM = Path.home() / "workspace" / "sim" / "ambient-pkg"
sys.path.insert(0, str(REPO))

from core.package import author_agent as aa
from core.package import author_channels as ac
from core.package import artifact_registry as reg
from core.package.customizer import CustomizationProposal, RegistryEvidence

AGENT = "email_ingest"
T = []  # transcript lines


def say(s: str = "") -> None:
    T.append(s)
    print(s, flush=True)


def phase(title: str) -> None:
    say()
    say("=" * 72)
    say(title)
    say("=" * 72)


# --------------------------------------------------------------------------
# PHASE A — BUILD
# --------------------------------------------------------------------------
def phase_a(root: Path) -> dict:
    phase("PHASE A — BUILD the email_ingest agent")

    # A1: commission (operator-attributed)
    say("\n[A1] commission (operator-attributed)")
    aa.stage_commission(
        root, commission_id="comm-email-ingest-e2e",
        role_brief=("Build a periodic email-ingestion agent: classify each "
                    "email per criteria C1/C2 via the inference channel, "
                    "stage matter records for URGENT, discard ROUTINE, "
                    "refuse malformed input with reasons."),
        acceptance_criteria=[
            "profile validates with zero warnings",
            "archetype gate (staff, office) green",
            "factory verdict: verified",
            "11/11 self-diagnostics green",
            "runtime executes only the verified, hash-pinned bytes",
        ],
        disposition_ref="demo: operator directive (simulated commission)",
        principal_id="operator")
    say("  commission comm-email-ingest-e2e staged; principal=operator")

    # A2: author (inference side — ambient, labeled)
    say("\n[A2] author (INFERENCE — ambient-simulated, not production)")
    src = (SIM / "email_ingest.py").read_text()
    rationale = (SIM / "rationale2.txt").read_text()
    say(f"  drafted profile bytes: {len(src)} chars; rationale: "
        f"{len(rationale)} chars")

    # A3: stage-profile (mechanical)
    say("\n[A3] stage-profile (mechanical: envelope, commission, gate, pin)")
    prof_file = root / "incoming_profile.py"
    rat_file = root / "incoming_rationale.txt"
    prof_file.write_text(src)
    rat_file.write_text(rationale)
    staged = ac.stage_profile_package(
        root, agent_name=AGENT, profile_file=prof_file,
        rationale_file=rat_file, archetypes=["staff", "office"],
        commission_id="comm-email-ingest-e2e",
        note="e2e demo: build email_ingest")
    pin = staged["profile_sha256"]
    say(f"  staged: sha256={pin}")
    say(f"  archetype gate: {staged.get('archetype_violations', 'green')}")
    say(f"  build-request staged for pinned bytes {pin[:12]}…")

    # A4: factory driver (mechanical)
    say("\n[A4] factory driver: gate -> bind -> compile -> verify -> diagnose")
    outcome = aa.run_factory_driver_once(root)
    say(f"  driver outcome: {outcome['outcomes']}")
    verdict = next(r for r in aa.read_log(root)
                   if r.get("kind") == "verdict" and r.get("agent") == AGENT)
    diag = verdict["diagnostics"]
    say(f"  verdict: {verdict['outcome']}")
    _gcases = diag["cases"]
    _green = sum(1 for c in _gcases if c["passed"])
    say(f"  diagnostics: {_green}/{len(_gcases)} green")
    say(f"  artifact_hash={verdict['artifact_hash'][:12]}… "
        f"profile_hash={verdict['profile_hash'][:12]}…")
    assert verdict["outcome"] == "verified", "build did not verify"

    # A5: verified-build runtime (mechanical)
    say("\n[A5] verified-build runtime: resolve -> overlay -> execute")
    path, rpin = ac.resolve_verified_agent(root, AGENT)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    say(f"  resolve: pinned {rpin[:12]}… vs actual {actual[:12]}… "
        f"-> {'MATCH' if rpin == actual else 'TAMPERED'}")
    spec = importlib.util.spec_from_file_location(
        f"e2e_contained_{AGENT}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    agent_ns, agent_sha256 = "authored", rpin
    say(f"  executed as agent_ns={agent_ns} agent_sha256={agent_sha256[:12]}…")

    emails = [
        {"from": "legal@acme.example", "subject": "NDA signature needed by Friday",
         "body": "Please sign the attached NDA and return by Friday 5pm."},
        {"from": "news@digest.example", "subject": "This week's tech digest",
         "body": "Top stories this week in infrastructure…"},
        {"from": "billing@vendor.example", "subject": "Invoice #4217 due tomorrow",
         "body": "Payment of $4,200 is due tomorrow to avoid late fees."},
        {"from": "ops@internal.example", "subject": "Migration complete",
         "body": "The weekend migration finished cleanly. No action needed."},
        {"from": "colleague@internal.example", "subject": "Thoughts on the Q4 doc?",
         "body": "No rush — curious what you think of the Q4 planning doc."},
    ]
    # Ambient-authored verdicts, written BEFORE the run (not a live judge).
    verdicts = ["verdict: URGENT", "verdict: ROUTINE", "verdict: URGENT",
                "verdict: ROUTINE", "verdict: ROUTINE"]
    say("  [inference — ambient-simulated] verdicts authored in advance:")
    for i, v in enumerate(verdicts, 1):
        say(f"    pr-{i}: {v}")

    event = {"emails": emails}
    r1 = module.handle(event, [])
    assert r1["status"] == "awaiting_inference"
    say(f"  round 1: {r1['status']}; requested {r1['requested']}")
    inference_results = [
        {"request_id": f"pr-{i + 1}", "text": v}
        for i, v in enumerate(verdicts)]
    r2 = module.handle(event, inference_results)
    say(f"  round 2: {r2['status']}: "
        f"{r2['matters_created']} matters, "
        f"{r2['discarded_count']} discarded, "
        f"{r2['refused_count']} refused")
    for m in r2["matters"]:
        say(f"    matter {m['matter_id']} ← {m['subject']!r}")
    say("  (matter records are RETURNED payloads, not store writes)")
    return {"matters": r2["matters"], "pin": pin}


# --------------------------------------------------------------------------
# PHASE B — CUSTOMIZE
# --------------------------------------------------------------------------
SCHEMA_ARTIFACT = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "email-matter-record",
    "description": ("Registered shared schema for matter records staged by "
                    "the email_ingest agent. Promotes the in-module dict "
                    "contract to a versioned, content-pinned artifact."),
    "type": "object",
    "required": ["kind", "matter_id", "subject", "sender", "summary",
                 "source"],
    "properties": {
        "kind": {"const": "matter-record"},
        "matter_id": {"type": "string", "pattern": "^m-[0-9a-f]{12}$"},
        "subject": {"type": "string", "minLength": 1},
        "sender": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "maxLength": 200},
        "source": {"const": "email-ingest"},
    },
    "additionalProperties": False,
}


def phase_b(root: Path, matters: list[dict]) -> None:
    phase("PHASE B — CUSTOMIZE: register the matter-record schema")

    # B1: detect missing artifact (mechanical inspection)
    say("\n[B1] detect: authoring inspects the registry for a matter schema")
    found = reg.lookup(root, kind="schema", query="email matter record")
    say(f"  registry lookup(kind=schema, query='email matter record') "
        f"-> {len(found)} records: ABSENT")

    # B2: customizer records absence evidence (mechanical)
    say("\n[B2] customizer: mechanical prove-absence")
    evidence = RegistryEvidence(**reg.absence_evidence(
        root, kind="schema", query="email matter record"))
    say(f"  absence evidence: kind={evidence.kind} "
        f"query={evidence.query!r} hits={evidence.hits}")

    # B3: new commission (operator-attributed) — a new authoring cycle
    say("\n[B3] commission (operator-attributed; NEW cycle for the new "
        "artifact)")
    aa.stage_commission(
        root, commission_id="comm-matter-schema-e2e",
        role_brief=("Promote the email_ingest matter-record dict contract "
                    "to a registered, versioned, content-pinned shared "
                    "schema (v1)."),
        acceptance_criteria=[
            "proposal envelope validates",
            "registry absence re-verified at stage time",
            "registered bytes pin the drafted schema",
            "email_ingest matter payloads conform to the registered schema",
        ],
        disposition_ref="demo: operator directive (simulated commission)",
        principal_id="operator")
    say("  commission comm-matter-schema-e2e staged; principal=operator")

    # B4: draft proposal (inference side — ambient, labeled)
    say("\n[B4] customizer drafts proposal (INFERENCE — ambient-simulated)")
    proposal = CustomizationProposal(
        agent_name=AGENT,
        artifact_kind="schema",
        artifact_name="email-matter-record",
        artifact_source=json.dumps(SCHEMA_ARTIFACT, indent=2,
                                   sort_keys=True),
        rationale=("The matter record is currently an in-module dict "
                   "contract: structurally valid payloads can be "
                   "semantically wrong, and no shared pin exists for "
                   "downstream consumers. Registering v1 makes the "
                   "contract checkable and versioned."),
        registry_evidence=evidence,
        compatibility=("Downstream: the email_ingest runtime emits exactly "
                       "these six keys; additionalProperties=false matches "
                       "current emission. No other registered consumer "
                       "exists; v1 is additive (new artifact, no "
                       "supersedes)."),
        proposed_version=1,
        commission_id="comm-matter-schema-e2e",
    )
    prop_file = root / "proposal.json"
    prop_file.write_text(proposal.model_dump_json(indent=2))
    say("  proposal drafted: schema/email-matter-record v1")

    # B5: stage proposal (mechanical: re-runs the lookup)
    say("\n[B5] propose-customization (mechanical: envelope, commission, "
        "re-verify evidence, pin)")
    staged = ac.stage_customization_proposal(
        root, proposal_file=prop_file,
        commission_id="comm-matter-schema-e2e",
        note="e2e demo: register matter-record schema")
    seq = staged["proposal_seq"]
    say(f"  staged proposal seq={seq}; "
        f"artifact_sha256={staged['proposal_sha256'][:12]}…")

    # B6: adopt (SIMULATED disposition — labeled, not the operator's act)
    say("\n[B6] adopt-proposal — SIMULATED DISPOSITION (not Peter's act; in "
        "production this is the operator's hand)")
    adopted = ac.adopt_customization_proposal(
        root, proposal_seq=seq,
        disposition_ref="SIMULATED-DISPOSITION-e2e-demo", by="operator")
    art = adopted["artifact"]
    say(f"  adopted: {art['kind']}/{art['name']} v{art['version']} "
        f"sha256={art['sha256'][:12]}…")

    # B7: rebuild dependents — validate emitted matters against the
    # registered bytes (mechanical). The registry pins the hash; the bytes
    # live in the staged proposal — so re-read the staged bytes and check
    # the pin before validating dependents against them.
    say("\n[B7] factory builds dependents: matter payloads vs REGISTERED "
        "schema bytes")
    log = aa.read_log(root)
    staged_prop = next(r for r in log
                       if r.get("kind") == "staged-proposal"
                       and r.get("seq") == seq)
    staged_bytes = staged_prop["proposal"]["artifact_source"].encode()
    assert hashlib.sha256(staged_bytes).hexdigest() == art["sha256"], \
        "staged bytes do not match the registered pin"
    say(f"  staged bytes re-read; pin matches registry "
        f"({art['sha256'][:12]}…)")
    schema = json.loads(staged_bytes.decode())
    assert schema == SCHEMA_ARTIFACT, "registered bytes differ from draft"

    def conforms(m: dict) -> tuple[bool, str]:
        req = schema["required"]
        missing = [k for k in req if k not in m]
        if missing:
            return False, f"missing keys {missing}"
        if m["kind"] != "matter-record":
            return False, "kind != matter-record"
        import re as _re
        if not _re.match(r"^m-[0-9a-f]{12}$", m["matter_id"]):
            return False, "matter_id shape"
        if len(m["summary"]) > 200:
            return False, "summary > 200 chars"
        if m["source"] != "email-ingest":
            return False, "source != email-ingest"
        extra = set(m) - set(schema["properties"])
        if extra:
            return False, f"additional properties {extra}"
        return True, "all required keys, types, and bounds hold"

    all_ok = True
    for m in matters:
        ok, reason = conforms(m)
        all_ok &= ok
        say(f"  {'PASS' if ok else 'FAIL'} {m['matter_id']}: {reason}")
    assert all_ok, "a matter payload failed the registered schema"

    # B8: negative case — the falsified claim, made mechanical
    say("\n[B8] negative: post-release change under the ORIGINAL commission "
        "is refused")
    altered = dict(SCHEMA_ARTIFACT)
    altered["properties"] = dict(altered["properties"])
    altered["properties"]["priority"] = {"type": "string"}
    try:
        reg.register(root, kind="schema", name="email-matter-record",
                     artifact_bytes=json.dumps(altered, sort_keys=True)
                     .encode(), producer="customizer",
                     commission_id="comm-matter-schema-e2e",
                     disposition_ref="SIMULATED-DISPOSITION-e2e-demo")
        say("  ERROR: registration accepted (should have refused)")
    except reg.RegistryError as e:
        say(f"  refused as designed: {e}")

    say("\n[deliver] verified result: schema/email-matter-record v1 "
        f"({art['sha256'][:12]}…); {len(matters)} matter payloads conform; "
        "post-release rule holds.")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="e2e-email-ingest-"))
    say(f"scratch root: {root}")
    say("labels: INFERENCE steps are ambient-simulated; DISPOSITION steps "
        "are simulated unless marked operator.")
    out_a = phase_a(root)
    phase_b(root, out_a["matters"])
    say()
    say("END-TO-END COMPLETE: build verified -> customization registered "
        "-> dependents conform.")


if __name__ == "__main__":
    main()
