"""Harness-native agent substrate runtime components — step-5 build of the D1-D7 agent factory (DR-CMD-061).

NEW machinery: this module implements the substrate the factory produces at
step 5, per the spec in ``doc/d1-d7-agent-substrate-spec.md`` (DRAFT, step-2
proposal; substrate + runtime contract as specified in §2/§3, trust
boundaries per §4, backend interface per §6).

Ratified decisions implemented here:
- DR-CMD-063 — harness-native: factory-built agents are dsys harness-plane
  entities (not substrate-neutral).
- DR-CMD-064 — actuation path for built agents is hybrid; the factory's own
  build pipeline is automaton flows (this module is a component library, not
  an operating scheduler — see spec §8 non-goals).
- DR-CMD-065 (Q3 resolved) — staging is accretion-backed: every staged
  proposal (actions + verification evidence) is committed to the accretion
  repo; pending proposals survive restarts and stay auditable.

``GATE_SEMANTICS_VERSION`` pins this module's reference interpretation of
the §2 trigger-wiring gate semantics (v1.0). Only concrete facility bindings
not specified here may differ.

Design constraints (hard):
- Deterministic: no wall-clock, no randomness, no network. Sequence
  counters only; never uuid/time.
- No imports from ``agent_behavior``: the substrate stays decoupled from the
  profile schema; the step-3 compiler will map profiles to these components.
- Only pydantic v2 + stdlib + ``abc``.
- No I/O except ``AccretionWriter``'s root dir. No git ops.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Canonical JSON helper (deterministic serialization for hashing)
# ---------------------------------------------------------------------------

def canonical_json(value: dict) -> str:
    """Canonical JSON: sorted keys, compact separators. The single hash input form."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Trigger wiring: listener, activation gate, authorization rule
# ---------------------------------------------------------------------------

GATE_SEMANTICS_VERSION = "1.0"


class TriggerEvent(BaseModel, frozen=True):
    """One observed trigger event arriving at a listener."""
    source: str
    event_id: str
    payload: dict = {}
    source_id: str = "unknown"
    signature_valid: bool | None = None
    session_authenticated: bool | None = None


class TriggerListener(ABC):
    """Abstract source of trigger events; drained FIFO by the wiring."""

    source: str

    @abstractmethod
    def drain(self) -> list[TriggerEvent]:
        """Drain all queued events (FIFO), returning them in arrival order."""
        ...


