#!/usr/bin/env python3
"""tool-commit-accretion (rb-accretion-commit, step 1): K1's accretion
writer (DR-CMD-039), ported to the executor. The sharpest tool in the
registry — specified first, as DR-CMD-055 requires.

ctx in: {flow_run_id, event_range: {first_seq, last_seq},
drive_identity, commit_authority} — seeded by the flow's transition
into the committing state. drive_identity is the drive-resolved
manifest identity (the drive contract's governed/process split: the
process side resolves it once at initiation; the tool's D3 check is a
pure comparison of ctx's value against the handle's dsys.repo-id).

The event log arrives on the K1 _commit_input channel (popped here,
never emitted — the driver injects it for rb-accretion-commit), or —
when the driver has not injected it — the tool reads the flow run's
recorded log from <DSYS_HOME>/var/runs/<flow_run_id>.json (as-built,
spec §11). The event_range bounds the diff in both channels.

The write: diff the range against the watermark (the most recent K1
accretion commit's covered event range — found by walking back past
any installer snapshots, as-built spec §11), build the canonical
payload (accretion-commit/v1, sorted-keys compact JSON, sha256
content-hash — K1 Q1), and commit via git (subprocess, §2 scope).

D3 pre-write identity check (K1 Q3(a), DR-CMD-047): the handle's
dsys.repo-id must equal drive_identity; mismatch — or a missing key on
either side — fails closed: abort, not retry (D4a), no commit.
Authority: standing commits without asking; operator on an autonomous
drive refuses (no terminal to prompt on); anything else aborts. Git is
a hard dependency (D5a): git unavailable, or the path not a git repo,
aborts.

Idempotency — the watermark re-check: it precedes the write.
Re-invocation after a crash reads the repo: if the covered range
already includes the events (the commit landed before the crash), the
diff is empty -> no commit, {"committed": false, "reason":
"already-covered"}. Otherwise the tool re-builds the byte-identical
canonical payload (deterministic from the same events) and commits.
Append-only (D6): the tool only ever runs `git add` + `git commit` —
no amend, no rebase — and stages exactly the one payload file, so no
unrelated work-tree content is swept into the journal.

Abort, not retry: the run-book policy is abort (D4a) — a failed commit
is never blindly retried inside the drive; the next drive's cumulative
commit is the retry.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-commit-accretion"

_GIT_TIMEOUT_S = 120  # as-built: the git spawn bound (spec §11)

# K1 D4: the message names the flow-run id and the source state; the
# payload hash names the payload bytes (I-19).
_ACCRETION_MSG = re.compile(
    r"^accretion: (\S+) from (\S+) events (\d+)-(\d+) payload ([0-9a-f]{12})$")


def _git(acc_path: str, *args: str):
    return subprocess.run(
        ["git", "-C", acc_path, *args],
        capture_output=True, text=True, timeout=_GIT_TIMEOUT_S)


def _last_accretion_commit(acc_path: str):
    """Locate the most recent K1 accretion commit by walking the log
    back past any non-accretion commits (installer snapshots share the
    repo). Returns (sha, last_seq, promotions_through), or
    (None, -1, 0) when the repo holds no accretion commit yet.

    The watermark is the tip accretion commit's covered event range
    (last_seq); promotions_through is the number of promotions its
    payload embedded — the slice point for the new payload's
    promotions. A tip accretion commit whose payload file is missing
    or disagrees with its message fails closed (modeling fault).
    """
    r = _git(acc_path, "log", "--format=%H %s")
    if r.returncode != 0:
        return None, -1, 0
    for line in r.stdout.splitlines():
        sha, _, subject = line.partition(" ")
        m = _ACCRETION_MSG.match(subject)
        if not m:
            continue
        last_seq = int(m.group(4))
        files = _git(acc_path, "show", "--name-only",
                     "--pretty=format:", sha)
        if files.returncode != 0:
            raise C.ToolAborted(
                "cannot inspect the tip accretion commit — refusing")
        payload_file = next(
            (f for f in files.stdout.splitlines()
             if f.startswith("accretion/") and f.endswith(".json")),
            None)
        if payload_file is None:
            raise C.ToolAborted(
                "tip accretion commit carries no payload file — refusing")
        show = _git(acc_path, "show", f"{sha}:{payload_file}")
        if show.returncode != 0:
            raise C.ToolAborted(
                "cannot read the tip accretion payload — refusing")
        try:
            payload = json.loads(show.stdout)
        except ValueError:
            raise C.ToolAborted(
                "tip accretion payload is not JSON — refusing")
        er = (payload.get("event_range") or {})
        if er.get("last_seq") != last_seq:
            raise C.ToolAborted(
                "tip accretion payload disagrees with its commit message "
                "— refusing")
        promotions = payload.get("promotions") or []
        return sha, last_seq, len(promotions)
    return None, -1, 0


def _read_promotions(home: Path) -> list:
    """All promotion records, filename order — the fixture's
    w.promotions list, as files."""
    pdir = home / "var" / "promotions"
    records = []
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                raise C.ToolAborted(
                    f"promotion record {p.name} is not JSON — refusing")
            records.append(rec)
    return records


def run(ctx: dict) -> dict:
    home = C.resolve_home()
    flow_run_id = ctx.get("flow_run_id")
    event_range = ctx.get("event_range") or {}
    drive_identity = ctx.get("drive_identity")  # None = missing: fail closed
    authority = ctx.get("commit_authority", "standing")

    # D5a: git is a hard dependency — fail closed, never degrade.
    if shutil.which("git") is None:
        raise C.ToolAborted(
            "git not available: the drive's durability guarantee rests "
            "on git (D5a) — refusing")
    manifest = C.read_manifest(home)
    acc_path = C.accretion_path(home, manifest)
    repo_ok = (_git(acc_path, "rev-parse", "--is-inside-work-tree")
               .returncode == 0)
    repo_identity = None
    if repo_ok:
        r = _git(acc_path, "config", "dsys.repo-id")
        repo_identity = r.stdout.strip() or None
    # D3 (K1 Q3(a), DR-CMD-047): the identity check is a pure
    # comparison of the drive-resolved identity against the handle's.
    bad_binding = C.i25_identity_binding(
        drive_identity, repo_identity, repo_ok)
    if bad_binding:
        raise C.ToolAborted("identity binding failed (D3): "
                            + "; ".join(bad_binding))
    if authority == "operator":
        # Autonomous operation cannot prompt (no terminal): refuse
        # loudly, never silently skip (K1 D3).
        raise C.ToolAborted(
            "accretion.commit_authority=operator: no terminal to prompt "
            "on — refusing the commit")
    if authority != "standing":
        raise C.ToolAborted(
            f"unknown accretion commit authority: {authority!r}")

    # The event log: the K1 _commit_input channel first (popped, never
    # emitted), else the flow run's recorded log.
    inp = ctx.pop("_commit_input", None)
    if inp is not None:
        if inp.get("kind") == "simulation":
            # I-22 (DR-CMD-041): simulation transcripts are
            # ontologically separate from production records — the
            # writer structurally cannot accept them.
            raise C.ToolAborted(
                "I-22: kind=simulation transcripts are not committable "
                "to the accretion repo")
        events = inp.get("events") or []
        run_id = inp.get("run_id") or flow_run_id
        source_state = inp.get("source_state")
    else:
        if not flow_run_id:
            raise C.ToolAborted(
                "committing run-book invoked without the driver's "
                "event-log input — modeling fault")
        rec_path = home / "var" / "runs" / f"{flow_run_id}.json"
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except OSError as e:
            raise C.ToolAborted(
                f"cannot read the flow run's event log: {e}")
        except ValueError:
            raise C.ToolAborted(
                "the flow run's event log is not JSON — refusing")
        events = rec.get("events") or []
        run_id = flow_run_id
        source_state = None
    first = event_range.get("first_seq")
    last = event_range.get("last_seq")
    ranged = [e for e in events
              if isinstance(e, dict) and isinstance(e.get("seq"), int)
              and (first is None or e["seq"] >= first)
              and (last is None or e["seq"] <= last)]
    if not ranged:
        raise C.ToolAborted(
            "committing run-book invoked with an empty event range — "
            "modeling fault")
    if source_state is None:
        source_state = ranged[0].get("from_state_id", "unknown")

    # The watermark re-check precedes the write (idempotency under
    # at-least-once crash recovery).
    _sha, watermark, prev_through = _last_accretion_commit(acc_path)
    new_events = [e for e in ranged if e["seq"] > watermark]
    if not new_events:
        return {
            "ok": True,
            "result": {"committed": False, "reason": "already-covered"},
            "ctx_delta": {},
        }
    promotions = _read_promotions(home)[prev_through:]
    decision = {"decision": ctx.get("decision"),
                "reason": ctx.get("reason")}
    verification = {"doctor_ok": ctx.get("doctor_ok"),
                    "promotion_recorded": ctx.get("promotion_recorded")}
    payload = C.canonical_payload(run_id, source_state, new_events,
                                  promotions, decision, verification)
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    first_seq, last_seq = new_events[0]["seq"], new_events[-1]["seq"]
    message = (f"accretion: {run_id} from {source_state} "
               f"events {first_seq}-{last_seq} payload "
               f"{payload_hash[:12]}")
    rel = f"accretion/{payload_hash}.json"
    payload_path = Path(acc_path) / rel
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(payload + "\n", encoding="utf-8")
    r = _git(acc_path, "add", rel)
    if r.returncode != 0:
        raise C.ToolAborted(
            f"git add failed: {r.stderr.strip()}")
    # The author/committer envelope is transport, never replay
    # identity (K1 D5): -c flags keep the tool independent of the
    # ambient git config without mutating the repo's config.
    r = _git(acc_path, "-c", "user.name=dsys-accretion",
             "-c", "user.email=dsys-accretion@localhost",
             "commit", "-m", message)
    if r.returncode != 0:
        raise C.ToolAborted(f"git commit failed: {r.stderr.strip()}")
    return {
        "ok": True,
        "result": {"committed": True, "payload_hash": payload_hash},
        "ctx_delta": {
            "commit_confirmed": True,
            "commit_skipped": False,
            "payload_hash": payload_hash,
            "commit_event_range": [first_seq, last_seq],
        },
    }
