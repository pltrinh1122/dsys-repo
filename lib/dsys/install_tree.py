"""install_tree: converge an install home to a profile's owned file set.

install(p) is specified as a pure function of (dist, p, operator-owned
material): re-running it, or switching profiles, converges the tree
regardless of history. Equality here is operational convergence, not
byte-identity (installed_at changes every run; __pycache__ regenerates).

OWNED(p) -- the dist-provided file set for a profile:
  base: bin/dsys, lib/dsys/*.py, lib/core/package/*.py
  full: base + lib/roles/** (sealed bundles) + share/scenarios/*.py

The sweep covers bin/, lib/, share/. Never touched: etc/config.yaml
(operator-owned) and var/ (accretion) -- except quarantine writes below.
Stray top-level files are outside the installer's domain and are left alone.

Triage rule for on-disk files under the sweep roots that are NOT in OWNED(p):
  - pristine per the previous manifest (hash matches) -> delete.
    Reproducible from the dist; this is the old `rm -rf` behavior, principled.
  - mutated (in manifest, hash differs) or unknown (never in manifest)
    -> quarantine to var/quarantine/<utc-ts>/ preserving relative paths,
       with a record.json. Never silently destroyed (declared-mutation rule).

Files IN OWNED(p) are overwritten from the dist ("tree replaced"):
reinstall is the sanctioned remedy for a mutated tree (doctor's own hint),
and the mutation playbook's patch rung carries an explicit upgrade-fate
gate for exactly this. The operator ran install explicitly.

Only stdlib. Run as: install_tree.py converge <home> <profile> <src>
<core_dir> <installer_version>
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SWEEP_ROOTS = ("bin", "lib", "share")
SKIP_DIR_NAMES = {"__pycache__"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def owned_files(src: Path, core_dir: Path, profile: str) -> dict[str, Path]:
    """Map home-relative posix path -> dist source path for profile p."""
    owned: dict[str, Path] = {}
    owned["bin/dsys"] = src / "bin" / "dsys"
    for p in sorted((src / "lib" / "dsys").glob("*.py")):
        owned[f"lib/dsys/{p.name}"] = p
    for p in sorted(Path(core_dir).glob("*.py")):
        owned[f"lib/core/package/{p.name}"] = p
    if profile == "full":
        roles_src = src / "roles"
        if roles_src.is_dir():
            for role_dir in sorted(d for d in roles_src.iterdir() if d.is_dir()):
                for f in sorted(role_dir.rglob("*")):
                    if f.is_file() and not (SKIP_DIR_NAMES & set(f.parts)):
                        owned[f"lib/roles/{role_dir.name}/{f.relative_to(role_dir).as_posix()}"] = f
        for p in sorted((src / "share" / "scenarios").glob("*.py")):
            owned[f"share/scenarios/{p.name}"] = p
    return owned


def _on_disk_sweep_files(home: Path) -> list[str]:
    """Sorted home-relative posix paths under the sweep roots (files only)."""
    rels: list[str] = []
    for root in SWEEP_ROOTS:
        base = home / root
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for fn in filenames:
                p = Path(dirpath) / fn
                rels.append(p.relative_to(home).as_posix())
    return sorted(rels)


def _read_old_manifest(home: Path) -> tuple[str, dict[str, str]]:
    """(old_profile, old files map); tolerant -- missing manifest means fresh."""
    path = home / "var" / "manifest.json"
    if not path.is_file():
        return "none", {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "none", {}
    if not isinstance(data, dict):
        return "none", {}
    files = data.get("files")
    return str(data.get("profile", "none")), files if isinstance(files, dict) else {}


def converge(
    home: Path, profile: str, src: Path, core_dir: Path, installer_version: str
) -> dict:
    home, src, core_dir = Path(home), Path(src), Path(core_dir)
    if profile not in ("base", "full"):
        raise ValueError(f"profile must be base|full, got {profile!r}")

    old_profile, old_files = _read_old_manifest(home)
    owned = owned_files(src, core_dir, profile)
    missing_src = [rel for rel, sp in owned.items() if not sp.is_file()]
    if missing_src:
        raise FileNotFoundError(
            f"dist incomplete for profile {profile}: missing {missing_src[:3]}"
        )

    # --- triage: on-disk files not in OWNED(p) ---
    to_delete: list[str] = []
    to_quarantine: list[dict] = []
    for rel in _on_disk_sweep_files(home):
        if rel in owned:
            continue
        disk_hash = sha256_file(home / rel)
        old_hash = old_files.get(rel)
        if old_hash is not None and old_hash == disk_hash:
            to_delete.append(rel)
        else:
            to_quarantine.append(
                {
                    "path": rel,
                    "sha256": disk_hash,
                    "reason": "mutated" if rel in old_files else "unknown",
                }
            )

    # --- quarantine first (fail closed: nothing deleted before this lands) ---
    quarantine_rel: str | None = None
    if to_quarantine:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        qdir = home / "var" / "quarantine" / ts
        for entry in to_quarantine:
            src_p, dst_p = home / entry["path"], qdir / entry["path"]
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_p), str(dst_p))
        record = {
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "from_profile": old_profile,
            "to_profile": profile,
            "installer_version": installer_version,
            "files": to_quarantine,
        }
        (qdir / "record.json").write_text(json.dumps(record, indent=2) + "\n", "utf-8")
        quarantine_rel = qdir.relative_to(home).as_posix()

    # --- delete pristine non-owned files, then drop emptied dirs ---
    for rel in to_delete:
        (home / rel).unlink()
    for root in SWEEP_ROOTS:
        base = home / root
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base, topdown=False):
            if not dirnames and not filenames:
                try:
                    Path(dirpath).rmdir()
                except OSError:
                    pass

    # --- lay down OWNED(p) wholesale (converges stale files too) ---
    def fresh_dir(rel: str) -> Path:
        d = home / rel
        if d.is_dir():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        return d

    bin_d = fresh_dir("bin")
    shutil.copy2(owned["bin/dsys"], bin_d / "dsys")
    os.chmod(bin_d / "dsys", 0o755)

    dsys_d = fresh_dir("lib/dsys")
    for rel, sp in owned.items():
        if rel.startswith("lib/dsys/"):
            shutil.copy2(sp, dsys_d / Path(rel).name)

    core_d = fresh_dir("lib/core/package")
    for rel, sp in owned.items():
        if rel.startswith("lib/core/package/"):
            shutil.copy2(sp, core_d / Path(rel).name)

    if profile == "full":
        roles_d = fresh_dir("lib/roles")
        for rel, sp in owned.items():
            if rel.startswith("lib/roles/"):
                dst = roles_d / Path(rel).relative_to("lib/roles")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sp, dst)
        scen_d = fresh_dir("share/scenarios")
        for rel, sp in owned.items():
            if rel.startswith("share/scenarios/"):
                shutil.copy2(sp, scen_d / Path(rel).name)
    else:
        for rel in ("lib/roles", "share/scenarios"):
            d = home / rel
            if d.is_dir():
                shutil.rmtree(d)

    return {
        "from_profile": old_profile,
        "to_profile": profile,
        "installed": len(owned),
        "removed_pristine": to_delete,
        "quarantined": to_quarantine,
        "quarantine_dir": quarantine_rel,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 6 or argv[0] != "converge":
        print(
            "usage: install_tree.py converge <home> <profile> <src>"
            " <core_dir> <installer_version>",
            file=sys.stderr,
        )
        return 2
    _, home, profile, src, core_dir, installer_version = argv
    try:
        summary = converge(Path(home), profile, Path(src), Path(core_dir), installer_version)
    except Exception as e:  # noqa: BLE001 -- installer reports, never tracebacks
        print(f"install_tree: FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    q = summary["quarantined"]
    print(f"converge: profile {summary['to_profile']} (from {summary['from_profile']})")
    print(f"converge: installed {summary['installed']} file(s) from dist")
    print(f"converge: removed {len(summary['removed_pristine'])} pristine file(s) not in the {profile} set")
    if q:
        n_mut = sum(1 for e in q if e["reason"] == "mutated")
        n_unk = len(q) - n_mut
        print(
            f"converge: quarantined {len(q)} file(s) -> {summary['quarantine_dir']}/"
            f" (mutated: {n_mut}, unknown: {n_unk}) -- see record.json"
        )
        for e in q:
            print(f"converge:   [{e['reason']}] {e['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
