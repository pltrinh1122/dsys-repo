"""Scenario simulation — the adopted DR-CMD-041 expansion (ambient-authored).

The claim (S1): dsys gains ambient-authored scenario simulations such that
the ambient authors scenario specs from falsification-derived briefs, the
strapped driver executes them against sandbox copies, and scenarios meeting
a coverage criterion harden into regression cases only on operator
disposition — because the ambient's different adversarial priors discover
scenarios the operator wouldn't have enumerated.

What this module is:
  - the authorship pipeline's data: Brief, ScenarioSpec (declarative
    {actor, input, expect} turns — data, never code, D2), SimulationTranscript
    (kind=simulation at construction, D7), SandboxCopy, CoverageReport,
    HardenedCase, ScenarioSuite;
  - sandbox provisioning from the installation manifest as a driver step
    (D9): provision_sandbox;
  - the scenario-execution World factory with containment enforced at
    construction (I-21): make_scenario_world;
  - the minimal scenario interpreter the golden run drives as the strapped
    driver (D3): execute_scenario / adjudicate / run_scenario;
  - the four predicates, not procedures (R3): i21_containment,
    i22_transcript_separation, covers_new_pair (I-23), and the hardening
    gate inside harden (I-24);
  - the hardening pipeline: coverage_report + harden, with the G6-Q1
    standing-class enumeration (STANDING_HARDENING_CLASSES).

What this module is NOT: new execution machinery (D3 — the updater's own
driver executes; the golden run plays the strapped driver), a new CLI
surface (P1), a new network touch (P2), or an installer change (P4).

Coverage baseline (D4 reading): "the existing suite" is the scenario
regression suite this pipeline feeds (seeded + hardened cases) — not the
updater's golden run, which is a different matter's regression net. This is
the reading under which the adopted acceptances are jointly satisfiable:
A5's anti-flood ("rephrasing existing golden-run cases → I-23 fails")
refers to this suite's own cases (hardened scenarios join the golden run
per D5), and A6's K2-refusal scenario hardens because its pair is new to
this suite. Cross-suite novelty is not measured: the scenario suite
measures its own coverage.

G6 answers (carried to build):
  Q1 — standing classes are enumerated in STANDING_HARDENING_CLASSES
       before first use; per-scenario DecisionRecords remain the default
       (F-S2: a gate that approves everything is not a gate).
  Q2 — manifest fidelity is upstream (installer-spec): SandboxCopy records
       its manifest_source; the fixture stipulates, production must cite an
       installer-issued manifest.
  Q3 — coverage is flow-scoped in v1: pairs are (transition, guard-outcome)
       over a flow's transition table. Generalization to run-books and
       harness runs is open.

Glossary (spec section 0, condensed): brief — the written charge
{source_falsification, survivor_under_test, risk_question, budget}; sandbox
copy — a manifest-provisioned copy under a sandbox path, never the live
installation; simulation transcript — the run record, kind=simulation;
hardening — promotion into the regression suite (measured D4, gated D5);
coverage criterion — covers_new_pair (I-23); operator gate — a cited
disposition per hardening (I-24).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from .schema import AutomatonRelease, FlowRun, SystemState
from .updater import FLOW_ID, World, compile_flow, drive

LIVE_HOME = "/home/op/dsys-inst"  # the fixture's live installation path


class SimRefused(Exception):
    """A simulation-pipeline refusal: raised before any effect, never after."""


class ContainmentRefused(SimRefused):
    """I-21: the scenario World would name forbidden ground."""


class SeparationRefused(SimRefused):
    """I-22: simulation kind presented to a production writer."""


class HardeningRefused(SimRefused):
    """I-23/I-24: the scenario may not join the regression suite."""


class BudgetExhausted(SimRefused):
    """D1/F-S1: the brief's authorship budget is spent — the brief retires."""


class ExpectationFailed(SimRefused):
    """The referee turn: the transcript did not meet the spec's expects."""


# ---------------------------------------------------------------------------
# Data: briefs, scenario specs, transcripts, sandboxes, reports, the suite
# ---------------------------------------------------------------------------

class Brief(BaseModel):
    """D1: the written charge for an authorship run. Budgets bound the
    attention cost of authoring-without-yield (F-S1)."""

    model_config = ConfigDict(frozen=True)

    id: str
    source_falsification: str  # e.g. "K2 F-B: unwritable accretion path"
    survivor_under_test: str
    risk_question: str
    budget: int = Field(ge=1)  # max scenarios authored under this brief
    authored: int = 0
    retired: bool = False


