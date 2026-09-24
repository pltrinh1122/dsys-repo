"""Countersign mapping: SystemState -> one Countersign core instance document.

Authored under dyad-system d-work #156 (PR-C). The Countersign core schema
(eight entities: Party, Act, Proposal, Countersignature, Mandate, Release,
Event, Escalation, plus the Check attribute) is defined by the dyad-system
craft `crafts/countersign/` (rules/schema.md); a copy is pinned beside this
module as `countersign-core.json` at PINNED_SCHEMA_VERSION, verified by
PINNED_SCHEMA_SHA256 (the golden run fails on a mismatch). This is a
projection (F7): no dsys entity, enum or store changes. See
doc/countersign-mapping.md.

Derivation rules (F3: neither mode nor processor is a stored dsys field;
both are derived by these rules, from the entity *type* and its links):

  P1 parties     every Human -> kind human; every Agent -> kind agent; one
                 party `party-executor` (kind executor) iff any AutomatonRun
                 or FlowRun exists (the zero-inference automaton executor).
  A1 acts        DecisionRecord -> explicit, processor = its proposer.
  A2             HarnessRun -> explicit, processor = its dyad's agent;
                 implicit instead iff a Directive targeting the run cites an
                 in-force set_standing disposition (decided yes, see C1):
                 the run proceeds under standing authority, not a live
                 per-act countersignature. (Stated rule, inference: dsys
                 records no other link from a run to a standing policy.)
  A3             AutomatonRun, FlowRun -> automatic, processor = executor.
  A4             Proposal (dsys) -> a synthesized explicit act
                 `act-proposal-<id>` processed by its dyad's agent, state its
                 RatificationRecord verdict (else `draft`).
  A5             a disposition that no record links to an act (A6) gets a
                 synthesized explicit act `act-disp-<id>`, processed by its
                 proposer; profile `synthesized: true`.
  A6 act of a disposition, first match wins: a DecisionRecord whose
                 disposition_id names it; a Directive citing it (-> the
                 target HarnessRun); an overrule's veto -> its directive ->
                 target run; a PromotionRecord citing it (-> the artifact's
                 HarnessRun); else A5.
  R1 proposals   DecisionRecord -> `proposal-dr-<id>` (the options put up,
                 author = proposer). Every non-triage Disposition not linked
                 to a DecisionRecord -> `proposal-disp-<id>` (the CTA put up,
                 author = proposer, body_ref = action_ref, artifact_hash =
                 state_ref). Proposal (dsys) -> `proposal-pr-<id>`.
  C1 countersignatures  every Disposition that is decided (status approved,
                 rejected or acted) or answered (a response; a counter keeps
                 status proposed, E3). answer: response yes -> yes, no -> no,
                 counter -> amend; with no response, status approved|acted
                 -> yes, rejected -> no (profile answer_source: status).
                 signer = disposer; text = the disposition text verbatim;
                 bound_hash = state_ref; at = "" (dsys has no clock).
                 subject: a triage -> the escalation of its disclosure_ref;
                 else the proposal of R1.
  C2 basis (F4)  DispositionMode is a disposition *kind*, renamed at this
                 boundary only: set_standing -> mandate; authorize cited by
                 a PromotionRecord -> release; every other authorize, ratify,
                 overrule, triage -> per-act. The original mode is kept in
                 the countersignature's profile as `disposition_mode`.
  M1 mandates    every set_standing Disposition whose countersignature
                 answers yes: scope.event_class = standing_domain, rights =
                 [standing_domain]; profile names what supersedes it.
  L1 releases    every AutomatonRelease; its countersignature is that of the
                 disposition a PromotionRecord with the same release_version
                 cites; definition_ref = its artifact ids; hash = their
                 content hashes; profile lists run-books and flows pinned to
                 the version.
  E1 events      AutomatonEvent -> act of its run; FlowTransitionEvent ->
                 act of its flow run; seq kept; at = `seq:<n>` (no clock).
  X1 escalations every Disclosure: from `ext:dsys-disclosure-<id>` (dsys
                 records no originating act), opens the act of the triage
                 disposition citing it (A6), or none while untriaged.

Ids: `<entity>-<kind>-<dsys id>`, lower-cased, runs outside [a-z0-9.-]
replaced by `-`; the original id is kept in every profile as `dsys_id`.
Deterministic: arrays sorted by id (numeric runs compared as numbers), no
clock, render() is sorted-key JSON. Extension entities (Principal, Hat, R,
Fleet, Directive, GateCheck, Application, LocalVeto, Claim, IFF gates, ...)
are the dsys profile and are NOT mapped into the core (F5).

`validate` and `check` mirror crafts/countersign/projectors/
project_countersign.py (same keyword subset, same four checks), stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .schema import DispositionMode, DispositionResponse, DispositionStatus, SystemState

PINNED_SCHEMA_VERSION = "0.1.0"
PINNED_SCHEMA_SHA256 = "647ef7d5c6e007a0584c39d78eecaa1f43b7b47cfc63223ad9f716c1fbc9ab1b"
PINNED_SCHEMA_SOURCE = ("dyad-system crafts/countersign/templates/countersign-core.json "
                        "@ 8302027 (d-work #156)")
SCHEMA_PATH = Path(__file__).with_name("countersign-core.json")
SYSTEM = "dsys"

ENTITIES = ("parties", "acts", "proposals", "countersignatures", "mandates",
            "releases", "events", "escalations")
PROCESSOR_KIND = {"explicit": "agent", "implicit": "agent", "automatic": "executor"}
EXECUTOR = "party-executor"
ANSWER_OF_RESPONSE = {DispositionResponse.YES: "yes", DispositionResponse.NO: "no",
                      DispositionResponse.COUNTER: "amend"}
ANSWER_OF_STATUS = {DispositionStatus.APPROVED: "yes", DispositionStatus.ACTED: "yes",
                    DispositionStatus.REJECTED: "no"}
BASIS_OF_MODE = {DispositionMode.SET_STANDING: "mandate", DispositionMode.AUTHORIZE: "per-act",
                 DispositionMode.RATIFY: "per-act", DispositionMode.OVERRULE: "per-act",
                 DispositionMode.TRIAGE: "per-act"}   # C2; authorize on a promotion -> release
CHECKS = (("dsys:referee validate (validators.validate)", "after", "act"),
          ("dsys:referee validate (validators.validate)", "after", "countersignature"),
          ("dsys:try_promote / try_apply_directive", "before", "release"))   # F6


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", str(s).lower()).strip("-") or "x"


def _id(prefix: str, dsys_id: str) -> str:
    return f"{prefix}-{_slug(dsys_id)}"


def _natkey(s: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def _sorted(items: list) -> list:
    return sorted(items, key=lambda d: _natkey(d.get("id", d.get("name", ""))))


def _v(x) -> str | None:
    return None if x is None else getattr(x, "value", x)


# ---- to_countersign: the projection -------------------------------------
def to_countersign(state: SystemState) -> dict:
    """The Countersign core instance document of `state` (rules in the docstring)."""
    s = state
    doc = {"schema_version": PINNED_SCHEMA_VERSION, "system": SYSTEM, **{e: [] for e in ENTITIES}}
    party = {}                                   # dsys id -> party id
    for coll, kind in (("humans", "human"), ("agents", "agent")):   # P1
        for k, ent in getattr(s, coll).items():
            pid = _id("party", k)
            party[k] = pid
            doc["parties"].append({"id": pid, "kind": kind,
                                   "profile": {"dsys_collection": coll, "dsys_id": k, "name": ent.name}})
    if s.automaton_runs or s.flow_runs:
        doc["parties"].append({"id": EXECUTOR, "kind": "executor",
                               "profile": {"dsys_component": "automaton-executor"}})

    def p(dsys_id: str | None) -> str:          # an unresolved party stays visible to check()
        return party.get(dsys_id or "", _id("party-unresolved", dsys_id or "none"))

    def dyad_agent(dyad_id: str | None) -> str:
        d = s.dyads.get(dyad_id or "")
        return p(d.agent_id if d else None)

    # C1: which dispositions countersign, and how
    def answer(d):
        if d.response is not None:
            return ANSWER_OF_RESPONSE[d.response], "response"
        if d.status in ANSWER_OF_STATUS:
            return ANSWER_OF_STATUS[d.status], "status"
        return None, None

    decided = {k: answer(d) for k, d in s.dispositions.items()}
    in_force_standing = {k for k, d in s.dispositions.items()
                         if d.mode == DispositionMode.SET_STANDING and decided[k][0] == "yes"}
    promoted = {}                                # disposition id -> release version
    for pr in s.promotions.values():
        promoted.setdefault(pr.disposition_id, pr.release_version)

    # acts: A1 decision records
    for k, r in s.decision_records.items():
        aid = _id("act-dr", k)
        doc["acts"].append({"id": aid, "title": r.matter or f"decision record {k}", "mode": "explicit",
                            "processor": p(r.proposer_id), "state": r.verdict,
                            "refs": sorted(r.premises) + ([r.disposition_id] if r.disposition_id else []),
                            "profile": {"dsys_collection": "decision_records", "dsys_id": k,
                                        "playbook": r.playbook, "rehearsal": r.rehearsal,
                                        "selector": r.selector_id, "rung": r.rung}})
        doc["proposals"].append({"id": _id("proposal-dr", k), "act": aid, "author": p(r.proposer_id),
                                 "body_ref": f"dsys:decision_records/{k}", "artifact_hash": None,
                                 "profile": {"dsys_collection": "decision_records", "dsys_id": k,
                                             "options": list(r.options), "selected": r.selected}})
    # A2 harness runs
    for k, h in s.harness_runs.items():
        standing = sorted(dv.disposition_id for dv in s.directives.values()
                          if dv.target_run_id == k and dv.disposition_id in in_force_standing)
        doc["acts"].append({"id": _id("act-hr", k),
                            "title": f"harness run {k} ({_v(h.authority_scope)})",
                            "mode": "implicit" if standing else "explicit",
                            "processor": dyad_agent(h.dyad_id), "state": _v(h.state),
                            "refs": [x for x in (h.principal_id, h.session_id) if x],
                            "profile": {"dsys_collection": "harness_runs", "dsys_id": k,
                                        "authority_scope": _v(h.authority_scope),
                                        "closure_reason": _v(h.closure_reason),
                                        "standing_dispositions": standing}})
    # A3 automaton runs and flow runs
    for k, r in s.automaton_runs.items():
        doc["acts"].append({"id": _id("act-ar", k), "title": f"automaton run {k}", "mode": "automatic",
                            "processor": EXECUTOR, "state": r.state,
                            "refs": [x for x in (r.runbook_id, r.parent_flow_run_id, r.flow_state_id) if x],
                            "profile": {"dsys_collection": "automaton_runs", "dsys_id": k,
                                        "idempotency_key": r.idempotency_key}})
    for k, r in s.flow_runs.items():
        doc["acts"].append({"id": _id("act-fr", k), "title": f"flow run {k}", "mode": "automatic",
                            "processor": EXECUTOR, "state": r.state,
                            "refs": [r.flow_id, r.current_state_id],
                            "profile": {"dsys_collection": "flow_runs", "dsys_id": k}})
    # A4 / R1 dsys proposals
    verdict = {rr.proposal_id: _v(rr.verdict) for rr in s.ratifications.values()}
    for k, pr in s.proposals.items():
        aid = _id("act-proposal", k)
        doc["acts"].append({"id": aid, "title": pr.text, "mode": "explicit",
                            "processor": dyad_agent(pr.dyad_id), "state": verdict.get(k, "draft"),
                            "refs": [], "profile": {"dsys_collection": "proposals", "dsys_id": k,
                                                    "synthesized": True}})
        doc["proposals"].append({"id": _id("proposal-pr", k), "act": aid, "author": dyad_agent(pr.dyad_id),
                                 "body_ref": f"dsys:proposals/{k}", "artifact_hash": None,
                                 "profile": {"dsys_collection": "proposals", "dsys_id": k,
                                             "criteria": list(pr.criteria)}})

    # A6: the act of a disposition
    def act_of(k: str, d) -> tuple[str, str | None]:
        """(act id, decision record id or None)."""
        for rk in sorted(s.decision_records, key=_natkey):
            if s.decision_records[rk].disposition_id == k:
                return _id("act-dr", rk), rk
        target = next((dv.target_run_id for _, dv in sorted(s.directives.items())
                       if dv.disposition_id == k), None)
        if target is None and d.veto_id and d.veto_id in s.local_vetoes:
            dv = s.directives.get(s.local_vetoes[d.veto_id].directive_id)
            target = dv.target_run_id if dv else None
        if target is None:
            for _, pr in sorted(s.promotions.items()):
                art = s.artifacts.get(pr.artifact_id)
                if pr.disposition_id == k and art:
                    target = art.run_id
                    break
        if target in s.harness_runs:
            return _id("act-hr", target), None
        aid = _id("act-disp", k)
        doc["acts"].append({"id": aid, "title": d.text, "mode": "explicit", "processor": p(d.proposer_id),
                            "state": _v(d.status), "refs": [],
                            "profile": {"dsys_collection": "dispositions", "dsys_id": k, "synthesized": True}})
        return aid, None

    disp_act = {}
    for k in sorted(s.dispositions, key=_natkey):
        d = s.dispositions[k]
        aid, rk = act_of(k, d)
        disp_act[k] = aid
        if d.mode == DispositionMode.TRIAGE:
            subject = _id("escalation-dis", d.disclosure_ref or "none")
        elif rk is not None:
            subject = _id("proposal-dr", rk)
        else:
            subject = _id("proposal-disp", k)
            doc["proposals"].append({"id": subject, "act": aid, "author": p(d.proposer_id),
                                     "body_ref": d.action_ref, "artifact_hash": d.state_ref,
                                     "profile": {"dsys_collection": "dispositions", "dsys_id": k,
                                                 "cta": d.cta, "status": _v(d.status)}})
        ans, source = decided[k]
        if ans is None:
            continue
        basis = "release" if (d.mode == DispositionMode.AUTHORIZE and k in promoted) else BASIS_OF_MODE[d.mode]
        doc["countersignatures"].append({
            "id": _id("countersignature", k), "subject": subject, "signer": p(d.disposer_id),
            "answer": ans, "basis": basis, "text": d.text, "bound_hash": d.state_ref, "at": "",
            "profile": {"dsys_collection": "dispositions", "dsys_id": k,
                        "disposition_mode": _v(d.mode), "status": _v(d.status),
                        "response": _v(d.response), "answer_source": source,
                        "counter_text": d.counter_text, "reentry_ref": d.reentry_ref}})
    signed = {c["profile"]["dsys_id"]: c for c in doc["countersignatures"]}

    # M1 mandates
    for k in sorted(in_force_standing, key=_natkey):
        d = s.dispositions[k]
        by = sorted(x for x, o in s.dispositions.items() if o.supersedes_disposition_id == k)
        doc["mandates"].append({"id": _id("mandate", k),
                                "scope": {"event_class": d.standing_domain or "", "plan_template": None,
                                          "budget": None, "rights": [d.standing_domain] if d.standing_domain else []},
                                "countersignature": signed[k]["id"],
                                "profile": {"dsys_collection": "dispositions", "dsys_id": k,
                                            "superseded_by": by,
                                            "supersedes": d.supersedes_disposition_id}})
    # L1 releases
    for k, rel in s.releases.items():
        prom = sorted((pk, pr) for pk, pr in s.promotions.items() if pr.release_version == rel.version)
        disp = prom[0][1].disposition_id if prom else None
        arts = sorted(rel.artifact_ids)
        doc["releases"].append({
            "id": _id("release", k),
            "definition_ref": "dsys:artifacts/" + ",".join(arts),
            "version": rel.version,
            "hash": ",".join(s.artifacts[a].content_hash if a in s.artifacts else "" for a in arts),
            "countersignature": signed[disp]["id"] if disp in signed else None,
            "profile": {"dsys_collection": "releases", "dsys_id": k,
                        "promotion": prom[0][0] if prom else None, "disposition": disp,
                        "runbooks": sorted(r for r, rb in s.runbooks.items() if rb.release_version == rel.version),
                        "flows": sorted(f for f, fl in s.automaton_flows.items() if fl.release_version == rel.version)}})
    # E1 events
    for k, e in s.automaton_events.items():
        doc["events"].append({"id": _id("event-ae", k), "act": _id("act-ar", e.run_id), "seq": e.seq,
                              "payload": {"kind": e.kind, "payload": e.payload}, "at": f"seq:{e.seq}",
                              "profile": {"dsys_collection": "automaton_events", "dsys_id": k}})
    for k, e in s.flow_transition_events.items():
        doc["events"].append({"id": _id("event-fte", k), "act": _id("act-fr", e.flow_run_id), "seq": e.seq,
                              "payload": {"from_state_id": e.from_state_id, "to_state_id": e.to_state_id,
                                          "trigger": e.trigger, "payload": e.payload},
                              "at": f"seq:{e.seq}",
                              "profile": {"dsys_collection": "flow_transition_events", "dsys_id": k}})
    # X1 escalations
    for k, x in s.disclosures.items():
        triage = sorted(dk for dk, d in s.dispositions.items()
                        if d.mode == DispositionMode.TRIAGE and d.disclosure_ref == k)
        doc["escalations"].append({"id": _id("escalation-dis", k), "from": f"ext:dsys-disclosure-{k}",
                                   "reason": f"{_v(x.kind)}: {x.text}",
                                   "opens": disp_act[triage[0]] if triage else None,
                                   "profile": {"dsys_collection": "disclosures", "dsys_id": k,
                                               "status": _v(x.status), "seq": x.seq,
                                               "triage_dispositions": triage}})
    doc["checks"] = [{"name": n, "timing": t, "target": tg} for n, t, tg in CHECKS]
    for e in ENTITIES:
        doc[e] = _sorted(doc[e])
    return doc


# ---- pinned schema ----------------------------------------------------------
def schema_sha256(path: Path = SCHEMA_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_problems(path: Path = SCHEMA_PATH) -> list[str]:
    """Drift check of the pinned copy (plan #156 P2): present, sha256 and version as pinned."""
    path = Path(path)
    if not path.exists():
        return [f"pinned schema missing: {path.name}"]
    got = schema_sha256(path)
    if got != PINNED_SCHEMA_SHA256:
        return [f"pinned schema sha256 {got} != {PINNED_SCHEMA_SHA256}"]
    ver = json.loads(path.read_text())["properties"]["schema_version"].get("const")
    if ver != PINNED_SCHEMA_VERSION:
        return [f"pinned schema version {ver} != {PINNED_SCHEMA_VERSION}"]
    return []


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(Path(path).read_text())


# ---- validate / check: mirror of the craft projector's ---------------------
_TYPES = {"object": dict, "array": list, "string": str, "null": type(None), "boolean": bool}


def _is(v, t: str) -> bool:
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t]) and not (t != "boolean" and isinstance(v, bool))


