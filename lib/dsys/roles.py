"""Role bundles: sealed prompt/bounds descriptors for the full profile.

A role bundle at <roles_dir>/<name>/ contains:

  role.yaml   flat `key: value` pairs (name, version, description), plus a
              sealed `hash:` line and a nested `files:` mapping (2-space
              indent) of bundle-file -> sha256:...
  prompt.md
  bounds.md

seal_bundle() computes the seal and writes it back into role.yaml.
load_bundle() recomputes the hashes and refuses on any mismatch. The
seal covers the bundle files; role_hash = sha256 hex of the sorted
"<file>:<hex>" listing.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

BUNDLE_FILES = ("prompt.md", "bounds.md")


class RoleError(Exception):
    """Raised when a role bundle is missing or fails seal verification."""


@dataclass
class RoleBundle:
    name: str
    version: str
    description: str
    role_hash: str
    dir: Path


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _bundle_hash(entries: dict[str, str]) -> str:
    listing = "\n".join(f"{fname}:{entries[fname]}" for fname in sorted(entries))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _parse_role_yaml(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse the flat subset of YAML role.yaml writes: top-level `key: value`
    pairs plus one nested 2-space-indented `files:` mapping."""
    flat: dict[str, str] = {}
    files: dict[str, str] = {}
    in_files = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[0] not in (" ", "\t") and ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key == "files" and val == "":
                in_files = True
                continue
            in_files = False
            flat[key] = val
        elif in_files and ":" in stripped:
            key, _, val = stripped.partition(":")
            files[key.strip()] = val.strip()
    return flat, files


def seal_bundle(bundle_dir: Path) -> Path:
    """Compute the bundle seal and write it back into role.yaml."""
    bundle_dir = Path(bundle_dir)
    yaml_path = bundle_dir / "role.yaml"
    if not yaml_path.is_file():
        raise RoleError(f"missing role.yaml in {bundle_dir}")
    flat, _ = _parse_role_yaml(yaml_path.read_text("utf-8"))
    name = flat.get("name") or bundle_dir.name
    entries: dict[str, str] = {}
    for fname in BUNDLE_FILES:
        p = bundle_dir / fname
        if not p.is_file():
            raise RoleError(f"missing bundle file {fname} in {bundle_dir}")
        entries[fname] = _sha256_file(p)
    role_hash = _bundle_hash(entries)
    lines = [
        f"name: {name}",
        f"version: {flat.get('version', '')}",
        f"description: {flat.get('description', '')}",
        f"hash: {role_hash}",
        "files:",
    ]
    lines.extend(f"  {fname}: sha256:{entries[fname]}" for fname in sorted(entries))
    yaml_path.write_text("\n".join(lines) + "\n", "utf-8")
    return yaml_path


def load_bundle(roles_dir: Path, name: str) -> RoleBundle:
    """Load and verify a role bundle; refuse on any hash mismatch."""
    roles_dir = Path(roles_dir)
    bundle_dir = roles_dir / name
    if not bundle_dir.is_dir():
        raise RoleError(f"missing role bundle directory: {bundle_dir}")
    yaml_path = bundle_dir / "role.yaml"
    if not yaml_path.is_file():
        raise RoleError(f"missing role.yaml in role bundle '{name}'")
    flat, files_map = _parse_role_yaml(yaml_path.read_text("utf-8"))
    sealed_hash = flat.get("hash")
    if not sealed_hash:
        raise RoleError(f"role '{name}' is not sealed (no hash in role.yaml)")
    entries: dict[str, str] = {}
    for fname in BUNDLE_FILES:
        p = bundle_dir / fname
        if not p.is_file():
            raise RoleError(f"hash mismatch in role '{name}': {fname} missing")
        got = _sha256_file(p)
        expected = files_map.get(fname)
        if expected != f"sha256:{got}":
            raise RoleError(
                f"hash mismatch in role '{name}': {fname} modified "
                f"(expected {expected}, got sha256:{got})"
            )
        entries[fname] = got
    role_hash = _bundle_hash(entries)
    if role_hash != sealed_hash:
        raise RoleError(
            f"hash mismatch in role '{name}': role hash mismatch "
            f"(expected {sealed_hash}, got {role_hash})"
        )
    return RoleBundle(
        name=flat.get("name") or name,
        version=flat.get("version", ""),
        description=flat.get("description", ""),
        role_hash=role_hash,
        dir=bundle_dir,
    )


def list_bundles(roles_dir: Path) -> list[RoleBundle]:
    """All role bundles sorted by name, each seal-verified (raise on first bad)."""
    roles_dir = Path(roles_dir)
    if not roles_dir.is_dir():
        raise RoleError(f"missing roles directory: {roles_dir}")
    names = sorted(
        p.name
        for p in roles_dir.iterdir()
        if p.is_dir() and "__pycache__" not in p.parts and not p.name.startswith(".")
    )
    return [load_bundle(roles_dir, name) for name in names]


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "seal":
        yaml_path = seal_bundle(Path(args[1]))
        print(json.dumps({"ok": True, "role_yaml": str(yaml_path)}))
    else:
        raise SystemExit("usage: roles.py seal <bundle_dir>")