class ScenarioTurn(BaseModel):
    """One declarative turn: {actor, input, expect} (spec section 0).
    Actors: world (fixture setup), driver (execute), referee (judge)."""

    model_config = ConfigDict(frozen=True)

    actor: str
    input: dict = Field(default_factory=dict)
    expect: dict = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    """D2: the scenario as data — YAML-declarable, no executable content.
    The interpreter (below) is the only reader."""

    model_config = ConfigDict(frozen=True)

    id: str
    brief_id: str
    target_flow_id: str = FLOW_ID
    narrative: str  # the brief-responsive story, in words
    turns: list[ScenarioTurn] = Field(min_length=1)


class FlowPair(BaseModel):
    """One (transition, guard-outcome) pair (D4). Taken transitions had
    their guard hold; guardless transitions carry 'unguarded'."""

    model_config = ConfigDict(frozen=True)

    transition_id: str
    guard_outcome: str  # "guard-true" | "unguarded"

    def key(self) -> str:
        return f"{self.transition_id}|{self.guard_outcome}"


class SimulationTranscript(BaseModel):
    """D7: the run record of a scenario execution against a sandbox copy.
    kind=simulation is set at construction — ontologically separate from
    production records, not a marking convention."""

    model_config = ConfigDict(frozen=True)

    id: str
    scenario_id: str
    kind: str = "simulation"
    sandbox_id: str
    run_id: str
    terminal_pair: FlowPair
    events: list[dict] = Field(min_length=1)
    pairs: list[FlowPair] = Field(min_length=1)
    pair_triggers: dict[str, str] = Field(default_factory=dict)
    bug_found: bool = False

    def as_commit_input(self) -> dict:
        """The shape a confused caller would present to the accretion
        writer — carrying kind=simulation so the writer refuses (I-22)."""
        return {"kind": "simulation", "run_id": self.run_id,
                "source_state": "simulation",
                "events": [dict(e) for e in self.events]}


class SandboxCopy(BaseModel):
    """D9: a manifest-provisioned copy of the installation's declared
    state, rooted under a sandbox path. manifest_source records fidelity
    provenance (G6 Q2): the fixture stipulates; production cites an
    installer-issued manifest."""

    model_config = ConfigDict(frozen=True)

    id: str
    root: str
    manifest_hash: str
    manifest_source: str = "stipulated-fixture"
    declared: dict = Field(default_factory=dict)


class CoverageReport(BaseModel):
    """D4: the measured coverage verdict for one candidate scenario."""

    model_config = ConfigDict(frozen=True)

    id: str
    scenario_id: str
    candidate_pairs: list[FlowPair]
    terminal_pair: FlowPair
    terminal_trigger: str
    suite_pairs_before: int
    new_pairs: list[FlowPair]
    bug_found: bool = False
    passes: bool


class HardenedCase(BaseModel):
    """D5: a scenario promoted into the regression suite — the spec placed,
    the golden-run case added (in the fixture: recorded here)."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    transcript_id: str
    pairs: list[FlowPair]  # the new pairs this case contributed
    disposition_ref: str  # per-scenario DR id, or "standing:<class>"
    coverage_report_id: str


@dataclass
class ScenarioSuite:
    """The regression suite the pipeline feeds: seeded + hardened cases.
    This suite — not the updater's golden run — is D4's 'existing suite'."""

    cases: list[HardenedCase] = field(default_factory=list)
    transcripts: dict[str, SimulationTranscript] = field(default_factory=dict)

    def covered_pairs(self) -> set[FlowPair]:
        pairs: set[FlowPair] = set()
        for c in self.cases:
            pairs.update(c.pairs)
        return pairs


# ---------------------------------------------------------------------------
# D1: briefed authorship with budgets
# ---------------------------------------------------------------------------

def author_scenario(brief: Brief, spec: ScenarioSpec
                    ) -> tuple[Brief, ScenarioSpec]:
    """D1: authorship consumes the brief's budget. An exhausted brief
    retires — zero-yield briefs retire the brief, never the pipeline
    (F-S1). Unbriefed authorship cannot harden: the spec must cite its
    brief."""
    if brief.retired or brief.authored >= brief.budget:
        raise BudgetExhausted(
            f"brief {brief.id}: budget spent "
            f"({brief.authored}/{brief.budget}) — the brief retires")
    if spec.brief_id != brief.id:
        raise BudgetExhausted(
            f"scenario {spec.id} cites brief {spec.brief_id}, not {brief.id} "
            f"— unbriefed authorship is not hardened (D1)")
    return brief.model_copy(update={"authored": brief.authored + 1}), spec


def retire_brief(brief: Brief) -> Brief:
    """F-S1: an exhausted brief retires explicitly, entering the record."""
    return brief.model_copy(update={"retired": True})


# ---------------------------------------------------------------------------
# D9: manifest-provisioned sandboxes (a driver step)
# ---------------------------------------------------------------------------

def provision_sandbox(manifest: dict, sandbox_root: str,
                      manifest_source: str = "stipulated-fixture"
                      ) -> SandboxCopy:
    """D9: derive the sandbox copy from the installation manifest's declared
    state — never hand-built (F-S3: drifted copies lie about the
    installation). The strapped driver calls this before executing the
    scenario, under the same strap as every other turn."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return SandboxCopy(id=f"sbx-{digest[:12]}", root=sandbox_root,
                       manifest_hash=digest, manifest_source=manifest_source,
                       declared=dict(manifest))


