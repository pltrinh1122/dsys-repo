#!/usr/bin/env python3
"""Shared helpers for the dsys production tool registry (lib/dsys/tools/).

Not a tool: the leading underscore keeps it out of load_tools' registry
(executor.load_tools skips modules whose name starts with "_").

Contents: the ToolAborted exception (the K1 vocabulary — the executor's
C1 normalizes it into step_failed with the message preserved verbatim),
install-home resolution (DSYS_HOME, never ctx), the operator-owned
updater config block reader, manifest/accretion-path resolution, the K1
canonical payload (byte-identical port of core/package/updater.py's
canonical_payload), the version-bump classifier (port of _bump), the
I-25 identity-binding predicate (port), the I-31 pinned-registry
predicate, and the DR-5 disclosure minter.
"""

import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

_LIB_DSYS = Path(__file__).resolve().parent.parent
if str(_LIB_DSYS) not in sys.path:
    sys.path.insert(0, str(_LIB_DSYS))

import yamlutil  # noqa: E402  (lib/dsys top-level module, same as config.py)


class ToolAborted(Exception):
    """A tool refused its work: the run-book run aborts (run_aborted).

    The executor's C1 normalizes a raised tool into step_failed with the
    error "tool raised ToolAborted: <message>" — the reason reaches the
    operator verbatim (production-tools spec §5).
    """


def resolve_home() -> Path:
    """Return the dsys install root. DSYS_HOME wins; otherwise the home
    is derived from this file's location (<home>/lib/dsys/tools/).
    Environment facts stay out of the recorded log — tools never take
    the home from ctx (spec §2)."""
    env = os.environ.get("DSYS_HOME")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


_UPDATER_DEFAULTS = {
    "feed_url": None,      # no default: a feed URL is a trust decision,
    "policy": "notify",    # never smuggled in (spec §4.4, R5)
    "auto_max_bump": "patch",
}


def read_updater_config(home: Path) -> dict:
    """Read the operator-owned updater config block.

    etc/config.yaml may carry a one-level nested ``updater:`` mapping
    (the yamlutil subset). Absent file or block -> defaults. A missing
    feed_url stays None — the fetch tool aborts loudly rather than
    inventing a pin. Raises ToolAborted on a malformed file or a
    non-mapping updater block.
    """
    cfg = dict(_UPDATER_DEFAULTS)
    path = Path(home) / "etc" / "config.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return cfg
    try:
        raw = yamlutil.loads(text)
    except ValueError as e:
        raise ToolAborted(f"cannot parse etc/config.yaml: {e}")
    block = raw.get("updater")
    if block is None:
        return cfg
    if not isinstance(block, dict):
        raise ToolAborted("etc/config.yaml: 'updater' must be a mapping")
    for key in ("feed_url", "policy", "auto_max_bump"):
        if block.get(key) is not None:
            cfg[key] = block[key]
    return cfg


def read_manifest(home: Path) -> dict | None:
    """Read the installation manifest, or None when absent/unparseable."""
    path = Path(home) / "var" / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def accretion_path(home: Path, manifest: dict | None) -> str:
    """Resolve the accretion journal path.

    The manifest's recorded accretion.path when the journal is enabled
    and recorded (the installer's established resolution); else the
    default rule over the home's basename (installer-spec §13, K2).
    """
    acc = (manifest or {}).get("accretion") or {}
    if acc.get("enabled") and acc.get("path"):
        return str(acc["path"])
    return "/var/daccretion/" + Path(home).name


