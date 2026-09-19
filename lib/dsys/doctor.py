"""Doctor: hermetic self-checks for a dsys install tree.

No network anywhere: every check is a local file/import/computation check.
Exit posture is data, not action: checks report status ok|warn|fail and the
caller (bin/dsys) decides. `pristine` is true iff the manifest tree-hashes
check passes -- that is the only meaning of "unmutated" here; config edits
etc/config.yaml is operator-owned and never trips the doctor.

The vendored core (pydantic-dependent) is imported in-process via the
install-home convention: sys.path.insert(0, "<home>/lib/core") then
`from package import ...`. The core is never mutated here; it is only
imported and executed for read-only verification.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# lib/dsys modules import each other as top-level modules.
import manifest
import roles

_OK = "ok"
_WARN = "warn"
_FAIL = "fail"


def _check(checks: list, name: str, status: str, detail: str, hint: str = "") -> None:
    checks.append({"name": name, "status": status, "detail": detail, "hint": hint})


def _ensure_core_on_path(home: Path) -> None:
    core_dir = str(home / "lib" / "core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)


def run_checks(home: Path, *, strict: bool) -> dict:
    """Run all doctor checks. Returns
    {"profile": str|None, "pristine": bool, "checks": [{...}]}."""
    home = Path(home)
    checks: list = []
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # 1. python_version
    if sys.version_info >= (3, 10):
        _check(checks, "python_version", _OK, f"python {pyver}")
    else:
        _check(
            checks,
            "python_version",
            _FAIL,
            f"python {pyver} below minimum 3.10",
            hint="upgrade to python 3.10 or newer",
        )

    # 2. manifest: present, valid JSON, required keys
    m: dict | None = None
    try:
        m = manifest.read_manifest(home)
        missing_keys = [k for k in ("files", "profile", "install_path") if k not in m]
        if missing_keys:
            _check(
                checks,
                "manifest",
                _FAIL,
                f"manifest missing keys: {', '.join(missing_keys)}",
                hint="rewrite the manifest or reinstall",
            )
            m = None
        else:
            _check(
                checks,
                "manifest",
                _OK,
                f"profile={m['profile']} install_path={m['install_path']}",
            )
    except manifest.ManifestError as e:
        _check(checks, "manifest", _FAIL, str(e), hint="rewrite the manifest or reinstall")

    # 3. tree_location: manifest install_path must resolve to this home
    if m is not None and Path(m["install_path"]).resolve() == home.resolve():
        _check(checks, "tree_location", _OK, f"install_path matches {home}")
    else:
        _check(
            checks,
            "tree_location",
            _FAIL,
            "tree moved — install_path does not resolve to this home",
            hint="reinstall; venvs are not relocatable",
        )

    # 4. tree_hashes: the pristine check
    pristine = False
    try:
        res = manifest.verify_tree(home)
        if res["ok"]:
            pristine = True
            n = len((manifest.read_manifest(home).get("files") or {}))
            _check(checks, "tree_hashes", _OK, f"pristine ({n} files)")
        else:
            bad = res["diverged"] + res["missing"]
            _check(
                checks,
                "tree_hashes",
                _FAIL,
                f"MUTATED: {', '.join(bad[:5])}{'...' if len(bad) > 5 else ''}",
                hint="reinstall, or declare the mutation through the dsys-mutation playbook",
            )
    except manifest.ManifestError as e:
        _check(checks, "tree_hashes", _FAIL, str(e), hint="rewrite the manifest or reinstall")

    # 5. core_import: vendored core imports
    try:
        _ensure_core_on_path(home)
        from package import schema  # noqa: F401

        _check(checks, "core_import", _OK, "package.schema imports")
    except Exception as e:
        _check(
            checks,
            "core_import",
            _FAIL,
            f"{type(e).__name__}: {e}",
            hint="core tree mutated or missing — reinstall",
        )

    # 6. core_hash: recomputed core tree hash matches the manifest
    try:
        if m is None:
            raise manifest.ManifestError("no manifest to compare against")
        if manifest.core_tree_hash(home) == m.get("core_hash"):
            _check(checks, "core_hash", _OK, "core tree hash matches manifest")
        else:
            _check(
                checks,
                "core_hash",
                _FAIL,
                "core tree hash differs from manifest",
                hint="core tree mutated — reinstall",
            )
    except Exception as e:
        _check(
            checks,
            "core_hash",
            _FAIL,
            f"{type(e).__name__}: {e}",
            hint="core tree mutated — reinstall",
        )

    # 7. golden_chain: in-process golden run, ok iff result ok and no violations
    try:
        _ensure_core_on_path(home)
        from package.golden_run import run  # noqa: E402

        result = run()
        ok = (
            isinstance(result, dict)
            and bool(result.get("ok"))
            and not (result.get("violations") or [])
        )
        refusals = (
            result.get("refusals")
            if isinstance(result, dict) and "refusals" in result
            else (result.get("refusal_count") if isinstance(result, dict) else None)
        )
        refusal_detail = f", {refusals} refusal cases" if refusals is not None else ""
        if ok:
            _check(
                checks,
                "golden_chain",
                _OK,
                f"golden run PASS{refusal_detail}, 0 violations",
            )
        else:
            _check(
                checks,
                "golden_chain",
                _FAIL,
                f"golden run did not pass: {result!r}",
                hint="core tree mutated",
            )
    except Exception as e:
        _check(
            checks,
            "golden_chain",
            _FAIL,
            f"{type(e).__name__}: {e}",
            hint="core tree mutated",
        )

    # 8. profile_layout
    profile = m.get("profile") if m else None
    if profile == "base":
        stray = [
            rel
            for rel in ("lib/roles", "share/scenarios")
            if (home / rel).exists()
        ]
        if stray:
            _check(
                checks,
                "profile_layout",
                _FAIL,
                f"base profile must not contain: {', '.join(stray)}",
                hint="remove the stray dirs or install the full profile",
            )
        else:
            _check(
                checks,
                "profile_layout",
                _OK,
                "base layout: lib/roles and share/scenarios absent",
            )
    elif profile == "full":
        missing_dirs = [
            str(home / rel)
            for rel in ("lib/roles", "share/scenarios")
            if not (home / rel).is_dir()
        ]
        if missing_dirs:
            _check(
                checks,
                "profile_layout",
                _FAIL,
                f"full profile missing: {', '.join(missing_dirs)}",
                hint="install the full profile",
            )
        else:
            try:
                bundles = roles.list_bundles(home / "lib" / "roles")
                _check(
                    checks,
                    "profile_layout",
                    _OK,
                    f"full layout: {len(bundles)} role bundle(s) seal-verified",
                )
            except roles.RoleError as e:
                _check(
                    checks,
                    "profile_layout",
                    _FAIL,
                    f"role bundle verification failed: {e}",
                    hint="re-seal or reinstall the role bundles",
                )
    else:
        status = _FAIL if strict else _WARN
        _check(
            checks,
            "profile_layout",
            status,
            f"unknown profile in manifest: {profile!r}",
            hint="check the manifest profile",
        )

    # 9. config: operator-owned etc/config.yaml must parse via config.load
    try:
        import config  # noqa: E402

        config.load(home / "etc" / "config.yaml")
        _check(checks, "config", _OK, "etc/config.yaml parses")
    except Exception as e:
        _check(
            checks,
            "config",
            _FAIL,
            f"{type(e).__name__}: {e}",
            hint="fix etc/config.yaml (operator-owned; never affects pristine)",
        )

    # 10. var_writable: var/, var/state, var/log exist and are writable
    try:
        var_dirs = [home / "var", home / "var" / "state", home / "var" / "log"]
        not_writable = []
        for d in var_dirs:
            d.mkdir(parents=True, exist_ok=True)
            if not os.access(d, os.W_OK):
                not_writable.append(d.relative_to(home).as_posix())
        if not_writable:
            _check(
                checks,
                "var_writable",
                _FAIL,
                f"not writable: {', '.join(not_writable)}",
                hint="fix permissions on var/",
            )
        else:
            _check(checks, "var_writable", _OK, "var/, var/state, var/log exist and writable")
    except Exception as e:
        _check(
            checks,
            "var_writable",
            _FAIL,
            f"{type(e).__name__}: {e}",
            hint="fix permissions on var/",
        )

    # 11. hermetic note: no network probes, by design
    _check(
        checks,
        "hermetic",
        _OK,
        "no network probes performed — hermetic checks only (F-I4)",
    )

    return {"profile": profile, "pristine": pristine, "checks": checks}
