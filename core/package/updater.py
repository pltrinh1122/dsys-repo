"""Release-monitor automaton — the adopted updater expansion (DR-CMD-035).

Contents:
  - Pydantic v2 source models (DR-CMD-028): MonitorState, MonitorTransition,
    ReleaseMonitorFlow, and the authoritative RELEASE_MONITOR instance
    (spec §1: 9 states, 16 transitions — K1 added the `committing` state).
  - compile_flow(): the updater's compilation path from source models to
    AutomatonFlow / FlowState / FlowTransition entities, executed by FlowRun
    (DR-CMD-030). The generic bridge remains a future governed matter; this
    function is deliberately shaped so the bridge can generalize it.
  - The six run-books' tool implementations (zero inference throughout).
  - A minimal deterministic driver + an AST-allowlisted guard evaluator
    (the v1 expression-language decision, scoped to the guards used here).
  - The production-drive contract (DR-CMD-050): the gated entry point
    production_drive() with the DriveInitiation record and the I-26
    authorized-initiation predicate (spec D1–D7, R3).
  - replay(): re-derivation of the state path from the FlowTransitionEvent
    log with tools and network disabled (R1).

All behavior here is mechanical: poll, compare, verify, invoke, record.
"""
from __future__ import annotations

import ast
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schema import (
    AutomatonFlow,
    AutomatonRun,
    FlowState,
    FlowTransition,
    FlowTransitionEvent,
    RunBook,
    Step,
    SystemState,
    Tool,
)

FLOW_ID = "flow-release-monitor"
RELEASE_VERSION = "0.1.0"

Trigger = Literal["timer", "run_completed", "run_aborted", "external"]
StateKind = Literal["task", "wait", "end"]
EndOutcome = Literal["completed", "aborted"]


# ---------------------------------------------------------------------------
# Source models (pydantic v2 — the DR-CMD-028 pin)
# ---------------------------------------------------------------------------

