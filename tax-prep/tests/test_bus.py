"""Tests for the git-backed broadcast message bus. All fixtures synthetic."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from taxprep import bus
from taxprep.bus import (
    default_tuning_path,
    list_messages,
    load_tuning,
    poll_once,
    publish,
    save_tuning,
    set_session_id,
    subscribe,
    subscribed_topics,
    topics,
    unsubscribe,
)

SESSION_A = "architect-a1b2c3"
SESSION_B = "workstation-9f2e11"


def git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=t@t.t", "-c", "user.name=t",
         "-c", "init.defaultBranch=main", *args],
        cwd=str(cwd), capture_output=True, text=True, check=True,
    )


@pytest.fixture()
def busdir(tmp_path):
    d = tmp_path / "bus"
    d.mkdir()
    return d


@pytest.fixture()
def tuning_path(tmp_path):
    return tmp_path / "tuning.toml"


# -- publish -----------------------------------------------------------


def test_publish_writes_valid_message(busdir, tuning_path):
    p = publish("tax-prep.build", "code-landed", {"commit": "abc123", "n_files": 4},
                SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    assert p.parent == busdir / "tax-prep.build"
    assert p.suffix == ".json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for field in ("id", "ts", "from", "topic", "type", "correlation_id", "payload"):
        assert field in data
    assert data["id"].startswith("msg_") and len(data["id"]) == 16
    assert data["from"] == SESSION_A
    assert data["topic"] == "tax-prep.build"
    assert data["payload"] == {"commit": "abc123", "n_files": 4}


def test_topic_validation(busdir, tuning_path):
    for bad in ["UPPER", "has space", "../evil", "", "a/b", "-lead", ".lead"]:
        with pytest.raises(ValueError, match="invalid topic"):
            publish(bad, "t", {}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    for good in ["a", "tax-prep.build", "x.y-z.2"]:
        publish(good, "t", {}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)


def test_pii_guard(busdir, tuning_path):
    with pytest.raises(ValueError, match="SSN"):
        publish("t", "x", {"note": "ssn 123-45-6789 here"}, SESSION_A,
                bus_dir=busdir, tuning_path=tuning_path)
    with pytest.raises(ValueError, match="EIN"):
        publish("t", "x", {"nested": {"ein": "12-3456789"}}, SESSION_A,
                bus_dir=busdir, tuning_path=tuning_path)
    # clean payload passes
    publish("t", "x", {"doc_id": "w2-acme-2024-0f7facdd", "n_fields": 10},
            SESSION_A, bus_dir=busdir, tuning_path=tuning_path)


def test_payload_must_be_json_dict(busdir, tuning_path):
    with pytest.raises(TypeError):
        publish("t", "x", ["not", "a", "dict"], SESSION_A,
                bus_dir=busdir, tuning_path=tuning_path)
    with pytest.raises(TypeError):
        publish("t", "x", {"bad": object()}, SESSION_A,
                bus_dir=busdir, tuning_path=tuning_path)


def test_torn_write_is_skipped(busdir, tuning_path):
    publish("t", "x", {"ok": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    (busdir / "t" / "garbage.json").write_text("{not json", encoding="utf-8")
    msgs = list_messages("t", bus_dir=busdir)
    assert len(msgs) == 1 and msgs[0]["payload"] == {"ok": 1}


# -- list / ordering ----------------------------------------------------


def test_list_messages_ordering_and_since_id(busdir, tuning_path):
    for i in range(3):
        publish("t", "x", {"n": i}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    msgs = list_messages("t", bus_dir=busdir)
    assert len(msgs) == 3
    assert [m["ts"] for m in msgs] == sorted(m["ts"] for m in msgs)
    # strictly newer than the first
    rest = list_messages("t", since_id=msgs[0]["id"], bus_dir=busdir)
    assert [m["id"] for m in rest] == [m["id"] for m in msgs[1:]]
    # unknown cursor -> catch up (everything)
    assert len(list_messages("t", since_id="msg_deadbeef00", bus_dir=busdir)) == 3


def test_topics(busdir, tuning_path):
    assert topics(bus_dir=busdir) == []
    publish("tax-prep.build", "x", {}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    publish("tax-prep.ops", "x", {}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    (busdir / "NOT A TOPIC").mkdir()
    assert topics(bus_dir=busdir) == ["tax-prep.build", "tax-prep.ops"]


# -- poll / cursor ------------------------------------------------------


def test_poll_once_cursor(tmp_path, busdir, tuning_path):
    cursor = tmp_path / "cursor.json"
    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    first = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor, do_pull=False, tuning_path=tuning_path)
    assert len(first) == 1
    sid = load_tuning(tuning_path)["session"]["id"]
    assert json.loads(cursor.read_text())["sessions"][sid]["t"] == first[0]["id"]
    publish("t", "x", {"n": 2}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    second = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor, do_pull=False, tuning_path=tuning_path)
    assert [m["payload"]["n"] for m in second] == [2]
    third = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor, do_pull=False, tuning_path=tuning_path)
    assert third == []


def test_poll_once_pull_failure_warns(tmp_path, busdir, tuning_path):
    # tmp_path is not a git repo -> pull fails, warning recorded, no crash
    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    cursor = tmp_path / "cursor.json"
    result = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor, do_pull=True, tuning_path=tuning_path)
    assert len(result) == 1  # local messages still readable
    assert result.warnings and "git pull" in result.warnings[0]


def test_broadcast_end_to_end_git(tmp_path, tuning_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    a = tmp_path / "A"
    subprocess.run(["git", "clone", str(origin), str(a)],
                   capture_output=True, check=True)
    git("commit", "--allow-empty", "-m", "seed", cwd=a)
    git("push", "-u", "origin", "HEAD:main", cwd=a)
    b = tmp_path / "B"
    subprocess.run(["git", "clone", str(origin), str(b)],
                   capture_output=True, check=True)

    bus_a = a / "bus"
    publish("tax-prep.build", "code-landed", {"commit": "deadbee", "n_files": 7},
            SESSION_A, bus_dir=bus_a, tuning_path=tuning_path)
    git("add", "bus", cwd=a)
    git("commit", "-m", "bus: code-landed", cwd=a)
    git("push", cwd=a)

    bus_b = b / "bus"
    cursor = tmp_path / "cursor.json"
    got = poll_once("tax-prep.build", b, bus_dir=bus_b, cursor_path=cursor, do_pull=True, tuning_path=tuning_path)
    assert not got.warnings, got.warnings
    assert len(got) == 1
    assert got[0]["payload"] == {"commit": "deadbee", "n_files": 7}
    assert got[0]["from"] == SESSION_A
    # second poll: cursor advanced, nothing new
    again = poll_once("tax-prep.build", b, bus_dir=bus_b, cursor_path=cursor, do_pull=True, tuning_path=tuning_path)
    assert again == []


# -- tuning (local-only) -------------------------------------------------


def test_tuning_save_load_roundtrip(tuning_path):
    t = load_tuning(tuning_path)
    t["session"]["id"] = "workstation-a1b2c3"
    t["tuning"]["topics"] = ["tax-prep.build"]
    t["tuning"]["poll_interval_seconds"] = 10
    save_tuning(t, tuning_path)
    back = load_tuning(tuning_path)
    assert back["session"]["id"] == "workstation-a1b2c3"
    assert back["tuning"]["topics"] == ["tax-prep.build"]
    assert back["tuning"]["poll_interval_seconds"] == 10


def test_tuning_defaults_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TAXPREP_SESSION_ID", "workstation")
    t = load_tuning(tmp_path / "nope.toml")
    assert t["session"]["id"] == "workstation"
    assert t["tuning"]["topics"] == ["*"]
    assert t["tuning"]["poll_interval_seconds"] == 30


def test_tuning_defaults_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    t = load_tuning(tmp_path / "nope.toml")
    assert t["session"]["id"] == ""


def test_subscribe_unsubscribe(tuning_path):
    subscribe("tax-prep.build", tuning_path)
    # subscribing while tuned to '*' is a no-op (already everything)
    assert load_tuning(tuning_path)["tuning"]["topics"] == ["*"]
    unsubscribe("tax-prep.ops", tuning_path)
    # '*' expanded to explicit list on first narrow
    assert load_tuning(tuning_path)["tuning"]["topics"] == []
    subscribe("tax-prep.build", tuning_path)
    subscribe("tax-prep.ops", tuning_path)
    assert load_tuning(tuning_path)["tuning"]["topics"] == [
        "tax-prep.build", "tax-prep.ops"]
    unsubscribe("tax-prep.build", tuning_path)
    assert load_tuning(tuning_path)["tuning"]["topics"] == ["tax-prep.ops"]


def test_subscribe_rejects_bad_topic(tuning_path):
    with pytest.raises(ValueError, match="invalid topic"):
        subscribe("BAD TOPIC", tuning_path)


def test_set_session_id(tuning_path):
    set_session_id("human-00ff11", tuning_path)
    assert load_tuning(tuning_path)["session"]["id"] == "human-00ff11"


def test_default_tuning_path_xdg(tmp_path, monkeypatch):
    cfg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    repo = tmp_path / "repo"
    repo.mkdir()
    p = default_tuning_path()
    assert p == cfg / "taxprep" / "bus.toml"
    assert repo not in p.parents  # never inside a repo


def test_subscribed_topics_star_resolution(busdir, tuning_path):
    publish("tax-prep.build", "x", {}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    tuning = load_tuning(tuning_path)  # topics == ["*"]
    assert subscribed_topics(tuning, bus_dir=busdir) == ["tax-prep.build"]
    tuning["tuning"]["topics"] = ["tax-prep.ops"]
    assert subscribed_topics(tuning, bus_dir=busdir) == ["tax-prep.ops"]


# -- session identity / echo filtering ------------------------------------


def test_exclude_from_filters_own_messages(busdir, tuning_path):
    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    publish("t", "x", {"n": 2}, SESSION_B, bus_dir=busdir, tuning_path=tuning_path)
    assert [m["from"] for m in list_messages("t", bus_dir=busdir)] == [SESSION_A, SESSION_B]
    only_b = list_messages("t", bus_dir=busdir, exclude_from=SESSION_A)
    assert [m["from"] for m in only_b] == [SESSION_B]


def test_publish_defaults_from_id_from_tuning(tmp_path, monkeypatch):
    monkeypatch.setenv("TAXPREP_SESSION_ID", "workstation")
    tp = tmp_path / "tuning.toml"
    busd = tmp_path / "bus"
    p = publish("t", "x", {"n": 1}, bus_dir=busd, tuning_path=tp)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert re.fullmatch(r"workstation-[0-9a-f]{6}", data["from"])
    # persisted in the tuning file
    assert load_tuning(tp)["session"]["id"] == data["from"]
    # second publish reuses the persisted id
    p2 = publish("t", "x", {"n": 2}, bus_dir=busd, tuning_path=tp)
    assert json.loads(p2.read_text(encoding="utf-8"))["from"] == data["from"]


def test_publish_generates_session_id_when_none(tmp_path, monkeypatch):
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    tp = tmp_path / "tuning.toml"
    p = publish("t", "x", {}, bus_dir=tmp_path / "bus", tuning_path=tp)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert re.fullmatch(r"session-[0-9a-f]{6}", data["from"])
    assert load_tuning(tp)["session"]["id"] == data["from"]


def test_poll_once_exclude_from(tmp_path, busdir, tuning_path):
    cursor = tmp_path / "cursor.json"
    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    publish("t", "x", {"n": 2}, SESSION_B, bus_dir=busdir, tuning_path=tuning_path)
    got = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                    do_pull=False, exclude_from=SESSION_A, tuning_path=tuning_path)
    assert [m["from"] for m in got] == [SESSION_B]
    # cursor advanced past the delivered message only, in this session's section
    sid = load_tuning(tuning_path)["session"]["id"]
    assert json.loads(cursor.read_text(encoding="utf-8"))["sessions"][sid]["t"] == got[0]["id"]
    # no more non-excluded messages
    assert poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                     do_pull=False, exclude_from=SESSION_A, tuning_path=tuning_path) == []


def test_two_sessions_independent_cursor_positions(tmp_path, busdir):
    """N listeners on one machine: each sees every broadcast, independent
    positions -- one session's cursor advancing never starves the other."""
    from taxprep.bus import set_session_id

    tp_a = tmp_path / "tuning_a.toml"
    tp_b = tmp_path / "tuning_b.toml"
    set_session_id("alpha-aaaaaa", tp_a)
    set_session_id("beta-bbbbbb", tp_b)
    cursor = tmp_path / "cursor.json"

    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tp_a)
    publish("t", "x", {"n": 2}, SESSION_A, bus_dir=busdir, tuning_path=tp_a)

    # alpha reads both messages; beta has not polled yet
    got_a = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                      do_pull=False, tuning_path=tp_a)
    assert [m["payload"]["n"] for m in got_a] == [1, 2]

    # beta still receives the FULL set -- alpha's advance didn't starve it
    got_b = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                      do_pull=False, tuning_path=tp_b)
    assert [m["payload"]["n"] for m in got_b] == [1, 2]

    # cursor file holds both sessions' independent positions
    data = json.loads(cursor.read_text(encoding="utf-8"))
    assert set(data["sessions"]) == {"alpha-aaaaaa", "beta-bbbbbb"}
    assert data["sessions"]["alpha-aaaaaa"]["t"] == got_a[-1]["id"]
    assert data["sessions"]["beta-bbbbbb"]["t"] == got_b[-1]["id"]

    # a third message arrives: both sessions see it on next poll
    publish("t", "x", {"n": 3}, SESSION_A, bus_dir=busdir, tuning_path=tp_a)
    again_a = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                        do_pull=False, tuning_path=tp_a)
    again_b = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                        do_pull=False, tuning_path=tp_b)
    assert [m["payload"]["n"] for m in again_a] == [3]
    assert [m["payload"]["n"] for m in again_b] == [3]


def test_legacy_flat_cursor_starts_at_beginning(tmp_path, busdir, tuning_path):
    """A pre-hardening flat cursor file (no 'sessions' key) is treated as
    unknown: the session catches up from the beginning."""
    cursor = tmp_path / "cursor.json"
    cursor.write_text(json.dumps({"t": "msg_legacy0000"}), encoding="utf-8")
    publish("t", "x", {"n": 1}, SESSION_A, bus_dir=busdir, tuning_path=tuning_path)
    got = poll_once("t", tmp_path, bus_dir=busdir, cursor_path=cursor,
                    do_pull=False, tuning_path=tuning_path)
    assert [m["payload"]["n"] for m in got] == [1]
    # and the file is rewritten in the new session-keyed format
    data = json.loads(cursor.read_text(encoding="utf-8"))
    assert "sessions" in data