# ---------------------------------------------------------------------------
# I-21: simulation containment — path discipline at World construction
# ---------------------------------------------------------------------------

def _norm(p: str) -> str:
    return os.path.normpath(p)


def _under(path: str, root: str) -> bool:
    return os.path.commonpath([_norm(path), _norm(root)]) == _norm(root)


def i21_containment(install_home: str, sandbox_root: str,
                    live_home: str = LIVE_HOME) -> list[str]:
    """I-21 (predicate): the scenario install_home must be rooted under the
    sandbox root and must name neither the live installation path nor any
    path outside the sandbox. No OS sandboxing is required (the
    installer-spec's 'no Docker v1' non-goal stands): the only mutating
    tool takes an explicit path, so path discipline is sufficient (D6)."""
    v: list[str] = []
    if not _under(install_home, sandbox_root):
        v.append(f"I-21: install_home {install_home} is outside the "
                 f"sandbox root {sandbox_root}")
    if _under(install_home, live_home):
        v.append(f"I-21: install_home {install_home} names the live "
                 f"installation {live_home}")
    return v


def make_scenario_world(sandbox: SandboxCopy, live_home: str = LIVE_HOME,
                        **kw) -> World:
    """Construct the scenario-execution World. Containment is asserted
    BEFORE construction: a violation refuses the run before execution,
    with nothing constructed and nothing mutated. The default home is
    derived from the sandbox root — never the live path, never ambient."""
    install_home = kw.get("install_home",
                          sandbox.root.rstrip("/") + "/dsys-inst")
    violations = i21_containment(install_home, sandbox.root, live_home)
    for extra in ("prev_install_home", "prev_accretion_path"):
        if kw.get(extra):
            violations += i21_containment(kw[extra], sandbox.root, live_home)
    if violations:
        raise ContainmentRefused("; ".join(violations))
    kw["install_home"] = install_home
    return World(**kw)


# ---------------------------------------------------------------------------
# I-22: transcript separation — production writers cannot accept simulation
# ---------------------------------------------------------------------------

def i22_transcript_separation(presented: list[dict]) -> list[str]:
    """I-22 (predicate): no kind=simulation content is acceptable to a
    production record writer (the accretion writer), a disclosure funnel, or
    a replay corpus. Separation is structural (D7)."""
    v: list[str] = []
    for p in presented:
        if p.get("kind") == "simulation" and p.get("destination") in (
                "accretion-writer", "disclosure", "replay-corpus"):
            v.append(f"I-22: kind=simulation presented to production "
                     f"{p['destination']}")
    return v


def disclose_from_transcript(transcript: SimulationTranscript,
                             text: str) -> dict:
    """The single transcript→disclosure funnel. Simulation transcripts
    cannot become disclosures — there is no other path, so they are
    structurally absent from disclosure views (DR-5)."""
    if transcript.kind == "simulation":
        raise SeparationRefused(
            "I-22: kind=simulation transcripts cannot be disclosed upward")
    return {"transcript_id": transcript.id, "text": text}


# ---------------------------------------------------------------------------
# The strapped driver's scenario turn (D3): execute + adjudicate
# ---------------------------------------------------------------------------

def _sim_state(run_id: str) -> SystemState:
    s = SystemState()
    aflow, states, transitions, runbooks, steps, tools = compile_flow()
    s.releases["rel-0.1.0"] = AutomatonRelease(
        id="rel-0.1.0", version="0.1.0")
    s.automaton_flows[FLOW_ID] = aflow
    for st in states:
        s.flow_states[st.id] = st
    for t in transitions:
        s.flow_transitions[t.id] = t
    for rb in runbooks:
        s.runbooks[rb.id] = rb
    for step in steps:
        s.steps[step.id] = step
    for tool in tools:
        s.tools[tool.id] = tool
    s.flow_runs[run_id] = FlowRun(id=run_id, flow_id=FLOW_ID,
                                 current_state_id="urm-idle", state="running")
    return s


