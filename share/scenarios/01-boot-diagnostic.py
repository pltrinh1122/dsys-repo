"""Scenario 01 — boot up and self diagnostic.

Installed adaptation (dsys dist): three lines marked
"installed-adaptation" differ from the repo original so the
scenario runs from share/scenarios (package resolved from the
import, DSYS_HOME-aware roles check, refusal canary at 37).

In-session equivalent of `dyad-agent doctor` + fresh-state boot:
verifies the runtime, the machine-native core, the golden chain,
and the disclosure surface, then reports backend/role readiness.

Exit 0: no FAILs. WARNs are honest gaps, not failures.
"""
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))  # `import package` from the repo root

results: list[tuple[str, str, str]] = []  # (name, OK/WARN/FAIL, detail)


def check(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main() -> int:
    # 1. runtime
    if sys.version_info >= (3, 10):
        check("python", "OK", f"{sys.version.split()[0]}")
    else:
        check("python", "FAIL", f"{sys.version.split()[0]} < 3.10")

    # 2. core importable
    try:
        from package import golden_run, schema, validators, views  # noqa: F401
        import package as _pkg  # installed-adaptation: resolve from import
        _pkgdir = Path(_pkg.__file__).resolve().parent
        core_files = ["schema.py", "validators.py", "views.py",
                      "golden_run.py", "__main__.py"]
        hashes = {f: sha256(_pkgdir / f) for f in core_files}
        check("core import", "OK",
              "package.{schema,validators,views,golden_run}")
        check("core hashes", "OK",
              ", ".join(f"{k}={v}" for k, v in hashes.items()))
    except Exception as e:  # noqa: BLE001
        check("core import", "FAIL", str(e))
        return report()

    # 3. golden chain
    try:
        result = golden_run.run()
        n_refusals = len(result["refusals"])
        if result["ok"] and result["violations"] == [] and n_refusals == 37:  # canary: update when golden_run changes
            check("golden chain", "OK",
                  f"PASS, 0 violations, {n_refusals} refusal cases")
        else:
            check("golden chain", "FAIL",
                  f"ok={result['ok']} violations={result['violations']} "
                  f"refusals={n_refusals}")
    except AssertionError as e:
        check("golden chain", "FAIL", f"assertion: {e}")

    # 4. fresh-state boot
    try:
        s = golden_run.build_state()
        violations = validators.validate(s)
        if violations == []:
            counts = {}
            for k, v in s.model_dump().items():
                if v:
                    counts[k] = len(v)
            check("fresh boot", "OK",
                  f"{sum(counts.values())} entities across "
                  f"{len(counts)} types, 0 violations")
        else:
            check("fresh boot", "FAIL", "; ".join(violations))
    except Exception as e:  # noqa: BLE001
        check("fresh boot", "FAIL", str(e))

    # 5. disclosure surface on fresh state
    try:
        rows = views.verification_view(s)
        if rows == []:
            check("verification view", "OK", "empty queue on fresh state")
        else:
            check("verification view", "FAIL", f"expected empty, got {len(rows)}")
    except Exception as e:  # noqa: BLE001
        check("verification view", "FAIL", str(e))

    # 6. role bundles (CLI spec §2 — not yet implemented)
    import os as _os  # installed-adaptation: DSYS_HOME-aware roles check
    _dshome = _os.environ.get("DSYS_HOME")
    roles = ["cos", "operator", "auditor"]
    if _dshome:
        roles_dir = Path(_dshome) / "lib" / "roles"
        _roles_ok = roles_dir.is_dir() and all(
            (roles_dir / r / "prompt.md").exists() for r in roles)
    else:
        roles_dir = REPO.parent / "dyad-agent" / "dyad_agent" / "roles"
        _roles_ok = roles_dir.is_dir() and all(
            (roles_dir / f"{r}.md").exists() for r in roles)
    if _roles_ok:
        check("role bundles", "OK", ",".join(roles))
    else:
        check("role bundles", "WARN",
              "not implemented — role prompts supplied in-session per scenario")

    # 7. backends
    if shutil.which("claude"):
        check("backend claude-cli", "OK", shutil.which("claude"))
    else:
        check("backend claude-cli", "WARN", "not on PATH")
    check("backend in-session", "OK",
          "orchestrator-spawned subagents (prompt-framed roles)")

    return report()


def report() -> int:
    print("dyad test-drive — scenario 01: boot up + self diagnostic")
    width = max(len(n) for n, _, _ in results)
    for name, status, detail in results:
        print(f"  [{status:4}] {name:<{width}}  {detail}")
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    warns = sum(1 for _, s, _ in results if s == "WARN")
    print(f"summary: {fails} FAIL, {warns} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
