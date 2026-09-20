"""GitHub Release acquisition for the dsys installer.

Binding point between install.sh and github.com/pltrinh1122/dsys-repo
releases. Used ONLY for acquisition (this module may use the network);
everything after the tarball is unpacked proceeds through the existing
offline install path -- F-I1: acquisition may need network, deployment
is offline given a local dist.

Release layout (convention):
  tag:               v<dist_version>        (e.g. v0.1.0)
  tarball asset:     dsys-<tag>.tar.gz     (git archive of the tag)
  checksum asset:    dsys-<tag>.tar.gz.sha256

Verification: sha256(tarball) must equal the release's published
checksum asset, or a locally pinned --sha256 when given. Downloading
from github.com is NOT verification (F-I13). Trust basis, stated:
TLS to github.com plus the release publisher attaching both assets;
the checksum is the release's own attestation, not an independent
one. For fleet use, pin --sha256 out-of-band.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

DEFAULT_REPO = "pltrinh1122/dsys-repo"
API = "https://api.github.com/repos/{repo}/releases/tags/{tag}"


class ReleaseError(Exception):
    """Raised when the release cannot be acquired or verified."""


def _get_json(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "dsys-installer"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ReleaseError(f"GitHub API {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ReleaseError(f"network error reaching {url}: {e}") from e


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "dsys-installer"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as f:
            for chunk in iter(lambda: resp.read(65536), b""):
                f.write(chunk)
    except (urllib.error.URLError, TimeoutError) as e:
        raise ReleaseError(f"download failed for {url}: {e}") from e


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(tag: str, destdir: str | Path, *, repo: str = DEFAULT_REPO,
          pinned_sha256: str | None = None) -> dict:
    """Acquire and verify a release; unpack it; return acquisition record.

    Returns {"tag", "tarball_sha256", "src_dir", "assets": [...]}.
    Raises ReleaseError on any failure (not found, download error,
    checksum mismatch, bad tarball).
    """
    dest = Path(destdir)
    dest.mkdir(parents=True, exist_ok=True)
    tarball_name = f"dsys-{tag}.tar.gz"
    checksum_name = tarball_name + ".sha256"

    rel = _get_json(API.format(repo=repo, tag=tag))
    assets = {a.get("name"): a.get("browser_download_url")
              for a in (rel.get("assets") or []) if a.get("name")}
    missing = [n for n in (tarball_name, checksum_name) if n not in assets]
    if missing:
        raise ReleaseError(
            f"release {tag} is missing assets: {', '.join(missing)} "
            f"(found: {', '.join(sorted(assets)) or 'none'})"
        )

    tarball = dest / tarball_name
    checksum_file = dest / checksum_name
    _download(assets[tarball_name], tarball)
    _download(assets[checksum_name], checksum_file)

    published = checksum_file.read_text("utf-8").strip().split()[0].lower()
    if len(published) != 64 or any(c not in "0123456789abcdef" for c in published):
        raise ReleaseError(
            f"checksum asset {checksum_name} is malformed: {published!r}"
        )
    if pinned_sha256 is not None:
        pin = pinned_sha256.strip().lower()
        if pin != published:
            raise ReleaseError(
                "pinned --sha256 does not match the release's published "
                "checksum; refusing (out-of-band pin wins)"
            )
    actual = _sha256_file(tarball)
    if actual != published:
        raise ReleaseError(
            f"checksum mismatch for {tarball_name}: expected {published}, "
            f"got {actual}; refusing (F-I13: download is not verification)"
        )

    src_dir = dest / f"dsys-{tag}"
    try:
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(dest)
    except (tarfile.TarError, OSError) as e:
        raise ReleaseError(f"cannot unpack {tarball_name}: {e}") from e
    # git archive was created with --prefix=dsys-<tag>/; fall back to the
    # dest dir itself if the layout differs.
    if not src_dir.is_dir():
        src_dir = dest
    return {
        "tag": tag,
        "tarball_sha256": actual,
        "src_dir": str(src_dir),
        "assets": sorted(assets),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    # usage: release.py fetch <tag> <destdir> [--sha256 <hex>] [--repo owner/repo]
    if len(args) >= 3 and args[0] == "fetch":
        _, tag, destdir, *rest = args
        pinned = None
        repo = DEFAULT_REPO
        i = 0
        while i < len(rest):
            if rest[i] == "--sha256" and i + 1 < len(rest):
                pinned = rest[i + 1]
                i += 2
            elif rest[i] == "--repo" and i + 1 < len(rest):
                repo = rest[i + 1]
                i += 2
            else:
                raise SystemExit(f"release.py: unknown argument: {rest[i]}")
        try:
            rec = fetch(tag, destdir, repo=repo, pinned_sha256=pinned)
        except ReleaseError as e:
            print(f"release.py: {e}", file=sys.stderr)
            raise SystemExit(1)
        print(rec["src_dir"])
    else:
        raise SystemExit(
            "usage: release.py fetch <tag> <destdir> "
            "[--sha256 <hex>] [--repo owner/repo]"
        )
