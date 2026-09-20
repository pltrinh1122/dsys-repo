#!/usr/bin/env python3
"""dsys command-line interface (base-profile machinery).

Startup order: (1) resolve the install home and read var/manifest.json
(refusing on a missing manifest or a moved tree); (2) parse args;
(3) load config (flags > config file > DEFAULTS); (4) dispatch.

On the base profile, ``roles``, ``scenario``, ``execute``, ``derive`` and
``session`` refuse with an unavailable-capability error (exit 1);
``referee``, ``state`` and ``doctor`` are served by the sibling modules.
``execute`` and ``session`` are full-profile stubs with their own refusals.

Exit codes: 0 ok / 1 usage|config|unavailable-capability /
2 backend failure (missing) / 4 agent refusal / 5 validation violations
(``referee validate``) or derivation failed/refused (``derive``) /
6 scenario failure.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Sibling modules live next to this file and import each other as top-level
# modules (bin/dsys execs this file directly, so its dir is sys.path[0]).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import resolve_home
from config import ConfigError, load as load_config
from envelope import TOOL_VERSION, envelope

BASE_BLOCKED = ("roles", "scenario", "execute", "derive", "session")
_DOCTOR_STATUS = {"ok": "ok", "warn": "WARN", "fail": "FAIL"}


# --------------------------------------------------------------------------
# startup helpers


def _prescan(argv):
    """Best-effort scan for --format and the subcommand before full parsing.

    The manifest is checked before argparse runs, but JSON-mode failures
    still need an envelope, so --format is detected up front.
    """
    fmt = None
    command = None
    i, n = 0, len(argv)
    while i < n:
        a = argv[i]
        if a == "--format" and i + 1 < n:
            fmt, i = argv[i + 1], i + 2
        elif a.startswith("--format="):
            fmt, i = a.split("=", 1)[1], i + 1
        elif a in ("--config", "--backend"):
            i += 2
        elif a.startswith("--config=") or a.startswith("--backend="):
            i += 1
        elif a in ("-q", "--quiet", "-v", "--verbose", "--version"):
            i += 1
        elif a == "--":
            if i + 1 < n:
                command = argv[i + 1]
            break
        elif a.startswith("-") and a != "-":
            i += 1
        else:
            command = a
            break
    return fmt, command


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors exit 1 (not argparse's 2)."""

    def error(self, message):
        info = getattr(self, "_dsys", {}) or {}
        as_json = info.get("json", False)
        cmd = info.get("command") or "none"
        profile = info.get("profile")
        full = f"dsys: error: {message}"
        if as_json:
            print(json.dumps(envelope(cmd, profile, 1, error={"message": full})))
        else:
            self.print_usage(sys.stderr)
            print(full, file=sys.stderr)
        raise SystemExit(1)


