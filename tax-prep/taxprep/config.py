"""Local workstation configuration (machine-local, never committed).

Resolution order for every key:
    CLI flag > environment variable > ~/.config/taxprep/config.toml
    (XDG_CONFIG_HOME respected) > built-in default.

Keys:
    source_dir   TAXPREP_SOURCE_DIR    default: None (set once via
                 `taxprep config set source_dir <dir>`)
    data_dir     TAXPREP_DATA_DIR      REQUIRED -- no built-in default.
                 Set once via `taxprep config set data_dir <dir>` (or the
                 env var / --data-dir flag). Resolution fails closed with
                 a hard error naming that command. Paths inside
                 site-packages are refused outright: taxpayer data must
                 never live inside the Python install.
    scope_years  TAXPREP_SCOPE_YEARS   default: 2023,2024,2025,2026
                 (comma-separated in env/file)
    store_dir    TAXPREP_STORE_DIR     default: ~/workspace/dsys-store
                 (the dsys-store git checkout the message bus accretes to)

The config file lives OUTSIDE the repo and must never be committed: it
holds machine-local paths. The repo is public; this file is not part of
it.
"""

from __future__ import annotations

import os
import sysconfig
import tomllib
from pathlib import Path

_KEYS = ("source_dir", "data_dir", "scope_years", "store_dir")
_ENV = {
    "source_dir": "TAXPREP_SOURCE_DIR",
    "data_dir": "TAXPREP_DATA_DIR",
    "scope_years": "TAXPREP_SCOPE_YEARS",
    "store_dir": "TAXPREP_STORE_DIR",
}
_DEFAULTS = {
    "source_dir": None,
    "scope_years": [2023, 2024, 2025, 2026],
    "store_dir": str(Path.home() / "workspace" / "dsys-store"),
}
# data_dir has NO default (N1): it must be configured explicitly.


def _site_package_roots() -> list[Path]:
    """Resolved purelib/platlib dirs. Best effort -- [] on odd installs."""
    roots: list[Path] = []
    try:
        paths = sysconfig.get_paths()
    except Exception:
        return []
    for key in ("purelib", "platlib"):
        p = paths.get(key)
        if not p:
            continue
        try:
            roots.append(Path(p).resolve())
        except OSError:
            continue
    return roots


def _checked_data_dir(raw: str) -> str:
    """Expand a data_dir value and refuse site-packages locations.

    Taxpayer data must never live inside the Python install (a source
    checkout resolves to tax-prep/data inside the git work tree; a
    normal install resolves inside the venv). Fail closed.
    """
    expanded = os.path.expanduser(raw)
    try:
        resolved = Path(expanded).resolve()
    except OSError:
        resolved = Path(expanded).absolute()
    for sp in _site_package_roots():
        if resolved == sp or sp in resolved.parents:
            raise ValueError(
                f"refusing data_dir inside the Python install ({resolved}): "
                "taxpayer data must live outside site-packages -- run "
                "`taxprep config set data_dir <path>` with a directory "
                "elsewhere"
            )
    return expanded


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "taxprep" / "config.toml"


def _parse_scope_years(raw: str) -> list[int]:
    years = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            years.append(int(part))
        except ValueError:
            raise ValueError(
                f"invalid scope_years entry {part!r}: expected comma-separated years"
            )
    if not years:
        raise ValueError("scope_years must name at least one year")
    return sorted(set(years))


def _coerce(key: str, raw: str):
    if key == "scope_years":
        return _parse_scope_years(raw)
    if key == "data_dir":
        return _checked_data_dir(raw)
    return os.path.expanduser(raw)


def load_file(path: str | Path | None = None) -> dict:
    """Read the TOML config file; missing file -> {}. Never raises."""
    p = Path(path) if path is not None else default_config_path()
    if not p.is_file():
        return {}
    try:
        with p.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def set_value(key: str, value: str, path: str | Path | None = None) -> Path:
    """Validate and persist one key. Returns the config file path."""
    if key not in _KEYS:
        raise ValueError(f"unknown config key {key!r}; expected one of {_KEYS}")
    coerced = _coerce(key, value)  # validates now, not later
    p = Path(path) if path is not None else default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_file(p)
    if key == "scope_years":
        data[key] = ",".join(str(y) for y in coerced)
    else:
        data[key] = value
    lines = [f"{k} = {d!r}" for k, d in data.items() if k in _KEYS]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def resolve(key: str, cli_value=None):
    """CLI flag > env var > config file > default.

    data_dir is REQUIRED (N1): with no flag, env var, or config-file
    value this raises ValueError naming `taxprep config set data_dir
    <path>`. Paths inside site-packages are refused at every source.
    """
    if key not in _KEYS:
        raise ValueError(f"unknown config key {key!r}; expected one of {_KEYS}")
    if key == "data_dir":
        return _resolve_data_dir(cli_value)
    if cli_value is not None:
        return _coerce(key, str(cli_value)) if key == "scope_years" else cli_value
    env = os.environ.get(_ENV[key])
    if env:
        return _coerce(key, env)
    file_data = load_file()
    if key in file_data and file_data[key] not in (None, ""):
        return _coerce(key, str(file_data[key]))
    default = _DEFAULTS[key]
    if key == "source_dir" and default is None:
        return None
    return default


def _resolve_data_dir(cli_value=None) -> str:
    """--data-dir flag > TAXPREP_DATA_DIR env > config.toml data_dir.

    Fail closed: no default, and site-packages locations refused. The
    hard error names the one-time setup command.
    """
    if cli_value is not None:
        return _checked_data_dir(str(cli_value))
    env = os.environ.get(_ENV["data_dir"])
    if env:
        return _checked_data_dir(env)
    file_data = load_file()
    if "data_dir" in file_data and file_data["data_dir"] not in (None, ""):
        return _checked_data_dir(str(file_data["data_dir"]))
    raise ValueError(
        "no data_dir configured (set once, not per command): run "
        "`taxprep config set data_dir <path>`"
    )
