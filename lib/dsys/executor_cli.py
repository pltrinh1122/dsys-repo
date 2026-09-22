#!/usr/bin/env python3
"""dsys automaton — run-level invocation surface (executor spec §§4–10).

``init --runbook`` binds an AutomatonRun record (idempotent on the
initiation inputs). ``advance --run`` steps it to quiescence through the
executor. ``replay --run`` re-validates the transcript (I-28/I-29/I-30,
state narrowing) and never reinvokes tools.

This module is the wrapper: it owns record IO, the OS file locks (§10),
and the run-book/tool registries. The executor (executor.py) owns the
step semantics. Run records live at <home>/var/runs/<run_id>.json.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import executor as X

_HERE = Path(__file__).resolve().parent
_TOOLS_DIR = _HERE / "tools"
_RUNBOOKS_DIR = _HERE / "runbooks"


def _runs_dir(home: Path) -> Path:
    return home / "var" / "runs"


def _load_run(home: Path, run_id: str):
    path = _runs_dir(home) / f"{run_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None, path
    except FileNotFoundError:
        return None, f"dsys automaton: unknown run {run_id!r}", path
    except (OSError, json.JSONDecodeError) as e:
        return None, f"dsys automaton: cannot read run {run_id!r}: {e}", path


def _all_runs(home: Path) -> list:
    runs = []
    d = _runs_dir(home)
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(r, dict):
                runs.append(r)
    return runs


# --------------------------------------------------------------------------
# run-book resolution: dist-shipped fixtures/pinned run-books, then the
# updater's entity adapter (production run-books whose tools are unbuilt —
# the executor records the missing tool loudly at advance time, §8).
# --------------------------------------------------------------------------

def make_runbook_resolver(updater=None):
    def resolve(runbook_id: str):
        rb = X.load_runbook(_RUNBOOKS_DIR, runbook_id)
        if rb is not None:
            return rb
        if updater is None:
            return None
        aflow, _states, _trans, runbooks, steps, _tools = \
            updater.compile_flow()
        if runbook_id not in {r.id for r in runbooks}:
            return None
        rb_steps = sorted(
            (s for s in steps if s.runbook_id == runbook_id),
            key=lambda s: s.seq)
        rb = {
            "runbook_id": runbook_id,
            "release_version": aflow.release_version,
            "steps": [{"seq": s.seq - 1, "tool": s.tool_id, "expr": s.expr}
                      for s in rb_steps],
        }
        X.check_runbook(rb, f"updater-entity:{runbook_id}")
        return rb
    return resolve


def _idempotency_key(runbook_id: str, release_version: str,
                     policy: str, ctx: dict) -> str:
    canon = json.dumps(ctx, sort_keys=True, separators=(",", ":"))
    raw = "\0".join([runbook_id, release_version, policy, canon])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# commands — each returns (exit_code, text, notes, data, error)


def init_run(home: Path, runbook_id: str, ctx_json: str | None,
             policy_spec: str, updater=None):
    """Bind an AutomatonRun. Idempotent: the same initiation inputs always
    address the same record (I-30)."""
    resolve = make_runbook_resolver(updater)
    rb = resolve(runbook_id)
    if rb is None:
        return (1, None, None, None,
                f"dsys automaton init: unknown run-book {runbook_id!r}")
    try:
        X.parse_policy(policy_spec)
    except ValueError as e:
        return 1, None, None, None, f"dsys automaton init: {e}"
    ctx = {}
    if ctx_json is not None:
        try:
            ctx = json.loads(ctx_json)
        except json.JSONDecodeError as e:
            return (1, None, None, None,
                    f"dsys automaton init: --ctx is not JSON: {e}")
        if not isinstance(ctx, dict):
            return (1, None, None, None,
                    "dsys automaton init: --ctx must be a JSON object")
    key = _idempotency_key(rb["runbook_id"], rb.get("release_version", ""),
                           policy_spec, ctx)
    run_id = "r-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    runs_dir = _runs_dir(home)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.json"
    try:
        with X.locked(path) as f:
            f.seek(0, 2)
            if f.tell() == 0:
                run, created = None, True
            else:
                try:
                    run = X.read_locked(f)
                except json.JSONDecodeError as e:
                    return (1, None, None, None,
                            f"dsys automaton init: existing record "
                            f"{run_id!r} is corrupt: {e}")
                created = False
            if created:
                run = {
                    "run_id": run_id,
                    "kind": "run",
                    "runbook_id": rb["runbook_id"],
                    "release_version": rb.get("release_version"),
                    "state": "open",
                    "policy": policy_spec,
                    "idempotency_key": key,
                    "ctx": ctx,
                    "events": [{"seq": 0, "kind": "run_created", "payload": {
                        "runbook_id": rb["runbook_id"],
                        "release_version": rb.get("release_version"),
                        "policy": policy_spec, "ctx": ctx}}],
                }
                X.write_locked(f, run)
    except X.LeaseBusy as e:
        return 1, None, None, None, f"dsys automaton init: {e}"
    # A record that exists but carries a different key is a hash
    # collision in the 64-bit prefix — report it, don't silently adopt.
    if run.get("idempotency_key") != key:
        return (1, None, None, None,
                f"dsys automaton init: run-id collision for {run_id!r} "
                "(record carries a different idempotency key)")
    data = {"run_id": run_id, "runbook_id": rb["runbook_id"],
            "state": run.get("state"), "created": created}
    text = (f"run {run_id} initiated (runbook={rb['runbook_id']})"
            if created else
            f"run {run_id} already bound (runbook={rb['runbook_id']})")
    return 0, text, None, data, None


def advance_run_cmd(home: Path, run_id: str, external_kind: str | None,
                    payload_json: str | None, max_steps: int, updater=None):
    """Step a run to quiescence. Refuses to extend a tampered log."""
    run, err, path = _load_run(home, run_id)
    if err is not None:
        return 1, None, None, None, err
    if run.get("kind") == "flow":
        return (1, None, None, None,
                f"dsys automaton advance: {run_id!r} is a flow run "
                "(use --flow-run)")
    if not isinstance(max_steps, int) or max_steps < 1:
        return (1, None, None, None,
                "dsys automaton advance: --max-steps must be a positive integer")
    external = None
    if external_kind is not None:
        if not external_kind.strip():
            return (1, None, None, None,
                    "dsys automaton advance: --external kind must be "
                    "non-empty")
        payload = {}
        if payload_json is not None:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError as e:
                return (1, None, None, None,
                        f"dsys automaton advance: --payload is not JSON: {e}")
            if not isinstance(payload, dict):
                return (1, None, None, None,
                        "dsys automaton advance: --payload must be a JSON "
                        "object")
        external = (external_kind, payload)
    resolve = make_runbook_resolver(updater)
    rb = resolve(run.get("runbook_id"))
    if rb is None:
        return (1, None, None, None,
                f"dsys automaton advance: unknown run-book "
                f"{run.get('runbook_id')!r}")
    try:
        tools = X.load_tools(_TOOLS_DIR)
    except ValueError as e:
        return 1, None, None, None, f"dsys automaton advance: {e}"
    try:
        with X.locked(path) as f:
            run = X.read_locked(f)
            if run.get("state") in ("completed", "aborted"):
                data = {"run_id": run_id, "state": run.get("state"),
                        "steps_advanced": 0, "events_appended": 0,
                        "closed": True}
                return 0, None, "run already closed — no-op", data, None
            # Refuse to extend a tampered log (the pre-check re-validates;
            # the advance itself never reinvokes tools for recorded steps).
            bad = X.revalidate_transcript(
                run.get("events", []), rb, run.get("policy", "abort"))
            if bad:
                data = {"run_id": run_id, "valid": False,
                        "violations": bad}
                return (5, None, None, data,
                        "dsys automaton advance: transcript invalid — "
                        "refusing to extend it")
            summary = X.advance_run(run, rb, tools, external=external,
                                    max_steps=max_steps)
            X.write_locked(f, run)
    except X.LeaseBusy as e:
        return 1, None, None, None, f"dsys automaton advance: {e}"
    notes = None
    if summary["hit_bound"]:
        notes = (f"resource bound hit after {summary['iterations']} "
                 "iterations — no semantic stop recorded")
    text = (f"run {run_id}: state={summary['state']} "
            f"steps_advanced={summary['steps_advanced']} "
            f"events_appended={summary['events_appended']}")
    return 0, text, notes, summary, None


def replay_run_cmd(home: Path, run_id: str, updater=None):
    """Re-validate a run's transcript. Never reinvokes tools."""
    run, err, _path = _load_run(home, run_id)
    if err is not None:
        return 1, None, None, None, err
    resolve = make_runbook_resolver(updater)
    violations = X.i_state_narrowed(run)
    rb = resolve(run.get("runbook_id"))
    if rb is None:
        violations.append(
            f"unknown run-book {run.get('runbook_id')!r}: "
            "cannot re-validate guards")
    else:
        violations.extend(X.revalidate_transcript(
            run.get("events", []), rb, run.get("policy", "abort")))
    violations.extend(X.i30_init_idempotency(_all_runs(home)))
    data = {"run_id": run_id, "valid": not violations,
            "violations": violations}
    if violations:
        return (5, None, None, data,
                "dsys automaton replay: transcript invalid: "
                + "; ".join(violations))
    return 0, f"run {run_id}: transcript valid", None, data, None
