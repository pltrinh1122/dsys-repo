#!/usr/bin/env python3
"""make install — verify the Half 1 author-agent tree.

1. checks python3 (>= 3.10) and pip
2. installs pydantic on the host python if missing (pinned to the verified version)
3. bootstraps the contained venv (~/.dsys/author-venv, hash-pinned;
   override with AUTHOR_VENV_DIR)
4. runs all four golden batteries and asserts the exact expected counts
5. smoke-tests the channel CLI (read-only)
6. writes install-receipt.json — proof of install; `make run` refuses without it

Idempotent: safe to re-run. Logs go to <tree>/install-logs/.
Exit 0 on all green, 1 otherwise.
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "install-logs"
LOGDIR.mkdir(exist_ok=True)
RECEIPT = ROOT / "install-receipt.json"
PY3 = "python3"

failed: list[str] = []


def ok(msg: str) -> None:
    print(f"PASS: {msg}")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    failed.append(msg)


def sh(*args: str, cwd: Path = ROOT, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


def step(n: str) -> None:
    print(f"\n==> {n}")


# --- 1. preconditions ------------------------------------------------------
step("1/5 preconditions")
ok(f"tree root: {ROOT}")
r = sh(PY3, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')")
pyver = r.stdout.strip()
r = sh(PY3, "-c", "import sys; print('yes' if sys.version_info >= (3, 10) else 'no')")
if r.returncode == 0 and r.stdout.strip() == "yes":
    ok(f"python3 {pyver} (>= 3.10)")
else:
    fail(f"python3 {pyver} missing or < 3.10 (need >= 3.10)")
if sh(PY3, "-m", "pip", "--version").returncode == 0:
    ok("pip available")
else:
    fail("pip not available for python3 (try: python3 -m ensurepip)")

# --- 2. host pydantic ------------------------------------------------------
step("2/5 host pydantic")
r = sh(PY3, "-c", "import pydantic; print(pydantic.VERSION)")
if r.returncode == 0:
    ok(f"pydantic {r.stdout.strip()} already installed")
    pydantic_ver = r.stdout.strip()
else:
    print("installing pydantic==2.13.5 (verified version; needs network)...")
    r = sh(PY3, "-m", "pip", "install", "pydantic==2.13.5")
    (LOGDIR / "pip-pydantic.log").write_text(r.stdout + r.stderr)
    if r.returncode == 0:
        ok("pydantic installed")
        pydantic_ver = "2.13.5"
    else:
        fail("pip install pydantic failed (network?) — see install-logs/pip-pydantic.log")
        pydantic_ver = "?"

# --- 3. contained venv (harness-managed; ratified J-C1) --------------------
step("3/5 contained venv")
venv_dir = os.environ.get("AUTHOR_VENV_DIR") or str(Path.home() / ".dsys" / "author-venv")
if failed:
    fail("skipped: earlier step failed")
else:
    sys.path.insert(0, str(ROOT))
    try:
        from core.package.author_contain import ensure_venv, venv_fingerprint
        py = ensure_venv(Path(venv_dir))
        ok(f"contained venv ready ({py}; fingerprint {venv_fingerprint(py)})")
    except Exception as e:  # noqa: BLE001
        fail(f"ensure_venv failed: {e}")

# --- 4. golden batteries ---------------------------------------------------
step("4/5 golden batteries")
batteries = [
    ("factory", "passed cases: 183", [PY3, "-m", "core.package.factory_golden_run"]),
    ("channels", '"ok": true', [PY3, "-m", "core.package.author_channels_golden_run"]),
    ("author", '"ok": true', [PY3, "-m", "core.package.author_agent_golden_run"]),
    ("contain", "6/6 passed", [PY3, "core/package/author_contain_golden_run.py"]),
]
for name, expect, cmd in batteries:
    if failed:
        fail(f"{name} skipped (earlier failure)")
        continue
    r = sh(*cmd)
    (LOGDIR / f"{name}.log").write_text(r.stdout + r.stderr)
    if r.returncode == 0 and expect in r.stdout:
        ok(f"{name} ({expect})")
    else:
        fail(f"{name} (expected '{expect}') — see install-logs/{name}.log")
flog = LOGDIR / "factory.log"
if flog.exists():
    if '"violations": []' in flog.read_text():
        ok("factory: 0 violations")
    else:
        fail("factory violations non-empty — see install-logs/factory.log")

# --- 5. CLI smoke (read-only) ----------------------------------------------
step("5/5 channel CLI smoke (read-only)")
if failed:
    fail("skipped: earlier failure")
else:
    r = sh(PY3, "-m", "core.package.author_channels", "pending")
    if r.returncode == 0 and r.stdout.strip() == "[]":
        ok("pending -> []")
    else:
        fail("pending did not return []")
    r = sh(PY3, "-m", "core.package.author_channels",
           "report", "--commission", "commission-001")
    if r.returncode == 0 and '"all_green": true' in r.stdout:
        ok("report commission-001 -> diagnostics all green")
    else:
        fail("report commission-001 not all green")

# --- 6. receipt + summary ----------------------------------------------------
print()
if not failed:
    def git(*a: str) -> str | None:
        try:
            r = sh("git", "-C", str(ROOT), *a, timeout=10)
            return r.stdout.strip() or None
        except Exception:  # noqa: BLE001
            return None

    branch, sha = git("branch", "--show-current"), git("rev-parse", "--short", "HEAD")
    receipt = {
        "installer_version": "make install (scripts/install_author_agent.py)",
        "installed_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tree": str(ROOT),
        "tree_git": f"{branch}@{sha}" if branch and sha else None,
        "python": pyver,
        "pydantic": pydantic_ver,
        "venv_dir": venv_dir,
        "checks": {"factory": True, "channels": True, "author": True,
                   "contain": True, "cli_smoke": True},
    }
    RECEIPT.write_text(json.dumps(receipt, indent=1) + "\n")
    print(f"receipt written: {RECEIPT}")
    print("RESULT: all green — install verified.")
    print(f"  tree           : {ROOT}")
    print(f"  contained venv : {venv_dir} (override: AUTHOR_VENV_DIR=... make install)")
    print(f"  receipt        : {RECEIPT}")
    print("  next           : make run")
    print("  spec           : doc/d1-d7-author-agent-spec.md (ratified DR-CMD-084)")
    print(f"  logs           : {LOGDIR}")
    sys.exit(0)
else:
    print(f"RESULT: FAILED — see {LOGDIR} (send the failing log back)")
    sys.exit(1)
