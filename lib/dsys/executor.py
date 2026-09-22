#!/usr/bin/env python3
"""dsys automaton executor — the runtime that steps the automaton plane.

Implements doc/automaton-executor-spec.md (adopted DR-CMD-054, C1–C6):
run-level step semantics (§5), failure policies (§6), flow driving (§7),
the tool contract (§8), replay (§9), concurrency (§10), and the
referee-callable validators I-28/I-29/I-30 plus the AutomatonRun.state
narrowing (§14.4).

A step function, not a server: each call loads state, advances to
quiescence, appends events, exits. No inference, no network, no clock.
Run-level guards are the AST-allowlisted Python-subset expressions over
``ctx``; flow transition guards use the same subset over ``payload``.
Guards compile once per (definition, release_version) and cache
in-process.

Event model (run-level), all dicts {"seq", "kind", "payload"}:
  run_created   — immutable cfg + initial ctx
  step_started  — {"step_seq", "tool"}
  step_completed— {"step_seq", "tool", "result", "ctx_delta"}
  step_failed   — {"step_seq", "tool", "error", "malformed"}
  step_skipped  — {"step_seq", "reason"}
  step_parked   — {"step_seq"}  ("not yet", not failure)
  event_injected— {"kind", "payload"} (payload merges into ctx)
  run_completed / run_aborted — terminal

Tool registry: dist-shipped, release-pinned — lib/dsys/tools/<name>.py
next to this module. Each module defines TOOL_NAME: str and
run(ctx: dict) -> {"ok","result","ctx_delta"}. Run-book registry:
lib/dsys/runbooks/<id>.json;
{"runbook_id","release_version","steps":[{"seq","expr","tool"}]}.
There are no overlays or search paths: anything the registries cannot
resolve is a definition/vehicle fault that surfaces loudly (never a
silent substitution).

This module never touches the network, the clock, or inference.

Two layers live here, kept explicit:

1. The pure walker (§§5–6, 8–9): compile_guard / eval_guard /
   parse_policy / fold_log / advance_run / revalidate_transcript and the
   I-28/I-29/I-30 validators. advance_run takes an in-memory run record
   and mutates it; it performs no IO of its own. The only effects are the
   tool invocations it is handed.

2. The §7 flow driver: advance_flow / evaluate_transitions / spawn_child /
   find_child / mint_disclosure. This is the driver's IO-bearing layer —
   it reads and writes run records under OS file locks and mints
   disclosures into the drain outbox. It is in this module (not the CLI)
   because the transition-set evaluation and child-lifecycle rules are
   spec'd executor semantics; the CLI wrapper only supplies locking,
   record IO, and trigger evaluation.
"""

import ast
import fcntl
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Attribute,
    ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq, ast.And, ast.Or,
    ast.Not,
)

_GUARD_CACHE: dict = {}


class _Scope:
    """Attribute-access view over a dict (cf. updater._Payload).

    A missing key reads as None (falsy) — "not yet", not an error: a
    guard over a key the world hasn't provided yet is false, so the
    step parks and a later --external can unpark it (spec §5). Python
    comparison semantics apply throughout (None != 'x' is True). A
    guard that raises a genuine type error (e.g. adding a string) is a
    definition fault, handled by the caller.
    """

    def __init__(self, d: dict):
        self.__dict__["_d"] = d

    def __getattr__(self, name: str):
        try:
            v = self.__dict__["_d"][name]
        except KeyError:
            return None
        if isinstance(v, dict):
            return _Scope(v)
        return v


