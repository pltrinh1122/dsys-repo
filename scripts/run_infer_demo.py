#!/usr/bin/env python3
"""make infer — run the Half 2 inference-service demo and gather pasteable
telemetry for verification in chat.

Refuses unless `make install` has completed (install-receipt.json).

Runs the `infer` channel command against the hand-built demo_classifier_agent:
round 1 the agent emits a classify prompt-request for a principal message;
the harness accommodates it with a `claude` CLI invocation (stub-backed;
telemetry marks the backing); round 2 the agent reads the verdict and
completes.

Prints a bounded telemetry block; exit 0 on PASS (outcome complete),
1 otherwise.
"""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

RECEIPT = ROOT / "install-receipt.json"
AGENT = "demo_classifier_agent"
EVENT = {"text": "Please review the Q3 budget draft when you get a chance."}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# --- installer gate ----------------------------------------------------------
try:
    receipt = json.loads(RECEIPT.read_text())
    for k in ("installer_version", "installed_utc", "venv_dir", "tree"):
        assert receipt.get(k), f"receipt missing {k}"
except Exception as e:  # noqa: BLE001
    print(f"FAIL: install-receipt.json missing or invalid: {e}", file=sys.stderr)
    print("Run `make install` first.", file=sys.stderr)
    sys.exit(1)


def pick_python() -> str:
    cands = [
        Path(receipt["venv_dir"]) / "bin" / "python",
        Path(os.environ["AUTHOR_VENV_DIR"]) / "bin" / "python"
        if os.environ.get("AUTHOR_VENV_DIR") else None,
        Path.home() / ".dsys" / "author-venv" / "bin" / "python",
    ]
    for c in cands:
        if c and c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return sys.executable


PY = pick_python()
env = dict(os.environ)
env["CLAUDE_BIN"] = str(ROOT / "scripts" / "claude-stub")

r = subprocess.run(
    [PY, "-m", "core.package.author_channels", "infer",
     "--agent", AGENT, "--event", json.dumps(EVENT), "--max-rounds", "3"],
    capture_output=True, text=True, timeout=600, env=env)


def git(*a: str) -> str | None:
    try:
        q = subprocess.run(["git", "-C", str(ROOT), *a],
                           capture_output=True, text=True, timeout=10)
        return q.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


print("=== BEGIN INFER-DEMO TELEMETRY ===")
print("script: make infer (scripts/run_infer_demo.py)")
print(f"utc: {utc()}")
print(f"host: {socket.gethostname()}")
print(f"tree: {ROOT}")
branch, sha = git("branch", "--show-current"), git("rev-parse", "--short", "HEAD")
print(f"tree.git: branch={branch}@{sha}")
print(f"install.receipt: {receipt.get('installed_utc')} "
      f"({receipt.get('installer_version')})")
print(f"claude.backing: stub ({ROOT / 'scripts' / 'claude-stub'})")

ok = False
try:
    t = json.loads(r.stdout)
    print("[infer loop]")
    print(f"agent: {t['agent']}")
    for rd in t["rounds"]:
        reqs = ", ".join(f"{q['kind']} {q['request_id']}"
                         for q in rd["requests"]) or "none"
        print(f"round.{rd['round']}.requests: {reqs}")
    res = t.get("result") or {}
    print(f"result.status: {res.get('status')}")
    print(f"result.verdict: {res.get('verdict')}")
    print(f"outcome: {t['outcome']}")
    ok = t["outcome"] == "complete" and res.get("status") == "complete"
except Exception as e:  # noqa: BLE001
    print(f"transcript unparsable: {e}")
    print(f"infer exit: {r.returncode}")
    print("stderr tail:", r.stderr[-500:])

print(f"verdict: {'PASS' if ok else 'FAIL'}")
print("=== END INFER-DEMO TELEMETRY ===")
sys.exit(0 if ok else 1)