def validate(inst, sch: dict, root: dict | None = None, where: str = "$") -> list[str]:
    """The stdlib subset of JSON Schema the pinned file uses; an unknown keyword is an error."""
    root = sch if root is None else root
    known = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const",
             "required", "properties", "additionalProperties", "items", "pattern", "minimum"}
    unknown = set(sch) - known
    if unknown:
        return [f"{where}: schema keyword(s) {sorted(unknown)} not supported by this validator"]
    if "$ref" in sch:
        node = root
        for part in sch["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return validate(inst, node, root, where)
    errs = []
    if "type" in sch:
        types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_is(inst, t) for t in types):
            return [f"{where}: {type(inst).__name__} is not {'|'.join(types)}"]
    if "const" in sch and inst != sch["const"]:
        errs.append(f"{where}: {inst!r} is not {sch['const']!r}")
    if "enum" in sch and inst not in sch["enum"]:
        errs.append(f"{where}: {inst!r} not in {sch['enum']}")
    if "pattern" in sch and isinstance(inst, str) and not re.search(sch["pattern"], inst):
        errs.append(f"{where}: {inst!r} does not match {sch['pattern']}")
    if "minimum" in sch and _is(inst, "number") and inst < sch["minimum"]:
        errs.append(f"{where}: {inst} < {sch['minimum']}")
    if isinstance(inst, dict):
        for k in sch.get("required", []):
            if k not in inst:
                errs.append(f"{where}: missing '{k}'")
        props = sch.get("properties", {})
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], root, f"{where}.{k}")
            elif sch.get("additionalProperties") is False:
                errs.append(f"{where}: unexpected '{k}'")
    if isinstance(inst, list) and "items" in sch:
        for i, v in enumerate(inst):
            errs += validate(v, sch["items"], root, f"{where}[{i}]")
    return errs


