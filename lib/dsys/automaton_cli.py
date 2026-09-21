#!/usr/bin/env python3
"""dsys automaton — the flow-drive invocation surface (cli-interface-spec §3.7).

This is the enforcement home for I-26 (authorized initiation) and I-27
(authorized acquisition): ``init-flow`` performs the full initiation gate
sequence — profile, I-26, real acquisition against the install config /
manifest / git repo — before binding the run. Refusals happen before the
run exists, so a refused initiation writes nothing.

This module is the invocation surface only. Step semantics, trigger
validation, failure policies, and replay semantics are the executor's
contract (doc/automaton-executor-spec.md §§4–9); the drive execution
vehicle (production tool implementations) is not built, so ``advance``
gates, re-validates post-hoc, and refuses rather than faking a run
(the cmd_execute / cmd_session precedent).

Run records live at <home>/var/runs/<run_id>.json: the initiation record,
the acquisition record, and the append-only event log the executor will
extend. ``replay`` re-validates that log with the package's replay and
never reinvokes tools.

Manifest identity field: ``accretion_repo.identity`` (nested object), per
the K1 Q3(a) binding spec D1/D5. The installer-spec implements the real
mint; until it does, real installations carry no identity and init-flow
refuses per the acquisition contract D3(b) — the fail-fast working.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

# The vendored core lives at <home>/lib/core in an installed tree. In the
# source working tree (no lib/core) fall back to <repo>/core so the surface
# stays testable without an install.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _updater(home: Path):
    """Import core.package.updater the install-home way, with a repo fallback."""
    candidates = [home / "lib" / "core", _REPO_ROOT / "core"]
    for cand in candidates:
        if (cand / "package" / "updater.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            from package import updater  # noqa: E402
            return updater
    raise ImportError(
        "dsys automaton: vendored core not found "
        f"(looked in {[str(c) for c in candidates]})"
    )


def _schema(home: Path):
    _updater(home)  # ensures the core is on sys.path
    from package import schema  # noqa: E402
    return schema


def _flows(U) -> tuple:
    return (U.FLOW_ID,)


def _runs_dir(home: Path) -> Path:
    return home / "var" / "runs"


def _manifest_identity(manifest: dict):
    """The installer's minted repo UUID, or None (un-minted install)."""
    acc = manifest.get("accretion_repo")
    if isinstance(acc, dict):
        ident = acc.get("identity")
        return ident if isinstance(ident, str) and ident else None
    return None


