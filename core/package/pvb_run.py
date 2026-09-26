"""Live runner for the PVB workflow — the Harness-side harness.

Event-sourced: <run_dir>/input_events.jsonl is the source of truth. Every
injection appends one attributed event and re-derives the case by driving
ALL input events from the opening snapshot, so the derived state is always
the deterministic fold of the log. Derived artifacts (case.json,
flow_events.jsonl) are rewritten, never hand-edited.

Usage (from the repo root):
    python3 -m core.package.pvb_run open <run_dir> <case_id> <document_path>
    python3 -m core.package.pvb_run inject <run_dir> '<event json>'
    python3 -m core.package.pvb_run status <run_dir>
"""
from __future__ import annotations

import json
import os
import sys

from .pvb_workflow import (
    ENTITIES,
    PVBCase,
    PVBWorld,
    begin_case,
    drive,
    replay,
)

_, STATES, _, _, _, _ = ENTITIES
STATE_NAMES = {s.id: s.name for s in STATES}
INITIAL_STATE = ENTITIES[0].initial_state_id


def _paths(run_dir: str) -> dict[str, str]:
    return {
        "meta": os.path.join(run_dir, "meta.json"),
        "input": os.path.join(run_dir, "input_events.jsonl"),
        "case": os.path.join(run_dir, "case.json"),
        "flow": os.path.join(run_dir, "flow_events.jsonl"),
        "records": os.path.join(run_dir, "records"),
    }


def open_run(run_dir: str, case_id: str, document_path: str) -> None:
    p = _paths(run_dir)
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(p["records"], exist_ok=True)
    case = begin_case(case_id, document_path)
    meta = {"case_id": case_id,
            "initial_document_path": os.path.abspath(document_path),
            "initial_document_hash": case.document_hash}
    with open(p["meta"], "w", encoding="utf-8") as f:
        json.dump(meta, f, sort_keys=True, indent=2)
    open(p["input"], "w").close()
    _recompute(run_dir)


def _recompute(run_dir: str) -> tuple[PVBCase, list]:
    """Re-derive the case from the full input log. The single place where
    the automaton runs."""
    p = _paths(run_dir)
    with open(p["meta"], encoding="utf-8") as f:
        meta = json.load(f)
    events = []
    with open(p["input"], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    case = PVBCase(case_id=meta["case_id"],
                   document_path=meta["initial_document_path"],
                   document_hash=meta["initial_document_hash"])
    world = PVBWorld(records_dir=p["records"])
    log = drive(case, world, events, flow_run_id=f"fr-{meta['case_id']}")
    with open(p["case"], "w", encoding="utf-8") as f:
        json.dump(case.model_dump(mode="json"), f, sort_keys=True, indent=2)
    with open(p["flow"], "w", encoding="utf-8") as f:
        for e in log:
            f.write(json.dumps(e.model_dump(mode="json"),
                               sort_keys=True) + "\n")
    return case, log


def inject(run_dir: str, event: dict) -> tuple[PVBCase, list]:
    """Append one attributed event and re-derive. A refused event is rolled
    back out of the log — the log only ever holds accepted events."""
    from .pvb_workflow import DriveRefused
    p = _paths(run_dir)
    with open(p["input"], "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    try:
        return _recompute(run_dir)
    except DriveRefused:
        with open(p["input"], encoding="utf-8") as f:
            lines = f.readlines()
        with open(p["input"], "w", encoding="utf-8") as f:
            f.writelines(lines[:-1])
        raise


def simulate(run_dir: str, events: list[dict]) -> dict:
    """Hypothetical continuation from the live case's current state.

    Containment (the scenario-simulation discipline, DR-CMD-041): the live
    run's logs are never touched — the full input log plus the hypothetical
    events are driven on a fresh case with the records dir redirected to a
    temp dir. Nothing here is a disposition and nothing here ratifies.
    """
    import tempfile
    p = _paths(run_dir)
    with open(p["meta"], encoding="utf-8") as f:
        meta = json.load(f)
    prior = []
    with open(p["input"], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                prior.append(json.loads(line))
    case = PVBCase(case_id=meta["case_id"],
                   document_path=meta["initial_document_path"],
                   document_hash=meta["initial_document_hash"])
    with tempfile.TemporaryDirectory() as tmp:
        world = PVBWorld(records_dir=os.path.join(tmp, "records"))
        log = drive(case, world, prior + events,
                    flow_run_id=f"fr-{meta['case_id']}-sim")
    path = replay(log)
    return {
        "simulation": True,
        "hypothetical_events": events,
        "path": [STATE_NAMES.get(s, s) for s in path],
        "state": STATE_NAMES.get(path[-1], path[-1]) if path else None,
        "open_findings": sum(1 for x in case.findings
                             if x.status == "open"),
        "revisions": case.revisions,
        "ratified": case.ratification is not None,
    }


def status(run_dir: str) -> dict:
    p = _paths(run_dir)
    with open(p["case"], encoding="utf-8") as f:
        case = json.load(f)
    path, last = [], None
    with open(p["flow"], encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if not path:
                path.append(e["from_state_id"])
            path.append(e["to_state_id"])
            last = e
    cur = path[-1] if path else INITIAL_STATE
    display_path = [INITIAL_STATE] if not path else path
    # Replay check: the log alone re-derives the path.
    with open(p["flow"], encoding="utf-8") as f:
        from .schema import FlowTransitionEvent
        evs = [FlowTransitionEvent(**json.loads(line)) for line in f
               if line.strip()]
    assert replay(evs) == path
    return {
        "case_id": case["case_id"],
        "state": STATE_NAMES.get(cur, cur),
        "path": [STATE_NAMES.get(s, s) for s in display_path],
        "open_findings": sum(1 for x in case["findings"]
                             if x["status"] == "open"),
        "revisions": case["revisions"],
        "ratified": case["ratification"] is not None,
        "document_hash": case["document_hash"][:12],
    }


def main(argv: list[str]) -> None:
    cmd = argv[1]
    if cmd == "open":
        _, _, run_dir, case_id, doc = argv
        open_run(run_dir, case_id, doc)
        print(json.dumps(status(run_dir), indent=2))
    elif cmd == "inject":
        _, _, run_dir, event_json = argv
        case, _ = inject(run_dir, json.loads(event_json))
        print(json.dumps(status(run_dir), indent=2))
    elif cmd == "simulate":
        _, _, run_dir, events_json = argv
        print(json.dumps(simulate(run_dir, json.loads(events_json)),
                         indent=2))
    elif cmd == "status":
        _, _, run_dir = argv
        print(json.dumps(status(run_dir), indent=2))
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv)
