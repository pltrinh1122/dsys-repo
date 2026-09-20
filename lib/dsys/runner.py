"""The runner: deterministic derivation executor (runner-spec.md).

v1 implements the *mechanism*; the derivation set is ``{"identity"}``.
Real derivations (e.g. exprc) arrive later as pinned toolchain entries;
the mechanism — manifest in, pins verified, derive twice, compare,
receipt out — is what's being built here.

Design stress-test (falsifiers), 2026-09-20:
- F-DRV-1 "URL inputs break derive's never-network hermeticity."
  Survives narrowed: only filesystem paths and ``file://`` URLs
  resolve; ``http(s)://`` is refused citing the offline rule
  (installer-spec section 4). As the *manifest* locator it's a usage
  refusal (exit 1); as an *input* locator it's a check result
  (exit 5) with the reason recorded in the receipt's failures —
  the locator is CLI usage, the inputs are the check's subject.
  A URL is accepted as a *locator*, never as a network fetch.
- F-DRV-2 "Identity derivation is a vacuous runner." Survives as
  v1: the deliverable is the attested-derivation mechanism, and
  identity is the spec's own smoke test (installer-spec section 5:
  "output hash == input hash"). Cleverness is a toolchain's job.
- F-DRV-3 "Self-pin is circular (the runner verifies itself)."
  Survives narrowed: the pin is verified against the
  doctor-verified installed manifest (attestation chain,
  installer-spec section 11) — the check is real, the trust is
  declared (cf. F-RUN-2: never trusted, only checkable; dishonesty
  is diversity's problem, F-RUN-4).
- F-DRV-4 "The bare positional form bypasses the manifest."
  Falsified as a bypass: the bare form *constructs* the manifest
  internally (single input, identity, implicit runner self-pin);
  one code path, and every receipt cites a manifest hash.
- F-DRV-5 "Cache hits skip double-derive, weakening R-3."
  Survives per R-5/F-RUN-3: hits cite the original receipt and mint
  no fresh attestation — and only *complete* closures (every input
  sha256-pinned, C-1) consult the cache at all.

Exit-code mapping (cli-interface-spec section 2):
- 0: derivation passed, receipt issued.
- 1: the check could not run (usage, malformed manifest, unreadable
  input, remote URL refused, base profile).
- 5: the check ran and the derivation failed or was refused
  (unknown toolchain, pin mismatch, input hash mismatch or
  unresolvable input locator, double-derive mismatch). The receipt
  is still emitted: refusals are data, like referee exit codes
  (runner-spec section 1); failure is deterministic (C-6).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.request import url2pathname
from urllib.parse import urlparse

DERIVATIONS = ("identity",)
TOOLCHAIN_NAME = "runner"
CACHE_SUBDIR = Path("var") / "runner" / "cache"

_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


class RunnerRefusal(Exception):
    """The check could not run (usage/tool failure). CLI maps to exit 1."""


class DerivationFailure(Exception):
    """The check ran; the derivation failed or was refused.

    Carries the attested-failure receipt. CLI maps to exit 5 and
    emits the receipt.
    """

    def __init__(self, message: str, receipt: dict):
        super().__init__(message)
        self.receipt = receipt


# ---------------------------------------------------------------------------
# input resolution (offline: paths and file:// URLs only)


def resolve_to_path(locator: str) -> Path:
    """A locator to a local Path. Remote URLs are a clean refusal."""
    if locator.startswith("file://"):
        return Path(url2pathname(urlparse(locator).path))
    if _URL_RE.match(locator):
        raise RunnerRefusal(
            f"derive is offline (installer-spec section 4): refusing remote "
            f"URL {locator!r} — provide a filesystem path or a file:// URL")
    return Path(locator).expanduser()


def canonical_dir_bytes(root: Path) -> bytes:
    """Deterministic canonical bytes for a directory tree.

    Sorted POSIX relative paths; each entry is
    relpath + NUL + kind + payload, where kind is b"f" (regular file:
    8-byte big-endian length + bytes), b"l" (symlink: target string),
    or b"o" (other: empty payload). Nothing is silently skipped and
    nothing is refused — v1 exercises no judgment (R-4).
    """
    entries: list[bytes] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        here = Path(dirpath)
        for name in sorted(dirnames):
            full = here / name
            if full.is_symlink():
                rel = full.relative_to(root).as_posix()
                entries.append(rel.encode("utf-8") + b"\x00l"
                               + os.readlink(full).encode("utf-8"))
        for name in sorted(filenames):
            full = here / name
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                entries.append(rel.encode("utf-8") + b"\x00l"
                               + os.readlink(full).encode("utf-8"))
            elif full.is_file():
                data = full.read_bytes()
                entries.append(rel.encode("utf-8") + b"\x00f"
                               + len(data).to_bytes(8, "big") + data)
            else:
                entries.append(rel.encode("utf-8") + b"\x00o")
    return b"".join(entries)


def read_input_bytes(locator: str) -> bytes:
    """Bytes of a derivation input: a file's bytes, or a directory's
    canonical bytes."""
    path = resolve_to_path(locator)
    if not path.exists():
        raise RunnerRefusal(f"derive: input not found: {locator}")
    if path.is_dir() and not path.is_symlink():
        return canonical_dir_bytes(path)
    if path.is_file() or path.is_symlink():
        return path.read_bytes()
    raise RunnerRefusal(f"derive: not a file or directory: {locator}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# manifests


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise RunnerRefusal(message)


def load_manifest(locator: str) -> dict:
    """Parse and shape-check a DerivationManifest from a path/file:// URL."""
    path = resolve_to_path(locator)
    _require(path.is_file(),
             f"derive: manifest is not a file: {locator}")
    try:
        raw = path.read_bytes().decode("utf-8")
    except OSError as e:
        raise RunnerRefusal(f"derive: cannot read manifest {locator}: {e}")
    except UnicodeDecodeError as e:
        raise RunnerRefusal(f"derive: manifest {locator} is not UTF-8: {e}")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RunnerRefusal(f"derive: manifest {locator} is not valid JSON: {e}")
    _require(isinstance(doc, dict),
             f"derive: manifest {locator} is not a JSON object")
    allowed = {"derivation", "toolchain", "inputs", "params"}
    unknown = sorted(set(doc) - allowed)
    _require(not unknown,
             f"derive: manifest {locator} has unknown keys {unknown} — "
             f"the runner never resolves ambiguity (R-4)")
    _require(isinstance(doc.get("derivation"), str),
             f"derive: manifest {locator}: 'derivation' must be a string")
    tc = doc.get("toolchain")
    _require(isinstance(tc, dict)
             and isinstance(tc.get("name"), str)
             and isinstance(tc.get("version"), str),
             f"derive: manifest {locator}: 'toolchain' must be "
             f"{{name: str, version: str}}")
    inputs = doc.get("inputs")
    _require(isinstance(inputs, list) and inputs,
             f"derive: manifest {locator}: 'inputs' must be a non-empty list")
    for i, inp in enumerate(inputs):
        _require(isinstance(inp, dict), f"derive: input {i} is not an object")
        has_path, has_url = "path" in inp, "url" in inp
        _require(has_path != has_url,
                 f"derive: input {i} needs exactly one of 'path'/'url'")
        _require(isinstance(inp.get("path" if has_path else "url"), str),
                 f"derive: input {i} locator must be a string")
        pin = inp.get("sha256")
        _require(pin is None or (isinstance(pin, str) and pin),
                 f"derive: input {i} 'sha256' must be a non-empty string")
    params = doc.get("params", {})
    _require(isinstance(params, dict),
             f"derive: manifest {locator}: 'params' must be an object")
    return doc