def _event_dicts(s: SystemState) -> list[dict]:
    return [{
        "seq": e.seq,
        "from_state_id": e.from_state_id,
        "to_state_id": e.to_state_id,
        "trigger": e.trigger,
        "payload": json.loads(e.payload),
    } for e in sorted(s.flow_transition_events.values(),
                      key=lambda e: e.seq)]


def execute_scenario(spec: ScenarioSpec, sandbox: SandboxCopy,
                     live_home: str = LIVE_HOME,
                     run_id: str = "fr-sim") -> tuple:
    """D3: the world + driver turns. World inputs come from the spec's
    world turns; the driver turn carries run_id/until. Returns
    (state, world, path, events). The golden run plays the strapped
    driver; no new execution machinery is built."""
    world_kw: dict = {}
    driver_kw: dict = {}
    for turn in spec.turns:
        if turn.actor == "world":
            world_kw.update(turn.input)
        elif turn.actor == "driver":
            driver_kw.update(turn.input)
        elif turn.actor == "referee":
            continue
        else:
            raise ExpectationFailed(
                f"unknown scenario actor: {turn.actor!r}")
    world = make_scenario_world(sandbox, live_home, **world_kw)
    run_id = driver_kw.get("run_id", run_id)
    s = _sim_state(run_id)
    path = drive(s, world, run_id, until=driver_kw.get("until"))
    return s, world, path, _event_dicts(s)


def event_pairs(events: list[dict], transitions: list) -> set[FlowPair]:
    """Map each event to its (transition, guard-outcome) pair by
    (from, to, trigger). Taken transitions had their guard hold."""
    by_triple = {(t.from_state_id, t.to_state_id, t.trigger): t
                 for t in transitions}
    pairs: set[FlowPair] = set()
    for e in events:
        t = by_triple.get(
            (e["from_state_id"], e["to_state_id"], e["trigger"]))
        if t is None:
            raise ValueError(f"no transition matches event {e['seq']}")
        pairs.add(FlowPair(
            transition_id=t.id,
            guard_outcome="guard-true" if t.guard else "unguarded"))
    return pairs


def adjudicate(spec: ScenarioSpec, sandbox: SandboxCopy, run_id: str,
               path: list[str], events: list[dict]) -> SimulationTranscript:
    """D3: the referee turn. Checks the spec's expects against the run;
    assembles the transcript, kind marked at construction (D7)."""
    expect: dict = {}
    for turn in spec.turns:
        if turn.actor == "referee":
            expect.update(turn.expect)
    _, _, transitions, _, _, _ = compile_flow()
    pairs = event_pairs(events, transitions)
    fails: list[str] = []
    if "ends_at" in expect and path[-1] != expect["ends_at"]:
        fails.append(f"expected end {expect['ends_at']}, got {path[-1]}")
    if "path" in expect and path != expect["path"]:
        fails.append(f"path mismatch: {path}")
    if "covers" in expect:
        want = {FlowPair(transition_id=t, guard_outcome=g)
                for t, g in expect["covers"]}
        if not want <= pairs:
            missing = sorted((p.transition_id, p.guard_outcome)
                             for p in want - pairs)
            fails.append(f"pairs not covered: {missing}")
    if fails:
        raise ExpectationFailed("; ".join(fails))
    by_triple = {(t.from_state_id, t.to_state_id, t.trigger): t
                 for t in transitions}
    last = events[-1]
    terminal_t = by_triple[(last["from_state_id"], last["to_state_id"],
                            last["trigger"])]
    terminal_pair = FlowPair(
        transition_id=terminal_t.id,
        guard_outcome="guard-true" if terminal_t.guard else "unguarded")
    return SimulationTranscript(
        id=f"tx-{spec.id}", scenario_id=spec.id, sandbox_id=sandbox.id,
        run_id=run_id, terminal_pair=terminal_pair, events=events,
        pairs=sorted(pairs, key=lambda p: p.key()),
        pair_triggers={p.key(): _trigger_of(p, events, transitions)
                       for p in pairs})


def _trigger_of(pair: FlowPair, events: list[dict], transitions: list) -> str:
    by_id = {t.id: t for t in transitions}
    return by_id[pair.transition_id].trigger