def _config_accretion_path(home: Path):
    """Read the raw etc/config.yaml accretion.path (one nested level).

    config.load warns-and-ignores unknown keys, so the nested accretion
    mapping is read raw here — mirroring install.sh's awk reader.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import yamlutil  # noqa: E402
    cfg_path = home / "etc" / "config.yaml"
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        raw = yamlutil.loads(text)
    except ValueError:
        return None
    acc = raw.get("accretion")
    if isinstance(acc, dict):
        p = acc.get("path")
        if isinstance(p, str) and p.strip():
            return p.strip()
    return None


def _resolve_accretion_path(home: Path, flag: str | None):
    """Precedence: --accretion-path > config accretion.path > default."""
    if flag:
        return flag, "flag"
    cfg_path = _config_accretion_path(home)
    if cfg_path:
        return cfg_path, "config"
    return f"/var/daccretion/{home.name}", "default"


def _git(args, git_dir: str):
    """Run git against a repo dir. Returns (returncode, stdout)."""
    try:
        proc = subprocess.run(
            ["git", f"--git-dir={git_dir}"] + args,
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def _acquire_at(path: str, source: str, manifest_identity: str | None, U):
    """The D1 acquisition mechanic against a given path. Returns
    (AcquisitionRecord, error_message). error_message is None on success."""
    git_dir = str(Path(path) / ".git")
    rc, _ = _git(["rev-parse", "--git-dir"], git_dir)
    git_available = (rc == 0)
    repo_identity = None
    if git_available:
        rc, out = _git(["config", "dsys.repo-id"], git_dir)
        if rc == 0 and out:
            repo_identity = out
    rec = U.AcquisitionRecord(
        path_source=source, path=path, git_available=git_available,
        manifest_identity=manifest_identity, repo_identity=repo_identity,
        at_initiation=True,
    )
    bad = U.i27_authorized_acquisition(rec)
    if bad:
        return None, ("acquisition refused (fail fast): " + "; ".join(bad))
    return rec, None


def _acquire(home: Path, manifest: dict, accretion_path_flag: str | None, U):
    """Resolve (flag > config > default) then acquire. Returns
    (AcquisitionRecord, error_message)."""
    path, source = _resolve_accretion_path(home, accretion_path_flag)
    return _acquire_at(path, source, _manifest_identity(manifest), U)


def _run_id(flow_id: str, profile: str, path: str, manifest_identity: str | None) -> str:
    """Idempotency key: content hash of (flow_id, profile, accretion path,
    manifest identity). A new identity (fresh install) is a new run (D4)."""
    key = "\0".join([flow_id, profile, path, manifest_identity or ""])
    return "fr-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _load_run(home: Path, run_id: str):
    path = _runs_dir(home) / f"{run_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"dsys automaton: unknown flow run {run_id!r}"
    except (OSError, json.JSONDecodeError) as e:
        return None, f"dsys automaton: cannot read run {run_id!r}: {e}"


# --------------------------------------------------------------------------
# commands — each returns (exit_code, text, notes, data, error)


def init_flow(home: Path, manifest: dict, flow_id: str,
              accretion_path_flag: str | None):
    U = _updater(home)
    if flow_id not in _flows(U):
        return (1, None, None, None,
                f"dsys automaton init-flow: unknown flow {flow_id!r}")
    profile = manifest.get("profile") or "base"
    manifest_identity = _manifest_identity(manifest)

    # I-26: the CLI invocation is the operator-direct, strapped-Harness
    # path (drive contract D2, adopted). The Harness module itself is
    # future work; the strapping is architectural, claimed by the adopted
    # contract — not a runtime fact this surface can demonstrate.
    initiation = U.DriveInitiation(
        initiator="operator", origin="operator-direct",
        principal="dyad-or-human", harness_strapped=True,
        profile=profile, manifest_identity=manifest_identity,
    )
    bad = U.i26_authorized_initiation(initiation)
    if bad:
        return (1, None, None, None,
                "dsys automaton init-flow: initiation refused: " + "; ".join(bad))

    acquisition, err = _acquire(home, manifest, accretion_path_flag, U)
    if err is not None:
        return 1, None, None, None, f"dsys automaton init-flow: {err}"

    run_id = _run_id(flow_id, profile, acquisition.path,
                     acquisition.manifest_identity)
    runs_dir = _runs_dir(home)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_file = runs_dir / f"{run_id}.json"
    if run_file.is_file():
        run, rerr = _load_run(home, run_id)
        if rerr is not None:
            return 1, None, None, None, rerr
        # Idempotent re-init returns the existing run — but never silently
        # hands back a run whose acquisition has gone invalid under it.
        invalid = _revalidate(home, run, manifest, U)
        if invalid is not None:
            return (1, None, None, None,
                    f"dsys automaton init-flow: existing run {run_id} is "
                    f"invalid: {invalid}")
        data = {"run_id": run_id, "flow_id": flow_id,
                "state": run.get("state"), "created": False}
        return 0, f"flow run {run_id} already bound (flow={flow_id})", None, data, None

    aflow = U.compile_flow()[0]
    run = {
        "run_id": run_id,
        "flow_id": flow_id,
        "state": "running",
        "current_state_id": aflow.initial_state_id,
        "initiation": {
            "initiator": initiation.initiator,
            "origin": initiation.origin,
            "principal": initiation.principal,
            "harness_strapped": initiation.harness_strapped,
            "profile": initiation.profile,
            "manifest_identity": initiation.manifest_identity,
        },
        "acquisition": {
            "path_source": acquisition.path_source,
            # The resolved path is liveness, not identity: it rides the run
            # record (the transcript envelope, R1) and never enters guards.
            "path": acquisition.path,
            "manifest_identity": acquisition.manifest_identity,
            "repo_identity": acquisition.repo_identity,
            "at_initiation": acquisition.at_initiation,
        },
        "events": [],
    }
    try:
        run_file.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    except OSError as e:
        return 1, None, None, None, \
            f"dsys automaton init-flow: cannot write run record: {e}"
    data = {"run_id": run_id, "flow_id": flow_id,
            "state": "running", "created": True}
    return 0, f"flow run {run_id} initiated (flow={flow_id})", None, data, None


def _revalidate(home: Path, run, manifest: dict, U):
    """Post-hoc I-26/I-27 over the stored initiation/acquisition records,
    against the live world. Returns an error message, or None when the
    stored records still hold. A drive found post-hoc to violate is
    invalid (drive contract D3)."""
    i = run.get("initiation", {})
    a = run.get("acquisition", {})
    initiation = U.DriveInitiation(
        initiator=i.get("initiator"), origin=i.get("origin"),
        principal=i.get("principal"),
        harness_strapped=i.get("harness_strapped", False),
        profile=i.get("profile"), manifest_identity=i.get("manifest_identity"),
    )
    bad = U.i26_authorized_initiation(initiation)
    if bad:
        return "stored initiation no longer authorized: " + "; ".join(bad)
    # Re-run the real acquisition mechanic at the stored path against the
    # live manifest: rebinding (new repo at the path) or reinstall (new
    # manifest identity) surfaces here, not from trusted storage.
    live_manifest_identity = _manifest_identity(manifest)
    rec, err = _acquire_at(a.get("path") or "", a.get("path_source") or "default",
                           live_manifest_identity, U)
    if err is not None:
        return f"stored acquisition no longer valid: {err}"
    if (rec.manifest_identity != a.get("manifest_identity")
            or rec.repo_identity != a.get("repo_identity")):
        return ("stored acquisition no longer valid: identity changed under "
                "the run (rebound path or reinstall — binding D2 / D4)")
    return None


def advance_flow_run(home: Path, manifest: dict, flow_run_id: str,
                     trigger: str | None, payload: str | None,
                     max_steps: int):
    U = _updater(home)
    run, err = _load_run(home, flow_run_id)
    if err is not None:
        return 1, None, None, None, err
    if run.get("state") in ("done", "aborted"):
        data = {"run_id": flow_run_id, "state": run.get("state"),
                "steps_advanced": 0, "events_appended": 0, "closed": True}
        return 0, None, "run already closed — no-op", data, None
    invalid = _revalidate(home, run, manifest, U)
    if invalid is not None:
        return 1, None, None, None, \
            f"dsys automaton advance: {invalid}"
    if trigger not in (None, "timer", "external"):
        return (1, None, None, None,
                f"dsys automaton advance: bad trigger {trigger!r} "
                "(timer|external)")
    if payload is not None:
        try:
            json.loads(payload)
        except json.JSONDecodeError as e:
            return (1, None, None, None,
                    f"dsys automaton advance: --payload is not JSON: {e}")
    if not isinstance(max_steps, int) or max_steps < 1:
        return (1, None, None, None,
                "dsys automaton advance: --max-steps must be a positive integer")
    # The drive execution vehicle — production tool implementations and the
    # executor's step semantics (automaton-executor-spec §§5–8) — is not
    # built. Refusing rather than faking a run (the cmd_execute precedent).
    return (1, None, None, None,
            "dsys automaton advance: drive execution is not implemented in "
            "this build — refusing rather than faking a run")


def replay_flow_run(home: Path, manifest: dict, flow_run_id: str):
    U = _updater(home)
    schema = _schema(home)
    run, err = _load_run(home, flow_run_id)
    if err is not None:
        return 1, None, None, None, err
    aflow, _states, transitions, _rb, _steps, _tools = U.compile_flow()
    events = []
    for e in run.get("events", []):
        try:
            events.append(schema.FlowTransitionEvent(
                flow_run_id=flow_run_id, seq=e["seq"],
                from_state_id=e["from_state_id"], to_state_id=e["to_state_id"],
                trigger=e["trigger"], payload=json.dumps(e.get("payload", {})),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            data = {"run_id": flow_run_id, "valid": False,
                    "violations": [f"malformed stored event: {exc}"]}
            return 5, None, None, data, None
    try:
        _path = U.replay(events, transitions, aflow.initial_state_id)
    except ValueError as e:
        data = {"run_id": flow_run_id, "valid": False, "violations": [str(e)]}
        return 5, None, None, data, None
    data = {"run_id": flow_run_id, "valid": True, "violations": []}
    return 0, f"flow run {flow_run_id}: transcript valid", None, data, None
