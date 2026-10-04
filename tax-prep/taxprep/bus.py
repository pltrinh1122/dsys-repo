"""Git-backed broadcast message bus for multi-session collaboration.

Transport is a SEPARATE git repo, dsys-store
(github.com/pltrinh1122/dsys-store): publishing writes a JSON file
under ``<store>/bus/<topic>/``, broadcasting is commit + push of the
store repo, listening is ``git pull`` + read. Poll-scale latency (tens
of seconds) fits build notifications and discrepancy reports.

Two-repo topology: dsys-repo is software (code, specs, tests); dsys-store
is the append-only accretion medium for broadcast messages. The code repo
never carries message files.

Broadcast model: listeners tune in by topic. Topic names are
lowercase alphanumerics, dots and dashes only.

Well-known topics (free-form otherwise):
    tax-prep.build    architect -> workstation/human: code landed, pull and re-run
    tax-prep.ops      workstation -> architect/human: run completions, discrepancy shapes
    tax-prep.review   human -> all: decisions / approvals

PII RULE (hard): payloads are shapes only -- ids, counts, enums,
status strings. Never values, names, EINs, SSNs, dollar amounts.
``publish`` refuses payloads matching SSN/EIN, unhyphenated 9-digit
run, masked-SSN, long-digit-run, and currency-amount patterns. The
blind-orchestrator contract holds end to end: no listening session
ever sees PII in its context.

SESSION IDENTITY: every message carries a unique per-session-instance
id in ``from``: ``<role>-<6 hex>`` (e.g. ``workstation-a1b2c3``).
``publish`` defaults ``from_id`` to the tuned session id from the
local tuning config, generating and persisting one (role from
TAXPREP_SESSION_ID env, else "session") when none exists yet.
Listeners tune OUT their own broadcasts: pass your own session id as
``exclude_from`` to ``list_messages``/``poll_once`` so a session never
hears its own echo. (The later ``taxprep bus listen`` wiring will
default this to the tuned session id with an opt-out flag.)

LOCAL-ONLY STATE: per-session tuning (session id, which topics a
session listens to, poll interval) lives in
``~/.config/taxprep/bus.toml`` (``XDG_CONFIG_HOME`` respected) and
the listen cursor in ``~/.config/taxprep/bus_cursor.json``. The cursor
file is keyed by session id inside -- ``{"sessions": {sid: {topic:
last_msg_id}}}`` -- so N listeners on one machine each keep an
independent position. Neither file is ever committed -- the store repo
carries messages, never listener state.

On a new machine, clone the store repo first::

    git clone https://github.com/pltrinh1122/dsys-store ~/workspace/dsys-store

then ``taxprep bus whoami`` to confirm the resolved store dir.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

# -- topic validation ------------------------------------------------

_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")


def _check_topic(topic: str) -> str:
    if not isinstance(topic, str) or not _TOPIC_RE.match(topic):
        raise ValueError(
            f"invalid topic {topic!r}: lowercase alphanumerics, dots and "
            "dashes only, must start with an alphanumeric"
        )
    return topic


# -- PII guard --------------------------------------------------------

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EIN_RE = re.compile(r"\b\d{2}-\d{7}\b")
# N3: the guard used to catch only hyphenated SSN/EIN. Extend it:
#  - \b\d{8}\b             8-digit runs (brokerage/bank account numbers)
#  - \b\d{9}\b            unhyphenated 9-digit runs (SSN without dashes)
#  - XXX-XX-\d{4}         masked SSNs, any case (XXX, xxx, Xxx, ...)
#  - \b\d{10,}\b          long digit runs (account / lot numbers)
#  - \$[\d,]*\.\d{2}      currency amounts ($85,000.00)
# Legitimate shapes still pass: 4-digit years, small counts, enum
# strings, doc_ids, commit SHAs -- none match the patterns above.
_ACCT_8_RE = re.compile(r"\b\d{8}\b")
_PLAIN_9_RE = re.compile(r"\b\d{9}\b")
_MASKED_SSN_RE = re.compile(r"\b[xX]{3}-[xX]{2}-\d{4}\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{10,}\b")
_CURRENCY_RE = re.compile(r"\$[\d,]*\.\d{2}")


def _check_no_pii(serialized: str) -> None:
    if _SSN_RE.search(serialized):
        raise ValueError(
            "payload refused: matches SSN pattern (\\d{3}-\\d{2}-\\d{4}); "
            "the bus carries shapes only, never PII"
        )
    if _EIN_RE.search(serialized):
        raise ValueError(
            "payload refused: matches EIN pattern (\\d{2}-\\d{7}); "
            "the bus carries shapes only, never PII"
        )
    if _MASKED_SSN_RE.search(serialized):
        raise ValueError(
            "payload refused: matches masked-SSN pattern (XXX-XX-\\d{4}); "
            "the bus carries shapes only, never PII"
        )
    if _ACCT_8_RE.search(serialized):
        raise ValueError(
            "payload refused: matches 8-digit run (account number?); "
            "the bus carries shapes only, never PII"
        )
    if _PLAIN_9_RE.search(serialized):
        raise ValueError(
            "payload refused: matches 9-digit run (unhyphenated SSN?); "
            "the bus carries shapes only, never PII"
        )
    if _LONG_DIGITS_RE.search(serialized):
        raise ValueError(
            "payload refused: matches long digit run (account/lot number?); "
            "the bus carries shapes only, never PII"
        )
    if _CURRENCY_RE.search(serialized):
        raise ValueError(
            "payload refused: matches currency amount ($N.NN); "
            "the bus carries shapes only, never PII"
        )


# -- path resolution ---------------------------------------------------

_STORE_CLONE_HINT = "git clone https://github.com/pltrinh1122/dsys-store"


def _default_store_dir() -> Path:
    return Path.home() / "workspace" / "dsys-store"


def resolve_store_dir(store_dir: str | Path | None = None) -> Path:
    """Resolve the dsys-store checkout location (no existence check).

    store_dir param > TAXPREP_STORE_DIR env > config.toml ``store_dir`` >
    ``~/workspace/dsys-store``.
    """
    if store_dir is not None:
        return Path(store_dir)
    env = os.environ.get("TAXPREP_STORE_DIR")
    if env:
        return Path(env)
    try:
        from . import config as config_mod

        file_value = config_mod.load_file().get("store_dir")
    except Exception:
        file_value = None
    if file_value:
        return Path(os.path.expanduser(str(file_value)))
    return _default_store_dir()


def _require_store_checkout(store_dir: str | Path | None = None) -> Path:
    """Resolve the store dir and require it to be a git checkout.

    Raises FileNotFoundError (missing) or ValueError (not a git
    checkout), both naming the expected clone command.
    """
    d = resolve_store_dir(store_dir)
    if not d.is_dir():
        raise FileNotFoundError(
            f"dsys-store checkout not found at {d}; clone it with:\n"
            f"  {_STORE_CLONE_HINT} {d}"
        )
    if not (d / ".git").is_dir():
        raise ValueError(
            f"{d} exists but is not a git checkout; the bus accretes to "
            f"dsys-store -- clone it with:\n  {_STORE_CLONE_HINT} {d}"
        )
    return d


def resolve_bus_dir(
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
) -> Path:
    """Resolve the bus directory.

    Resolution order: explicit bus_dir param > TAXPREP_BUS_DIR env >
    ``<dsys-store>/bus`` (the store checkout is required to exist and
    be a git checkout -- see _require_store_checkout). Writes never
    escape the resolved dir.
    """
    if bus_dir is not None:
        return Path(bus_dir)
    env = os.environ.get("TAXPREP_BUS_DIR")
    if env:
        return Path(env)
    return _require_store_checkout(store_dir) / "bus"


def resolve_pull_target(
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
) -> Path | None:
    """Git checkout to ``git pull`` when listening, or None for local-only.

    Store-derived bus dirs pull the store checkout itself; an
    explicitly-provided bus dir (param or TAXPREP_BUS_DIR) pulls its
    enclosing git root, or None when there is none.
    """
    explicit = bus_dir is not None or os.environ.get("TAXPREP_BUS_DIR")
    if not explicit:
        return _require_store_checkout(store_dir)
    root = resolve_bus_dir(bus_dir, store_dir)
    for parent in [root, *root.parents]:
        if (parent / ".git").is_dir():
            return parent
    return None


def _config_dir() -> Path:
    """Local-only config dir. Never inside the git repo."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "taxprep"