def canonical_payload(run_id: str, source_state: str, events: list,
                      promotions: list, decision: dict,
                      verification: dict) -> str:
    """K1 Q1, byte-identical port of core/package/updater.py's
    canonical_payload: sorted keys, compact separators — deterministic
    bytes from deterministic events. Replay identity is these bytes
    (D5's payload/envelope distinction): the git envelope is transport,
    never replay identity."""
    payload = {
        "schema": "accretion-commit/v1",
        "flow_run_id": run_id,
        "source_state": source_state,
        "event_range": {"first_seq": events[0]["seq"],
                        "last_seq": events[-1]["seq"]},
        "events": events,
        "promotions": promotions,
        "policy_decision": decision,
        "verification": verification,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


_BUMP_ORDER = {"patch": 0, "minor": 1, "major": 2}


def bump(old: str, new: str) -> str:
    """Classify the bump old->new. Exact port of updater._bump:
    defensive — real-world versions carry suffixes ('1.2.3-rc1') and
    uneven segment counts; parse leading digits per segment, pad short,
    compare major/minor/rest."""

    def nums(v: str) -> list[int]:
        out = []
        for seg in v.split("."):
            digits = ""
            for ch in seg:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            out.append(int(digits) if digits else 0)
        return out

    o, n = nums(old), nums(new)
    width = max(len(o), len(n))
    o += [0] * (width - len(o))
    n += [0] * (width - len(n))
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"


def i25_identity_binding(manifest_identity: str | None,
                         repo_identity: str | None,
                         git_available: bool) -> list[str]:
    """I-25 (K1 Q3a, DR-CMD-047), exact port of the updater predicate:
    the committing tool writes only to a handle whose repo identity
    (dsys.repo-id) equals the manifest-recorded accretion_repo.identity.
    Violations: identity missing on either side; mismatch; the D5a
    conjunct (the handle is not a git repo)."""
    v: list[str] = []
    if not git_available:
        v.append("I-25: handle is not a git repo (D5a conjunct)")
    if manifest_identity is None:
        v.append("I-25: manifest records no accretion_repo.identity")
    if repo_identity is None:
        v.append("I-25: handle has no dsys.repo-id (missing key)")
    if (manifest_identity is not None and repo_identity is not None
            and manifest_identity != repo_identity):
        v.append("I-25: handle identity does not match the "
                 "manifest-recorded identity")
    return v


def i31_pinned_registry(run: dict, tools_dir: Path,
                        dist_release_version: str | None = None) -> list[str]:
    """I-31 (candidate, production-tools spec §7): a predicate over the
    run record — for every step_started event, the tool resolves in the
    dist's tool registry (loaded the dist-shipped way, no overlays), and
    the run's recorded release_version identifies that dist. Violation
    -> the run is invalid (referee's exit 5, same class as replay
    violations). Enforcement in init/advance is future work; the golden
    run checks the predicate (R2)."""
    import executor  # lib/dsys top-level module

    try:
        registry = executor.load_tools(Path(tools_dir))
    except Exception as e:
        return [f"I-31: cannot load the dist tool registry: {e}"]
    v: list[str] = []
    for e in run.get("events", []):
        if isinstance(e, dict) and e.get("kind") == "step_started":
            tool = e.get("payload", {}).get("tool")
            if tool not in registry:
                v.append(
                    f"I-31: step_started for tool {tool!r} resolves "
                    f"nowhere in the dist registry")
    recorded = run.get("release_version")
    if dist_release_version is not None and recorded != dist_release_version:
        v.append(
            f"I-31: run's recorded release_version {recorded!r} does not "
            f"identify the loaded dist ({dist_release_version!r})")
    return v


def mint_disclosure(home: Path, kind: str, text: str) -> dict:
    """Mint a Disclosure into the drain outbox (<home>/var/disclosures/).

    The DR-5 seq discipline: seq is write-path-minted and monotonic, no
    clock enters the record. Shares the outbox's _seq file with the
    automaton's minting, so seqs stay monotonic across disclosure
    families (automaton-exception, updater-deferred).
    """
    ddir = Path(home) / "var" / "disclosures"
    ddir.mkdir(parents=True, exist_ok=True)
    seq_file = ddir / "_seq"
    f = open(seq_file, "a+b")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read().decode("utf-8").strip()
        seq = (int(raw) + 1) if raw else 1
        f.seek(0)
        f.truncate()
        f.write(str(seq).encode())
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()
    rec = {
        "id": f"dl-{seq:06d}",
        "seq": seq,
        "kind": kind,
        "text": text,
        "status": "open",
    }
    (ddir / f"dl-{seq:06d}.json").write_text(
        json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec


def payload_sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()
