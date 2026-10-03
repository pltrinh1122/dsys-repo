"""Tests for config.py: data_dir is REQUIRED (N1), fail closed.

No built-in default, no package-relative fallback. Resolution order
--data-dir flag > TAXPREP_DATA_DIR env > config.toml data_dir > hard
error naming `taxprep config set data_dir <path>`. Paths inside
site-packages are refused at every source. All fixtures synthetic.
"""

import os
import sysconfig
from pathlib import Path

import pytest

from taxprep import config


@pytest.fixture()
def xdg(tmp_path, monkeypatch):
    cfg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    for var in ("TAXPREP_DATA_DIR", "TAXPREP_SOURCE_DIR",
                "TAXPREP_SCOPE_YEARS", "TAXPREP_STORE_DIR"):
        monkeypatch.delenv(var, raising=False)
    return cfg


def test_data_dir_required_names_setup_command(xdg):
    with pytest.raises(ValueError, match=r"taxprep config set data_dir"):
        config.resolve("data_dir")


def test_data_dir_precedence_flag_env_file(xdg, monkeypatch, tmp_path):
    flag, env, filev = (tmp_path / n for n in ("flag", "env", "file"))
    config.set_value("data_dir", str(filev))
    assert config.resolve("data_dir") == str(filev)          # file
    monkeypatch.setenv("TAXPREP_DATA_DIR", str(env))
    assert config.resolve("data_dir") == str(env)           # env > file
    assert config.resolve("data_dir", cli_value=str(flag)) == str(flag)  # flag wins


def test_data_dir_env_tilde_expanded(xdg, monkeypatch):
    monkeypatch.setenv("TAXPREP_DATA_DIR", "~/taxprep-data")
    assert config.resolve("data_dir") == os.path.expanduser("~/taxprep-data")


def _site_packages_probe() -> Path:
    return Path(sysconfig.get_paths()["purelib"]) / "taxprep-data-probe"


def test_data_dir_inside_site_packages_refused_everywhere(xdg, monkeypatch):
    sp = str(_site_packages_probe())
    # env var source
    monkeypatch.setenv("TAXPREP_DATA_DIR", sp)
    with pytest.raises(ValueError, match="site-packages"):
        config.resolve("data_dir")
    # CLI flag source
    with pytest.raises(ValueError, match="site-packages"):
        config.resolve("data_dir", cli_value=sp)
    # config set (fail fast at write time)
    with pytest.raises(ValueError, match="site-packages"):
        config.set_value("data_dir", sp)


def test_data_dir_set_value_roundtrip(xdg, tmp_path):
    p = config.set_value("data_dir", str(tmp_path / "mydata"))
    assert p == config.default_config_path()
    assert config.resolve("data_dir") == str(tmp_path / "mydata")


def test_no_package_default_constant():
    assert not hasattr(config, "PACKAGE_DEFAULT_DATA_DIR")


def test_other_keys_unaffected(xdg):
    assert config.resolve("scope_years") == [2023, 2024, 2025, 2026]
    assert config.resolve("source_dir") is None
    assert config.resolve("store_dir").endswith("dsys-store")