def default_cursor_path() -> Path:
    return _config_dir() / "bus_cursor.json"


def default_tuning_path() -> Path:
    return _config_dir() / "bus.toml"


# -- publish / list ----------------------------------------------------

_SESSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*-[0-9a-f]{6}$")


def _sanitize_role(role: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "", role.strip().lower())
    return cleaned or "session"


def _default_session_id(tuning_path: str | Path | None = None) -> str:
    """Tuned session id, generating (<role>-<6 hex>) and persisting it first.

    A tuned id is reused only if it already has the <role>-<6 hex>
    shape; a bare TAXPREP_SESSION_ID value is treated as the *role*,
    not the id.
    """
    tuning = load_tuning(tuning_path)
    sid = tuning.get("session", {}).get("id", "")
    if sid and _SESSION_ID_RE.match(sid):
        return sid
    role = _sanitize_role(sid or os.environ.get("TAXPREP_SESSION_ID", ""))
    new_id = f"{role}-{secrets.token_hex(3)}"
    set_session_id(new_id, tuning_path)
    return new_id

_REQUIRED_FIELDS = ("id", "ts", "from", "topic", "type", "payload")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def publish(
    topic: str,
    msg_type: str,
    payload: dict,
    from_id: str | None = None,
    correlation_id: str | None = None,
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    tuning_path: str | Path | None = None,
) -> Path:
    """Write one message file to the bus. Returns the file path.

    Payload must be a JSON-serializable dict (TypeError otherwise) and
    must not match SSN/EIN patterns (ValueError otherwise).

    ``from_id`` defaults to the tuned session id from the local tuning
    config; when the config has no session id yet, one is generated
    (``<role>-<6 hex>``, role from TAXPREP_SESSION_ID env else
    "session") and persisted via the tuning save path. NOTE: this makes
    publish write the tuning file on first use.
    """
    _check_topic(topic)
    if from_id is None:
        from_id = _default_session_id(tuning_path)
    if not isinstance(from_id, str) or not from_id:
        raise ValueError("from_id must be a non-empty string")
    if not isinstance(msg_type, str) or not msg_type:
        raise ValueError("msg_type must be a non-empty string")
    if not isinstance(payload, dict):
        raise TypeError(
            f"payload must be a dict, got {type(payload).__name__}"
        )
    try:
        serialized = json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"payload is not JSON-serializable: {exc}") from exc
    _check_no_pii(serialized)

    now = _utc_now()
    msg_id = f"msg_{secrets.token_hex(6)}"
    message = {
        "id": msg_id,
        "ts": now.isoformat(),
        "from": from_id,
        "topic": topic,
        "type": msg_type,
        "correlation_id": correlation_id,
        "payload": json.loads(serialized),
    }
    topic_dir = resolve_bus_dir(bus_dir, store_dir) / topic
    topic_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{now.strftime('%Y%m%dT%H%M%S%f')}-{msg_id}.json"
    path = topic_dir / fname
    # Never write outside the resolved bus dir (topic names cannot
    # contain '/', but belt-and-braces against traversal).
    if path.resolve().parent != topic_dir.resolve():
        raise ValueError(f"refusing to write outside bus dir: {path}")
    path.write_text(json.dumps(message, indent=2) + "\n", encoding="utf-8")
    return path


