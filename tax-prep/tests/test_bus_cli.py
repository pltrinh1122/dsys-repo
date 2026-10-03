"""Tests for the taxprep bus/config/relevance/gaps CLI surface.

All fixtures synthetic. Env-isolated: XDG_CONFIG_HOME, TAXPREP_BUS_DIR,
TAXPREP_DATA_DIR, TAXPREP_SOURCE_DIR point at tmp dirs so nothing
touches the real home or repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from taxprep import bus as bus_mod
from taxprep.cli import main
from taxprep.models import Document
from taxprep.store import DocumentStore


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    cfg = tmp_path / "xdg"
    busd = tmp_path / "bus"
    datad = tmp_path / "data"
    srcd = tmp_path / "src"
    srcd.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("TAXPREP_BUS_DIR", str(busd))
    monkeypatch.setenv("TAXPREP_DATA_DIR", str(datad))
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    monkeypatch.delenv("TAXPREP_SOURCE_DIR", raising=False)
    return {"cfg": cfg, "bus": busd, "data": datad, "src": srcd}


def _run(*argv):
    return main(list(argv))


# -- bus publish / topics / listen ----------------------------------------


def test_bus_publish_and_topics(iso, capsys):
    assert _run("bus", "publish", "--topic", "tax-prep.build",
                "--type", "code-landed",
                "--payload", '{"commit": "abc", "n_files": 2}') == 0
    out = capsys.readouterr().out
    path = Path(out.splitlines()[0])
    assert path.is_file() and path.parent.name == "tax-prep.build"
    assert "commit + push" in out  # broadcast reminder printed

    assert _run("bus", "topics") == 0
    assert capsys.readouterr().out.strip() == "tax-prep.build"


def test_bus_publish_refuses_pii_payload(iso, capsys):
    rc = _run("bus", "publish", "--topic", "t", "--type", "x",
              "--payload", '{"note": "ssn 123-45-6789"}')
    assert rc == 2
    assert "refused" in capsys.readouterr().err


def test_bus_publish_bad_json(iso, capsys):
    assert _run("bus", "publish", "--topic", "t", "--type", "x",
                "--payload", "{nope") == 2


def test_bus_listen_once_prints_json_lines(iso, capsys):
    # another session's message (echo filter would drop our own)
    bus_mod.publish("tax-prep.ops", "run-done", {"n_docs": 3},
                    from_id="workstation-abcdef",
                    bus_dir=iso["bus"],
                    tuning_path=iso["cfg"] / "taxprep" / "bus.toml")
    assert _run("bus", "listen", "--once", "--timeout", "5") == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    msg = json.loads(lines[0])
    assert msg["from"] == "workstation-abcdef"
    assert msg["payload"] == {"n_docs": 3}
    # second --once: cursor advanced, nothing new
    assert _run("bus", "listen", "--once", "--timeout", "5") == 0
    assert capsys.readouterr().out.strip() == ""


def test_bus_listen_excludes_own_by_default(iso, capsys):
    _run("bus", "publish", "--topic", "t", "--type", "x",
         "--payload", '{"n": 1}')
    capsys.readouterr()  # drain
    assert _run("bus", "listen", "--once", "--timeout", "5",
                "--topic", "t") == 0
    assert capsys.readouterr().out.strip() == ""  # own echo tuned out
    # ...unless asked
    assert _run("bus", "listen", "--once", "--timeout", "5",
                "--topic", "t", "--include-own") == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


def test_bus_listen_no_topics(iso, capsys):
    # empty bus dir -> '*' resolves to nothing
    assert _run("bus", "listen", "--once") == 1
    assert "no topics" in capsys.readouterr().err


# -- bus tune / whoami ------------------------------------------------------


def test_bus_tune_and_whoami(iso, capsys):
    assert _run("bus", "tune", "--topic", "tax-prep.build") == 0
    assert _run("bus", "tune", "--topic", "tax-prep.ops") == 0
    # tuned to '*' still (subscribe is a no-op) -- narrow explicitly
    assert _run("bus", "tune", "--topic", "tax-prep.build", "--off") == 0
    out = capsys.readouterr().out
    assert "tax-prep.ops" in out and "tax-prep.build" not in out.splitlines()[-1]

    assert _run("bus", "whoami") == 0
    out = capsys.readouterr().out
    assert "session_id:" in out and "subscribed:" in out
    assert "bus_dir:" in out and "tuning:" in out and "cursor:" in out
    assert "store_dir:" in out and "dsys-store" in out
    assert str(iso["bus"]) in out


def test_bus_publish_via_store_dir(tmp_path, monkeypatch, capsys):
    # TAXPREP_BUS_DIR unset: the bus accretes to the dsys-store checkout.
    import subprocess
    store = tmp_path / "dsys-store"
    store.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(store)],
                   capture_output=True, check=True)
    cfg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.delenv("TAXPREP_BUS_DIR", raising=False)
    monkeypatch.setenv("TAXPREP_STORE_DIR", str(store))
    monkeypatch.delenv("TAXPREP_SESSION_ID", raising=False)
    assert _run("bus", "publish", "--topic", "tax-prep.ops",
                "--type", "run-done",
                "--payload", '{"n_docs": 1}') == 0
    out = capsys.readouterr().out
    assert "dsys-store" in out  # broadcast reminder names the store repo
    assert (store / "bus" / "tax-prep.ops").is_dir()
    # nothing landed in the code repo
    assert not (Path(__file__).resolve().parent.parent / "bus" / "tax-prep.ops").exists()

    assert _run("bus", "whoami") == 0
    assert f"store_dir:   {store}" in capsys.readouterr().out


def test_bus_publish_missing_store_errors(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.delenv("TAXPREP_BUS_DIR", raising=False)
    monkeypatch.setenv("TAXPREP_STORE_DIR", str(tmp_path / "no-store"))
    rc = _run("bus", "publish", "--topic", "t", "--type", "x",
              "--payload", '{"a": 1}')
    assert rc == 2
    err = capsys.readouterr().err
    assert "git clone https://github.com/pltrinh1122/dsys-store" in err


# -- config ------------------------------------------------------------------


def test_config_set_show_and_ingest_default(iso, capsys, monkeypatch):
    assert _run("config", "set", "source_dir", str(iso["src"])) == 0
    assert (iso["cfg"] / "taxprep" / "config.toml").is_file()
    assert _run("config", "show") == 0
    out = capsys.readouterr().out
    assert f"source_dir   = {iso['src']}" in out
    assert "never committed" in out

    # ingest with no positional uses the configured source_dir
    (iso["src"] / "note.txt").write_text("hello\n", encoding="utf-8")
    assert _run("ingest") == 0
    assert "Ingested" in capsys.readouterr().out


def test_config_set_bad_key(iso, capsys):
    assert _run("config", "set", "nope", "x") == 2
    assert "unknown config key" in capsys.readouterr().err


def test_config_set_scope_years(iso, capsys):
    assert _run("config", "set", "scope_years", "2024,2025") == 0
    assert _run("config", "show") == 0
    assert "scope_years  = [2024, 2025]" in capsys.readouterr().out


def test_config_set_store_dir(iso, capsys):
    assert _run("config", "set", "store_dir", "/tmp/somewhere-store") == 0
    assert _run("config", "show") == 0
    assert "store_dir    = /tmp/somewhere-store" in capsys.readouterr().out


def test_ingest_no_source_dir_errors(iso, capsys):
    assert _run("ingest") == 2
    assert "config set source_dir" in capsys.readouterr().err


def test_env_overrides_config_file(iso, capsys, monkeypatch):
    _run("config", "set", "source_dir", str(iso["src"]))
    other = iso["src"] / "other"
    other.mkdir()
    monkeypatch.setenv("TAXPREP_SOURCE_DIR", str(other))
    (other / "f.txt").write_text("x\n", encoding="utf-8")
    assert _run("ingest") == 0
    assert str(other) in capsys.readouterr().out


# -- relevance / gaps CLI ------------------------------------------------------


def _seed(store_dir):
    s = DocumentStore(store_dir)
    d = Document(doc_id="w1", tax_year=2024, form_type="W-2",
                 source_path="w1.pdf", ocr_text_ref="ocr/w1.txt",
                 fields={}, status="transcribed")
    s.save_ocr("w1", "w2 text")
    s.upsert(d)
    u = Document(doc_id="myst", tax_year=2024, form_type="UNKNOWN",
                 source_path="m.pdf", ocr_text_ref="ocr/myst.txt",
                 fields={}, status="needs_review")
    s.save_ocr("myst", "mystery")
    s.upsert(u)
    return s


def test_relevance_cli_persists_and_prints(iso, capsys):
    _seed(iso["data"])
    assert _run("relevance") == 0
    out = capsys.readouterr().out
    assert "relevant     1" in out
    assert "needs_human" in out and "myst" in out
    # persisted into the store
    assert DocumentStore(iso["data"]).get("w1").relevance == "relevant"


def test_relevance_cli_year_filter(iso, capsys):
    _seed(iso["data"])
    assert _run("relevance", "--year", "2024") == 0
    assert "year=2024" in capsys.readouterr().out


def test_gaps_cli_shape_and_report(iso, capsys):
    _seed(iso["data"])
    assert _run("gaps", "--year", "2024") == 0
    out = capsys.readouterr().out
    assert "2024:" in out and "no transcript" in out
    assert "operator's eyes only" in out
    report = Path(out.strip().splitlines()[-1].split(": ", 1)[1])
    assert report.is_file()