def _build_parser():
    parser = _Parser(prog="dsys", description="dsys CLI — base-profile machinery")
    parser.add_argument("--config", metavar="PATH", default=None,
                        help="config file (default: <home>/etc/config.yaml)")
    parser.add_argument("--backend", metavar="NAME", default=None,
                        help="agent backend (overrides config)")
    parser.add_argument("--format", choices=("text", "json"), default=None,
                        help="output format (overrides config)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="suppress non-error diagnostics")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="extra diagnostics on stderr")
    parser.add_argument("--version", action="store_true",
                        help="print version info and exit")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_exec = sub.add_parser("execute", help="run an agent turn (full profile only)")
    p_exec.add_argument("--as", dest="as_role", required=True, metavar="ROLE")
    p_exec.add_argument("--prompt", default=None, metavar="TEXT")
    p_exec.add_argument("--prompt-file", default=None, metavar="PATH")
    p_exec.add_argument("--timeout", type=int, default=None, metavar="SEC")
    p_exec.add_argument("--stream", action="store_true")
    p_exec.add_argument("--max-tokens", type=int, default=None, metavar="N")

    p_roles = sub.add_parser("roles", help="role bundles (full profile only)")
    s_roles = p_roles.add_subparsers(dest="roles_cmd", metavar="<roles-command>",
                                     required=True)
    s_roles.add_parser("list", help="list role bundles")
    p_rshow = s_roles.add_parser("show", help="print a role's prompt")
    p_rshow.add_argument("role", metavar="ROLE")

    p_ref = sub.add_parser("referee", help="validate state files / render views")
    s_ref = p_ref.add_subparsers(dest="referee_cmd", metavar="<referee-command>",
                                 required=True)
    p_val = s_ref.add_parser("validate", help="validate a state file")
    p_val.add_argument("--state", required=True, metavar="FILE")
    p_view = s_ref.add_parser("view", help="render a verification view")
    p_view.add_argument("--state", required=True, metavar="FILE")
    p_view.add_argument("--view", required=True, metavar="NAME")

    p_scen = sub.add_parser("scenario", help="test-drive scenarios (full profile only)")
    s_scen = p_scen.add_subparsers(dest="scenario_cmd",
                                   metavar="<scenario-command>", required=True)
    s_scen.add_parser("list", help="list scenarios")
    p_srun = s_scen.add_parser("run", help="run a scenario")
    p_srun.add_argument("name", metavar="NAME")

    p_state = sub.add_parser("state", help="state files")
    s_state = p_state.add_subparsers(dest="state_cmd", metavar="<state-command>",
                                     required=True)
    p_init = s_state.add_parser("init", help="write an initial state file")
    p_init.add_argument("--seed", choices=("golden", "empty"), default="golden")
    p_init.add_argument("--out", metavar="FILE", default=None,
                        help="output path (default: <home>/var/state/state.json)")
    p_get = s_state.add_parser("get", help="read records from a state file")
    p_get.add_argument("--state", required=True, metavar="FILE")
    p_get.add_argument("--collection", required=True, metavar="NAME")
    p_get.add_argument("--id", default=None, metavar="ID")

    p_doc = sub.add_parser("doctor", help="run self checks")
    p_doc.add_argument("--strict", action="store_true",
                       help="treat warnings as failures")

    p_sess = sub.add_parser("session", help="session sync (full profile only)")
    s_sess = p_sess.add_subparsers(dest="session_cmd", metavar="<session-cmd>")
    for _sc in ("init", "join", "push", "pull", "status", "divergences"):
        s_sess.add_parser(_sc)

    p_der = sub.add_parser("derive", help="run a derivation (full profile only)")
    p_der.add_argument("input", nargs="?", default=None, metavar="PATH|URL",
                       help="derivation input: filesystem path or file:// URL "
                            "(remote URLs are refused: derive is offline)")
    p_der.add_argument("--manifest", default=None, metavar="PATH|URL",
                       help="DerivationManifest JSON as a path or file:// URL")
    p_der.add_argument("--out", default=None, metavar="DIR",
                       help="write output.bin + receipt.json here")

    return parser


# --------------------------------------------------------------------------
# result helpers
#
# Handlers return (exit_code, stdout_text, stderr_notes, data, error_message):
#   stdout_text   -> stdout in text mode (the command's primary output)
#   stderr_notes  -> stderr in text mode, non-fatal (suppressed by -q)
#   data          -> the JSON envelope's "data"
#   error_message -> stderr in text mode; JSON envelope's error.message


def _import_sibling(name, what):
    try:
        return __import__(name), None
    except ImportError:
        return None, f"dsys: {what} is not available in this build"


def _render_row(row):
    if isinstance(row, dict):
        return ", ".join(f"{k}={v}" for k, v in row.items())
    return str(row)


def _finish(cmd, profile, result, as_json, quiet):
    code, out, notes, data, error = result
    if as_json:
        print(json.dumps(envelope(cmd, profile, code, data=data,
                                  error={"message": error} if error else None)))
    else:
        if out:
            print(out)
        if notes and not quiet:
            print(notes, file=sys.stderr)
        if error:
            print(error, file=sys.stderr)
    return code


# --------------------------------------------------------------------------
# handlers


def cmd_derive(args, cfg, home, manifest):
    runner, err = _import_sibling("runner", "runner")
    if runner is None:
        return 1, None, None, None, err
    try:
        result = runner.derive_command(
            input=args.input, manifest_locator=args.manifest,
            out_dir=args.out, home=home,
            installed_manifest=manifest, tool_version=TOOL_VERSION)
    except runner.RunnerRefusal as e:
        return 1, None, None, None, f"dsys: {e}"
    except runner.DerivationFailure as e:
        text = json.dumps(e.receipt, indent=2, sort_keys=True)
        return 5, text, None, e.receipt, None
    receipt = result["receipt"]
    text = json.dumps(receipt, indent=2, sort_keys=True)
    notes = None
    if result["cache_hit"]:
        notes = ("cache hit — original receipt cited, no fresh attestation "
                 "minted (R-5)")
    return 0, text, notes, receipt, None


def cmd_execute(args, cfg, home):
    return (2, None, None, None,
            "dsys execute: no agent backend in this build — "
            "refusing rather than faking a run")


def cmd_session(args, cfg, home):
    return (1, None, None, None,
            "dsys session: sync service not implemented in this build")


def cmd_roles_list(args, cfg, home):
    roles, err = _import_sibling("roles", "role bundles")
    if roles is None:
        return 1, None, None, None, err
    try:
        bundles = roles.list_bundles(Path(cfg["roles_dir"]))
    except roles.RoleError as e:
        return 1, None, None, None, f"dsys roles: {e}"
    lines = [f"{b.name} {b.version} {b.role_hash[:12]}" for b in bundles]
    data = [{"name": b.name, "version": b.version, "role_hash": b.role_hash}
            for b in bundles]
    return 0, "\n".join(lines), None, {"bundles": data}, None


def cmd_roles_show(args, cfg, home):
    roles, err = _import_sibling("roles", "role bundles")
    if roles is None:
        return 1, None, None, None, err
    try:
        bundle = roles.load_bundle(Path(cfg["roles_dir"]), args.role)
    except roles.RoleError as e:
        return 1, None, None, None, f"dsys roles: {e}"
    prompt = (bundle.dir / "prompt.md").read_text(encoding="utf-8")
    notes = f"role {bundle.name} {bundle.version} {bundle.role_hash[:12]}"
    data = {"role": bundle.name, "version": bundle.version,
            "role_hash": bundle.role_hash, "prompt": prompt}
    return 0, prompt, notes, data, None


def cmd_referee_validate(args, cfg, home):
    referee, err = _import_sibling("referee", "referee")
    if referee is None:
        return 1, None, None, None, err
    try:
        code, payload = referee.validate_state(home, args.state)
    except referee.RefereeError as e:
        return 1, None, None, None, f"dsys referee: {e}"
    except OSError as e:
        return 1, None, None, None, f"dsys referee: cannot read {args.state}: {e}"
    violations = payload.get("violations", []) or []
    if code == 0:
        return 0, "clean", None, payload, None
    text = "\n".join(str(v) for v in violations)
    return code, text, None, payload, None


def cmd_referee_view(args, cfg, home):
    referee, err = _import_sibling("referee", "referee")
    if referee is None:
        return 1, None, None, None, err
    try:
        code, payload = referee.view_state(home, args.state, args.view)
    except referee.RefereeError as e:
        return 1, None, None, None, f"dsys referee: {e}"
    except OSError as e:
        return 1, None, None, None, f"dsys referee: cannot read {args.state}: {e}"
    rows = payload.get("rows", []) or []
    return code, "\n".join(_render_row(r) for r in rows), None, payload, None


def _scenario_dir(home):
    return Path(home) / "share" / "scenarios"


def cmd_scenario_list(args, cfg, home):
    sdir = _scenario_dir(home)
    if not sdir.is_dir():
        return 1, None, None, None, f"dsys scenario: no scenarios directory at {sdir}"
    names = sorted(p.stem for p in sdir.glob("*.py") if p.is_file())
    return 0, "\n".join(names), None, {"scenarios": names}, None


def cmd_scenario_run(args, cfg, home, verbose):
    sdir = _scenario_dir(home)
    script = sdir / args.name
    if script.suffix != ".py":
        script = sdir / (args.name + ".py")
    if not script.is_file():
        return 1, None, None, None, f"dsys scenario: unknown scenario {args.name!r}"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(home) / "lib" / "core")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            env=env, capture_output=True, text=True,
            timeout=cfg["timeout_s"],
        )
    except subprocess.TimeoutExpired:
        return (6, None, None,
                {"name": args.name, "passed": False, "timed_out": True},
                f"scenario {args.name}: TIMEOUT after {cfg['timeout_s']}s")
    data = {"name": args.name, "passed": proc.returncode == 0,
            "exit_code": proc.returncode, "timed_out": False}
    if proc.returncode == 0:
        notes = None
        if verbose and (proc.stdout.strip() or proc.stderr.strip()):
            notes = f"--- {script.name} stdout ---\n{proc.stdout.rstrip()}"
            if proc.stderr.strip():
                notes += f"\n--- {script.name} stderr ---\n{proc.stderr.rstrip()}"
        return 0, f"scenario {args.name}: PASS", notes, data, None
    notes = None
    if verbose and (proc.stdout.strip() or proc.stderr.strip()):
        notes = f"--- {script.name} stdout ---\n{proc.stdout.rstrip()}"
        if proc.stderr.strip():
            notes += f"\n--- {script.name} stderr ---\n{proc.stderr.rstrip()}"
    return (6, None, notes, data,
            f"scenario {args.name}: FAIL (exit {proc.returncode})")