def bare_manifest(input_locator: str, tool_version: str) -> dict:
    """The bare positional form, as an internally constructed manifest
    (F-DRV-4): single unpinned input, identity derivation, implicit
    runner self-pin. Unpinned inputs mean an incomplete closure, so the
    bare form never consults the cache (F-RUN-3)."""
    return {"derivation": "identity",
            "toolchain": {"name": TOOLCHAIN_NAME, "version": tool_version},
            "inputs": [{"path": input_locator}],
            "params": {}}


def manifest_hash(manifest: dict) -> str:
    canonical = json.dumps(manifest, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return sha256_hex(canonical)


# ---------------------------------------------------------------------------
# toolchain pin verification (R-2)


def verify_toolchain(manifest: dict, home: Path, installed_manifest: dict,
                     tool_version: str) -> dict:
    """Verify the manifest's toolchain pin against the installed,
    doctor-verified manifest. v1: the runner pins itself."""
    tc = manifest["toolchain"]
    if tc["name"] != TOOLCHAIN_NAME:
        raise DerivationFailure(
            f"derive: unknown toolchain {tc['name']!r} "
            f"(not in the installed manifest)",
            _base_receipt(manifest, home, tool_version,
                          failures=[f"unknown toolchain: {tc['name']!r}"]))
    if tc["version"] != tool_version:
        raise DerivationFailure(
            f"derive: toolchain version mismatch: manifest pins "
            f"{tc['version']!r}, installed runner is {tool_version!r}",
            _base_receipt(manifest, home, tool_version,
                          failures=[f"toolchain version mismatch: "
                                    f"pinned {tc['version']!r}"]))
    expected = (installed_manifest.get("files") or {}).get(
        "lib/dsys/runner.py")
    if not expected:
        raise DerivationFailure(
            "derive: installed manifest has no hash for lib/dsys/runner.py",
            _base_receipt(manifest, home, tool_version,
                          failures=["installed manifest lacks runner hash"]))
    actual = sha256_hex((home / "lib" / "dsys" / "runner.py").read_bytes())
    if actual != expected:
        raise DerivationFailure(
            "derive: runner code hash mismatch — tree mutated; reinstall",
            _base_receipt(manifest, home, tool_version,
                          failures=["runner code hash mismatch"]))
    return {"name": TOOLCHAIN_NAME, "version": tool_version,
            "code_sha256": actual, "verified": True,
            "verified_against":
                "var/manifest.json: files['lib/dsys/runner.py']"}


# ---------------------------------------------------------------------------
# derivation


def _base_receipt(manifest: dict, home: Path, tool_version: str,
                  failures: list[str]) -> dict:
    return {
        "manifest_hash": manifest_hash(manifest),
        "runner": {"identity": "dsys-derive", "version": tool_version},
        "toolchain": {"name": manifest["toolchain"]["name"],
                      "version": manifest["toolchain"]["version"],
                      "verified": False},
        "derivation": manifest["derivation"],
        "inputs": [],
        "output_sha256": None,
        "double_derive": {"run1": None, "run2": None, "match": False},
        "hermeticity": {
            "network_used": False,
            "seal": "declared — no sealed environment in v1 "
                    "(runner-spec R-1 is mechanism-agnostic); attestation "
                    "is declared trust, checkable via diversity (F-RUN-4)",
            "notes": "inputs resolve from local paths and file:// URLs "
                     "only; remote URLs are refused",
        },
        "result": "fail",
        "failures": failures,
        "cache": {"hit": False,
                  "complete_closure": _complete_closure(manifest)},
    }


def _complete_closure(manifest: dict) -> bool:
    return all(isinstance(i.get("sha256"), str) and i["sha256"]
               for i in manifest["inputs"])


def derive_once(manifest: dict) -> tuple[list[dict], bytes, list[str]]:
    """One derivation pass. Returns (input_records, output_bytes, failures).

    Identity derivation: output = concatenation of the inputs' bytes,
    each verified against its pinned sha256 when pinned (R-2 on the
    closure; unpinned inputs are recorded as such — declared, per the
    bare-form rule).
    """
    records: list[dict] = []
    failures: list[str] = []
    parts: list[bytes] = []
    for inp in manifest["inputs"]:
        locator = inp.get("path", inp.get("url"))
        try:
            data = read_input_bytes(locator)
        except RunnerRefusal as e:
            failures.append(str(e))
            continue
        digest = sha256_hex(data)
        pinned = inp.get("sha256")
        pin_match = None
        if pinned is not None:
            pin_match = (digest == pinned.lower())
            if not pin_match:
                failures.append(
                    f"input hash mismatch for {locator}: pinned {pinned}, "
                    f"actual {digest}")
        records.append({"locator": locator, "bytes_sha256": digest,
                        "pinned_sha256": pinned, "pin_match": pin_match})
        parts.append(data)
    return records, b"".join(parts), failures


def run_derivation(manifest: dict, *, home: Path, installed_manifest: dict,
                   tool_version: str) -> dict:
    """Full pipeline: cache check, toolchain pin, derive twice, receipt.

    Returns {"cache_hit": bool, "receipt": dict}. Raises RunnerRefusal
    (exit 1) or DerivationFailure (exit 5, receipt attached).
    """
    mhash = manifest_hash(manifest)
    complete = _complete_closure(manifest)
    cache_file = home / CACHE_SUBDIR / mhash / "receipt.json"
    if complete and cache_file.is_file():
        # R-5: hits cite the original receipt; never mint attestation.
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise RunnerRefusal(f"derive: unreadable cache entry: {e}")
        if isinstance(cached, dict) and cached.get("manifest_hash") == mhash:
            return {"cache_hit": True, "receipt": cached}
        # Corrupt entry: fall through and re-derive (never trust blindly).

    if manifest["derivation"] not in DERIVATIONS:
        raise RunnerRefusal(
            f"derive: unknown derivation {manifest['derivation']!r} "
            f"(v1 supports: {', '.join(DERIVATIONS)})")

    toolchain = verify_toolchain(manifest, home, installed_manifest,
                                 tool_version)

    rec1, out1, fail1 = derive_once(manifest)
    rec2, out2, fail2 = derive_once(manifest)
    h1, h2 = sha256_hex(out1), sha256_hex(out2)

    failures = list(fail1)
    for f in fail2:
        if f not in failures:
            failures.append(f)
    double_match = (h1 == h2)
    if not double_match:
        failures.append(
            f"double-derive mismatch: run1 {h1}, run2 {h2} "
            f"(nondeterminism or mid-run input change)")

    receipt = {
        "manifest_hash": mhash,
        "runner": {"identity": "dsys-derive", "version": tool_version,
                   "code_sha256": toolchain["code_sha256"]},
        "toolchain": toolchain,
        "derivation": manifest["derivation"],
        "inputs": rec1,
        "output_sha256": h1 if double_match else None,
        "double_derive": {"run1": h1, "run2": h2, "match": double_match},
        "hermeticity": _base_receipt(manifest, home, tool_version, [])[
            "hermeticity"],
        "result": "pass" if not failures else "fail",
        "failures": failures,
        "cache": {"hit": False, "complete_closure": complete},
    }
    if failures:
        raise DerivationFailure(
            "derive: derivation failed: " + "; ".join(failures), receipt)
    if complete:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(receipt, indent=2, sort_keys=True)
                              + "\n", encoding="utf-8")
    return {"cache_hit": False, "receipt": receipt}