def compile_guard(expr: str, roots=("ctx",), cache_key=None):
    """Compile an allowlisted guard expression over the ``roots`` namespaces.

    Run-level step guards use roots=("ctx",); flow transition guards use
    roots=("payload", "run") per spec §3 (I-15's narrow context: the
    trigger payload and the child run's status — no wall-clock value may
    enter guard evaluation or replay).

    Raises ValueError on non-expression syntax or non-allowlisted nodes.
    Cached in-process per (cache_key, roots, expr).
    """
    if isinstance(roots, str):
        roots = (roots,)
    roots = tuple(roots)
    key = (cache_key, roots, expr)
    if key in _GUARD_CACHE:
        return _GUARD_CACHE[key]
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"guard is not an expression: {e}")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(
                f"guard uses non-allowlisted syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in roots:
            raise ValueError(
                f"guard may only reference {roots}, got {node.id!r}")
    code = compile(tree, "<guard>", "eval")
    _GUARD_CACHE[key] = code
    return code


def eval_guard(code, scopes: dict) -> bool:
    """Evaluate compiled guard code against a {namespace: dict} mapping.

    Each dict scope is viewed through _Scope (attribute access); the
    ``run`` namespace for a transition guard is {"status": ...} (the
    child run's terminal status, or None for CLI-supplied triggers at
    wait states — spec §3).
    """
    ns = {name: (_Scope(scope) if isinstance(scope, dict) else scope)
          for name, scope in scopes.items()}
    return bool(eval(code, {"__builtins__": {}}, ns))


# ---------------------------------------------------------------------------
# Failure policies (§6)
# ---------------------------------------------------------------------------

def parse_policy(spec: str):
    """'abort | skip | retry:<n>' → ('abort',) | ('skip',) | ('retry', n).

    retry:<n> allows n failed attempts total: the (n+1)-th attempt is a
    violation (spec §6: "retry:3 but a fourth attempt appears").
    """
    if spec == "abort":
        return ("abort",)
    if spec == "skip":
        return ("skip",)
    if spec.startswith("retry:"):
        try:
            n = int(spec.split(":", 1)[1])
        except ValueError:
            raise ValueError(f"bad retry count in policy {spec!r}")
        if n < 1:
            raise ValueError(f"retry count must be >= 1, got {spec!r}")
        return ("retry", n)
    raise ValueError(
        f"bad failure policy {spec!r} (abort | skip | retry:<n>)")


def _consequence(policy, fails: int) -> str:
    """The policy consequence after ``fails`` failed attempts: retry|skip|abort."""
    kind = policy[0]
    if kind == "abort":
        return "abort"
    if kind == "skip":
        return "skip"
    return "retry" if fails < policy[1] else "abort"


# ---------------------------------------------------------------------------
# Tools (§8) + C1
# ---------------------------------------------------------------------------

class ToolResult:
    __slots__ = ("ok", "result", "ctx_delta", "malformed", "error")

    def __init__(self, ok, result, ctx_delta, malformed, error):
        self.ok = ok
        self.result = result
        self.ctx_delta = ctx_delta
        self.malformed = malformed
        self.error = error


def invoke_tool(fn, ctx: dict) -> ToolResult:
    """Invoke a tool. Any contract deviation (C1) — exception, non-dict
    return, a missing required key (``ok`` / ``result`` / ``ctx_delta``),
    a non-boolean ``ok``, a non-JSON-object ``ctx_delta``, or a
    non-JSON-shaped ``result`` — is a *tool failure*; the caller applies
    the declared failure policy and records a normalized step_failed
    (the malformed bytes never enter ctx)."""
    try:
        ret = fn(ctx)
    except Exception as e:
        return ToolResult(False, None, {}, True,
                          f"tool raised {type(e).__name__}: {e}")
    if not isinstance(ret, dict):
        return ToolResult(False, None, {}, True,
                          f"tool returned {type(ret).__name__}, not a dict")
    missing = [k for k in ("ok", "result", "ctx_delta") if k not in ret]
    if missing:
        return ToolResult(False, None, {}, True,
                          "tool result missing: " + ", ".join(missing))
    if not isinstance(ret["ok"], bool):
        return ToolResult(False, None, {}, True,
                          f"tool 'ok' is {type(ret['ok']).__name__}, "
                          "not a boolean")
    delta = ret["ctx_delta"]
    if not isinstance(delta, dict):
        return ToolResult(False, None, {}, True,
                          "tool ctx_delta is not a JSON object")
    try:
        json.dumps(ret["result"])
        json.dumps(delta)
    except (TypeError, ValueError) as e:
        return ToolResult(False, None, {}, True,
                          f"tool result not JSON-shaped: {e}")
    return ToolResult(ret["ok"], ret["result"], delta, False, None)


def load_tools(dist_tools_dir: Path) -> dict:
    """Load the tool registry: dist-shipped, release-pinned modules only
    (no overlays, no search paths — §8). A module that fails to define
    TOOL_NAME: str and run(ctx) is a packaging fault and raises."""
    registry: dict = {}
    d = Path(dist_tools_dir)
    if d.is_dir():
        for mod_path in sorted(d.glob("*.py")):
            if mod_path.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(
                f"dsys_tool_{mod_path.stem}", mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            name = getattr(mod, "TOOL_NAME", None)
            run = getattr(mod, "run", None)
            if not isinstance(name, str) or not callable(run):
                raise ValueError(
                    f"bad tool module {mod_path}: need TOOL_NAME: str "
                    f"and run(ctx)")
            if name not in registry:
                registry[name] = run
    return registry


# ---------------------------------------------------------------------------
# Run-books
# ---------------------------------------------------------------------------

def load_runbook(dist_rb_dir: Path, runbook_id: str):
    """Resolve a run-book definition from the dist-shipped, release-pinned
    registry (no overlays — §8). Returns the definition dict, or None
    when unknown. Guards compile at load — a bad expression fails fast
    here, not mid-run."""
    for d in (Path(dist_rb_dir),):
        p = d / f"{runbook_id}.json"
        if not p.is_file():
            continue
        try:
            rb = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"bad run-book {p}: {e}")
        _check_runbook(rb, p)
        return rb
    return None


def _check_runbook(rb: dict, where) -> None:
    if not isinstance(rb, dict):
        raise ValueError(f"bad run-book {where}: not an object")
    for k in ("runbook_id", "release_version", "steps"):
        if k not in rb:
            raise ValueError(f"bad run-book {where}: missing {k!r}")
    steps = rb["steps"]
    if not isinstance(steps, list):
        raise ValueError(f"bad run-book {where}: steps is not a list")
    seen = set()
    for s in steps:
        if not isinstance(s, dict):
            raise ValueError(f"bad run-book {where}: step is not an object")
        for k in ("seq", "expr", "tool"):
            if k not in s:
                raise ValueError(
                    f"bad run-book {where}: step missing {k!r}")
        if s["seq"] in seen:
            raise ValueError(
                f"bad run-book {where}: duplicate step seq {s['seq']}")
        seen.add(s["seq"])
        compile_guard(s["expr"], "ctx",
                      cache_key=(rb["runbook_id"], rb["release_version"],
                                 s["seq"]))


def check_runbook(rb: dict, where) -> None:
    """Public form of the run-book definition check — used by the CLI's
    updater-entity adapter, which builds definitions from entities
    rather than loading them from the dist registry."""
    _check_runbook(rb, where)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _append(events: list, kind: str, payload: dict) -> dict:
    e = {"seq": len(events), "kind": kind, "payload": payload}
    events.append(e)
    return e


# ---------------------------------------------------------------------------
# Fold (§5)
# ---------------------------------------------------------------------------

def fold(events: list):
    """Fold the event log → (ctx, per-step info).

    per-step: {seq: {"status", "fails"}}; status ∈ completed | skipped |
    parked | failed | in_flight | pending. A dangling step_started
    (crash, F-E3) folds as in_flight — the next advance re-invokes.
    """
    ctx: dict = {}
    info: dict = {}
    for e in events:
        kind = e["kind"]
        p = e.get("payload", {})
        if kind == "run_created":
            ctx = dict(p.get("ctx", {}))
        elif kind == "event_injected":
            payload = p.get("payload", {})
            if isinstance(payload, dict):
                ctx.update(payload)
        elif kind in ("step_started", "step_completed", "step_failed",
                      "step_skipped", "step_parked"):
            seq = p["step_seq"]
            s = info.setdefault(seq, {"status": "pending", "fails": 0})
            if kind == "step_started":
                s["status"] = "in_flight"
            elif kind == "step_completed":
                delta = p.get("ctx_delta", {})
                if isinstance(delta, dict):
                    ctx.update(delta)
                s["status"] = "completed"
            elif kind == "step_failed":
                s["fails"] += 1
                s["status"] = "failed"
            elif kind == "step_skipped":
                s["status"] = "skipped"
            elif kind == "step_parked":
                s["status"] = "parked"
        # run_completed / run_aborted: terminal; nothing folds
    return ctx, info


# ---------------------------------------------------------------------------
# advance_run — the step loop (§5)
# ---------------------------------------------------------------------------

def _summary(run, steps_advanced, events_appended, iterations, hit_bound):
    return {
        "run_id": run["run_id"],
        "state": run["state"],
        "steps_advanced": steps_advanced,
        "events_appended": events_appended,
        "iterations": iterations,
        "closed": run["state"] in ("completed", "aborted"),
        "hit_bound": hit_bound,
    }


def advance_run(run: dict, runbook: dict, tools: dict,
                external=None, max_steps: int = 1000) -> dict:
    """Step a run record to quiescence (§5). Mutates ``run`` in place
    (appends events, folds ctx, updates state).

    external: (kind, payload-dict) | None — appended as event_injected
    before stepping. max_steps is a resource bound (F-E4): tripping it
    exits with hit_bound=True, having recorded the steps taken (the
    *stop* records nothing semantic).

    I-29: a trailing terminal/step_parked event with no new input is a
    no-op — no duplicate parked/terminal events are ever appended.
    """
    events = run["events"]
    if external is not None:
        kind, payload = external
        if not isinstance(payload, dict):
            raise ValueError("external payload must be a JSON object")
        _append(events, "event_injected", {"kind": kind, "payload": payload})
    if external is None and events and events[-1]["kind"] in (
            "run_completed", "run_aborted", "step_parked"):
        return _summary(run, 0, 0, 0, False)
    policy = parse_policy(run["policy"])
    steps = sorted(runbook["steps"], key=lambda s: s["seq"])
    cache_key = (runbook["runbook_id"], runbook.get("release_version"))
    steps_advanced = 0
    iterations = 0
    events_before = len(events)
    hit_bound = False
    for _ in range(max_steps):
        iterations += 1
        if run["state"] in ("completed", "aborted"):
            break
        ctx, info = fold(events)
        target = None
        for s in steps:
            st = info.get(s["seq"], {"status": "pending", "fails": 0})
            if st["status"] in ("completed", "skipped"):
                continue
            target = (s, st["status"], st["fails"])
            break
        if target is None:
            _append(events, "run_completed", {})
            run["state"] = "completed"
            break
        step, st, fails = target
        if st == "failed":
            cons = _consequence(policy, fails)
            if cons == "abort":
                _append(events, "run_aborted", {
                    "reason": f"policy {run['policy']}: {fails} failed "
                              f"attempt(s) on step {step['seq']}"})
                run["state"] = "aborted"
                break
            if cons == "skip":
                _append(events, "step_skipped", {
                    "step_seq": step["seq"],
                    "reason": f"policy {run['policy']}"})
                continue
            # retry → fall through to attempt
        code = compile_guard(step["expr"], "ctx",
                             cache_key + (step["seq"],))
        try:
            guard_true = eval_guard(code, {"ctx": ctx})
        except Exception as e:
            # A guard that raises is a definition fault, not "not yet":
            # record it as the step's failure so the policy machinery —
            # and I-28 — handle it loudly, never as silent parking.
            _append(events, "step_failed", {
                "step_seq": step["seq"], "tool": step["tool"],
                "error": f"guard error: {e}", "malformed": False})
            continue
        if not guard_true:
            if st != "parked":
                _append(events, "step_parked", {"step_seq": step["seq"]})
            break  # quiescent (I-29: never a duplicate parked event)
        tool_fn = tools.get(step["tool"])
        _append(events, "step_started",
                {"step_seq": step["seq"], "tool": step["tool"]})
        if tool_fn is None:
            # The attempt began and failed at tool lookup: the event
            # grammar stays uniform (every attempt is started → outcome),
            # so I-28's adjacency holds for this failure like any other.
            _append(events, "step_failed", {
                "step_seq": step["seq"], "tool": step["tool"],
                "error": f"unknown tool {step['tool']!r} at advance time",
                "malformed": False})
            continue
        res = invoke_tool(tool_fn, ctx)
        if res.ok:
            _append(events, "step_completed", {
                "step_seq": step["seq"], "tool": step["tool"],
                "result": res.result, "ctx_delta": res.ctx_delta})
            steps_advanced += 1
        else:
            _append(events, "step_failed", {
                "step_seq": step["seq"], "tool": step["tool"],
                "error": res.error, "malformed": res.malformed})
            # The policy consequence applies at the next iteration, keeping
            # step_failed → consequence adjacent for I-28.
    else:
        hit_bound = True
    run["ctx"] = ctx  # the folded ctx is the run's mutable state; the flow
    # driver mints child-completion trigger payloads from it (§7).
    return _summary(run, steps_advanced, len(events) - events_before,
                    iterations, hit_bound)

# ---------------------------------------------------------------------------
# Replay + validators (§9, §14.4; I-28/I-29/I-30)
# ---------------------------------------------------------------------------

_KNOWN_KINDS = {
    "run_created", "step_started", "step_completed", "step_failed",
    "step_skipped", "step_parked", "event_injected",
    "run_completed", "run_aborted",
}

_TERMINAL = ("run_completed", "run_aborted")


def i28_policy_consequence(events: list, policy_spec: str) -> list[str]:
    """I-28: every step_failed is followed by its policy's consequence.

    A trailing step_failed (bound tripped before the policy applied) is
    valid — the consequence is pending, same class as C2.
    """
    violations = []
    try:
        policy = parse_policy(policy_spec)
    except ValueError as e:
        return [f"bad policy {policy_spec!r}: {e}"]
    fails: dict = {}
    n = len(events)
    for i, e in enumerate(events):
        kind = e["kind"]
        p = e.get("payload", {})
        if kind in ("step_completed", "step_skipped"):
            fails[p.get("step_seq")] = 0
        elif kind == "step_failed":
            seq = p.get("step_seq")
            k = fails.get(seq, 0) + 1
            fails[seq] = k
            if i == n - 1:
                continue  # consequence pending — valid (cf. C2)
            nxt = events[i + 1]
            want = _consequence(policy, k)
            ok = (
                (want == "abort" and nxt["kind"] == "run_aborted")
                or (want == "skip" and nxt["kind"] == "step_skipped"
                    and nxt.get("payload", {}).get("step_seq") == seq)
                or (want == "retry" and nxt["kind"] == "step_started"
                    and nxt.get("payload", {}).get("step_seq") == seq)
            )
            if not ok:
                violations.append(
                    f"I-28: step_failed for step {seq} (failure #{k}) not "
                    f"followed by its {want} consequence "
                    f"(next: {nxt['kind']} at seq {nxt.get('seq')})")
    return violations


def i29_quiescence_stickiness(events: list) -> list[str]:
    """I-29: no event after a terminal/step_parked event without
    intervening input (event_injected)."""
    violations = []
    for i, e in enumerate(events):
        if e["kind"] in _TERMINAL + ("step_parked",) and i + 1 < len(events):
            nxt = events[i + 1]
            if nxt["kind"] != "event_injected":
                violations.append(
                    f"I-29: {e['kind']} at seq {e.get('seq')} followed by "
                    f"{nxt['kind']} with no intervening input")
    return violations


def i30_init_idempotency(runs: list) -> list[str]:
    """I-30: at most one open run per idempotency key."""
    violations = []
    seen: dict = {}
    for r in runs:
        if not isinstance(r, dict) or r.get("kind") != "run":
            continue
        if r.get("state") != "open":
            continue
        key = r.get("idempotency_key")
        if key in seen:
            violations.append(
                f"I-30: idempotency key {key!r} carried by two open runs "
                f"({seen[key]} and {r.get('run_id')})")
        else:
            seen[key] = r.get("run_id")
    return violations


def i_state_narrowed(run: dict) -> list[str]:
    """AutomatonRun.state ∈ open|completed|aborted (§14.4)."""
    if run.get("state") not in ("open", "completed", "aborted"):
        return [f"AutomatonRun.state {run.get('state')!r} not in "
                f"open|completed|aborted (run {run.get('run_id')})"]
    return []


def revalidate_transcript(events: list, runbook: dict,
                           policy_spec: str) -> list[str]:
    """§9 transcript re-validation. Re-folds the log from seq 0 and
    re-checks, **never reinvoking tools**. Returns violations (empty =
    valid). C2: a trailing step_started with no outcome is valid (crash
    recovery pending, F-E3)."""
    violations = []
    for i, e in enumerate(events):
        if not isinstance(e, dict) or e.get("seq") != i:
            violations.append(
                f"seq gap at index {i}: got "
                f"{e.get('seq') if isinstance(e, dict) else type(e).__name__}")
    unknown = {e["kind"] for e in events
               if isinstance(e, dict)} - _KNOWN_KINDS
    if unknown:
        violations.append(f"unknown event kinds: {sorted(unknown)}")
    if violations:
        return violations
    steps = {s["seq"]: s for s in runbook["steps"]}
    cache_key = (runbook["runbook_id"], runbook.get("release_version"))
    ctx: dict = {}
    started: set = set()
    for e in events:
        kind = e["kind"]
        p = e.get("payload", {})
        if kind == "run_created":
            ctx = dict(p.get("ctx", {}))
        elif kind == "event_injected":
            if isinstance(p.get("payload"), dict):
                ctx.update(p["payload"])
        elif kind == "step_started":
            seq = p.get("step_seq")
            if seq not in steps:
                violations.append(
                    f"step_started for unknown step {seq} at seq {e['seq']}")
                continue
            try:
                g = eval_guard(
                    compile_guard(steps[seq]["expr"], "ctx",
                                  cache_key + (seq,)), {"ctx": ctx})
            except Exception:
                g = "error"
            if g is False:
                violations.append(
                    f"step {seq} started with guard false at seq {e['seq']}")
            # g == "error": the valid recorded outcome is a step_failed
            # carrying the guard error (checked via I-28 adjacency below).
            started.add(seq)
        elif kind == "step_completed":
            seq = p.get("step_seq")
            if seq not in started:
                violations.append(
                    f"step_completed for step {seq} with no step_started "
                    f"at seq {e['seq']}")
            delta = p.get("ctx_delta", {})
            if isinstance(delta, dict):
                ctx.update(delta)
        elif kind == "run_completed":
            # §9: only after the last step's step_completed; terminal.
            pending = [s for s in steps
                       if not _step_done(events, s, e["seq"])]
            if pending:
                violations.append(
                    f"run_completed at seq {e['seq']} with steps pending: "
                    f"{pending}")
    violations.extend(i28_policy_consequence(events, policy_spec))
    violations.extend(i29_quiescence_stickiness(events))
    # run_aborted only via the abort policy (§9): it must follow a
    # step_failed whose consequence is abort.
    for i, e in enumerate(events):
        if e["kind"] == "run_aborted" and i > 0:
            prev = events[i - 1]
            if prev["kind"] != "step_failed":
                violations.append(
                    f"run_aborted at seq {e['seq']} not via the abort "
                    f"policy (previous: {prev['kind']})")
    return violations


def _step_done(events: list, seq: int, before_seq: int) -> bool:
    """Whether step ``seq`` reached completed/skipped before ``before_seq``."""
    done = False
    for e in events:
        if e.get("seq") >= before_seq:
            break
        if e["kind"] in ("step_completed", "step_skipped") and \
                e.get("payload", {}).get("step_seq") == seq:
            done = True
    return done


# ---------------------------------------------------------------------------
# Concurrency (§10)
# ---------------------------------------------------------------------------

class LeaseBusy(Exception):
    """A second concurrent invoker hit the OS file lock (exit 1)."""


@contextmanager
def locked(path: Path):
    """Exclusive, non-blocking OS file lock on ``path`` (§10), held for
    the duration of the critical section. Raises LeaseBusy when held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise LeaseBusy(f"automaton-lease-busy: {path.name}")
    try:
        yield f
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def read_locked(f) -> dict:
    f.seek(0)
    return json.loads(f.read().decode("utf-8"))


def write_locked(f, record: dict) -> None:
    f.seek(0)
    f.truncate()
    f.write((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())


# ---------------------------------------------------------------------------
# Disclosures (§7): the automaton's cry for help, routed to the DR-5 drain
# ---------------------------------------------------------------------------

def disclosure_template(flow_id: str, flow_run_id: str, state_id: str,
                         trigger: str) -> str:
    """The fixed template: flow id, run id, state, trigger — no prose,
    no judgment (F-F4: signaling, not promotion)."""
    return (f"flow_id: {flow_id}\n"
            f"flow_run_id: {flow_run_id}\n"
            f"state_id: {state_id}\n"
            f"trigger: {trigger}\n")


def mint_disclosure(home: Path, flow_id: str, flow_run_id: str,
                    state_id: str, trigger: str) -> dict:
    """Mint an automaton-exception Disclosure into the drain outbox
    (<home>/var/disclosures/). seq is write-path-minted and monotonic
    (DR-5); no clock enters the record."""
    ddir = home / "var" / "disclosures"
    ddir.mkdir(parents=True, exist_ok=True)
    seq_file = ddir / "_seq"
    with locked(seq_file) as f:
        raw = f.read().decode("utf-8").strip()
        seq = (int(raw) + 1) if raw else 1
        f.seek(0)
        f.truncate()
        f.write(str(seq).encode())
    rec = {
        "id": f"dl-{seq:06d}",
        "seq": seq,
        "kind": "automaton-exception",
        "text": disclosure_template(flow_id, flow_run_id, state_id, trigger),
        "status": "open",
        "flow_id": flow_id,
        "flow_run_id": flow_run_id,
        "state_id": state_id,
        "trigger": trigger,
    }
    (ddir / f"dl-{seq:06d}.json").write_text(
        json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec


# ---------------------------------------------------------------------------
# Flow driver (§7)
# ---------------------------------------------------------------------------

class UnhandledTrigger(Exception):
    """No transition routed (from_state, trigger): none true without a
    guardless default, or multiple true (I-15)."""


class FlowDefinitionError(Exception):
    """The flow definition is at fault (unknown state, bad step_policy)."""


def evaluate_transitions(transitions: list, from_state_id: str,
                         trigger: str, payload: dict, run_status=None,
                         cache_key=None) -> str:
    """I-15 set evaluation: exactly one guarded winner wins; none true
    falls to the single guardless default; otherwise unhandled. Returns
    the winning to_state_id.

    Guards evaluate over the (payload, run) namespaces (spec §3): the
    trigger payload, and run.status — the child run's terminal status
    for executor-minted run_completed/run_aborted triggers, None for
    CLI-supplied triggers at wait states.
    """
    cands = [t for t in transitions
             if t["from_state_id"] == from_state_id
             and t["trigger"] == trigger]
    winners = []
    for t in cands:
        guard = t.get("guard")
        if not guard:
            continue
        code = compile_guard(guard, ("payload", "run"),
                             (cache_key, from_state_id, trigger,
                              t.get("id")))
        try:
            satisfied = eval_guard(code, {"payload": payload,
                                          "run": {"status": run_status}})
        except Exception:
            # A guard that raises on this payload (e.g. a missing key)
            # cannot be satisfied by this trigger: the transition is not
            # a winner. If nothing routes, the trigger is unhandled and
            # the §7 abort+disclosure path handles it — never a crash.
            continue
        if satisfied:
            winners.append(t)
    if len(winners) == 1:
        return winners[0]["to_state_id"]
    if not winners:
        defaults = [t for t in cands if not t.get("guard")]
        if len(defaults) == 1:
            return defaults[0]["to_state_id"]
    raise UnhandledTrigger(
        f"unhandled trigger {trigger!r} in state {from_state_id!r}: "
        f"{len(winners)} guarded winners, "
        f"{len([t for t in cands if not t.get('guard')])} guardless defaults")


def _append_flow_event(events: list, from_state_id: str, to_state_id: str,
                       trigger: str, payload: dict) -> None:
    events.append({
        "seq": len(events),
        "from_state_id": from_state_id,
        "to_state_id": to_state_id,
        "trigger": trigger,
        "payload": payload,
    })


def _child_key(flow_run_id: str, state_id: str, entry_seq: int) -> str:
    return f"{flow_run_id}:{state_id}:{entry_seq}"


def _child_run_id(home: Path, key: str) -> str:
    runs_dir = home / "var" / "runs"
    n = 0
    if runs_dir.is_dir():
        for p in runs_dir.glob("*.json"):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(r, dict) and r.get("idempotency_key") == key:
                n += 1
    return "r-" + hashlib.sha256(f"{key}#{n}".encode()).hexdigest()[:16]


def find_child(home: Path, key: str):
    """The open child run carrying ``key``, or the latest closed one, or
    None. (A closed child found here was advanced directly — the
    intervention path; the driver picks up its outcome.)"""
    runs_dir = home / "var" / "runs"
    if not runs_dir.is_dir():
        return None
    found = []
    for p in runs_dir.glob("*.json"):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(r, dict) and r.get("kind") == "run" \
                and r.get("idempotency_key") == key:
            found.append((p, r))
    for p, r in found:
        if r.get("state") == "open":
            return p, r
    return found[-1] if found else None


def spawn_child(home: Path, flow_run_id: str, key: str, state_id: str,
                runbook: dict, step_policy: str) -> tuple:
    """Spawn a child AutomatonRun for a task-state entry (§7, flow-spec
    §6). The policy comes from the task state's step_policy."""
    parse_policy(step_policy)  # fail fast on a definition fault
    run_id = _child_run_id(home, key)
    record = {
        "run_id": run_id,
        "kind": "run",
        "runbook_id": runbook["runbook_id"],
        "release_version": runbook.get("release_version"),
        "state": "open",
        "policy": step_policy,
        "idempotency_key": key,
        "ctx": {},
        "parent_flow_run_id": flow_run_id,
        "flow_state_id": state_id,
        "events": [{"seq": 0, "kind": "run_created", "payload": {
            "runbook_id": runbook["runbook_id"],
            "release_version": runbook.get("release_version"),
            "policy": step_policy, "ctx": {}}}],
    }
    path = home / "var" / "runs" / f"{run_id}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path, record


def advance_flow(frun: dict, flow: dict, resolve_runbook, tools: dict,
                 home: Path, trigger=None, payload=None,
                 max_steps: int = 1000) -> dict:
    """Drive a flow run per §7. Mutates ``frun`` in place.

    flow: {"flow_id","initial_state_id","states":{id:{kind,runbook_id?,
    step_policy?,outcome?}},"transitions":[{from_state_id,trigger,guard?,
    to_state_id,id?}]}. resolve_runbook(runbook_id) → definition dict.
    The CLI-supplied trigger is invocation-scoped input, consumed by the
    first wait state that needs it; executor-minted run_completed /
    run_aborted triggers drive task-state exits (never CLI-supplied).
    """
    if trigger is not None and trigger not in ("timer", "external"):
        raise ValueError(f"bad trigger {trigger!r} (timer|external)")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("trigger payload must be a JSON object")
    if trigger is None and payload is not None:
        raise ValueError("--payload without --trigger is meaningless")
    events = frun["events"]
    states = flow["states"]
    transitions = flow["transitions"]
    pending_trigger = trigger
    pending_payload = payload or {}
    events_before = len(events)
    transitions_taken = 0
    iterations = 0
    hit_bound = False
    for _ in range(max_steps):
        iterations += 1
        if frun["state"] in ("done", "aborted"):
            break
        state_id = frun["current_state_id"]
        state = states.get(state_id)
        if state is None:
            raise FlowDefinitionError(f"unknown state {state_id!r}")
        kind = state["kind"]
        if kind == "end":
            outcome = state.get("outcome")
            frun["state"] = "done" if outcome == "completed" else "aborted"
            break
        if kind == "wait":
            if pending_trigger is None:
                break  # quiescent — the wrapper returns with a trigger
            trig, pl = pending_trigger, pending_payload
            pending_trigger, pending_payload = None, {}
            try:
                to_id = evaluate_transitions(
                    transitions, state_id, trig, pl, run_status=None,
                    cache_key=flow.get("flow_id"))
            except UnhandledTrigger:
                frun["state"] = "aborted"
                mint_disclosure(home, frun["flow_id"], frun["run_id"],
                                state_id, trig)
                break
            _append_flow_event(events, state_id, to_id, trig, pl)
            frun["current_state_id"] = to_id
            transitions_taken += 1
            continue
        if kind == "task":
            runbook_id = state.get("runbook_id")
            rb = resolve_runbook(runbook_id)
            if rb is None:
                raise FlowDefinitionError(
                    f"task state {state_id!r}: unknown run-book "
                    f"{runbook_id!r} — not executor-drivable")
            try:
                step_policy = state.get("step_policy") or "abort"
                parse_policy(step_policy)
            except ValueError as e:
                raise FlowDefinitionError(
                    f"task state {state_id!r}: {e}")
            key = _child_key(frun["run_id"], state_id, len(events))
            found = find_child(home, key)
            if found is None:
                _path, child = spawn_child(home, frun["run_id"], key,
                                           state_id, rb, step_policy)
            else:
                _path, child = found
            with locked(_path) as f:
                child = read_locked(f)
                remaining = max_steps - iterations
                res = advance_run(child, rb, tools, external=None,
                                  max_steps=max(remaining, 1))
                write_locked(f, child)
            iterations += res["iterations"]
            if child["state"] == "open":
                break  # child parked — quiescent
            minted = ("run_completed" if child["state"] == "completed"
                      else "run_aborted")
            # The trigger payload is the child's folded ctx — the run's
            # accumulated knowledge, re-derived from its recorded log
            # (deterministic, never reinvoked). Transition guards read
            # their fields from payload (e.g. payload.remote_version).
            out_payload = dict(child.get("ctx", {}))
            try:
                to_id = evaluate_transitions(
                    transitions, state_id, minted, out_payload,
                    run_status=child["state"],
                    cache_key=flow.get("flow_id"))
            except UnhandledTrigger:
                frun["state"] = "aborted"
                mint_disclosure(home, frun["flow_id"], frun["run_id"],
                                state_id, minted)
                break
            _append_flow_event(events, state_id, to_id, minted, out_payload)
            frun["current_state_id"] = to_id
            transitions_taken += 1
            continue
        raise FlowDefinitionError(
            f"state {state_id!r} has unknown kind {kind!r}")
    else:
        hit_bound = True
    return {
        "run_id": frun["run_id"],
        "state": frun["state"],
        "transitions_taken": transitions_taken,
        "events_appended": len(events) - events_before,
        "iterations": iterations,
        "closed": frun["state"] in ("done", "aborted"),
        "hit_bound": hit_bound,
    }