def cmd_state_init(args, cfg, home):
    state_mod, err = _import_sibling("state", "state commands")
    if state_mod is None:
        return 1, None, None, None, err
    out = args.out if args.out is not None else str(Path(home) / "var" / "state" / "state.json")
    try:
        out_path = state_mod.cmd_init(home, args.seed, out)
    except state_mod.StateError as e:
        return 1, None, None, None, f"dsys state: {e}"
    data = {"out": str(out_path), "seed": args.seed}
    return 0, f"wrote {out_path}", None, data, None


def cmd_state_get(args, cfg, home):
    state_mod, err = _import_sibling("state", "state commands")
    if state_mod is None:
        return 1, None, None, None, err
    try:
        result = state_mod.cmd_get(args.state, args.collection, args.id)
    except state_mod.StateError as e:
        return 1, None, None, None, f"dsys state: {e}"
    records = result if isinstance(result, list) else [result]
    text = "\n".join(_render_row(r) for r in records)
    data = {"state_file": args.state, "collection": args.collection,
            "id": args.id, "records": records}
    return 0, text, None, data, None


def cmd_doctor(args, cfg, home):
    doctor_mod, err = _import_sibling("doctor", "self-checks")
    if doctor_mod is None:
        return 1, None, None, None, err
    try:
        payload = doctor_mod.run_checks(Path(home), strict=args.strict)
    except Exception as e:  # noqa: BLE001 - doctor must never traceback the CLI
        return 1, None, None, None, f"dsys doctor: {type(e).__name__}: {e}"
    checks = payload.get("checks", []) or []
    lines = []
    for c in checks:
        status = _DOCTOR_STATUS.get(str(c.get("status", "?")).lower(), "?")
        lines.append(f"{status}  {c.get('name', '?')} {c.get('detail', '')}".rstrip())
    if payload.get("pristine"):
        lines.append("pristine")
    else:
        bad = []
        try:
            import manifest
            res = manifest.verify_tree(Path(home))
            bad = res.get("diverged", []) + res.get("missing", [])
        except Exception:  # noqa: BLE001 - fall back to the check detail
            pass
        if bad:
            lines.append(f"MUTATED ({len(bad)} files: {', '.join(bad)})")
        else:
            lines.append("MUTATED")
    statuses = [str(c.get("status", "")).lower() for c in checks]
    code = 0
    if "fail" in statuses or ("warn" in statuses and args.strict):
        code = 1
    data = dict(payload)
    data["strict"] = args.strict
    error = None
    if code != 0:
        n_fail = statuses.count("fail")
        n_warn = statuses.count("warn")
        error = f"dsys doctor: {n_fail} failed, {n_warn} warning(s)"
    return code, "\n".join(lines), None, data, error