def derive_command(*, input: str | None, manifest_locator: str | None,
                   out_dir: str | None, home: Path,
                   installed_manifest: dict, tool_version: str) -> dict:
    """CLI entry point. Returns {"cache_hit", "receipt", "output_bytes"}."""
    if (input is None) == (manifest_locator is None):
        raise RunnerRefusal(
            "derive: give exactly one of INPUT or --manifest")
    if manifest_locator is not None:
        manifest = load_manifest(manifest_locator)
    else:
        manifest = bare_manifest(input, tool_version)
    result = run_derivation(manifest, home=home,
                            installed_manifest=installed_manifest,
                            tool_version=tool_version)
    receipt = result["receipt"]
    output_bytes = None
    if out_dir is not None:
        if receipt["result"] != "pass":
            raise RunnerRefusal(
                "derive: not writing --out for a failed derivation")
        # Re-resolve deterministically for the written bytes: the receipt
        # already pins output_sha256; write the pass's bytes.
        out = Path(out_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        _, data, write_failures = derive_once(manifest)
        if write_failures or sha256_hex(data) != receipt["output_sha256"]:
            raise RunnerRefusal(
                "derive: output changed between receipt and --out write; "
                "aborting write")
        (out / "output.bin").write_bytes(data)
        (out / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        output_bytes = data
    result["output_bytes"] = output_bytes
    return result