class MonitorState(BaseModel):
    """One FSM state — compiles to FlowState."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: StateKind
    runbook_id: str | None = None  # required iff kind == 'task'
    step_policy: str | None = None  # iff kind == 'task': abort | skip | retry:<n>
    outcome: EndOutcome | None = None  # iff kind == 'end'


class MonitorTransition(BaseModel):
    """One guarded edge — compiles to FlowTransition."""

    model_config = ConfigDict(frozen=True)

    from_state: str
    trigger: Trigger
    guard: str | None = None  # AST-allowlisted expr over payload.*
    to_state: str


class ReleaseMonitorFlow(BaseModel):
    """The release-monitor automaton — compiles to AutomatonFlow + entities."""

    model_config = ConfigDict(frozen=True)

    name: Literal["release-monitor"] = "release-monitor"
    release_version: str
    initial_state: str = "idle"
    states: list[MonitorState] = Field(min_length=1)
    transitions: list[MonitorTransition] = Field(min_length=1)


RELEASE_MONITOR = ReleaseMonitorFlow(
    release_version=RELEASE_VERSION,
    states=[
        MonitorState(name="idle", kind="wait"),
        MonitorState(name="checking", kind="task",
                     runbook_id="rb-release-check", step_policy="retry:3"),
        MonitorState(name="candidate", kind="task",
                     runbook_id="rb-release-verify", step_policy="abort"),
        MonitorState(name="gate", kind="task",
                     runbook_id="rb-policy-gate", step_policy="abort"),
        MonitorState(name="driving", kind="task",
                     runbook_id="rb-release-drive", step_policy="abort"),
        MonitorState(name="verifying", kind="task",
                     runbook_id="rb-release-verify-installed",
                     step_policy="abort"),
        MonitorState(name="committing", kind="task",
                     runbook_id="rb-accretion-commit",
                     step_policy="abort"),  # K1 repair (DR-CMD-039)
        MonitorState(name="done", kind="end", outcome="completed"),
        MonitorState(name="failed", kind="end", outcome="aborted"),
    ],
    transitions=[
        MonitorTransition(from_state="idle", trigger="timer",
                          to_state="checking"),
        MonitorTransition(from_state="checking", trigger="run_completed",
                          guard="payload.remote_version != payload.installed_version",
                          to_state="candidate"),
        MonitorTransition(from_state="checking", trigger="run_completed",
                          guard="payload.remote_version == payload.installed_version",
                          to_state="idle"),
        MonitorTransition(from_state="checking", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="candidate", trigger="run_completed",
                          to_state="gate"),
        MonitorTransition(from_state="candidate", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="gate", trigger="run_completed",
                          guard="payload.decision == 'drive'",
                          to_state="driving"),
        MonitorTransition(from_state="gate", trigger="run_completed",
                          guard="payload.decision == 'defer'",
                          to_state="idle"),
        MonitorTransition(from_state="gate", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="driving", trigger="run_completed",
                          to_state="verifying"),
        MonitorTransition(from_state="driving", trigger="run_aborted",
                          to_state="failed"),
        MonitorTransition(from_state="verifying", trigger="run_completed",
                          guard="payload.doctor_ok and payload.promotion_recorded",
                          to_state="committing"),  # K1: was `done`
        MonitorTransition(from_state="verifying", trigger="run_completed",
                          guard="not (payload.doctor_ok and payload.promotion_recorded)",
                          to_state="failed"),
        MonitorTransition(from_state="verifying", trigger="run_aborted",
                          to_state="failed"),
        # K1 repair (DR-CMD-039): the commit is governed — `committing`
        # captures the complete record (verification outcome known) before
        # the terminal state. The message never names `done`: terminality
        # follows from the transition taken out of `committing`.
        MonitorTransition(from_state="committing", trigger="run_completed",
                          guard="payload.commit_confirmed",
                          to_state="done"),
        MonitorTransition(from_state="committing", trigger="run_aborted",
                          to_state="failed"),
    ],
)


# ---------------------------------------------------------------------------
# Compilation: source models -> AutomatonFlow / FlowState / FlowTransition
# ---------------------------------------------------------------------------

def _state_id(name: str) -> str:
    return f"urm-{name}"


def compile_flow(flow: ReleaseMonitorFlow = RELEASE_MONITOR):
    """Compile the source model into entities. Returns
    (AutomatonFlow, [FlowState], [FlowTransition], [RunBook], [Step], [Tool])."""
    aflow = AutomatonFlow(
        id=FLOW_ID, name=flow.name, release_version=flow.release_version,
        initial_state_id=_state_id(flow.initial_state))
    states = [
        FlowState(
            id=_state_id(s.name), flow_id=FLOW_ID, name=s.name, kind=s.kind,
            runbook_id=s.runbook_id, outcome=s.outcome,
            step_policy=s.step_policy)
        for s in flow.states
    ]
    transitions = [
        FlowTransition(
            id=f"urmt-{i + 1:02d}", flow_id=FLOW_ID,
            from_state_id=_state_id(t.from_state), trigger=t.trigger,
            guard=t.guard, to_state_id=_state_id(t.to_state))
        for i, t in enumerate(flow.transitions)
    ]
    runbooks, steps, tools = _runbook_entities()
    return aflow, states, transitions, runbooks, steps, tools


def _runbook_entities():
    """The six run-books as RunBook/Step/Tool entities. Steps are strictly
    sequential; each step is an (allowlisted expr, tool) pair."""
    specs = [
        ("rb-release-check", [("True", "tool-fetch-feed"),
                              ("True", "tool-compare-versions")]),
        ("rb-release-verify", [("True", "tool-verify-checksum")]),
        ("rb-policy-gate", [("True", "tool-read-policy")]),
        ("rb-release-drive", [("True", "tool-invoke-installer")]),
        ("rb-release-verify-installed", [("True", "tool-run-doctor"),
                                        ("True", "tool-record-promotion")]),
        ("rb-accretion-commit", [("True", "tool-commit-accretion")]),  # K1
    ]
    runbooks, steps, tools = [], [], []
    seen_tools: set[str] = set()
    for rb_id, step_specs in specs:
        runbooks.append(RunBook(id=rb_id, release_version=RELEASE_VERSION,
                                name=rb_id))
        for seq, (expr, tool_id) in enumerate(step_specs, start=1):
            steps.append(Step(id=f"{rb_id}-s{seq}", runbook_id=rb_id, seq=seq,
                              expr=expr, tool_id=tool_id))
            if tool_id not in seen_tools:
                seen_tools.add(tool_id)
                tools.append(Tool(id=tool_id, name=tool_id))
    return runbooks, steps, tools


# ---------------------------------------------------------------------------
# World (fixture) + tools — zero inference
# ---------------------------------------------------------------------------

class ToolAborted(Exception):
    """A tool refused its work: the run-book run aborts (run_aborted)."""


class NetworkDisabled(Exception):
    """The feed poll attempted a network touch while disabled (replay)."""


@dataclass
class World:
    """Everything outside the machine the golden run scripts."""
    feed_version: str = "0.1.1"
    feed_sha256: str = "sha256:feed-bytes-fixture"
    feed_checksum_ok: bool = True
    installed_version: str = "0.1.0"
    updater_policy: str = "auto"  # auto | notify | off
    auto_max_bump: str = "patch"  # patch | minor | major
    poll_interval_s: int = 3600
    network_enabled: bool = True
    doctor_ok: bool = True
    installer_exit_code: int = 0  # nonzero -> the drive fails, loudly
    installer_invocations: list[str] = field(default_factory=list)
    installer_argvs: list[list[str]] = field(default_factory=list)  # K2 repair
    # K2 repair: the install-home concept. The drive's installer invocation
    # explicitly resumes the previous installation's accretion repo (D1).
    install_home: str = "/home/op/dsys-inst"  # own home (first install)
    prev_install_home: str | None = None      # previous install's home
    prev_accretion_path: str | None = None    # its config accretion.path
    accretion_writable: bool = True           # fixture: can the path be written
    promotions: list[dict] = field(default_factory=list)
    surfaced: list[dict] = field(default_factory=list)  # notify/off observations
    # K1 repair (DR-CMD-039): the fixture accretion repo. Each commit is a
    # dict {payload, payload_hash, message, first_seq, last_seq,
    # promotions_through}. The fixture models the repo's contract —
    # append-only, content-hash named — not git's bytes; the writer only
    # ever appends (D6). The production tool shells out to real git; the
    # golden run pins the contract the production tool must honor.
    accretion_commits: list[dict] = field(default_factory=list)
    git_available: bool = True  # K1 D5a: git is a hard dependency
    # K1 Q3a (DR-CMD-047): the identity binding. The installation
    # manifest records accretion_repo.identity (the minter's record,
    # D1); the repo's git config carries dsys.repo-id (the handle's
    # identity, D2). None = the key is absent on that side. The
    # fixture's World is an installed system, so __post_init__ mints
    # both sides consistently; a golden-run case breaks one side to
    # exercise the refusal.
    manifest_repo_identity: str | None = None
    accretion_repo_id: str | None = None
    # K1 D3: standing (default — the operator's standing disposition covers
    # journaling) | operator (autonomous drive cannot prompt: refuse).
    accretion_commit_authority: str = "standing"

    def __post_init__(self):
        # K1 Q3a D1: installation mints the repo identity once and
        # records it in both places. The default World is an installed
        # system; an explicit one-sided construction is a deliberate
        # (possibly broken) scenario and is left untouched.
        if (self.manifest_repo_identity is None
                and self.accretion_repo_id is None):
            minted = mint_repo_identity()
            self.manifest_repo_identity = minted
            self.accretion_repo_id = minted


def mint_repo_identity() -> str:
    """K1 Q3a D1: the installer mints the repo UUID (UUIDv4). The
    golden-run fixture performs the mint on the installer's behalf —
    the contract (field, format, write-both-places) is what is pinned;
    the installer-spec implements the real mint."""
    return str(uuid.uuid4())


def _bump(old: str, new: str) -> str:
    """Classify the bump old->new. Defensive: real-world versions carry
    suffixes ('1.2.3-rc1') and uneven segment counts; parse leading
    digits per segment, pad short, compare major/minor/rest."""

    def nums(v: str) -> list[int]:
        out = []
        for seg in v.split("."):
            digits = ""
            for ch in seg:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            out.append(int(digits) if digits else 0)
        return out

    o, n = nums(old), nums(new)
    width = max(len(o), len(n))
    o += [0] * (width - len(o))
    n += [0] * (width - len(n))
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"


_BUMP_ORDER = {"patch": 0, "minor": 1, "major": 2}


def _tool_fetch_feed(ctx: dict, w: World) -> None:
    if not w.network_enabled:
        raise NetworkDisabled("feed poll attempted with network disabled")
    # The sole network touch: one GET of the pinned feed. Nothing leaves.
    ctx["feed_sha256"] = w.feed_sha256
    ctx["remote_version"] = w.feed_version
    ctx["feed_checksum"] = w.feed_sha256 if w.feed_checksum_ok else "sha256:tampered"


def _tool_compare_versions(ctx: dict, w: World) -> None:
    ctx["installed_version"] = w.installed_version
    # Guards compare payload.remote_version != payload.installed_version.


def _tool_verify_checksum(ctx: dict, w: World) -> None:
    if ctx.get("feed_checksum") != w.feed_sha256:
        raise ToolAborted("checksum mismatch: no candidacy")


def _tool_read_policy(ctx: dict, w: World) -> None:
    policy = w.updater_policy
    if policy == "auto":
        bump = _bump(ctx["installed_version"], ctx["remote_version"])
        if _BUMP_ORDER[bump] <= _BUMP_ORDER[w.auto_max_bump]:
            ctx["decision"] = "drive"
            ctx["reason"] = f"policy=auto, bump={bump} within {w.auto_max_bump}"
        else:
            ctx["decision"] = "defer"
            ctx["reason"] = f"policy=auto but bump={bump} exceeds {w.auto_max_bump}"
            w.surfaced.append({"version": ctx["remote_version"],
                               "reason": ctx["reason"]})
    elif policy == "notify":
        ctx["decision"] = "defer"
        ctx["reason"] = "policy=notify: surfaced, not driven"
        w.surfaced.append({"version": ctx["remote_version"],
                           "reason": ctx["reason"]})
    elif policy == "off":
        ctx["decision"] = "defer"
        ctx["reason"] = "policy=off: recorded only"
    else:
        # Unknown policy is a config error: abort loudly. Silently
        # degrading to 'off' would hide a typo'd policy ('autoo').
        raise ToolAborted(f"unknown updater policy: {policy!r}")


def _accretion_path(w: World) -> str:
    # K2 repair D1: the previous install's effective accretion path —
    # its config override when known, else the default rule over the
    # previous home's basename. First install (no previous home): derive
    # from our own home. Always explicit — never ambient defaults.
    if w.prev_accretion_path:
        return w.prev_accretion_path
    home = w.prev_install_home or w.install_home
    return "/var/daccretion/" + home.strip("/").split("/")[-1]


def _tool_invoke_installer(ctx: dict, w: World) -> None:
    # The composed perform step: install.sh --release <version>
    # --accretion-path <explicit> --accretion-required (K2 repair).
    # The drive always passes the explicit path (never --overwrite: D5)
    # and always fail-closed (D2): an unwritable path refuses the drive
    # rather than warn-and-continue under autonomous operation (D3).
    version = ctx["remote_version"]
    acc_path = _accretion_path(w)
    argv = ["install.sh", "--release", version,
            "--accretion-path", acc_path, "--accretion-required"]
    w.installer_argvs.append(argv)
    w.installer_invocations.append(version)
    if not w.accretion_writable:
        # The world models the installer faithfully: fail-closed accretion
        # fails the install before converge — nothing is written, nothing
        # is adopted, the drive refuses loudly.
        raise ToolAborted(
            f"accretion path not writable: {acc_path} (--accretion-required)")
    if w.installer_exit_code != 0:
        # The drive fails; the version does NOT converge (world models the
        # installer faithfully: a failed install changes nothing).
        raise ToolAborted(
            f"installer exited {w.installer_exit_code} for {version}")
    w.installed_version = version  # the world converges, like the installer
    ctx["exit_code"] = 0


def _tool_run_doctor(ctx: dict, w: World) -> None:
    ctx["doctor_ok"] = w.doctor_ok


def _tool_record_promotion(ctx: dict, w: World) -> None:
    # The promotion bridge records the step-change. The accretion commit is
    # the installer's own discipline — mirrored here as a world fact.
    # (K1, updater-spec §9: that assignment covers install-time state only;
    # the updater's inter-install event log has no writer in this build.)
    if ctx.get("doctor_ok"):
        w.promotions.append({"version": w.installed_version,
                             "feed_sha256": w.feed_sha256})
        ctx["promotion_recorded"] = True
    else:
        ctx["promotion_recorded"] = False


# ---------------------------------------------------------------------------
# K1 repair (DR-CMD-039): the updater's accretion writer
# ---------------------------------------------------------------------------

def canonical_payload(run_id: str, source_state: str, events: list[dict],
                      promotions: list[dict], decision: dict,
                      verification: dict) -> str:
    """Q1 (build detail, pinned by the golden run): the canonical byte form
    of an accretion commit payload. Sorted keys, compact separators —
    deterministic bytes from deterministic events (D5). Replay identity is
    these bytes (D5's payload/envelope distinction): the git envelope —
    author/committer timestamps, commit hash — is transport, never replay
    identity."""
    payload = {
        "schema": "accretion-commit/v1",
        "flow_run_id": run_id,
        "source_state": source_state,
        "event_range": {"first_seq": events[0]["seq"],
                        "last_seq": events[-1]["seq"]},
        "events": events,
        "promotions": promotions,
        "policy_decision": decision,
        "verification": verification,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _tool_commit_accretion(ctx: dict, w: World) -> None:
    """The accretion writer: commits the cumulative event frontier to the
    accretion repo (D4 — all events since the last commit, located via the
    watermark, not just this run's). Pure function of the logged events
    (D5); git is a hard dependency (D5a); standing authority commits
    without asking while operator authority refuses (D3); append-only
    (D6); abort, not retry — the next drive's cumulative commit is the
    retry (D4a). The driver's `_commit_input` (popped here, never emitted)
    carries the flow log the writer diffs against the watermark."""
    if not w.git_available:
        raise ToolAborted("git not available: the drive's durability "
                          "guarantee rests on git (D5a) — refusing")
    # D3 (K1 Q3a, DR-CMD-047): the identity check extends D5a. Before
    # every write, the handle's repo identity (dsys.repo-id) must equal
    # the manifest-recorded accretion_repo.identity; mismatch — or a
    # missing key on either side — fails closed: abort, not retry
    # (D4a), no commit, run_aborted -> failed.
    bad_binding = i25_identity_binding(w.manifest_repo_identity,
                                       w.accretion_repo_id,
                                       w.git_available)
    if bad_binding:
        raise ToolAborted("identity binding failed (D3): "
                          + "; ".join(bad_binding))
    if w.accretion_commit_authority == "operator":
        # Autonomous operation cannot prompt (no terminal): refuse loudly,
        # never silently skip (D3 — composes with K2's fail-closed
        # philosophy, DR-CMD-038).
        raise ToolAborted("accretion.commit_authority=operator: no terminal "
                          "to prompt on — refusing the commit")
    if w.accretion_commit_authority != "standing":
        raise ToolAborted("unknown accretion commit authority: "
                          f"{w.accretion_commit_authority!r}")
    inp = ctx.pop("_commit_input", None)
    if inp is None:
        raise ToolAborted("committing run-book invoked without the driver's "
                          "event-log input — modeling fault")
    if inp.get("kind") == "simulation":
        # I-22 (DR-CMD-041): simulation transcripts are ontologically
        # separate from production records. The writer structurally cannot
        # accept them — separation is not a marking convention the writer
        # could ignore (D7).
        raise ToolAborted("I-22: kind=simulation transcripts are not "
                          "committable to the accretion repo")
    events = inp["events"]  # the flow log, seq order
    watermark = (w.accretion_commits[-1]["last_seq"]
                 if w.accretion_commits else 0)
    new_events = [e for e in events if e["seq"] > watermark]
    if not new_events:
        # D4: a commit is skipped when there is nothing to commit (the
        # installer's rule). The step completes — confirmed, nothing written.
        ctx["commit_confirmed"] = True
        ctx["commit_skipped"] = True
        return
    prev_through = (w.accretion_commits[-1]["promotions_through"]
                    if w.accretion_commits else 0)
    payload = canonical_payload(
        inp["run_id"], inp["source_state"], new_events,
        w.promotions[prev_through:],
        {"decision": ctx.get("decision"), "reason": ctx.get("reason")},
        {"doctor_ok": ctx.get("doctor_ok"),
         "promotion_recorded": ctx.get("promotion_recorded")})
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    first, last = new_events[0]["seq"], new_events[-1]["seq"]
    # D4: the message names the flow-run id and the source state —
    # terminality follows from the transition taken out of `committing`,
    # so the message never claims a terminal state the drive hasn't reached.
    message = (f"accretion: {inp['run_id']} from {inp['source_state']} "
               f"events {first}-{last} payload {payload_hash[:12]}")
    # D6: append-only — the writer only ever appends; no amend, no rebase.
    w.accretion_commits.append({
        "payload": payload,
        "payload_hash": payload_hash,
        "message": message,
        "first_seq": first,
        "last_seq": last,
        "promotions_through": len(w.promotions),
    })
    ctx["commit_confirmed"] = True
    ctx["commit_skipped"] = False
    ctx["payload_hash"] = payload_hash
    ctx["commit_event_range"] = [first, last]


def i18_commit_completeness(commits_before: list[dict],
                            commits_after: list[dict],
                            flow_events: list[dict]) -> list[str]:
    """I-18 (K1, DR-CMD-039): every drive reaching `committing` leaves
    exactly one commit, covering exactly the events since the last commit
    (the cumulative frontier — gapless from the previous watermark, and the
    payload honestly embeds precisely the events it claims). The drive's
    terminal edge rides the *next* drive's commit (D4b) — it is covered by
    the frontier check, not by this commit."""
    v: list[str] = []
    new = commits_after[len(commits_before):]
    if len(new) != 1:
        v.append(f"I-18: drive reaching committing left {len(new)} commits, "
                 f"expected exactly one")
        return v
    c = new[0]
    prev_last = commits_before[-1]["last_seq"] if commits_before else 0
    if c["first_seq"] != prev_last + 1:
        v.append(f"I-18: commit starts at {c['first_seq']}, expected "
                 f"{prev_last + 1} (gapless from the watermark)")
    claimed = json.loads(c["payload"])["events"]
    actual = [e for e in flow_events
              if prev_last < e["seq"] <= c["last_seq"]]
    if claimed != actual:
        v.append("I-18: committed payload does not embed exactly the events "
                 f"in its claimed range {c['first_seq']}-{c['last_seq']}")
    if flow_events and c["last_seq"] > max(e["seq"] for e in flow_events):
        v.append("I-18: commit claims events beyond the flow log")
    return v


def i19_payload_canonicity(commit: dict) -> list[str]:
    """I-19 (K1): the committed payload is byte-equal to the canonical
    serialization of the events since the last commit — replay identity is
    the payload bytes (D5), never the git envelope."""
    v: list[str] = []
    payload = json.loads(commit["payload"])
    if commit["payload"] != canonical_payload(
            payload["flow_run_id"], payload["source_state"], payload["events"],
            payload["promotions"], payload["policy_decision"],
            payload["verification"]):
        v.append("I-19: committed payload is not the canonical serialization "
                 "of its claimed inputs")
    if commit["payload_hash"] != hashlib.sha256(
            commit["payload"].encode()).hexdigest():
        v.append("I-19: payload_hash does not name the payload bytes")
    return v


def i20_append_only(commits: list[dict]) -> list[str]:
    """I-20 (K1): no committed payload is ever mutated — the tamper-evident
    form of append-only (D6): every stored payload still hashes to its
    content-hash name, and commit ranges never overlap."""
    v: list[str] = []
    for i, c in enumerate(commits):
        if c["payload_hash"] != hashlib.sha256(
                c["payload"].encode()).hexdigest():
            v.append(f"I-20: commit {i} payload mutated (hash mismatch) — "
                     f"history was rewritten")
    for a, b in zip(commits, commits[1:]):
        if b["first_seq"] <= a["last_seq"]:
            v.append(f"I-20: overlapping commit ranges "
                     f"{a['first_seq']}-{a['last_seq']} and "
                     f"{b['first_seq']}-{b['last_seq']}")
    return v


def i25_identity_binding(manifest_identity: str | None,
                         repo_identity: str | None,
                         git_available: bool) -> list[str]:
    """I-25 (K1 Q3a, DR-CMD-047): the committing tool writes only to a
    handle whose repo identity (dsys.repo-id) equals the
    manifest-recorded accretion_repo.identity. A predicate over
    (manifest, handle), not a procedure. Violations: identity missing
    on either side; mismatch; the D5a conjunct (the handle is not a
    git repo)."""
    v: list[str] = []
    if not git_available:
        v.append("I-25: handle is not a git repo (D5a conjunct)")
    if manifest_identity is None:
        v.append("I-25: manifest records no accretion_repo.identity")
    if repo_identity is None:
        v.append("I-25: handle has no dsys.repo-id (missing key)")
    if (manifest_identity is not None and repo_identity is not None
            and manifest_identity != repo_identity):
        v.append("I-25: handle identity does not match the "
                 "manifest-recorded identity")
    return v


TOOLS: dict[str, Callable[[dict, World], None]] = {
    "tool-fetch-feed": _tool_fetch_feed,
    "tool-compare-versions": _tool_compare_versions,
    "tool-verify-checksum": _tool_verify_checksum,
    "tool-read-policy": _tool_read_policy,
    "tool-invoke-installer": _tool_invoke_installer,
    "tool-run-doctor": _tool_run_doctor,
    "tool-record-promotion": _tool_record_promotion,
    "tool-commit-accretion": _tool_commit_accretion,  # K1 repair (DR-CMD-039)
}


# ---------------------------------------------------------------------------
# Guard evaluator — AST allowlist over payload.* (v1 expression language)
# ---------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Attribute,
    ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq, ast.And, ast.Or,
    ast.Not,
)


class _Payload:
    def __init__(self, d: dict):
        self.__dict__["_d"] = d

    def __getattr__(self, name: str):
        try:
            return self.__dict__["_d"][name]
        except KeyError:
            raise AttributeError(f"payload has no attribute {name!r}")


def eval_guard(guard: str | None, payload: dict) -> bool:
    """Evaluate an allowlisted guard. None (guardless) counts as true."""
    if guard is None:
        return True
    tree = ast.parse(guard, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"guard uses non-allowlisted syntax: "
                             f"{type(node).__name__}")
        if isinstance(node, ast.Name) and node.id != "payload":
            raise ValueError(f"guard may only reference payload, "
                             f"got '{node.id}'")
    code = compile(tree, "<guard>", "eval")
    return bool(eval(code, {"__builtins__": {}}, {"payload": _Payload(payload)}))


# ---------------------------------------------------------------------------
# Driver — advances a FlowRun through the compiled entities
# ---------------------------------------------------------------------------

def _payload_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def drive(s: SystemState, world: World, run_id: str = "fr-updater",
          max_steps: int = 50, until: str | None = None) -> list[str]:
    """Advance the release-monitor FlowRun.

    Runs to an end state by default. `until` stops early when the run
    returns to the named state after at least one transition — for the
    monitor's non-terminating regime (notify/off, or a deferred bump):
    under those policies the correct steady-state behavior is the
    watch cycle itself, so the golden run observes one cycle.
    """
    flow_id = FLOW_ID
    try:
        run = s.flow_runs[run_id]
    except KeyError:
        raise ValueError(f"unknown flow run: {run_id}") from None
    trans = [t for t in s.flow_transitions.values() if t.flow_id == flow_id]
    path = [run.current_state_id]
    seq = len(s.flow_transition_events) + 1
    ar_n = 0
    # The accumulator: payload data flows between states by merging each
    # state's emitted context snapshot (the full ctx at that state, stored
    # as the event payload). Replay re-derives the same accumulator by
    # merging the logged snapshots in seq order.
    accum: dict = {}

    for _ in range(max_steps):
        st = s.flow_states[run.current_state_id]
        if st.kind == "end":
            run = run.model_copy(update={
                "state": "done" if st.outcome == "completed" else "aborted"})
            s.flow_runs[run_id] = run
            return path
        if st.kind == "wait":
            trigger, emitted = "timer", {"tick": world.poll_interval_s}
        else:
            ar_n += 1
            ar_id = f"{run_id}-ar{ar_n}"
            s.automaton_runs[ar_id] = AutomatonRun(
                id=ar_id, runbook_id=st.runbook_id, state="running",
                idempotency_key=f"{run_id}:{st.id}:{ar_n}",
                parent_flow_run_id=run_id, flow_state_id=st.id)
            try:
                ctx_in = dict(accum)
                if st.runbook_id == "rb-accretion-commit":
                    # K1 (D4): the committing run-book's input channel — the
                    # flow log the writer diffs against the commit watermark.
                    # Popped by the tool; never lands in the emitted payload.
                    flow_events = sorted(
                        (e for e in s.flow_transition_events.values()
                         if s.flow_runs[e.flow_run_id].flow_id == flow_id),
                        key=lambda e: e.seq)
                    ctx_in["_commit_input"] = {
                        "run_id": run_id,
                        "source_state": s.flow_states[path[-2]].name,
                        "events": [{
                            "seq": e.seq,
                            "from_state_id": e.from_state_id,
                            "to_state_id": e.to_state_id,
                            "trigger": e.trigger,
                            "payload": json.loads(e.payload),
                        } for e in flow_events],
                    }
                emitted = _run_runbook(s, st.runbook_id, world, ctx_in)
                trigger = "run_completed"
                new_ar_state = "completed"
            except _RunAborted as e:
                emitted = {"error": str(e)}
                trigger = "run_aborted"
                new_ar_state = "aborted"
            s.automaton_runs[ar_id] = s.automaton_runs[ar_id].model_copy(
                update={"state": new_ar_state})
        accum.update(emitted)
        # I-15 faults (ambiguity or no route) propagate loudly: a broken
        # flow definition must never masquerade as a normal run_aborted.
        nxt = _select(trans, run.current_state_id, trigger, accum, run_id)
        evt_id = f"{run_id}-e{seq}"
        s.flow_transition_events[evt_id] = FlowTransitionEvent(
            id=evt_id, flow_run_id=run_id, seq=seq,
            from_state_id=run.current_state_id, to_state_id=nxt,
            trigger=trigger, payload=_payload_json(emitted))
        seq += 1
        run = run.model_copy(update={"current_state_id": nxt})
        s.flow_runs[run_id] = run
        path.append(nxt)
        if until is not None and nxt == until:
            # One observed cycle of the non-terminating regime.
            return path
    raise RuntimeError("driver exceeded max steps without reaching an end state")


def _run_runbook(s: SystemState, runbook_id: str, world: World,
                 ctx: dict) -> dict:
    """Execute a run-book's steps in seq order starting from ctx (the
    accumulated payload). Steps invoke tools, which mutate ctx. A tool
    raising ToolAborted/NetworkDisabled aborts the run: the driver reports
    run_aborted. Returns ctx (the state's emitted payload, merged by the
    driver into the accumulator)."""
    steps = sorted(
        (st for st in s.steps.values() if st.runbook_id == runbook_id),
        key=lambda st: st.seq)
    try:
        for step in steps:
            if not eval_guard(step.expr, ctx):
                continue  # expr gates the step; 'True' always runs
            tool = TOOLS.get(step.tool_id)
            if tool is None:
                # Unknown tool is a modeling error: abort the run loudly,
                # never crash the driver with a KeyError.
                raise ToolAborted(f"unknown tool: {step.tool_id}")
            tool(ctx, world)
    except (ToolAborted, NetworkDisabled) as e:
        # Mark the failure on the child run, then propagate as run_aborted.
        raise _RunAborted(str(e)) from e
    return ctx


class _RunAborted(Exception):
    pass


def _select(trans: list, from_id: str, trigger: str, payload: dict,
            run_id: str) -> str:
    cands = [t for t in trans
             if t.from_state_id == from_id and t.trigger == trigger]
    winners = [t for t in cands if eval_guard(t.guard, payload)]
    if len(winners) != 1:
        # I-15: ambiguity (or no route) is a fault, not an ordering problem.
        raise _RunAborted(
            f"I-15 fault in {run_id}: {len(winners)} winners for "
            f"({from_id}, {trigger})")
    return winners[0].to_state_id


# ---------------------------------------------------------------------------
# Production-drive contract (DR-CMD-050, spec D1–D7): the gated entry
# point for production drives of the updater flow. The contract, not a
# driver entity (refused, F1/A2); stepping is AX2's strapped Harness,
# which `drive()` models. This block pins: the named initiator (D1),
# the principal binding (D3), the K3 tripwire (D4), the drive-resolved
# manifest identity (D5), the full-profile gate (D6), and the
# fail-closed aftermath (D7). I-26 is the R3 predicate.
# ---------------------------------------------------------------------------

class DriveRefused(Exception):
    """The drive was refused before starting: an I-26 violation or a
    non-full profile. Refusal is not failure — nothing ran, nothing
    was written, and the refusal is loud. The CLI maps this to exit 1
    naming the component (D6)."""


@dataclass
class DriveInitiation:
    """The initiation record (spec glossary): the drive transcript
    envelope's record of initiator, principal, and the drive-resolved
    manifest identity. Checked by I-26.

    origin: "operator-direct" (the human invoked the CLI) |
            "operator-instructed" (the ambient acted on the operator's
            explicit instruction — the operator's act through the
            ambient's hands) | "ambient" (the ambient on its own
            authority — K3 revived, refused by I-26).
    """
    initiator: str = "operator"
    origin: str = "operator-direct"
    principal: str = "dyad-or-human"
    harness_strapped: bool = True
    profile: str = "full"  # base | full (D6)
    manifest_identity: str | None = None  # drive-resolved at initiation (D5)


def i26_authorized_initiation(init: DriveInitiation) -> list[str]:
    """I-26 (DR-CMD-050): authorized initiation. A predicate over the
    initiation record, not a procedure. Violations: the initiator is not
    the operator principal (D1/D3); the origin is the ambient acting on
    its own authority (D4 — the K3 tripwire); the principal is not
    dyad-or-human (agents excluded); the drive was not invoked through
    a strapped Harness (AX1/AX2, D2)."""
    v: list[str] = []
    if init.initiator != "operator":
        v.append("I-26: initiator is not the operator principal")
    if init.origin == "ambient":
        v.append("I-26: ambient-originated initiation (D4: K3 revived)")
    if init.origin not in ("operator-direct", "operator-instructed",
                           "ambient"):
        v.append(f"I-26: unknown initiation origin: {init.origin!r}")
    if init.principal != "dyad-or-human":
        v.append("I-26: principal is not dyad-or-human (agents excluded)")
    if not init.harness_strapped:
        v.append("I-26: drive not invoked through a strapped "
                 "Harness (AX1/AX2)")
    return v


def production_drive(s: SystemState, world: World,
                     initiation: DriveInitiation,
                     run_id: str = "fr-drive",
                     max_steps: int = 50,
                     until: str | None = None) -> dict:
    """The production-drive contract's gated entry point. Returns the
    drive record: {initiation, state, path|None, events, surfaced|None}.

    - D6: a non-full profile refuses before anything runs (DriveRefused
      names the component; the CLI maps it to exit 1).
    - I-26: violations refuse before anything runs — the drive does not
      start (the K3 tripwire as a gate, not a comment).
    - D5: the manifest identity is resolved once, here, at initiation
      (process side); the committing tool's D3 check is a pure
      comparison against it (governed side — no file I/O in the tool).
    - D7: after fail-closed — no retry, no re-initiation. The failure is
      recorded in the drive record and surfaced; the next drive requires
      a new initiation (D1).
    """
    rec = {
        "initiator": initiation.initiator,
        "origin": initiation.origin,
        "principal": initiation.principal,
        "harness_strapped": initiation.harness_strapped,
        "profile": initiation.profile,
        # D5: the manifest read happens once, at initiation. The fixture
        # World's manifest_repo_identity is the installation manifest's
        # accretion_repo.identity, read here — not per write.
        "manifest_identity": world.manifest_repo_identity,
    }
    if initiation.profile != "full":
        raise DriveRefused(
            "the production-drive contract requires the full profile "
            f"(D6): profile={initiation.profile!r} refused")
    bad = i26_authorized_initiation(initiation)
    if bad:
        raise DriveRefused("unauthorized initiation (I-26): "
                           + "; ".join(bad))
    events_before = len(s.flow_transition_events)
    path = drive(s, world, run_id=run_id, max_steps=max_steps, until=until)
    run = s.flow_runs[run_id]
    events = len(s.flow_transition_events) - events_before
    if run.state == "aborted":
        # D7: the drive failed closed (e.g. the D3 check aborted the
        # commit). Record it, surface it, do not retry, do not
        # re-initiate — the wrapper returns; a new drive is a new
        # initiation.
        failure = {"kind": "drive_failed", "run_id": run_id,
                   "terminal": run.current_state_id, "initiation": rec}
        world.surfaced.append(failure)
        return {"initiation": rec, "state": "failed", "path": path,
                "events": events, "surfaced": failure}
    return {"initiation": rec, "state": "done", "path": path,
            "events": events, "surfaced": None}


# ---------------------------------------------------------------------------
# Replay (R1) — re-derive the state path from the event log; tools disabled
# ---------------------------------------------------------------------------

def replay(events: list[FlowTransitionEvent],
           transitions: list[FlowTransition],
           initial_state_id: str) -> list[str]:
    """Re-derive the state path from recorded events. Never invokes tools,
    never touches the network: guards are re-evaluated over recorded
    payloads and the recorded transition must be the unique winner."""
    by_from: dict[str, list[FlowTransition]] = {}
    for t in transitions:
        by_from.setdefault(t.from_state_id, []).append(t)
    path = [initial_state_id]
    current = initial_state_id
    merged: dict = {}  # the accumulator, re-derived by merging the log
    for e in sorted(events, key=lambda e: e.seq):
        if e.from_state_id != current:
            raise ValueError(f"replay: event {e.seq} starts at "
                             f"{e.from_state_id}, expected {current}")
        merged.update(json.loads(e.payload))
        cands = [t for t in by_from.get(current, [])
                 if t.trigger == e.trigger]
        winners = [t for t in cands if eval_guard(t.guard, merged)]
        if len(winners) != 1 or winners[0].to_state_id != e.to_state_id:
            raise ValueError(f"replay: event {e.seq} does not re-derive "
                             f"(winners={[w.id for w in winners]})")
        current = e.to_state_id
        path.append(current)
    return path


def path_hash(path: list[str]) -> str:
    return hashlib.sha256("\n".join(path).encode()).hexdigest()
