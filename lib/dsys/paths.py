"""Install-home resolution for the dsys CLI.

The install root ("home") holds bin/dsys, lib/dsys/, lib/core/,
etc/config.yaml and var/. DSYS_HOME wins when set; otherwise the home is
derived from this file's location (<home>/lib/dsys/paths.py).
"""

import os
from pathlib import Path


def resolve_home() -> Path:
    """Return the dsys install root as a resolved absolute Path."""
    env = os.environ.get("DSYS_HOME")
    if env:
        return Path(env).resolve()
    # __file__ == <home>/lib/dsys/paths.py -> parents[2] == <home>
    return Path(__file__).resolve().parents[2]