class MemoryTriggerListener(TriggerListener):
    """In-memory FIFO trigger listener (test / reference implementation)."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._queue: list[TriggerEvent] = []

    def enqueue(self, event: TriggerEvent) -> None:
        """Append an event to the tail of the queue."""
        self._queue.append(event)

    def drain(self) -> list[TriggerEvent]:
        """Remove and return all queued events, oldest first."""
        events = self._queue
        self._queue = []
        return events


class StagingEventListener(TriggerListener):
    """Staging-event feed: the listener the D6 ``agent`` source subscribes to
    (DR-CMD-078).

    Tails the accretion-backed staging file (``staging.jsonl``) and emits
    one TriggerEvent per new *proposal* record (kind == "proposal") authored
    by a built agent other than the owner. Disposition records and the
    owner's own proposals do not emit — they are not new inputs.

    Attestation is pre-computed here (J-I): ``session_authenticated`` is
    True iff (a) the staging file's hash chain verifies end-to-end AND (b)
    the record's author id is in ``verified_agents``. A broken chain fails
    closed for the whole drain; an unknown author (spoof) fails closed for
    that event. The activation gate's existing ``authenticated`` keyword
    then admits on that flag — no new gate-semantics keyword, so
    ``GATE_SEMANTICS_VERSION`` is unchanged.

    Watermarked at the last read seq: construction watermarks at the
    current file head (history is the SELF cadence sweep's jurisdiction);
    ``drain()`` advances past everything read, emitted or not — a skipped
    record is not re-emitted; the sweep covers it. Deterministic: seq
    counters only.
    """

    source = "agent"

    def __init__(self, writer: AccretionWriter, verified_agents: set[str],
                 own_agent: str) -> None:
        self.writer = writer
        self.verified_agents = set(verified_agents)
        self.own_agent = own_agent
        self._watermark = self._head_seq()

    def _head_seq(self) -> int:
        """Highest seq present in the file, or -1 when empty."""
        head = -1
        if self.writer.file.exists():
            for line in self.writer.file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    head = int(json.loads(line)["seq"])
        return head

    def drain(self) -> list[TriggerEvent]:
        """Emit one event per new proposal record since the watermark."""
        chain_ok = self.writer.verify()
        events: list[TriggerEvent] = []
        if self.writer.file.exists():
            for line in self.writer.file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                seq = int(record["seq"])
                if seq <= self._watermark:
                    continue
                self._watermark = seq
                payload = record["payload"]
                if payload.get("kind") != "proposal":
                    continue
                author = payload.get("agent", "unknown")
                if author == self.own_agent:
                    continue
                author_ok = author in self.verified_agents
                events.append(TriggerEvent(
                    source="agent",
                    event_id=f"staging-ev-{seq:06d}",
                    payload={"staging_seq": seq,
                             "record_hash": record["record_hash"],
                             "kind": payload.get("kind"),
                             "author": author},
                    source_id=author,
                    session_authenticated=bool(chain_ok and author_ok),
                ))
        return events


class GateDecision(BaseModel, frozen=True):
    """The activation gate's verdict on one trigger event."""
    admitted: bool
    unrecognized: bool
    reason: str


class ActivationGate:
    """Reference gate semantics (v1.0): may the trigger fire?

    Rules (fail-closed where a security dependency is unmet):
    1. gate stripped+lowered in {"none","unauthenticated",""} -> admit,
       unrecognized=False, reason "open gate"
    2. "signature" in gate.lower() -> admit iff event.signature_valid is True
    3. "allowlist" in gate.lower() -> admit iff event.source_id in the
       allowlist (empty/unset allowlist -> deny)
    4. "authenticated" in gate.lower() -> admit iff
       event.session_authenticated is True
    5. "hardwired" in gate.lower() -> admit
    6. no keyword matched -> admit=True, unrecognized=True,
       reason "unrecognized gate: staged only, never acts"
    Rules 2-5 combine with AND when several keywords appear. The reason names
    the rule(s).
    """

    def __init__(self, gate: str, allowlist: set[str] | None = None) -> None:
        self.gate = gate
        self.allowlist: set[str] | None = set(allowlist) if allowlist is not None else None

    def decide(self, event: TriggerEvent) -> GateDecision:
        """Decide admission for one event under the reference semantics."""
        gate = self.gate.strip().lower()
        if gate in ("none", "unauthenticated", ""):
            return GateDecision(admitted=True, unrecognized=False, reason="open gate")

        rules: list[str] = []
        if "signature" in gate:
            rules.append("signature")
        if "allowlist" in gate:
            rules.append("allowlist")
        if "authenticated" in gate:
            rules.append("authenticated")
        if "hardwired" in gate:
            rules.append("hardwired")

        if not rules:
            return GateDecision(
                admitted=True,
                unrecognized=True,
                reason="unrecognized gate: staged only, never acts",
            )

        admitted = True
        for rule in rules:
            if rule == "signature":
                admitted = admitted and event.signature_valid is True
            elif rule == "allowlist":
                admitted = (
                    admitted
                    and self.allowlist is not None
                    and len(self.allowlist) > 0
                    and event.source_id in self.allowlist
                )
            elif rule == "authenticated":
                admitted = admitted and event.session_authenticated is True
            elif rule == "hardwired":
                admitted = admitted and True

        return GateDecision(
            admitted=admitted,
            unrecognized=False,
            reason="gate rule(s): " + "+".join(rules),
        )


class AuthorizationRule:
    """Authorization rule: may the agent act on the admitted trigger?

    "may-act" (act within standing dispositions) vs "stage-only" (propose
    for disposition). Fail-safe: an unrecognized gate never authorizes
    may-act.
    """

    def __init__(self, authorization: str) -> None:
        self.authorization = authorization

    def authorize(self, event: TriggerEvent, gate_unrecognized: bool) -> str:
        """Return "may-act" | "stage-only" for an admitted event."""
        if "may-act" in self.authorization.lower() and not gate_unrecognized:
            return "may-act"
        return "stage-only"


class WiringOutcome(BaseModel, frozen=True):
    """Result of running one event through the two-stage trigger pipeline."""
    event_id: str
    admitted: bool
    authorization: str  # "dropped" | "stage-only" | "may-act"


class TriggerWiring:
    """Two-stage trigger pipeline: activation gate THEN authorization rule."""

    def __init__(
        self,
        source: str,
        gate: str,
        authorization: str,
        allowlist: set[str] | None = None,
        listener: TriggerListener | None = None,
    ) -> None:
        self.source = source
        self.gate = ActivationGate(gate, allowlist=allowlist)
        self.authorization = AuthorizationRule(authorization)
        self.listener = listener if listener is not None else MemoryTriggerListener(source)

    def process(self, event: TriggerEvent) -> WiringOutcome:
        """Run one event through activation, then authorization. Dropped if the gate denies."""
        decision = self.gate.decide(event)
        if not decision.admitted:
            return WiringOutcome(event_id=event.event_id, admitted=False, authorization="dropped")
        authz = self.authorization.authorize(event, gate_unrecognized=decision.unrecognized)
        return WiringOutcome(event_id=event.event_id, admitted=True, authorization=authz)


# ---------------------------------------------------------------------------
# Event log (D4 instrumentation): append-only, hash-chained, seq-ordered
# ---------------------------------------------------------------------------

class LogRecord(BaseModel, frozen=True):
    """One append-only, hash-chained log record."""
    seq: int
    stream: str
    prev_hash: str
    record_hash: str
    payload: dict


class EventLog:
    """D4 instrumentation log: append-only, hash-chained, seq-ordered.

    No clock: ordering comes from the sequence counter alone.
    """

    STREAMS = ("event", "intent", "verification")

    def __init__(self) -> None:
        self._records: list[LogRecord] = []

    def record(self, stream: str, payload: dict) -> LogRecord:
        """Append one record to a stream; returns the committed record."""
        if stream not in self.STREAMS:
            raise ValueError(f"unknown stream {stream!r}; must be one of {self.STREAMS}")
        seq = len(self._records)
        prev_hash = self._records[-1].record_hash if self._records else "genesis"
        record_hash = hashlib.sha256(
            f"{seq}|{stream}|{prev_hash}|{canonical_json(payload)}".encode("utf-8")
        ).hexdigest()
        record = LogRecord(
            seq=seq, stream=stream, prev_hash=prev_hash, record_hash=record_hash, payload=payload
        )
        self._records.append(record)
        return record

    def verify_chain(self) -> bool:
        """Verify hash continuity and seq ordering over all records."""
        prev_hash = "genesis"
        for expected_seq, record in enumerate(self._records):
            if record.seq != expected_seq:
                return False
            if record.prev_hash != prev_hash:
                return False
            recomputed = hashlib.sha256(
                f"{record.seq}|{record.stream}|{record.prev_hash}|{canonical_json(record.payload)}".encode(
                    "utf-8"
                )
            ).hexdigest()
            if recomputed != record.record_hash:
                return False
            prev_hash = record.record_hash
        return True

    def read(self, stream: str | None = None) -> list[LogRecord]:
        """Read all records, optionally filtered to one stream. Read-only."""
        if stream is None:
            return list(self._records)
        return [r for r in self._records if r.stream == stream]


# ---------------------------------------------------------------------------
# Staging area (Q3 accretion-backed staging, DR-CMD-065)
# ---------------------------------------------------------------------------

class StagedProposal(BaseModel, frozen=True):
    """A staged action proposal with its verification evidence."""
    proposal_id: str
    agent: str
    action_class: str
    effects: list[dict]
    args: dict
    verification_evidence: list[str]
    trigger_ref: str
    disposition: str = "pending"
    disposition_record: dict | None = None


class AccretionWriter:
    """Q3 accretion-backed staging (DR-CMD-065): append-only hash-chained JSONL.

    Every staged proposal is committed to ``root/"staging.jsonl"`` as a
    hash-chained record, so pending proposals survive restarts and stay
    auditable. Deterministic: seq counters only; each line is canonical JSON.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = self.root / "staging.jsonl"

    def _head(self) -> tuple[int, str]:
        """Recover (next_seq, prev_hash) from the file.

        Head is derived from the file on every call, not cached: appends
        continue the same hash chain across restarts and across multiple
        writer instances on the same root (appends must be serialized —
        out of scope for this module).
        """
        seq = 0
        prev_hash = "genesis"
        if self.file.exists():
            for line in self.file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                seq = int(record["seq"]) + 1
                prev_hash = record["record_hash"]
        return seq, prev_hash

    def append(self, payload: dict) -> int:
        """Append ``{"seq","prev_hash","record_hash","payload"}``; returns seq."""
        seq, prev_hash = self._head()
        record_hash = hashlib.sha256(
            f"{seq}|{prev_hash}|{canonical_json(payload)}".encode("utf-8")
        ).hexdigest()
        record = {"seq": seq, "prev_hash": prev_hash, "record_hash": record_hash, "payload": payload}
        with self.file.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(record) + "\n")
        return seq

    def verify(self) -> bool:
        """Verify hash continuity and seq ordering of the whole file."""
        seq = 0
        prev_hash = "genesis"
        if not self.file.exists():
            return True
        for line in self.file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if int(record["seq"]) != seq or record["prev_hash"] != prev_hash:
                return False
            recomputed = hashlib.sha256(
                f"{seq}|{prev_hash}|{canonical_json(record['payload'])}".encode("utf-8")
            ).hexdigest()
            if recomputed != record["record_hash"]:
                return False
            seq += 1
            prev_hash = record["record_hash"]
        return True

    def read_all(self) -> list[dict]:
        """Read every payload in file order. Read-only."""
        if not self.file.exists():
            return []
        out = []
        for line in self.file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line)["payload"])
        return out


class StagingArea:
    """Where the agent's proposed actions wait with verification evidence.

    The commit IS the staging: ``stage()`` appends to the accretion writer
    and the proposal_id is derived from the writer's seq (``f"sp-{seq:06d}"``).
    An in-memory index supports ``get()``/``pending()`` within a session;
    durability lives in the writer's file.
    """

    def __init__(self, writer: AccretionWriter, agent: str) -> None:
        self.writer = writer
        self.agent = agent
        self._index: dict[str, StagedProposal] = {}

    def stage(
        self,
        action_class: str,
        effects: list[dict],
        args: dict,
        verification_evidence: list[str],
        trigger_ref: str,
    ) -> StagedProposal:
        """Stage a proposal: append to the accretion writer, index the result."""
        seq = self.writer.append(
            {
                "kind": "proposal",
                "agent": self.agent,
                "action_class": action_class,
                "effects": effects,
                "args": args,
                "verification_evidence": verification_evidence,
                "trigger_ref": trigger_ref,
            }
        )
        proposal = StagedProposal(
            proposal_id=f"sp-{seq:06d}",
            agent=self.agent,
            action_class=action_class,
            effects=effects,
            args=args,
            verification_evidence=verification_evidence,
            trigger_ref=trigger_ref,
        )
        self._index[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> StagedProposal | None:
        """Return the indexed proposal, or None if unknown."""
        return self._index.get(proposal_id)

    def pending(self) -> list[StagedProposal]:
        """All indexed proposals still awaiting disposition."""
        return [p for p in self._index.values() if p.disposition == "pending"]

    def mark_disposed(self, proposal_id: str, disposition_record: dict) -> StagedProposal:
        """Record a disposition: append a disposition record to the writer and return an updated copy."""
        current = self._index.get(proposal_id)
        if current is None:
            raise KeyError(f"unknown proposal_id {proposal_id!r}")
        self.writer.append(
            {"kind": "disposition", "proposal_id": proposal_id, "record": disposition_record}
        )
        updated = StagedProposal.model_validate(
            {**current.model_dump(), "disposition": "disposed", "disposition_record": disposition_record}
        )
        self._index[proposal_id] = updated
        return updated


# ---------------------------------------------------------------------------
# Disposition interface
# ---------------------------------------------------------------------------

DispositionPolicy = Literal["approve-all", "refuse-all", "standing-only", "escalate-all", "operator"]


class DispositionInterface:
    """Routes staged proposals; the operator is NEVER simulated here.

    The "operator" policy queues the proposal for a real operator decision;
    the operator decides via ``apply_operator_decision``. The ambient/factory
    never disposes.
    """

    def __init__(self, staging: StagingArea, standing_table: list[str]) -> None:
        self.staging = staging
        self.standing_table = list(standing_table)
        self._operator_queue: list[str] = []

    def route(self, proposal: StagedProposal, policy: DispositionPolicy) -> dict:
        """Route one proposal under a policy; returns {"proposal_id","decision","policy"}."""
        if policy == "approve-all":
            decision = "approved"
        elif policy == "refuse-all":
            decision = "refused"
        elif policy == "standing-only":
            decision = "approved" if proposal.action_class in self.standing_table else "staged"
        elif policy == "escalate-all":
            decision = "escalated"
        elif policy == "operator":
            decision = "queued"
            if proposal.proposal_id not in self._operator_queue:
                self._operator_queue.append(proposal.proposal_id)
        else:
            raise ValueError(f"unknown disposition policy {policy!r}")

        record = {
            "proposal_id": proposal.proposal_id,
            "decision": decision,
            "policy": policy,
        }
        # "queued" leaves the proposal pending; every other route disposes it.
        if decision != "queued":
            self.staging.mark_disposed(proposal.proposal_id, record)
        return record

    def pending_for_operator(self) -> list[str]:
        """Proposal ids awaiting a real operator decision."""
        return list(self._operator_queue)

    def apply_operator_decision(self, proposal_id: str, decision: str) -> dict:
        """Record the operator's actual decision on a queued proposal."""
        if decision not in ("approved", "refused", "escalated"):
            raise ValueError(f"invalid operator decision {decision!r}")
        if proposal_id not in self._operator_queue:
            raise KeyError(f"proposal_id {proposal_id!r} not queued for operator")
        self._operator_queue.remove(proposal_id)
        record = {
            "proposal_id": proposal_id,
            "decision": decision,
            "policy": "operator",
        }
        self.staging.mark_disposed(proposal_id, record)
        return record


# ---------------------------------------------------------------------------
# Orphan queue (structural orphan-triage policy, DR-CMD-081)
# ---------------------------------------------------------------------------

#: The only triage dispositions: an orphan leaves the queue exclusively
#: through one of these, always with a non-empty reason. Which orphan goes
#: where (shape-specific routing rules, aging thresholds) is the deferred
#: G6 — this structure presumes nothing about orphan shapes.
ORPHAN_TRIAGE_DISPOSITIONS = ("routed", "refused", "archived")


class OrphanTriageError(Exception):
    """Refuse-with-reasons: an invalid triage attempt. Nothing exits the
    orphan queue silently, and nothing exits it without reasons."""


class OrphanQueue:
    """The orphan queue: structural instantiation of the DR-5 orphan pattern
    (orphan queue + drain duty + closure bar, DR-CMD-081).

    An *orphan* is a staged proposal whose disposition record says
    ``"staged"`` — an admitted trigger that matched no standing disposition
    (DR-CMD-074 Item 5b: staged, not silently dropped) — with no
    superseding triage record.

    Queue membership is DERIVED from the append-only staging file on every
    call, never stored: because the file is append-only, the ONLY exit from
    the queue is a triage record, and :meth:`triage` is the only writer of
    triage records. The closure bar therefore holds by construction, not by
    convention: there is no removal API, and no code path can make an
    untriaged orphan stop being reported.

    The drain duty attaches to the coordinator (DR-CMD-081): its sweep plus
    staging-event wake already covers this substrate. Surfacing is
    :meth:`scan` — count + oldest age feed the coordinator's standing
    disclosure.
    """

    def __init__(self, writer: AccretionWriter) -> None:
        self.writer = writer

    def scan(self) -> list[dict]:
        """Untriaged orphans, oldest first.

        Each entry: ``{"proposal_id", "staged_seq", "agent",
        "action_class", "trigger_ref"}``. Deterministic: file order is seq
        order; no clocks.
        """
        proposals: dict[str, dict] = {}
        staged: dict[str, bool] = {}
        triaged: set[str] = set()
        if self.writer.file.exists():
            for line in self.writer.file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                payload = record["payload"]
                kind = payload.get("kind")
                if kind == "proposal":
                    pid = f"sp-{int(record['seq']):06d}"
                    proposals[pid] = {
                        "proposal_id": pid,
                        "staged_seq": int(record["seq"]),
                        "agent": payload.get("agent", "unknown"),
                        "action_class": payload.get("action_class", "unknown"),
                        "trigger_ref": payload.get("trigger_ref", "unknown"),
                    }
                elif kind == "disposition":
                    pid = payload.get("proposal_id")
                    if not pid:
                        continue
                    rec = payload.get("record", {})
                    if rec.get("decision") == "staged":
                        staged[pid] = True
                    if payload.get("triage") is True:
                        triaged.add(pid)
        return [
            proposals[pid]
            for pid in sorted(proposals, key=lambda p: proposals[p]["staged_seq"])
            if staged.get(pid) and pid not in triaged and pid in proposals
        ]

    def triage(self, proposal_id: str, disposition: str, reason: str,
               **extra: Any) -> dict:
        """Triage one orphan: append the superseding triage record.

        ``disposition`` must be one of ``ORPHAN_TRIAGE_DISPOSITIONS``;
        ``reason`` must be non-empty; ``proposal_id`` must be currently
        untriaged. ``extra`` carries the routing target for ``"routed"``
        (e.g. ``route_to="analyst"``) — supplied by the caller, never
        presumed by this structure. Raises :class:`OrphanTriageError`
        otherwise: refuse-with-reasons, never silent.

        Session-independent: operates at the accretion-file level, like the
        queue derivation itself, so orphans survive restarts triageable.
        """
        if disposition not in ORPHAN_TRIAGE_DISPOSITIONS:
            raise OrphanTriageError(
                f"unknown triage disposition {disposition!r}; must be one of "
                f"{ORPHAN_TRIAGE_DISPOSITIONS}")
        if not reason or not reason.strip():
            raise OrphanTriageError(
                f"triage of {proposal_id!r} refused: reason is required")
        untriaged = {o["proposal_id"] for o in self.scan()}
        if proposal_id not in untriaged:
            raise OrphanTriageError(
                f"triage of {proposal_id!r} refused: not an untriaged orphan")
        record = {"kind": "disposition", "proposal_id": proposal_id,
                  "triage": True,
                  "record": {"decision": disposition,
                             "reason": reason.strip(), **extra}}
        self.writer.append(record)
        return record["record"]


# ---------------------------------------------------------------------------
# Backend binding (spec §6; Q1 facility handle explicitly stubbed)
# ---------------------------------------------------------------------------

class InferenceParams(BaseModel, frozen=True):
    """D3-derived inference parameters for the harness inference facility."""
    temperature: float
    seed: int | None
    model_pin: str
    wall_clock_dependent: bool


class BackendNotBound(Exception):
    """Raised when inference is attempted with no concrete facility bound."""
    pass


class ModelBackend(ABC):
    """Abstract harness inference facility interface (spec §6)."""

    @abstractmethod
    def infer(self, prompt: str, params: InferenceParams) -> str:
        """infer(prompt, params) -> completion."""
        ...


class StubModelBackend(ModelBackend):
    """Q1: concrete facility binding explicitly stubbed — never silently usable."""

    def infer(self, prompt: str, params: InferenceParams) -> str:
        raise BackendNotBound("Q1: no concrete inference facility bound (stub)")


class BackendBinding:
    """Substrate component 2: the agent's handle to the harness inference facility."""

    def __init__(self, params: InferenceParams, backend: ModelBackend | None = None) -> None:
        self.params = params
        self.backend = backend if backend is not None else StubModelBackend()

    def infer(self, prompt: str) -> str:
        """Delegate to the bound backend, or raise BackendNotBound."""
        return self.backend.infer(prompt, self.params)


# ---------------------------------------------------------------------------
# Boundary verifiers (D7 trust boundaries)
# ---------------------------------------------------------------------------

class CheckResult(BaseModel, frozen=True):
    """Result of one trust-boundary check."""
    passed: bool
    evidence: str


class HaltAndStage(Exception):
    """Raised by fail-closed verifiers on check failure: halt and stage instead of acting."""

    def __init__(self, proposal_id: str, reason: str) -> None:
        super().__init__(reason)
        self.proposal_id = proposal_id
        self.reason = reason


class BoundaryVerifier(ABC):
    """D7 trust-boundary verifier component: check, then apply a failure policy.

    Failure policies: "escalate" (fail closed at the boundary — escalate),
    "fail_closed" (raise HaltAndStage), "fail_open" (continue; the caller
    logs the failure).
    """

    target: str  # set as a class attribute on subclasses

    def __init__(self, on_failure: str = "escalate", check_fn=None) -> None:
        if on_failure not in ("escalate", "fail_closed", "fail_open"):
            raise ValueError(f"unknown on_failure policy {on_failure!r}")
        self.on_failure = on_failure
        self.check_fn = check_fn  # optional: (dict) -> CheckResult | None

    def check(self, context: dict) -> CheckResult:
        """Run the injected check_fn if given, else the subclass default check."""
        if self.check_fn is not None:
            result = self.check_fn(context)
            if result is not None:
                return result
        return self._default_check(context)

    def _default_check(self, context: dict) -> CheckResult:
        """Base default: no default check defined — passes vacuously."""
        return CheckResult(passed=True, evidence="no default check")

    def apply_policy(self, result: CheckResult, proposal_id: str) -> str:
        """Map a check result to "continue" | "staged" | "escalated".

        passed -> "continue"; failed + fail_closed -> raise HaltAndStage;
        failed + fail_open -> "continue" (caller logs); failed + escalate ->
        "escalated".
        """
        if result.passed:
            return "continue"
        if self.on_failure == "fail_closed":
            raise HaltAndStage(proposal_id, result.evidence)
        if self.on_failure == "fail_open":
            return "continue"
        return "escalated"


class IntentVerifier(BoundaryVerifier):
    """Verifies the intent presented is the principal's (intent_target)."""

    target = "intent"

    def _default_check(self, context: dict) -> CheckResult:
        principal = context.get("principal", "unknown")
        passed = context.get("intent_authentic") is True
        return CheckResult(
            passed=passed,
            evidence=f"intent {'authentic' if passed else 'NOT authentic'} for principal {principal}",
        )


class EventVerifier(BoundaryVerifier):
    """Verifies the integrity of the trace itself (event_target)."""

    target = "event"

    def _default_check(self, context: dict) -> CheckResult:
        try:
            event_log = context["event_log"]
        except KeyError:
            return CheckResult(passed=False, evidence="no event log in context")
        passed = event_log.verify_chain() is True
        return CheckResult(
            passed=passed,
            evidence=f"event log chain {'intact' if passed else 'BROKEN'}",
        )


class WorldVerifier(BoundaryVerifier):
    """Verifies independent corroboration of world claims (world_target)."""

    target = "world"

    def _default_check(self, context: dict) -> CheckResult:
        passed = context.get("corroborated") is True
        return CheckResult(
            passed=passed,
            evidence=f"world claims {'corroborated' if passed else 'uncorroborated'}",
        )


class TriggerVerifier(BoundaryVerifier):
    """Verifies the trigger passed its activation gate (trigger_target)."""

    target = "trigger"

    def _default_check(self, context: dict) -> CheckResult:
        passed = context.get("gate_admitted") is True
        return CheckResult(
            passed=passed,
            evidence=f"trigger {'admitted' if passed else 'NOT admitted'} by activation gate",
        )
