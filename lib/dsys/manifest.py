"""Manifest: content-hash ledger of the dsys install tree.

etc/config.yaml is OPERATOR-OWNED (the `configure` rung) and is deliberately
EXCLUDED from the manifest: editing config must never trip the doctor.

Coverage:
  - bin/dsys
  - lib/dsys/*.py
  - lib/core/package/*.py
  - full profile additionally: lib/roles/** and share/scenarios/**
Never var/ or venv/. __pycache__ is always skipped.

lib/dsys modules import each other as top-level modules (e.g. `import
manifest`); the vendored core is imported as `from package.schema import ...`
after sys.path.insert(0, "<home>/lib/core").
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_REL = "var/manifest.json"
_MANIFEST_REQUIRED_KEYS = ("files", "profile", "install_path")


class ManifestError(Exception):
    """Raised when the manifest is missing, unreadable, or malformed."""


def file_sha256(p: Path) -> str:
    """Hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def covered_files(home: Path, profile: str) -> list[str]:
    """Sorted home-relative paths covered by the manifest for a profile.

    'base'  covers bin/dsys, lib/dsys/*.py, lib/core/package/*.py.
    'full'  additionally covers lib/roles/** and share/scenarios/**.
    """
    home = Path(home)
    rels: set[str] = set()

    def add_file(p: Path) -> None:
        if p.is_file():
            rels.add(p.relative_to(home).as_posix())

    add_file(home / "bin" / "dsys")
    dsys_dir = home / "lib" / "dsys"
    if dsys_dir.is_dir():
        for p in sorted(dsys_dir.glob("*.py")):
            add_file(p)
    core_pkg = home / "lib" / "core" / "package"
    if core_pkg.is_dir():
        for p in sorted(core_pkg.glob("*.py")):
            add_file(p)
    if profile == "full":
        for tree in (home / "lib" / "roles", home / "share" / "scenarios"):
            if tree.is_dir():
                for p in sorted(tree.rglob("*")):
                    if p.is_file() and "__pycache__" not in p.parts:
                        add_file(p)
    return sorted(rels)


def core_tree_hash(home: Path) -> str:
    """'sha256:' + hex of sha256 over the sorted core package tree listing."""
    home = Path(home)
    pkg = home / "lib" / "core" / "package"
    entries = [
        f"{p.relative_to(home).as_posix()}:{file_sha256(p)}"
        for p in sorted(pkg.glob("*.py"))
    ]
    return "sha256:" + hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def write_manifest(
    home: Path,
    *,
    profile: str,
    cli_version: str,
    installer_version: str,
    components: dict,
    source: dict | None = None,
) -> dict:
    """Build the manifest dict and write it (pretty) to var/manifest.json.

    `components` is the parsed components.json registry, embedded VERBATIM:
    the installer authors nothing about components and maintains nothing;
    it carries the dist's declaration into the manifest, where `dsys
    doctor` reads it to report per-component status.

    `source` records acquisition provenance: {"mode": "release", "tag",
    "tarball_sha256"} for --release installs, {"mode": "local", "path"}
    for --from installs. It is provenance, not verification.
    """
    home = Path(home)
    rels = covered_files(home, profile)
    manifest = {
        "installer_version": installer_version,
        "dist_version": cli_version,
        "profile": profile,
        "install_path": str(home),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "core_hash": core_tree_hash(home),
        "source": source if isinstance(source, dict) else {"mode": "unknown"},
        "components": components,
        "files": {rel: file_sha256(home / rel) for rel in rels},
    }
    var = home / "var"
    var.mkdir(parents=True, exist_ok=True)
    (var / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    return manifest


def read_manifest(home: Path) -> dict:
    """Read the manifest; raise ManifestError on missing/bad JSON."""
    path = Path(home) / MANIFEST_REL
    if not path.is_file():
        raise ManifestError(f"missing manifest: {path}")
    try:
        data = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ManifestError(f"bad manifest JSON at {path}: {e}")
    if not isinstance(data, dict):
        raise ManifestError(f"bad manifest at {path}: not a JSON object")
    return data


def verify_tree(home: Path) -> dict:
    """Recompute covered files (profile taken from the manifest) and compare.

    Returns {"ok": bool, "diverged": [rel], "missing": [rel]}.
    """
    home = Path(home)
    manifest = read_manifest(home)
    profile = manifest.get("profile", "base")
    expected: dict = manifest.get("files", {}) or {}
    on_disk = set(covered_files(home, profile))
    diverged = [
        rel
        for rel in covered_files(home, profile)
        if file_sha256(home / rel) != expected.get(rel)
    ]
    missing = sorted(rel for rel in expected if rel not in on_disk)
    return {"ok": not diverged and not missing, "diverged": diverged, "missing": missing}


def _load_components(path: str) -> dict:
    """Read and lightly validate the components registry file.

    The registry is carried verbatim; validation here is structural
    only (a dict with a "components" list of named entries). Doctor
    interprets entries leniently and never fails on an unknown field.
    """
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise ManifestError(f"bad components registry at {path}: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("components"), list):
        raise ManifestError(
            f"bad components registry at {path}: expected a dict with a "
            f"'components' list"
        )
    for entry in data["components"]:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise ManifestError(
                f"bad components registry at {path}: every component needs a name"
            )
    return data


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["write"] and len(args) in (6, 7):
        _, home, profile, cli_version, installer_version, components_path = args[:6]
        components = _load_components(components_path)
        source = None
        if len(args) == 7:
            try:
                source = json.loads(args[6])
            except json.JSONDecodeError as e:
                raise ManifestError(f"bad source JSON: {e}")
            if not isinstance(source, dict):
                raise ManifestError("bad source JSON: not an object")
        m = write_manifest(
            Path(home),
            profile=profile,
            cli_version=cli_version,
            installer_version=installer_version,
            components=components,
            source=source,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "manifest": str(Path(home) / MANIFEST_REL),
                    "profile": profile,
                    "files": len(m["files"]),
                }
            )
        )
    elif len(args) == 2 and args[0] == "verify":
        _, home = args
        print(json.dumps(verify_tree(Path(home))))
    else:
        raise SystemExit(
            "usage: manifest.py write <home> <profile> <cli_version> "
            "<installer_version> <components.json> [<source-json>]"
            " | verify <home>"
        )