def cmd_version(args, cfg, home, manifest, profile):
    lines = [f"dsys {TOOL_VERSION}", f"profile: {profile}",
             f"core: {str(manifest.get('core_hash', 'unknown'))[:19]}"]
    data = {"version": TOOL_VERSION, "profile": profile,
            "core_hash": manifest.get("core_hash"),
            "dist_version": manifest.get("dist_version")}
    notes = None
    dist = manifest.get("dist_version")
    if dist and dist != TOOL_VERSION:
        notes = f"version skew: cli reports {TOOL_VERSION} but manifest says {dist}"
    if profile == "full":
        roles, err = _import_sibling("roles", "role bundles")
        if roles is None:
            lines.append("roles: unavailable")
            data["roles"] = []
        else:
            try:
                bundles = roles.list_bundles(Path(cfg["roles_dir"]))
            except roles.RoleError as e:
                lines.append(f"roles: error ({e})")
                data["roles"] = []
            else:
                items = []
                for b in bundles:
                    lines.append(f"{b.name} {b.version} {b.role_hash[:12]}")
                    items.append({"name": b.name, "version": b.version,
                                  "role_hash": b.role_hash})
                data["roles"] = items
    return 0, "\n".join(lines), notes, data, None


# --------------------------------------------------------------------------
# dispatch + main


