"""Configuration loading for the dsys CLI.

Precedence: flags > config file > DEFAULTS.

The config file is the YAML subset parsed by yamlutil (flat ``key: value``
plus one nested mapping level). Unknown keys are a stderr warning, not
fatal. ``roles_dir`` is resolved to an absolute path (relative values are
resolved under the install home). ``core_pin``, when non-empty, must equal
``manifest.core_tree_hash(home)``.

Compatibility note: doctor.py calls ``config.load(<home>/etc/config.yaml)``
with the config *file* as the single positional argument. That call style
is tolerated: when the positional resolves to a YAML file, it is treated
as ``config_path`` and the home is recovered from its ``etc/`` parent.
The spec'd ``load(home, *, config_path=None, flags=None)`` behavior is
unchanged.
"""

import sys
from pathlib import Path

import yamlutil


class ConfigError(Exception):
    """Raised when configuration is malformed or invalid."""


DEFAULTS = {
    "backend": "auto",
    "timeout_s": 300,
    "format": "text",
    "roles_dir": "lib/roles",
    "core_pin": "",
}

_BACKENDS = ("auto", "claude-cli", "stub", "in-session")
_FORMATS = ("text", "json")


def _looks_like_config_file(p: Path) -> bool:
    return p.is_file() or p.name == "config.yaml" or p.suffix in (".yaml", ".yml")


def load(home: Path, *, config_path=None, flags: dict | None = None) -> dict:
    """Load and validate configuration. Raises ConfigError on any problem."""
    home = Path(home)
    if config_path is None and _looks_like_config_file(home):
        # Tolerated call style: config.load(<home>/etc/config.yaml).
        config_path = home
        etc = config_path.parent
        home = etc.parent if etc.name == "etc" else etc
    path = Path(config_path) if config_path is not None else home / "etc" / "config.yaml"

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw: dict = {}
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}")
    else:
        try:
            raw = yamlutil.loads(text)
        except ValueError as exc:
            raise ConfigError(f"malformed config file {path}: {exc}")

    cfg = dict(DEFAULTS)
    for key, value in raw.items():
        if key not in DEFAULTS:
            print(
                f"dsys: warning: unknown config key {key!r} in {path} (ignored)",
                file=sys.stderr,
            )
        else:
            cfg[key] = value
    if flags:
        for key, value in flags.items():
            if key in DEFAULTS and value is not None:
                cfg[key] = value

    if cfg["backend"] not in _BACKENDS:
        raise ConfigError(
            f"backend must be one of {', '.join(_BACKENDS)} (got {cfg['backend']!r})"
        )
    timeout = cfg["timeout_s"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ConfigError(f"timeout_s must be a positive integer (got {timeout!r})")
    if cfg["format"] not in _FORMATS:
        raise ConfigError(
            f"format must be one of {', '.join(_FORMATS)} (got {cfg['format']!r})"
        )
    roles_dir = cfg["roles_dir"]
    if not isinstance(roles_dir, str) or not roles_dir:
        raise ConfigError(f"roles_dir must be a non-empty string (got {roles_dir!r})")
    rd = Path(roles_dir)
    cfg["roles_dir"] = str((home / rd).resolve() if not rd.is_absolute() else rd.resolve())

    pin = cfg["core_pin"]
    if not isinstance(pin, str):
        raise ConfigError(f"core_pin must be a string (got {pin!r})")
    if pin:
        if not pin.startswith("sha256:"):
            raise ConfigError(f'core_pin must look like "sha256:..." (got {pin!r})')
        try:
            import manifest
        except ImportError:
            raise ConfigError(
                "core_pin is set but the manifest module is unavailable to verify it"
            )
        actual = manifest.core_tree_hash(home)
        if actual != pin:
            raise ConfigError(
                f"core_pin mismatch: config pins {pin}, core tree hashes to {actual}"
            )
    return cfg