# Pending-addresses sidecar: lets an operator tag the NEXT code_landed
# broadcast with requirement IDs it addresses (e.g. ["X1", "D5"]) without
# editing a running push script. Written as {"head": <sha>, "addresses": [...]}
# and consumed only when the head matches the broadcast being published.
_PENDING_ADDRESSES_PATH = Path.home() / ".config" / "taxprep" / "code_landed_addresses.json"


def _pending_addresses(head: str) -> list | None:
    """Consume the pending-addresses sidecar if it targets this head."""
    try:
        raw = _PENDING_ADDRESSES_PATH.read_text()
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("head") != head:
        return None
    addrs = data.get("addresses")
    if not isinstance(addrs, list) or not all(isinstance(a, str) for a in addrs):
        return None
    try:
        _PENDING_ADDRESSES_PATH.unlink()
    except OSError:
        pass
    return addrs


def code_landed_payload(repo: str, branch: str, head: str,
                        n_commits: int, addresses: list | None = None) -> dict:
    """Payload for a tax-prep.build / code_landed broadcast.

    Exact key set: {"repo", "branch", "head", "commits_pushed", "action"}
    plus optional "addresses": requirement IDs this push addresses
    (workstation re-install gate protocol). Every value is a shape --
    nothing PII-shaped, so it always survives the publish-side PII
    guard. Used by scripts/push-and-broadcast.sh.

    addresses may also arrive via the TAXPREP_CODE_LANDED_ADDRESSES
    env var (comma-separated) or the pending-addresses sidecar file.
    """
    if addresses is None:
        env = os.environ.get("TAXPREP_CODE_LANDED_ADDRESSES", "")
        if env.strip():
            addresses = [a.strip() for a in env.split(",") if a.strip()]
    if addresses is None:
        addresses = _pending_addresses(head)
    payload = {
        "repo": repo,
        "branch": branch,
        "head": head,
        "commits_pushed": n_commits,
        "action": f"pull {branch} and re-run verify_all",
    }
    if addresses:
        payload["addresses"] = addresses
    return payload


