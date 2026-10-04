"""W1 packaging smoke test (P1 + P2 pyproject half).

Acceptance: a pip-built wheel of a *clean export* of this repo (no
in-tree build/, .venv, or egg-info to contaminate the build), installed
into a throwaway environment, must let DocumentStore open and register
a synthetic document with the source tree nowhere on sys.path. This is
the failure the workstation gate audit found (medallion_schema.sql
missing from the wheel; source-tree-relative _SCHEMA_PATH) — the
in-tree test suite masks it.

Skips cleanly (with reason) when wheel/venv tooling is unavailable.
Outputs are metadata-only; no real taxpayer material is touched.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

_CHILD = textwrap.dedent(
    """\
    import json, sys, tempfile
    from pathlib import Path

    # Paranoia: the source tree must not be reachable from here.
    sys.path = [p for p in sys.path if "tax-prep" not in p]

    import taxprep.mstore as mstore
    from taxprep.mstore import MedallionStore

    result = {"module_file": mstore.__file__}
    tmp = Path(tempfile.mkdtemp(prefix="taxprep-smoke-"))
    store = MedallionStore(tmp / "data")
    sha = "ab" * 32  # synthetic fixture: no real document material
    assert store.register_bronze(sha, 128, source_root=str(tmp)) is True
    assert store.register_bronze(sha, 128, source_root=str(tmp)) is False
    result["bronze_roundtrip_ok"] = True
    print(json.dumps(result))
    """
)


def _run(cmd, **kwargs):
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 600)
    return subprocess.run(cmd, **kwargs)


@pytest.fixture()
def scratch():
    """Self-cleaning scratch dir for heavy artifacts (export, wheel, venv).

    pytest's tmp_path is retained for the last N runs; a venv (~150M) per
    retained run exhausts small /tmp filesystems. TemporaryDirectory
    deletes itself on exit.
    """
    with tempfile.TemporaryDirectory(prefix="taxprep-smoke-") as d:
        yield Path(d)


@pytest.fixture()
def clean_export(scratch):
    """Copy the repo to a staging dir minus build junk, like a clean export."""
    src = scratch / "export"
    shutil.copytree(
        REPO_ROOT,
        src,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", "*.pyc", "build", "dist",
            "*.egg-info", ".pytest_cache", "data",
        ),
    )
    assert (src / "pyproject.toml").exists()
    assert (src / "taxprep" / "medallion_schema.sql").exists()
    return src


def _build_wheel(src, scratch):
    """Build a wheel from a clean export; return (wheel_path,) or skip."""
    dist = scratch / "dist"
    dist.mkdir()
    wheel_cmd = [
        PY, "-m", "pip", "wheel", str(src),
        "--no-deps", "--no-build-isolation", "-w", str(dist), "-q",
    ]
    r = _run(wheel_cmd, cwd=scratch)
    if r.returncode != 0 and "setuptools" in (r.stderr or ""):
        # Backend env lacks setuptools: fall back to an isolated build env.
        wheel_cmd.remove("--no-build-isolation")
        r = _run(wheel_cmd, cwd=scratch)
    if r.returncode != 0:
        pytest.skip(f"wheel build unavailable: {(r.stderr or '')[-400:]}")
    wheels = list(dist.glob("*.whl"))
    assert wheels, "pip wheel produced no wheel artifact"
    return wheels[0]


def test_wheel_contains_schema_sql(clean_export, scratch):
    """The wheel artifact itself must ship medallion_schema.sql (P1)."""
    wheel = _build_wheel(clean_export, scratch)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert any(n.endswith("taxprep/medallion_schema.sql") for n in names), (
        "medallion_schema.sql missing from wheel; "
        "[tool.setuptools.package-data] not effective"
    )


def test_wheel_install_documentstore_outside_source_tree(clean_export, scratch):
    """P1 acceptance: built wheel -> clean install -> DocumentStore works."""
    wheel = _build_wheel(clean_export, scratch)
    try:
        __import__("venv")
    except ImportError:
        pytest.skip("venv module unavailable: cannot make a temp environment")

    venv_dir = scratch / "venv"
    r = _run([PY, "-m", "venv", str(venv_dir)])
    if r.returncode != 0:
        pytest.skip(f"venv creation failed: {(r.stderr or '')[-400:]}")
    vpy = venv_dir / "bin" / "python"
    r = _run([str(vpy), "-m", "pip", "install", "--no-deps", "-q", str(wheel)])
    if r.returncode != 0:
        pytest.skip(f"wheel install unavailable: {(r.stderr or '')[-400:]}")

    child = scratch / "smoke_child.py"
    child.write_text(_CHILD, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = _run([str(vpy), str(child)], cwd=scratch, env=env)
    assert r.returncode == 0, (
        "DocumentStore failed in the installed wheel:\n"
        f"{(r.stderr or '')[-1500:]}"
    )
    result = __import__("json").loads(r.stdout.strip().splitlines()[-1])
    assert "tax-prep" not in result["module_file"], (
        f"test did not run against the installed wheel: {result['module_file']}"
    )
    assert result["bronze_roundtrip_ok"] is True
