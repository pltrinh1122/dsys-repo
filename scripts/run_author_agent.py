#!/usr/bin/env python3
"""make run — execute the author-agent end-to-end and gather pasteable
telemetry for verification in chat.

Refuses unless `make install` has completed (install-receipt.json).

1. LIVE LOOP: in a FRESH scratch root (mirroring the specified replay in
   author_agent_golden_run._replay): pending -> commission ->
   authoring-session/profile/build-request staging -> drive -> report ->
   pending (queue drained). Uses the verified registrar profile bytes
   verbatim — no new inference.
2. DIAGNOSTICS x2: factory + channels + author + containment batteries,
   each twice; normalized outputs must be byte-identical across runs.
3. Prints a pasteable telemetry block; exit 0 on PASS, 1 on FAIL.

Verification contract (what the verifier checks in the pasted block):
  - tree.git matches the expected build/half1 head
  - install.receipt present with installer_version + installed_utc
    (install.tree_git may lag tree.git after a quick-fix git pull — fine)
  - every exit code is 0, report all_green true, every battery tally found
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

RECEIPT = ROOT / "install-receipt.json"
AGENT = "registrar"

fail_reasons: list[str] = []


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- installer gate ---------------------------------------------------------
try:
    receipt = json.loads(RECEIPT.read_text())
    for k in ("installer_version", "installed_utc", "venv_dir", "tree"):
        assert receipt.get(k), f"receipt missing {k}"
except Exception as e:  # noqa: BLE001
    print(f"FAIL: install-receipt.json missing or invalid: {e}", file=sys.stderr)
    print("Run `make install` first.", file=sys.stderr)
    sys.exit(1)

# --- python: the installer's venv first, then fallbacks (needs pydantic) ----
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
    return sys.executable  # the python3 invoking this script


PY = pick_python()
r = subprocess.run([PY, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                   capture_output=True, text=True)
PYV = r.stdout.strip() or "?"
r = subprocess.run([PY, "-c", "import pydantic; print(pydantic.VERSION)"],
                   capture_output=True, text=True)
if r.returncode != 0:
    print(f"FAIL: pydantic not importable under {PY} — re-run `make install`",
          file=sys.stderr)
    sys.exit(1)
PDV = r.stdout.strip()

r = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"],
                   capture_output=True, text=True)
branch = r.stdout.strip() or "?"
r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                   capture_output=True, text=True)
GIT_INFO = f"branch={branch}@{r.stdout.strip() or '?'}"

TS = utc()
TDIR = Path(tempfile.mkdtemp(prefix="run-tmp-"))
LOOP_ROOT = Path(tempfile.mkdtemp(dir=ROOT, prefix="run-scratch-"))
CH = [PY, "-m", "core.package.author_channels", "--root", str(LOOP_ROOT)]


def run_step(name: str, rel: str, *cmd: str, cwd: Path = ROOT) -> Path:
    """Run a step; save stdout to TDIR/rel; record exit/secs/sha. Never raises."""
    dest = TDIR / rel
    t0 = time.monotonic()
    try:
        p = subprocess.run(list(cmd), cwd=cwd, capture_output=True,
                           text=True, timeout=600)
        dest.write_text(p.stdout)
        code = p.returncode
        if p.stderr.strip():
            (TDIR / (rel + ".stderr")).write_text(p.stderr)
    except Exception as e:  # noqa: BLE001
        dest.write_text("")
        code = 127
        (TDIR / (rel + ".stderr")).write_text(f"harness error: {e}")
    secs = int(time.monotonic() - t0)
    (TDIR / f"step-{name}.meta").write_text(
        f"{code}|{secs}|{sha256_file(dest)}|{rel}")
    if code != 0:
        fail_reasons.append(f"step '{name}' exited {code}")
    return dest


# --- LIVE LOOP (fresh scratch root; mirrors author_agent_golden_run._replay) --
run_step("pending.before", "pending-before.json", *CH, "pending")
try:
    PEND_BEFORE = len(json.loads((TDIR / "pending-before.json").read_text()))
except Exception:  # noqa: BLE001
    PEND_BEFORE = "?"
    fail_reasons.append("pending.before output not parseable")

CID = f"telemetry-{TS}"
comm = run_step("commission", "commission.json", *CH, "commission",
                "--id", CID,
                "--brief", "telemetry self-check: drive the registrar demo agent through the governed loop",
                "--acceptance", "verdict record staged;report readable",
                "--disposition-ref", f"telemetry-run {TS}")
try:
    COMM_ID = json.loads(comm.read_text())["commission_id"]
except Exception:  # noqa: BLE001
    COMM_ID = "?"
    fail_reasons.append("commission id not parseable")


# Ambient/Harness-side staging (J1-ii stigmergic invocation), mirroring the
# specified replay: record the authoring session, pin the live verified
# registrar profile bytes, bind them to this commission as a build-request.
# Mechanical here — the bytes are reused verbatim, no new authoring.
def do_stage() -> dict:
    from core.package import author_agent as aa
    root = LOOP_ROOT
    live = ROOT / "core" / "package" / "authored"
    aa.record_authoring_session(root, COMM_ID, AGENT,
                                {k: True for k in aa.CHECKLIST},
                                note="telemetry")
    src = (live / f"{AGENT}.py").read_text()
    prof = aa.stage_authored_profile(
        root, AGENT, src,
        rationale="telemetry: verified registrar bytes reused verbatim",
        commission_id=COMM_ID)
    req = aa.stage_build_request(root, AGENT, COMM_ID)
    return {"agent": AGENT, "staged_profile_sha256": prof["sha256"],
            "build_request_seq": req["seq"]}


t0 = time.monotonic()
try:
    stage_out = do_stage()
    (TDIR / "stage.json").write_text(json.dumps(stage_out))
    stage_code = 0
except Exception as e:  # noqa: BLE001
    (TDIR / "stage.json").write_text("")
    (TDIR / "stage.json.stderr").write_text(f"harness error: {e}")
    stage_code = 1
(TDIR / "step-stage.meta").write_text(
    f"{stage_code}|{int(time.monotonic() - t0)}|{sha256_file(TDIR / 'stage.json')}|stage.json")
if stage_code != 0:
    fail_reasons.append("step 'stage' failed")

drive = run_step("drive", "drive.json", *CH, "drive")
try:
    BUILT = " ".join(json.loads(drive.read_text()).get("built", []))
except Exception:  # noqa: BLE001
    BUILT = "?"
if AGENT not in BUILT.split():
    fail_reasons.append(f"drive built nothing (built: [{BUILT}])")

report = run_step("report", "report.json", *CH, "report",
                  "--commission", CID)
try:
    rep = json.loads(report.read_text())
    REP_ALL_GREEN = rep.get("all_green")
    REP_VERDICTS = [(v.get("agent"), v.get("outcome")) for v in rep.get("verdicts", [])]
    if not (REP_ALL_GREEN and all(o == "verified" for _, o in REP_VERDICTS)):
        fail_reasons.append(
            f"report not all green (all_green={REP_ALL_GREEN}, verdicts={REP_VERDICTS})")
except Exception as e:  # noqa: BLE001
    REP_ALL_GREEN, REP_VERDICTS = "?", []
    fail_reasons.append(f"report output not parseable: {e}")

run_step("pending.after", "pending-after.json", *CH, "pending")
try:
    PEND_AFTER = len(json.loads((TDIR / "pending-after.json").read_text()))
except Exception:  # noqa: BLE001
    PEND_AFTER = "?"
if PEND_AFTER != 0:
    fail_reasons.append(f"queue not drained (pending after={PEND_AFTER}, want 0)")

# --- DIAGNOSTICS x2 ----------------------------------------------------------
# Normalization for determinism comparison: the containment battery names
# its per-run scratch dirs with a counter (contain-0054, ...) by design.
# Verdicts are deterministic; the scratch names are not. Strip them before
# hashing so the comparison tests verdict determinism, not scratch naming.
NORM = re.compile(r"\(contain-[0-9]+\)")


def norm(text: str) -> str:
    return NORM.sub("(contain-N)", text)


BATTERIES = [
    ("factory", "passed cases: 183", [PY, "-m", "core.package.factory_golden_run"]),
    ("channels", '"ok": true', [PY, "-m", "core.package.author_channels_golden_run"]),
    ("author", '"ok": true', [PY, "-m", "core.package.author_agent_golden_run"]),
    ("contain", "6/6 passed", [PY, "core/package/author_contain_golden_run.py"]),
]
battery_lines: list[str] = []
for name, tally, cmd in BATTERIES:
    r1 = run_step(f"{name}.r1", f"{name}-r1.log", *cmd)
    r2 = run_step(f"{name}.r2", f"{name}-r2.log", *cmd)
    det = "IDENTICAL" if (norm(r1.read_text()) == norm(r2.read_text())
                          and (TDIR / f"step-{name}.r1.meta").read_text().split("|")[0] == "0"
                          and (TDIR / f"step-{name}.r2.meta").read_text().split("|")[0] == "0") \
        else "DIFFERENT"
    tg = "found" if tally in r1.read_text() and tally in r2.read_text() else "missing"
    if det != "IDENTICAL":
        fail_reasons.append(f"battery '{name}' not deterministic")
    if tg != "found":
        fail_reasons.append(f"battery '{name}' tally missing (want {tally!r})")
    battery_lines.append(
        f"{name}: r1_exit={(TDIR / f'step-{name}.r1.meta').read_text().split('|')[0]} "
        f"r2_exit={(TDIR / f'step-{name}.r2.meta').read_text().split('|')[0]} "
        f"tally[{tally}]={tg} determinism={det} "
        f"r1_sha={hashlib.sha256(norm(r1.read_text()).encode()).hexdigest()} "
        f"r2_sha={hashlib.sha256(norm(r2.read_text()).encode()).hexdigest()}")


# --- telemetry block ---------------------------------------------------------
def meta(name: str) -> tuple[str, str, str]:
    code, secs, sha, *_ = (TDIR / f"step-{name}.meta").read_text().split("|")
    return code, secs, sha


L: list[str] = []
L.append("=== BEGIN AUTHOR-AGENT TELEMETRY ===")
L.append("script: make run (scripts/run_author_agent.py)")
L.append(f"utc: {TS}")
L.append(f"host: {socket.gethostname()}")
L.append(f"tree: {ROOT}")
L.append(f"tree.git: {GIT_INFO}")
L.append(f"install.receipt: {receipt['installed_utc']} ({receipt['installer_version']})")
L.append(f"install.tree_git: {receipt.get('tree_git')}")
L.append(f"python: {PYV} (pydantic {PDV})")
L.append("[live-loop]")
L.append("loop.root: scratch (fresh per run; live journal untouched)")
for s in ("pending.before", "commission", "stage", "drive", "report", "pending.after"):
    code, secs, sha = meta(s)
    L.append(f"{s}: exit={code} secs={secs} sha256={sha}")
L.append(f"pending.before.count={PEND_BEFORE}")
L.append(f"commission.id={COMM_ID}")
L.append(f"stage.agent={AGENT}")
L.append(f"drive.built={BUILT}")
L.append(f"report.all_green={REP_ALL_GREEN} report.verdicts={REP_VERDICTS}")
L.append(f"pending.after.count={PEND_AFTER}")
L.append("[diagnostics x2]")
L.append("note: determinism hashed on scratch-name-normalized output "
         "(per-run scratch counters excluded by design)")
L.extend(battery_lines)
VERDICT = "PASS" if not fail_reasons else "FAIL"
L.append(f"verdict: {VERDICT}")
if fail_reasons:
    L.append("fail_reasons: " + " | ".join(fail_reasons))
L.append(f"logs: {TDIR} {LOOP_ROOT}")
L.append("=== END AUTHOR-AGENT TELEMETRY ===")
print("\n".join(L))

sys.exit(0 if VERDICT == "PASS" else 1)
