#!/usr/bin/env python3
"""make install — verify the Half 1 author-agent tree.

1. checks python3 (>= 3.10) and the venv module
2. bootstraps the contained venv (~/.dsys/author-venv, hash-pinned;
   override with AUTHOR_VENV_DIR) — the venv is the ONLY python the
   tree ever runs under; the host interpreter is never mutated
   (this sidesteps PEP 668 externally-managed-environment systems)
3. runs all four golden batteries under the venv python and asserts
   the exact expected counts
4. smoke-tests the channel CLI (read-only) under the venv python
5. writes install-receipt.json — proof of install; `make run` refuses without it

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


def step(n: str) -> None:
    print(f"\n==> {n}")


def pyver(python: str) -> str:
    r = subprocess.run([python, "-c",
                        "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else "?"


# --- 1. preconditions ------------------------------------------------------
step("1/4 preconditions")
ok(f"tree root: {ROOT}")
r = subprocess.run([PY3, "-c",
                    "import sys; print('yes' if sys.version_info >= (3, 10) else 'no')"],
                   capture_output=True, text=True, timeout=60)
ver = pyver(PY3)
if r.returncode == 0 and r.stdout.strip() == "yes":
    ok(f"python3 {ver} (>= 3.10)")
else:
    fail(f"python3 {ver} missing or < 3.10 (need >= 3.10)")
r = subprocess.run([PY3, "-c", "import venv, ensurepip"],
                   capture_output=True, text=True, timeout=60)
if r.returncode == 0:
    ok("venv module available")
else:
    fail("python3 -m venv unavailable (Debian/Ubuntu: apt install python3-venv)")

# --- 2. contained venv (harness-managed; ratified J-C1) --------------------
step("2/4 contained venv")
venv_dir = os.environ.get("AUTHOR_VENV_DIR") or str(Path.home() / ".dsys" / "author-venv")
VPY = ""
if failed:
    fail("skipped: earlier step failed")
else:
    sys.path.insert(0, str(ROOT))
    try:
        from core.package.author_contain import ensure_venv, venv_fingerprint
        vpy = ensure_venv(Path(venv_dir))
        VPY = str(vpy)
        fp = venv_fingerprint(vpy)
        ok(f"contained venv ready ({VPY}; pydantic {fp['packages'].get('pydantic', '?')})")
    except Exception as e:  # noqa: BLE001
        (LOGDIR / "ensure-venv.log").write_text(str(e))
        fail(f"contained venv failed: {e} — see install-logs/ensure-venv.log")


def sh(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True,
                          text=True, timeout=timeout)


# --- 3. golden batteries (under the venv python) ---------------------------
step("3/4 golden batteries")
batteries = [
    ("factory", "passed cases: 183", [VPY, "-m", "core.package.factory_golden_run"]),
    ("channels", '"ok": true', [VPY, "-m", "core.package.author_channels_golden_run"]),
    ("author", '"ok": true', [VPY, "-m", "core.package.author_agent_golden_run"]),
    ("contain", "6/6 passed", [VPY, "core/package/author_contain_golden_run.py"]),
]
for name, expect, cmd in batteries:
    if failed or not VPY:
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

# --- 4. CLI smoke (read-only, under the venv python) -----------------------
step("4/4 channel CLI smoke (read-only)")
if failed or not VPY:
    fail("skipped: earlier failure")
else:
    r = sh(VPY, "-m", "core.package.author_channels", "pending")
    if r.returncode == 0 and r.stdout.strip() == "[]":
        ok("pending -> []")
    else:
        fail("pending did not return []")
    r = sh(VPY, "-m", "core.package.author_channels",
           "report", "--commission", "commission-001")
    if r.returncode == 0 and '"all_green": true' in r.stdout:
        ok("report commission-001 -> diagnostics all green")
    else:
        fail("report commission-001 not all green")

# --- 5. receipt + summary ----------------------------------------------------
print()
if not failed:
    def git(*a: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(ROOT), *a],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() or None
        except Exception:  # noqa: BLE001
            return None

    branch, sha = git("branch", "--show-current"), git("rev-parse", "--short", "HEAD")
    r = subprocess.run([VPY, "-c", "import pydantic; print(pydantic.VERSION)"],
                       capture_output=True, text=True, timeout=60)
    receipt = {
        "installer_version": "make install (scripts/install_author_agent.py)",
        "installed_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tree": str(ROOT),
        "tree_git": f"{branch}@{sha}" if branch and sha else None,
        "python": pyver(VPY),
        "pydantic": r.stdout.strip() if r.returncode == 0 else "?",
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