def _dispatch(args, cfg, home, manifest, profile, verbose):
    cmd = args.command
    if cmd == "execute":
        return cmd_execute(args, cfg, home)
    if cmd == "roles":
        if args.roles_cmd == "list":
            return cmd_roles_list(args, cfg, home)
        return cmd_roles_show(args, cfg, home)
    if cmd == "referee":
        if args.referee_cmd == "validate":
            return cmd_referee_validate(args, cfg, home)
        return cmd_referee_view(args, cfg, home)
    if cmd == "scenario":
        if args.scenario_cmd == "list":
            return cmd_scenario_list(args, cfg, home)
        return cmd_scenario_run(args, cfg, home, verbose)
    if cmd == "state":
        if args.state_cmd == "init":
            return cmd_state_init(args, cfg, home)
        return cmd_state_get(args, cfg, home)
    if cmd == "doctor":
        return cmd_doctor(args, cfg, home)
    if cmd == "session":
        return cmd_session(args, cfg, home)
    if cmd == "derive":
        return cmd_derive(args, cfg, home, manifest)
    return 1, None, None, None, f"dsys: unknown command {cmd!r}"


def _read_manifest(home):
    """Return (manifest_dict, error_message)."""
    path = home / "var" / "manifest.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"dsys: not an installed dsys tree (no manifest at {path})"
    except OSError as e:
        return None, f"dsys: cannot read manifest at {path}: {e}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"dsys: malformed manifest at {path}: {e}"
    if not isinstance(data, dict):
        return None, f"dsys: malformed manifest at {path}: not a JSON object"
    return data, None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pre_fmt, pre_cmd = _prescan(argv)
    pre_json = (pre_fmt == "json")

    home = resolve_home()

    def startup_fail(message, profile=None, command=None):
        cmd = command or pre_cmd or "none"
        if pre_json:
            print(json.dumps(envelope(cmd, profile, 1,
                                      error={"message": message})))
        else:
            print(message, file=sys.stderr)
        return 1

    # (1) install home + manifest
    manifest, merr = _read_manifest(home)
    if manifest is None:
        return startup_fail(merr)
    if not manifest.get("install_path"):
        return startup_fail(
            f"dsys: malformed manifest at {home / 'var' / 'manifest.json'}: "
            "missing install_path")
    actual = str(home.resolve())
    if str(Path(manifest["install_path"]).resolve()) != actual:
        return startup_fail(
            f"dsys: installed tree moved (manifest: {manifest['install_path']}, "
            f"actual: {actual}) — reinstall; venvs are not relocatable")
    profile = manifest.get("profile") or "base"
    if profile not in ("base", "full"):
        return startup_fail(
            f"dsys: malformed manifest: unknown profile {profile!r}",
            profile=profile)

    # vendored core importable the install-home way for handlers
    core_dir = str(home / "lib" / "core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)

    # (2) parse args
    parser = _build_parser()
    parser._dsys = {"json": pre_json, "command": pre_cmd, "profile": profile}
    args = parser.parse_args(argv)
    if args.command is None and not args.version:
        parser.error("no command given")

    # (3) load config (flags > config file > DEFAULTS)
    flags = {"backend": args.backend, "format": args.format}
    try:
        cfg = load_config(home, config_path=args.config, flags=flags)
    except ConfigError as e:
        return startup_fail(f"dsys: {e}", profile=profile,
                            command="version" if args.version else args.command)
    as_json = (cfg["format"] == "json")

    # (4a) --version
    if args.version:
        result = cmd_version(args, cfg, home, manifest, profile)
        return _finish("version", profile, result, as_json, args.quiet)

    # (4b) base-profile gating
    cmd = args.command
    if profile == "base" and cmd in BASE_BLOCKED:
        msg = (f"`{cmd}` is not available in the base profile — "
               "reinstall with `--profile full`")
        return _finish(cmd, profile, (1, None, None, None, msg),
                       as_json, args.quiet)

    # (4c) dispatch
    result = _dispatch(args, cfg, home, manifest, profile, args.verbose)
    return _finish(cmd, profile, result, as_json, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