def _read_message(path: Path) -> dict | None:
    """Parse one message file; None if invalid (torn write mid-pull)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if any(f not in data for f in _REQUIRED_FIELDS):
        return None
    return data


def list_messages(
    topic: str,
    since_id: str | None = None,
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    exclude_from: str | None = None,
) -> list[dict]:
    """All messages in a topic, sorted by (ts, id).

    ``since_id`` keeps strictly newer messages (unknown id -> everything,
    i.e. catch up). ``exclude_from`` skips messages whose ``from`` equals
    it -- listeners pass their own session id so a session never hears
    its own broadcast echo.
    """
    _check_topic(topic)
    topic_dir = resolve_bus_dir(bus_dir, store_dir) / topic
    paths: list = []
    if topic_dir.is_dir():
        paths = sorted(topic_dir.glob("*.json"))
    if since_id is not None:
        # Filename pre-filter: filenames embed the publish timestamp and
        # sort in the same order as (ts, id), so files at or before the
        # cursor's file are never even read -- the watermark avoids
        # re-reading, not just re-delivery. since_id is matched by suffix;
        # no path is ever constructed from it.
        cursor_names = [p.name for p in paths if p.name.endswith(f"-{since_id}.json")]
        if cursor_names:
            cutoff = cursor_names[0]
            paths = [p for p in paths if p.name > cutoff]
        # unknown cursor id -> read everything (catch up), as before
    messages: list[dict] = []
    for path in paths:
        msg = _read_message(path)
        if msg is not None:
            messages.append(msg)
    messages.sort(key=lambda m: (m["ts"], m["id"]))
    if exclude_from is not None:
        messages = [m for m in messages if m.get("from") != exclude_from]
    return messages


def topics(
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
) -> list[str]:
    """Topic names with at least one message file."""
    root = resolve_bus_dir(bus_dir, store_dir)
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and _TOPIC_RE.match(d.name)
    )


# -- listen ------------------------------------------------------------


class _PollResult(list):
    """list[dict] of new messages, with a .warnings list attached."""

    def __init__(self, messages: list[dict], warnings: list[str] | None = None):
        super().__init__(messages)
        self.warnings: list[str] = warnings or []


def _load_cursor(cursor_path: Path) -> dict:
    try:
        data = json.loads(cursor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cursor(cursor_path: Path, cursor: dict) -> None:
    # Atomic: tmp + fsync + os.replace (the D1 pattern). A crash mid-write
    # must never leave a torn cursor that forces a full-history re-delivery.
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cursor_path.with_name(cursor_path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(cursor, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, cursor_path)


def poll_once(
    topic: str,
    repo_dir: str | Path,
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    cursor_path: str | Path | None = None,
    do_pull: bool = True,
    exclude_from: str | None = None,
    tuning_path: str | Path | None = None,
) -> _PollResult:
    """Pull (unless do_pull=False), then return messages newer than the cursor.

    ``repo_dir`` is the dsys-store checkout (kept the param name to avoid
    churning callers): ``git pull --ff-only`` runs there.

    The cursor lives at cursor_path (default
    ~/.config/taxprep/bus_cursor.json, never committed) and is keyed by
    session id inside the file::

        {"sessions": {"<session-id>": {"<topic>": "<last-msg-id>"}}}

    so N listeners on one machine each hold an independent position and
    every broadcast reaches every listener. The active session id comes
    from the tuning config -- the same source ``publish`` uses, generating
    and persisting one on first use. A legacy flat-format cursor file
    (no "sessions" key) is treated as unknown: the session starts at the
    beginning (catch-up), same as today's unknown-cursor behavior. The
    cursor advances to the newest *delivered* message id; other sessions'
    sections are untouched. A failed ``git pull --ff-only`` records a
    warning in the result instead of crashing -- offline work still
    reads local messages.

    ``exclude_from`` skips messages whose ``from`` equals it (pass your
    own session id to tune out your own broadcast echo); excluded
    messages do not advance the cursor.
    """
    _check_topic(topic)
    warnings: list[str] = []
    if do_pull:
        try:
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=str(repo_dir),
                capture_output=True,
                timeout=60,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            warnings.append(f"git pull --ff-only failed in {repo_dir}: {exc}")

    session_id = _default_session_id(tuning_path)
    cpath = Path(cursor_path) if cursor_path is not None else default_cursor_path()
    raw = _load_cursor(cpath)
    sessions = raw.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
    mine = sessions.get(session_id)
    if not isinstance(mine, dict):
        mine = {}
    messages = list_messages(
        topic, since_id=mine.get(topic), bus_dir=bus_dir,
        store_dir=store_dir, exclude_from=exclude_from,
    )
    if messages:
        mine[topic] = messages[-1]["id"]
        sessions[session_id] = mine
        _save_cursor(cpath, {"sessions": sessions})
    return _PollResult(messages, warnings)


# -- per-session tuning (local-only, never committed) -------------------

_DEFAULT_TUNING = {
    "session": {"id": ""},
    "tuning": {"topics": ["*"], "poll_interval_seconds": 30},
    "paths": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_tuning(path: str | Path | None = None) -> dict:
    """Read tuning TOML; missing file -> defaults. Merges file over defaults."""
    p = Path(path) if path is not None else default_tuning_path()
    tuning = json.loads(json.dumps(_DEFAULT_TUNING))  # deep copy
    tuning["session"]["id"] = os.environ.get("TAXPREP_SESSION_ID", "")
    if not p.is_file():
        return tuning
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    if not isinstance(data, dict):
        return tuning
    return _deep_merge(tuning, data)


def _toml_str(value: str) -> str:
    # JSON string escaping is valid TOML basic-string escaping for our values.
    return json.dumps(value)


def _write_tuning_toml(tuning: dict, path: Path) -> None:
    session = tuning.get("session", {}) or {}
    tune = tuning.get("tuning", {}) or {}
    paths = tuning.get("paths", {}) or {}
    lines = ["[session]"]
    lines.append(f"id = {_toml_str(str(session.get('id', '')))}")
    lines.append("")
    lines.append("[tuning]")
    topics = tune.get("topics", ["*"])
    lines.append(
        "topics = [" + ", ".join(_toml_str(str(t)) for t in topics) + "]"
    )
    lines.append(f"poll_interval_seconds = {int(tune.get('poll_interval_seconds', 30))}")
    lines.append("")
    lines.append("[paths]")
    for key, value in paths.items():
        lines.append(f"{key} = {_toml_str(str(value))}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_tuning(tuning: dict, path: str | Path | None = None) -> Path:
    """Write tuning TOML, creating parent dirs. Returns the path."""
    p = Path(path) if path is not None else default_tuning_path()
    _write_tuning_toml(tuning, p)
    return p


def subscribe(topic: str, path: str | Path | None = None) -> dict:
    """Tune into a topic.

    N3: tuning into a topic while subscribed to "*" is no longer a
    silent no-op -- "*" is first expanded to the explicit topic list
    present in the bus dir (mirroring unsubscribe), then the topic is
    added, so the tune is visible and a later --off narrows it.
    """
    _check_topic(topic)
    tuning = load_tuning(path)
    topics_list = tuning["tuning"]["topics"]
    if topics_list == ["*"]:
        topics_list = subscribed_topics(tuning)  # explicit list from bus dir
    if topic not in topics_list:
        topics_list = sorted([*topics_list, topic])
    tuning["tuning"]["topics"] = topics_list
    save_tuning(tuning, path)
    return tuning


def unsubscribe(topic: str, path: str | Path | None = None) -> dict:
    """Tune out of a topic. '*' expands to the explicit bus topic list first."""
    _check_topic(topic)
    tuning = load_tuning(path)
    topics_list = tuning["tuning"]["topics"]
    if topics_list == ["*"]:
        try:
            explicit = topics()
        except (FileNotFoundError, ValueError):
            explicit = []
        topics_list = sorted(explicit)
    tuning["tuning"]["topics"] = [t for t in topics_list if t != topic]
    save_tuning(tuning, path)
    return tuning


def set_session_id(sid: str, path: str | Path | None = None) -> dict:
    tuning = load_tuning(path)
    tuning["session"]["id"] = sid
    save_tuning(tuning, path)
    return tuning


def subscribed_topics(
    tuning: dict,
    bus_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
) -> list[str]:
    """Resolve '*' against topics actually present in the bus dir."""
    topics_list = tuning.get("tuning", {}).get("topics", ["*"])
    if topics_list == ["*"]:
        try:
            return topics(bus_dir=bus_dir, store_dir=store_dir)
        except (FileNotFoundError, ValueError):
            return []
    return list(topics_list)
