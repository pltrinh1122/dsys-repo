#!/usr/bin/env python3
"""Golden run for the dsys production tool registry (lib/dsys/tools/).

Mechanical verification for the DR-CMD-057 build, following the repo's
golden-run pattern. This exercises the eight production tools against
fixtures — a localhost feed server, a stub install.sh, temporary git
repos — through the REAL executor loading path (executor.load_tools +
invoke_tool + advance_run). It is a build-verification harness, not a
production drive: nothing here is presented as an executed production
run.

Verification order follows DR-CMD-055: tool-commit-accretion first
(the idempotency lead), then the registry in flow order.

Sections:
  A. tool-commit-accretion — happy path, crash-after-commit
     (already-covered), installer-snapshot walk-back, wrong identity,
     missing identity (each side), not-a-repo, git missing, operator
     authority, unknown authority, I-22 simulation, missing input,
     the file channel.
  B. rb-release-check through advance_run — honest path (A5 at
     run-book level), feed tamper, unparseable feed, network failure
     (retry:3 -> abort), crash recovery (C2 re-invocation).
  C. tool-read-policy — auto/drive, auto/defer over bump, notify,
     off, unknown policy, at-most-once surfacing under re-invocation.
  D. tool-invoke-installer — stub exit 0 (argv asserted byte-exact),
     exit 1, missing installer.
  E. tool-run-doctor fidelity (tool mirrors doctor.run_checks
     exactly) + tool-record-promotion (records / records nothing /
     byte-identical rewrite / unsafe version refused).
  F. R1 replay — revalidate_transcript over the honest and tamper
     transcripts: no violations, tools never reinvoked.
  G. I-31 — the pinned-registry predicate holds on honest runs;
     violations on release_version mismatch and unknown tool.
  H. A5 chain — the five updater run-books advance in flow order
     against the production registry (the timer-triggered flow itself
     needs the flow-driver integration noted in spec §11).

Returns {'ok', 'violations', 'cases'}. Prints RESULT: PASS/FAIL.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LIB_DSYS = Path(__file__).resolve().parent.parent
if str(LIB_DSYS) not in sys.path:
    sys.path.insert(0, str(LIB_DSYS))
TOOLS_DIR = Path(__file__).resolve().parent

import executor as X  # noqa: E402

VIOLATIONS: list[str] = []
CASES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CASES
    CASES += 1
    if cond:
        print(f"  ok: {name}")
    else:
        msg = f"FAIL: {name}" + (f" — {detail}" if detail else "")
        print(f"  {msg}")
        VIOLATIONS.append(msg)


@contextmanager
def temp_home():
    """A bare dsys home. DSYS_HOME points at it for the duration."""
    with tempfile.TemporaryDirectory(prefix="dsys-tools-") as td:
        home = Path(td)
        (home / "etc").mkdir()
        (home / "var").mkdir()
        old = os.environ.get("DSYS_HOME")
        os.environ["DSYS_HOME"] = str(home)
        try:
            yield home
        finally:
            if old is None:
                os.environ.pop("DSYS_HOME", None)
            else:
                os.environ["DSYS_HOME"] = old


def write_config(home: Path, **updater) -> None:
    lines = []
    if updater:
        lines.append("updater:")
        for k, v in updater.items():
            lines.append(f"  {k}: {v}")
    (home / "etc" / "config.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(home: Path, **kw) -> None:
    m = {"dist_version": "0.1.0"}
    m.update(kw)
    (home / "var" / "manifest.json").write_text(
        json.dumps(m, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Feed server
# ---------------------------------------------------------------------------

def make_feed_body(version: str) -> bytes:
    """The as-built feed contract (spec §11): {"version", "feed_sha256"}
    where feed_sha256 is the publisher's sha256 over the canonical JSON
    of the document with the feed_sha256 member removed."""
    bare = {"version": version}
    canonical = json.dumps(bare, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(canonical.encode()).hexdigest()
    doc = {"version": version, "feed_sha256": "sha256:" + h}
    return json.dumps(doc, sort_keys=True,
                      separators=(",", ":")).encode()


ROUTES: dict[str, tuple[int, bytes]] = {}


class _FeedHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path in ROUTES:
            status, body = ROUTES[self.path]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


@contextmanager
def feed_server():
    global ROUTES
    ROUTES = {
        "/feed.json": (200, make_feed_body("0.1.1")),
        "/tampered.json": (200, json.dumps(
            {"version": "9.9.9",
             "feed_sha256": "sha256:" + "0" * 64},
            sort_keys=True, separators=(",", ":")).encode()),
        "/bad.json": (200, b"not json{{{"),
    }
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FeedHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    old_no, old_NO = os.environ.get("no_proxy"), os.environ.get("NO_PROXY")
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        if old_no is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = old_no
        if old_NO is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = old_NO


def closed_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# Run-book + run scaffolding (the executor's in-memory shapes)
# ---------------------------------------------------------------------------

def make_runbook(runbook_id: str, steps: list[tuple[int, str, str]],
                 release_version: str = "test-dist") -> dict:
    return {
        "runbook_id": runbook_id,
        "release_version": release_version,
        "steps": [{"seq": s, "expr": e, "tool": t}
                  for s, e, t in steps],
    }


def make_run(runbook: dict, policy: str = "abort",
             ctx0: dict | None = None, run_id: str = "r-test") -> dict:
    return {
        "run_id": run_id,
        "kind": "run",
        "runbook_id": runbook["runbook_id"],
        "release_version": runbook.get("release_version"),
        "state": "open",
        "policy": policy,
        "idempotency_key": f"key-{run_id}",
        "ctx": {},
        "events": [{"seq": 0, "kind": "run_created", "payload": {
            "runbook_id": runbook["runbook_id"],
            "release_version": runbook.get("release_version"),
            "policy": policy, "ctx": dict(ctx0 or {})}}],
    }


def last_failed_error(run: dict):
    for e in reversed(run["events"]):
        if e["kind"] == "step_failed":
            return e["payload"]
    return None


def git(*args, cwd, env=None):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=60,
                          env=env)


def init_accretion_repo(path: Path, repo_id: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", cwd=path)
    git("config", "user.name", "t", cwd=path)
    git("config", "user.email", "t@t", cwd=path)
    git("config", "dsys.repo-id", repo_id, cwd=path)


def commit_count(path: Path) -> int:
    r = git("rev-list", "--count", "HEAD", cwd=path)
    return int(r.stdout.strip()) if r.returncode == 0 else 0


def flow_events(n: int, from_state: str = "driving") -> list[dict]:
    return [{"seq": i, "from_state_id": from_state,
             "to_state_id": "committing", "trigger": "run_completed",
             "payload": {"tick": i}} for i in range(n)]


# ---------------------------------------------------------------------------
# A. tool-commit-accretion (verified first, per DR-CMD-055)
# ---------------------------------------------------------------------------

def section_a_commit_accretion(tools: dict) -> None:
    print("A. tool-commit-accretion")
    commit = tools["tool-commit-accretion"]

    def ctx_for(home, acc, repo_id, authority="standing",
                with_input=True, n_events=3, first=0, last=2,
                kind=None):
        ctx = {
            "flow_run_id": "fr-test",
            "event_range": {"first_seq": first, "last_seq": last},
            "drive_identity": repo_id,
            "commit_authority": authority,
            "decision": "drive",
            "reason": "policy=auto",
            "doctor_ok": True,
            "promotion_recorded": True,
        }
        if with_input:
            inp = {"run_id": "fr-test", "source_state": "verifying",
                   "events": flow_events(n_events)}
            if kind is not None:
                inp["kind"] = kind
            ctx["_commit_input"] = inp
        return ctx

    # A1: happy path.
    with temp_home() as home:
        acc = home / "acc"; repo_id = "repo-1"
        init_accretion_repo(acc, repo_id)
        write_manifest(home, accretion={"enabled": True, "path": str(acc),
                                        "commit_authority": "standing"})
        res = X.invoke_tool(commit, ctx_for(home, acc, repo_id))
        check("A1 commit ok", res.ok and not res.malformed,
              f"error={res.error}")
        check("A1 payload hash recorded",
              res.ctx_delta.get("payload_hash") and
              res.ctx_delta.get("commit_event_range") == [0, 2])
        check("A1 one commit", commit_count(acc) == 1)
        # The payload is byte-identical to the canonical form.
        show = git("show", "HEAD:accretion/"
                   f"{res.ctx_delta['payload_hash']}.json", cwd=acc)
        import _common as C
        expected = C.canonical_payload(
            "fr-test", "verifying", flow_events(3), [],
            {"decision": "drive", "reason": "policy=auto"},
            {"doctor_ok": True, "promotion_recorded": True})
        check("A1 payload byte-canonical",
              show.stdout.strip() == expected)
        log = git("log", "-1", "--format=%s", cwd=acc).stdout.strip()
        check("A1 message names run, state, range",
              log.startswith("accretion: fr-test from verifying "
                             "events 0-2 payload "))
        # A2: crash-after-commit — re-invocation finds the watermark
        # covering the range: no duplicate commit.
        res2 = X.invoke_tool(commit, ctx_for(home, acc, repo_id))
        check("A2 already-covered",
              res2.ok and res2.result.get("committed") is False
              and res2.result.get("reason") == "already-covered"
              and res2.ctx_delta == {})
        check("A2 still one commit", commit_count(acc) == 1)
        # A3: an installer snapshot lands on top — the walk-back finds
        # the last accretion commit and the next drive commits only
        # the new events.
        git("commit", "-q", "--allow-empty", "-m",
            "snapshot: reinstall bracket", cwd=acc)
        ctx3 = ctx_for(home, acc, repo_id, n_events=5,
                       first=0, last=4)
        res3 = X.invoke_tool(commit, ctx3)
        check("A3 commit past snapshot ok", res3.ok,
              f"error={res3.error}")
        check("A3 covers only new events",
              res3.ctx_delta.get("commit_event_range") == [3, 4])
        check("A3 three commits total", commit_count(acc) == 3)

    # A4/A5/A6: identity binding.
    with temp_home() as home:
        acc = home / "acc"
        init_accretion_repo(acc, "repo-AAA")
        write_manifest(home, accretion={"enabled": True, "path": str(acc)})
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-BBB"))
        err = res.error or ""
        check("A4 wrong identity aborts closed",
              not res.ok and "identity binding failed (D3)" in err
              and "does not match" in err, err)
        check("A4 no commit written", commit_count(acc) == 0)
        check("A4 reason preserved verbatim",
              err == "tool raised ToolAborted: identity binding failed "
                     "(D3): I-25: handle identity does not match the "
                     "manifest-recorded identity", err)
        res = X.invoke_tool(commit, ctx_for(home, acc, None))
        check("A5 missing manifest identity aborts",
              not res.ok and "manifest records no accretion_repo.identity"
              in (res.error or ""))
        git("config", "--unset", "dsys.repo-id", cwd=acc)
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-AAA"))
        check("A5 missing handle identity aborts",
              not res.ok and "handle has no dsys.repo-id"
              in (res.error or ""))
    with temp_home() as home:
        acc = home / "acc"
        acc.mkdir(parents=True)  # not a git repo
        write_manifest(home, accretion={"enabled": True, "path": str(acc)})
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-AAA"))
        check("A6 not-a-repo aborts (D5a conjunct)",
              not res.ok and "not a git repo" in (res.error or ""),
              res.error)

    # A7: git missing entirely.
    with temp_home() as home:
        acc = home / "acc"; init_accretion_repo(acc, "repo-1")
        write_manifest(home, accretion={"enabled": True, "path": str(acc)})
        with tempfile.TemporaryDirectory() as emptydir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = emptydir
            try:
                res = X.invoke_tool(commit, ctx_for(home, acc, "repo-1"))
            finally:
                os.environ["PATH"] = old_path
        check("A7 git missing aborts (D5a)",
              not res.ok and "git not available" in (res.error or ""),
              res.error)

    # A8/A9/A10/A11: authority, simulation, missing input.
    with temp_home() as home:
        acc = home / "acc"; init_accretion_repo(acc, "repo-1")
        write_manifest(home, accretion={"enabled": True, "path": str(acc)})
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-1",
                                            authority="operator"))
        check("A8 operator authority refuses",
              not res.ok and "no terminal to prompt on" in (res.error or ""),
              res.error)
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-1",
                                            authority="whatever"))
        check("A9 unknown authority aborts",
              not res.ok and "unknown accretion commit authority"
              in (res.error or ""))
        res = X.invoke_tool(commit, ctx_for(home, acc, "repo-1",
                                            kind="simulation"))
        check("A10 simulation kind refused (I-22)",
              not res.ok and "I-22" in (res.error or ""), res.error)
        ctx11 = ctx_for(home, acc, "repo-1", with_input=False)
        del ctx11["flow_run_id"]
        res = X.invoke_tool(commit, ctx11)
        check("A11 missing input is a modeling fault",
              not res.ok and "without the driver's event-log input"
              in (res.error or ""), res.error)

    # A12: the file channel — no _commit_input; the flow run's
    # recorded log is read from var/runs/<flow_run_id>.json.
    with temp_home() as home:
        acc = home / "acc"; init_accretion_repo(acc, "repo-1")
        write_manifest(home, accretion={"enabled": True, "path": str(acc)})
        runs = home / "var" / "runs"
        runs.mkdir(parents=True)
        (runs / "fr-file.json").write_text(json.dumps(
            {"events": flow_events(2, from_state="driving")}))
        ctx = ctx_for(home, acc, "repo-1", with_input=False,
                      n_events=2, first=0, last=1)
        ctx["flow_run_id"] = "fr-file"
        res = X.invoke_tool(commit, ctx)
        check("A12 file channel commits", res.ok,
              f"error={res.error}")
        log = git("log", "-1", "--format=%s", cwd=acc).stdout.strip()
        check("A12 source_state from the log",
              "from driving events 0-1" in log, log)


print("loading the production registry...")
tools = X.load_tools(TOOLS_DIR)
for name in ("tool-fetch-feed", "tool-compare-versions",
             "tool-verify-checksum", "tool-read-policy",
             "tool-invoke-installer", "tool-run-doctor",
             "tool-record-promotion", "tool-commit-accretion"):
    check(f"registry resolves {name}", name in tools)
print(f"registry holds {len(tools)} entries")


# ---------------------------------------------------------------------------
# B. rb-release-check through advance_run (the honest path + negatives)
# ---------------------------------------------------------------------------

def section_b_release_check(tools: dict) -> None:
    print("B. rb-release-check through the executor")
    rb_check = make_runbook("rb-release-check",
                            [(0, "True", "tool-fetch-feed"),
                             (1, "True", "tool-compare-versions")])
    rb_verify = make_runbook("rb-release-verify",
                             [(0, "True", "tool-verify-checksum")])

    with feed_server() as base:
        # B1: honest path — advances past checking (A5 at run-book level).
        with temp_home() as home:
            write_config(home, feed_url=f"{base}/feed.json",
                         policy="auto", auto_max_bump="minor")
            write_manifest(home, dist_version="0.1.0")
            run = make_run(rb_check, policy="retry:3", run_id="r-b1")
            X.advance_run(run, rb_check, tools)
            check("B1 run completes", run["state"] == "completed",
                  run["state"])
            ctx = run["ctx"]
            check("B1 poll recorded",
                  ctx.get("remote_version") == "0.1.1"
                  and ctx.get("installed_version") == "0.1.0"
                  and ctx.get("feed_sha256") == ctx.get("feed_checksum"))
            # The verify run-book consumes the recorded poll data.
            run2 = make_run(rb_verify, run_id="r-b1v", ctx0=dict(ctx))
            X.advance_run(run2, rb_verify, tools)
            check("B1 checksum gate passes", run2["state"] == "completed")
            # R1: the transcripts revalidate with tools never reinvoked.
            v = X.revalidate_transcript(run["events"], rb_check, "retry:3")
            check("B1 transcript revalidates (R1)", v == [], v[:1])
            v = X.revalidate_transcript(run2["events"], rb_verify, "abort")
            check("B1 verify transcript revalidates", v == [], v[:1])

        # B2: feed tamper — the declared checksum does not match the
        # received bytes: no candidacy, run_aborted -> failed.
        with temp_home() as home:
            write_config(home, feed_url=f"{base}/tampered.json")
            write_manifest(home, dist_version="0.1.0")
            run = make_run(rb_check, run_id="r-b2")
            X.advance_run(run, rb_check, tools)
            runv = make_run(rb_verify, ctx0=dict(run["ctx"]),
                            run_id="r-b2v")
            X.advance_run(runv, rb_verify, tools)
            check("B2 tampered feed fails closed",
                  runv["state"] == "aborted", runv["state"])
            err = (last_failed_error(runv) or {}).get("error", "")
            check("B2 reason preserved verbatim",
                  err == "tool raised ToolAborted: "
                         "checksum mismatch: no candidacy", err)
            v = X.revalidate_transcript(runv["events"], rb_verify, "abort")
            check("B2 aborted transcript revalidates", v == [], v[:1])

        # B3: unparseable feed.
        with temp_home() as home:
            write_config(home, feed_url=f"{base}/bad.json")
            write_manifest(home)
            run = make_run(rb_check, policy="retry:3", run_id="r-b3")
            X.advance_run(run, rb_check, tools)
            err = (last_failed_error(run) or {}).get("error", "")
            check("B3 unparseable feed aborts",
                  run["state"] == "aborted"
                  and "unparseable feed" in err, err)

        # B4: network failure — retry:3, then abort (updater-spec §5).
        with temp_home() as home:
            write_config(home,
                         feed_url=f"http://127.0.0.1:{closed_port()}/feed.json")
            write_manifest(home)
            run = make_run(rb_check, policy="retry:3", run_id="r-b4")
            X.advance_run(run, rb_check, tools)
            starts = [e for e in run["events"]
                      if e["kind"] == "step_started"
                      and e["payload"]["step_seq"] == 0]
            check("B4 three attempts then abort",
                  run["state"] == "aborted" and len(starts) == 3,
                  f"state={run['state']} attempts={len(starts)}")

        # B5: crash recovery — a trailing step_started (C2) re-invokes
        # the pure fetch under at-least-once; no side effects duplicate.
        with temp_home() as home:
            write_config(home, feed_url=f"{base}/feed.json")
            write_manifest(home)
            run = make_run(rb_check, run_id="r-b5")
            run["events"].append(
                {"seq": 1, "kind": "step_started",
                 "payload": {"step_seq": 0, "tool": "tool-fetch-feed"}})
            X.advance_run(run, rb_check, tools)
            check("B5 crash recovery completes",
                  run["state"] == "completed", run["state"])
            check("B5 poll recorded once",
                  run["ctx"].get("remote_version") == "0.1.1")

        # B6: no pinned feed URL — refuse to invent a pin.
        with temp_home() as home:
            write_config(home, policy="auto")
            write_manifest(home)
            run = make_run(rb_check, run_id="r-b6")
            X.advance_run(run, rb_check, tools)
            err = (last_failed_error(run) or {}).get("error", "")
            check("B6 missing feed_url aborts",
                  run["state"] == "aborted"
                  and "no pinned feed URL" in err, err)


# ---------------------------------------------------------------------------
# C. tool-read-policy
# ---------------------------------------------------------------------------

def section_c_policy(tools: dict) -> None:
    print("C. tool-read-policy")
    rb_gate = make_runbook("rb-policy-gate",
                           [(0, "True", "tool-read-policy")])
    base_ctx = {"installed_version": "0.1.0", "remote_version": "0.1.1"}

    # C1: auto, patch bump within patch -> drive.
    with temp_home() as home:
        write_config(home, policy="auto", auto_max_bump="patch")
        run = make_run(rb_gate, ctx0=dict(base_ctx), run_id="r-c1")
        X.advance_run(run, rb_gate, tools)
        check("C1 auto within bump drives",
              run["state"] == "completed"
              and run["ctx"].get("decision") == "drive"
              and run["ctx"].get("policy") == "auto"
              and run["ctx"].get("auto_max_bump") == "patch")

    # C2: auto, minor bump against max patch -> defer + surface once.
    with temp_home() as home:
        write_config(home, policy="auto", auto_max_bump="patch")
        ctx0 = {"installed_version": "0.1.0", "remote_version": "0.2.0"}
        run = make_run(rb_gate, ctx0=dict(ctx0), run_id="r-c2")
        X.advance_run(run, rb_gate, tools)
        d = run["ctx"]
        check("C2 over-bump defers",
              d.get("decision") == "defer" and "exceeds patch" in
              d.get("reason", ""))
        ddir = home / "var" / "disclosures"
        files = sorted(ddir.glob("dl-*.json"))
        check("C2 one disclosure minted", len(files) == 1, files)
        rec = json.loads(files[0].read_text())
        check("C2 disclosure is updater-deferred",
              rec["kind"] == "updater-deferred"
              and "version: 0.2.0" in rec["text"])
        seq = d.get("surfaced_seq")
        # Crash recovery: re-invocation reuses the seq — at most once.
        run2 = make_run(rb_gate, ctx0=dict(d), run_id="r-c2b")
        run2["events"].append(
            {"seq": 1, "kind": "step_started",
             "payload": {"step_seq": 0, "tool": "tool-read-policy"}})
        X.advance_run(run2, rb_gate, tools)
        files2 = sorted(ddir.glob("dl-*.json"))
        check("C2 re-invocation surfaces at most once",
              len(files2) == 1
              and run2["ctx"].get("surfaced_seq") == seq)

    # C3: notify -> defer + surfaced, not driven.
    with temp_home() as home:
        write_config(home, policy="notify", auto_max_bump="patch")
        run = make_run(rb_gate, ctx0=dict(base_ctx), run_id="r-c3")
        X.advance_run(run, rb_gate, tools)
        check("C3 notify defers and surfaces",
              run["ctx"].get("decision") == "defer"
              and run["ctx"].get("reason")
              == "policy=notify: surfaced, not driven"
              and len(list((home / "var" / "disclosures").glob("dl-*.json")))
              == 1)

    # C4: off -> defer, recorded only, nothing surfaced.
    with temp_home() as home:
        write_config(home, policy="off")
        run = make_run(rb_gate, ctx0=dict(base_ctx), run_id="r-c4")
        X.advance_run(run, rb_gate, tools)
        check("C4 off defers silently",
              run["ctx"].get("decision") == "defer"
              and run["ctx"].get("reason") == "policy=off: recorded only"
              and not (home / "var" / "disclosures").exists())

    # C5: unknown policy aborts loudly — no silent degradation.
    with temp_home() as home:
        write_config(home, policy="autoo")
        run = make_run(rb_gate, ctx0=dict(base_ctx), run_id="r-c5")
        X.advance_run(run, rb_gate, tools)
        err = (last_failed_error(run) or {}).get("error", "")
        check("C5 unknown policy aborts",
              run["state"] == "aborted"
              and err == "tool raised ToolAborted: "
                         "unknown updater policy: 'autoo'", err)


# ---------------------------------------------------------------------------
# D. tool-invoke-installer (against a stub install.sh)
# ---------------------------------------------------------------------------

STUB_INSTALL = """#!/bin/bash
# Stub installer for the golden run: records argv, exits $STUB_EXIT.
echo "$@" >> "$STUB_ARGV_LOG"
exit "${STUB_EXIT:-0}"
"""


def section_d_installer(tools: dict) -> None:
    print("D. tool-invoke-installer")
    rb_drive = make_runbook("rb-release-drive",
                            [(0, "True", "tool-invoke-installer")])

    def with_stub(home, exit_code):
        inst = home / "install.sh"
        inst.write_text(STUB_INSTALL, encoding="utf-8")
        inst.chmod(0o755)
        old_env = dict(os.environ)
        os.environ["STUB_ARGV_LOG"] = str(home / "argv.log")
        os.environ["STUB_EXIT"] = str(exit_code)
        return old_env

    def restore_env(old_env):
        os.environ.clear()
        os.environ.update(old_env)

    with temp_home() as home:
        old_env = with_stub(home, 0)
        try:
            write_manifest(home, dist_version="0.1.0")
            run = make_run(rb_drive, run_id="r-d1",
                           ctx0={"remote_version": "0.1.1"})
            X.advance_run(run, rb_drive, tools)
        finally:
            restore_env(old_env)
        check("D1 stub install completes", run["state"] == "completed",
              run["state"])
        check("D1 ctx_delta exit_code 0",
              run["ctx"].get("exit_code") == 0)
        argv = (home / "argv.log").read_text().strip().split()
        check("D1 argv byte-exact (K2)",
              argv == ["--release", "0.1.1", "--accretion-path",
                       "/var/daccretion/" + home.name,
                       "--accretion-required"], argv)

    with temp_home() as home:
        old_env = with_stub(home, 1)
        try:
            write_manifest(home, dist_version="0.1.0")
            run = make_run(rb_drive, run_id="r-d2",
                           ctx0={"remote_version": "0.1.1"})
            X.advance_run(run, rb_drive, tools)
        finally:
            restore_env(old_env)
        err = (last_failed_error(run) or {}).get("error", "")
        check("D2 nonzero exit aborts loudly",
              run["state"] == "aborted"
              and err == "tool raised ToolAborted: "
                         "installer exited 1 for 0.1.1", err)

    with temp_home() as home:
        write_manifest(home, dist_version="0.1.0")
        run = make_run(rb_drive, run_id="r-d3",
                       ctx0={"remote_version": "0.1.1"})
        X.advance_run(run, rb_drive, tools)
        err = (last_failed_error(run) or {}).get("error", "")
        check("D3 missing installer aborts",
              run["state"] == "aborted"
              and "not found or not executable" in err, err)


# ---------------------------------------------------------------------------
# E. tool-run-doctor fidelity + tool-record-promotion
# ---------------------------------------------------------------------------

def section_e_doctor_promotion(tools: dict) -> None:
    print("E. tool-run-doctor + tool-record-promotion")

    # E1: the tool mirrors doctor.run_checks exactly (fidelity, not
    # verdict — the verdict depends on the tree under test).
    with temp_home() as home:
        import doctor  # noqa: E402

        direct = doctor.run_checks(home, strict=False)
        expected = not any(c.get("status") == "fail"
                           for c in direct.get("checks", []))
        res = X.invoke_tool(tools["tool-run-doctor"], {})
        check("E1 tool mirrors doctor",
              res.ok and res.ctx_delta.get("doctor_ok") is expected)
        check("E1 bare temp home fails doctor (honest)",
              expected is False)

    # E2: doctor_ok false -> records nothing.
    with temp_home() as home:
        res = X.invoke_tool(
            tools["tool-record-promotion"],
            {"doctor_ok": False, "remote_version": "0.1.1",
             "feed_sha256": "sha256:abc"})
        check("E2 no promotion on failed doctor",
              res.ok and res.ctx_delta.get("promotion_recorded") is False
              and not (home / "var" / "promotions").exists())

    # E3: doctor_ok true -> deterministic record; re-invocation is
    # byte-identical (no duplicate promotion can exist).
    with temp_home() as home:
        ctx = {"doctor_ok": True, "remote_version": "0.1.1",
               "feed_sha256": "sha256:abc123"}
        res = X.invoke_tool(tools["tool-record-promotion"], dict(ctx))
        p = home / "var" / "promotions" / "0.1.1.json"
        check("E3 promotion recorded",
              res.ok and res.ctx_delta.get("promotion_recorded") is True
              and p.is_file())
        first = p.read_bytes()
        check("E3 content canonical",
              first == b'{"feed_sha256":"sha256:abc123","version":"0.1.1"}\n',
              first[:60])
        res2 = X.invoke_tool(tools["tool-record-promotion"], dict(ctx))
        check("E3 re-invocation byte-identical",
              res2.ok and p.read_bytes() == first)

    # E4: a feed-supplied version must not become a path.
    with temp_home() as home:
        res = X.invoke_tool(
            tools["tool-record-promotion"],
            {"doctor_ok": True, "remote_version": "../../evil",
             "feed_sha256": "sha256:abc"})
        check("E4 unsafe version refused",
              not res.ok and "unsafe version string" in (res.error or ""),
              res.error)


# ---------------------------------------------------------------------------
# F. R1 replay — revalidate_transcript over further transcripts.
# ---------------------------------------------------------------------------

def section_f_replay(tools: dict) -> None:
    print("F. R1 replay")
    rb_gate = make_runbook("rb-policy-gate",
                           [(0, "True", "tool-read-policy")])
    with temp_home() as home:
        write_config(home, policy="notify")
        run = make_run(
            rb_gate, run_id="r-f1",
            ctx0={"installed_version": "0.1.0", "remote_version": "0.1.1"})
        X.advance_run(run, rb_gate, tools)
        v = X.revalidate_transcript(run["events"], rb_gate, "abort")
        check("F1 policy transcript revalidates", v == [], v[:1])
        # The disclosure minted on the live path is recorded data, not
        # re-minted by replay: exactly one file exists.
        check("F1 one disclosure total",
              len(list((home / "var" / "disclosures").glob("dl-*.json")))
              == 1)


# ---------------------------------------------------------------------------
# G. I-31 — the pinned-registry predicate
# ---------------------------------------------------------------------------

def section_g_i31(tools: dict) -> None:
    print("G. I-31 pinned registry")
    import _common as C

    rb = make_runbook("rb-release-check",
                      [(0, "True", "tool-fetch-feed"),
                       (1, "True", "tool-compare-versions")],
                      release_version="test-dist")
    with temp_home() as home:
        write_config(home, feed_url="http://127.0.0.1:9/feed.json")
        write_manifest(home)
        run = make_run(rb, run_id="r-g1")
        # Seed the fetch delta directly: I-31 is about the registry
        # binding, not the network.
        run["events"].append(
            {"seq": 1, "kind": "step_started",
             "payload": {"step_seq": 0, "tool": "tool-fetch-feed"}})
        run["events"].append(
            {"seq": 2, "kind": "step_completed",
             "payload": {"step_seq": 0, "tool": "tool-fetch-feed",
                         "result": {}, "ctx_delta": {}}})
    v = C.i31_pinned_registry(run, TOOLS_DIR, "test-dist")
    check("G1 honest run satisfies I-31", v == [], v[:1])

    bad_version = dict(run)
    bad_version["release_version"] = "9.9.9"
    v = C.i31_pinned_registry(bad_version, TOOLS_DIR, "test-dist")
    check("G2 version mismatch violates I-31",
          len(v) == 1 and "9.9.9" in v[0], v)

    bad_tool = dict(run)
    bad_tool["events"] = run["events"] + [
        {"seq": len(run["events"]), "kind": "step_started",
         "payload": {"step_seq": 9, "tool": "tool-nope"}}]
    v = C.i31_pinned_registry(bad_tool, TOOLS_DIR, "test-dist")
    check("G3 unknown tool violates I-31",
          any("tool-nope" in x for x in v), v)


# ---------------------------------------------------------------------------
# H. A5 chain — the five updater run-books in flow order
# ---------------------------------------------------------------------------

def section_h_chain(tools: dict, base: str) -> None:
    print("H. A5 run-book chain (flow order, production registry)")
    books = [
        make_runbook("rb-release-check",
                     [(0, "True", "tool-fetch-feed"),
                      (1, "True", "tool-compare-versions")]),
        make_runbook("rb-release-verify",
                     [(0, "True", "tool-verify-checksum")]),
        make_runbook("rb-policy-gate",
                     [(0, "True", "tool-read-policy")]),
        make_runbook("rb-release-drive",
                     [(0, "True", "tool-invoke-installer")]),
        make_runbook("rb-release-verify-installed",
                     [(0, "True", "tool-run-doctor"),
                      (1, "True", "tool-record-promotion")]),
    ]
    with temp_home() as home:
        write_config(home, feed_url=f"{base}/feed.json",
                     policy="auto", auto_max_bump="minor")
        write_manifest(home, dist_version="0.1.0")
        inst = home / "install.sh"
        inst.write_text(STUB_INSTALL, encoding="utf-8")
        inst.chmod(0o755)
        old_env = dict(os.environ)
        os.environ["STUB_ARGV_LOG"] = str(home / "argv.log")
        os.environ["STUB_EXIT"] = "0"
        try:
            ctx = {}
            states = []
            for i, rb in enumerate(books):
                run = make_run(rb, policy="retry:3",
                               run_id=f"r-h{i}", ctx0=dict(ctx))
                X.advance_run(run, rb, tools, max_steps=100)
                states.append(run["state"])
                ctx.update(run["ctx"])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        check("H1 all five run-books complete",
              states == ["completed"] * 5, states)
        check("H2 drive decision recorded",
              ctx.get("decision") == "drive", ctx.get("decision"))
        check("H3 installer converged the candidate",
              ctx.get("exit_code") == 0)
        # The bare temp home cannot pass doctor (no valid install
        # tree): the promotion step honestly records nothing.
        check("H4 doctor ran, promotion honestly skipped",
              ctx.get("doctor_ok") is False
              and ctx.get("promotion_recorded") is False)


def main() -> dict:
    with feed_server() as base:
        section_a_commit_accretion(tools)
        section_b_release_check(tools)
        section_c_policy(tools)
        section_d_installer(tools)
        section_e_doctor_promotion(tools)
        section_f_replay(tools)
        section_g_i31(tools)
        section_h_chain(tools, base)
    ok = not VIOLATIONS
    print(f"RESULT: {'PASS' if ok else 'FAIL'} — "
          f"{CASES} cases, {len(VIOLATIONS)} violations")
    return {"ok": ok, "violations": VIOLATIONS, "cases": CASES}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["ok"] else 1)