def check(doc: dict, sch: dict | None = None) -> list[str]:
    """The schema, then what it cannot say (craft rules/schema.md §1, conditions 1-4)."""
    errs = validate(doc, sch if sch is not None else load_schema())
    if errs:
        return errs
    ids = [d["id"] for e in ENTITIES for d in doc[e]]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"duplicate ids: {dup[:5]}")
    by = {e: {d["id"]: d for d in doc[e]} for e in ENTITIES}
    kind = {p["id"]: p["kind"] for p in doc["parties"]}
    for a in doc["acts"]:
        if kind.get(a["processor"]) != PROCESSOR_KIND[a["mode"]]:
            errs.append(f"{a['id']}: processor {a['processor']} ({kind.get(a['processor'])}) is not the "
                        f"{PROCESSOR_KIND[a['mode']]} a {a['mode']} act requires")
    for p in doc["proposals"]:
        if p["act"] not in by["acts"]:
            errs.append(f"{p['id']}: act {p['act']} unresolved")
        if kind.get(p["author"]) != "agent":
            errs.append(f"{p['id']}: author {p['author']} is not an agent")
    for s in doc["countersignatures"]:
        if s["subject"] not in by["proposals"] and s["subject"] not in by["escalations"]:
            errs.append(f"{s['id']}: subject {s['subject']} unresolved")
        if kind.get(s["signer"]) != "human":
            errs.append(f"{s['id']}: signer {s['signer']} is not human")
    for e in ("mandates", "releases"):
        for d in doc[e]:
            if d["countersignature"] is not None and d["countersignature"] not in by["countersignatures"]:
                errs.append(f"{d['id']}: countersignature {d['countersignature']} unresolved")
    for ev in doc["events"]:
        if ev["act"] not in by["acts"]:
            errs.append(f"{ev['id']}: act {ev['act']} unresolved")
    for x in doc["escalations"]:
        if not x["from"].startswith("ext:") and x["from"] not in by["acts"]:
            errs.append(f"{x['id']}: from {x['from']} unresolved")
        if x["opens"] is not None and by["acts"].get(x["opens"], {}).get("mode") != "explicit":
            errs.append(f"{x['id']}: opens {x['opens']}, not an explicit act")
    return errs


def render(doc: dict) -> str:
    """Byte-identical for the same document."""
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def counts(doc: dict) -> dict:
    return {e: len(doc[e]) for e in ENTITIES}