def run_scenario(spec: ScenarioSpec, sandbox: SandboxCopy,
                 live_home: str = LIVE_HOME,
                 run_id: str = "fr-sim") -> SimulationTranscript:
    """D3: one strapped-driver turn — execute, then adjudicate."""
    s, world, path, events = execute_scenario(spec, sandbox, live_home,
                                              run_id)
    return adjudicate(spec, sandbox, run_id, path, events)

# ---------------------------------------------------------------------------
# I-23: the coverage criterion — measured, not judged (D4)
# ---------------------------------------------------------------------------

def covers_new_pair(candidate_pairs: set[FlowPair],
                    suite_pairs: set[FlowPair]) -> tuple[bool, set[FlowPair]]:
    """I-23 (predicate): true iff the candidate exercises at least one
    (transition, guard-outcome) pair absent from the suite's covered set.
    Guard-outcomes include refusals: a scenario driving the policy gate to
    `defer`, or the installer to the K2 accretion refusal, covers pairs
    the happy path never touches. Flow-scoped in v1 (G6 Q3)."""
    new = set(candidate_pairs) - set(suite_pairs)
    return (len(new) > 0, new)


def coverage_report(scenario_id: str, transcript: SimulationTranscript,
                    suite: ScenarioSuite, report_id: str) -> CoverageReport:
    """D4: measure the candidate against the suite. The bug-finding
    alternative: a transcript exhibiting a real failure is hardenable
    even when every pair is covered."""
    suite_pairs = suite.covered_pairs()
    passes, new = covers_new_pair(set(transcript.pairs), suite_pairs)
    passes = passes or transcript.bug_found
    new_keys = {p.key() for p in new}
    return CoverageReport(
        id=report_id, scenario_id=scenario_id,
        candidate_pairs=list(transcript.pairs),
        terminal_pair=transcript.terminal_pair,
        terminal_trigger=transcript.pair_triggers[transcript.terminal_pair.key()],
        suite_pairs_before=len(suite_pairs),
        new_pairs=sorted(new, key=lambda p: p.key()),
        bug_found=transcript.bug_found, passes=passes)


# ---------------------------------------------------------------------------
# I-24: the hardening gate — operator disposition required (D5)
# ---------------------------------------------------------------------------

STANDING_HARDENING_CLASSES: dict[str, str] = {
    # G6 Q1: narrow classes enumerated before first use. Per-scenario
    # DecisionRecords remain the default; a standing class is the
    # exception, and it must be narrow (F-S2).
    "refusal-path": (
        "Scenarios whose terminal pair is a run_aborted (refusal) pair on "
        "a flow with a published transition table, with the coverage "
        "report attached. Narrow by construction: it admits only "
        "scenarios that drive the flow to a loud refusal — it cannot "
        "launder happy-path behavior into the suite."
    ),
}


def _check_standing_class(class_id: str, report: CoverageReport) -> None:
    if class_id == "refusal-path":
        if report.terminal_trigger != "run_aborted":
            raise HardeningRefused(
                "I-24: standing class 'refusal-path' admits only scenarios "
                f"terminating in a refusal (got {report.terminal_trigger})")
    else:  # unreachable — harden checks membership first; defense in depth
        raise HardeningRefused(
            f"I-24: unknown standing class {class_id!r}")


def harden(*, scenario: ScenarioSpec, transcript: SimulationTranscript,
           report: CoverageReport, suite: ScenarioSuite,
           disposition_ref: str | None = None,
           standing_class: str | None = None) -> HardenedCase:
    """D5: the hardening pipeline. I-23 measured first, I-24 gated second:
    a scenario joins the regression suite only with a cited disposition —
    a per-scenario DecisionRecord, or a narrow standing class (F-S2: a
    standing 'harden anything covering' is a rubber stamp and is refused).
    On any refusal the suite is untouched."""
    if not report.passes:
        raise HardeningRefused(
            "I-23: covers no new (transition, guard-outcome) pair and "
            "exhibits no failure — not hardenable")
    if standing_class is not None:
        if standing_class not in STANDING_HARDENING_CLASSES:
            raise HardeningRefused(
                f"I-24: unknown standing class {standing_class!r} — "
                f"no rubber stamps (F-S2)")
        _check_standing_class(standing_class, report)
        disp = f"standing:{standing_class}"
    elif disposition_ref:
        disp = disposition_ref
    else:
        raise HardeningRefused(
            "I-24: hardening requires a cited operator disposition — "
            "per-scenario DecisionRecord or standing class")
    case = HardenedCase(
        scenario_id=scenario.id, transcript_id=transcript.id,
        pairs=list(report.new_pairs), disposition_ref=disp,
        coverage_report_id=report.id)
    suite.cases.append(case)
    suite.transcripts[transcript.id] = transcript
    return case
