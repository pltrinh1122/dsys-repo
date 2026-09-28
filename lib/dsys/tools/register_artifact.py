#!/usr/bin/env python3
"""tool-register-artifact: the contracted write channel for the
content-addressed append-only artifact registry.

Given artifact bytes plus metadata, computes the content hash, appends
to the registry (core/package/artifact_registry.py), and returns a
receipt. Duplicate content-hash -> returns the existing receipt (no
duplicate row, no tip advance — DR-CMD-099's no-duplicate-hash
criterion, made mechanical). Append-only: never overwrites; new bytes
for an existing (kind, name) become version N+1 via the registry.

Contract: doc/tool-register-artifact-spec.md (tranche-1 commission,
DR-CMD-102; DR-CMD-055 tool discipline). Pure mechanical, deterministic,
zero inference. Every refusal raises ToolAborted with the reason
verbatim (the executor's C1 preserves it into the failure record).

Backs the write-scope channel 'artifact-registry' (recorder's
channel, DR-CMD-096; renamed from registrar_clerk, DR-CMD-107) in the
compiler's J1 registry.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL_NAME = "tool-register-artifact"

_ARTIFACT_KINDS = ("schema", "criteria", "contract")


def _load_registry():
    """Resolve the canonical artifact-registry module.

    Dist layout ships it at <home>/lib/core/package/artifact_registry.py;
    the repo working tree carries it at <repo>/core/package/. Probe in
    order, first match wins (deterministic). Abort loudly if neither
    exists — the tool never runs without the registry it writes to.
    """
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[3]):
        pkg = base / "core" / "package"
        if (pkg / "artifact_registry.py").is_file():
            parent = str(pkg.parent.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            from core.package import artifact_registry as R  # noqa: E402
            return R
    raise C.ToolAborted(
        "tool-register-artifact: cannot locate the artifact-registry "
        "module (looked in dist lib/core/package and repo core/package)")


def _require(ctx: dict, key: str, *, allow_empty: bool = False) -> str:
    val = ctx.get(key)
    if not isinstance(val, str) or (not allow_empty and not val.strip()):
        raise C.ToolAborted(
            f"tool-register-artifact refused: {key!r} is required "
            f"(non-empty string)")
    return val


def run(ctx: dict) -> dict:
    R = _load_registry()

    root = Path(_require(ctx, "artifact_registry_root"))
    data = ctx.get("artifact_bytes")
    if not isinstance(data, bytes) or not data:
        raise C.ToolAborted(
            "tool-register-artifact refused: 'artifact_bytes' must be "
            "non-empty bytes (passed in-process)")
    kind = _require(ctx, "kind")
    if kind not in _ARTIFACT_KINDS:
        raise C.ToolAborted(
            f"tool-register-artifact refused: unknown artifact kind "
            f"{kind!r} (must be one of {list(_ARTIFACT_KINDS)})")
    name = _require(ctx, "name").strip()
    producer = _require(ctx, "producer")
    commission_id = _require(ctx, "commission_id")
    disposition_ref = _require(ctx, "disposition_ref")

    sha = hashlib.sha256(data).hexdigest()
    try:
        rec = R.register(
            root, kind=kind, name=name, artifact_bytes=data,
            producer=producer, commission_id=commission_id,
            disposition_ref=disposition_ref)
        registered, duplicate = True, False
    except R.RegistryError as e:
        # Duplicate content-hash -> idempotent: return the existing
        # receipt, append nothing. The (kind, name) match keeps this
        # precise: same-bytes-different-name is the registry's
        # versioning business, not a duplicate. Any other RegistryError
        # (no disposition, post-release commission rule) is a genuine
        # refusal — reason preserved verbatim.
        existing = R.find_by_sha256(root, sha)
        if (existing is not None and existing.kind == kind
                and existing.name == name):
            rec = existing
            registered, duplicate = False, True
        else:
            raise C.ToolAborted(str(e))

    receipt = rec.model_dump(mode="json")
    return {
        "ok": True,
        "result": {
            "registered": registered,
            "duplicate": duplicate,
            "receipt": receipt,
        },
        "ctx_delta": {
            "artifact_registered": registered,
            "artifact_sha256": sha,
            "artifact_kind": kind,
            "artifact_name": name,
            "artifact_version": rec.version,
            "artifact_seq": rec.seq,
        },
    }
